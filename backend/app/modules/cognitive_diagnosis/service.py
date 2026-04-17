"""Cognitive Diagnosis — service layer.

Orchestrates:
  - ARCD-based mastery/decay computation (lightweight heuristic when model unavailable)
  - PathGen: ZPD-calibrated learning path generation
  - RevFell: PCO detection + urgency-based review scheduling
  - AdaEx: adaptive exercise generation via LLM
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from neo4j import Driver as Neo4jDriver

from app.core.settings import settings
from arcd_agent.model_registry import get_registry

from .repository import CognitiveDiagnosisRepository
from .schemas import (
    ExerciseResponse,
    LearningPathDiagnosisResponse,
    MasteryResponse,
    PathStep,
    PCOSkill,
    PortfolioResponse,
    ReviewResponse,
    SkillMastery,
    StudentEventCreate,
    WhatIfAnalysisRequest,
    WhatIfAnalysisResponse,
)

logger = logging.getLogger(__name__)


def _today_utc_date() -> datetime.date:
    return datetime.now(tz=UTC).date()


def _safe_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def _tokenize(text: str) -> set[str]:
    return {
        w.strip().lower()
        for w in text.replace("_", " ").replace("-", " ").split()
        if len(w.strip()) >= 4
    }


# ── ARCD forward-simulation (paper Eq. 6-11) ──────────────────────────────
#
# Default parameters match the model's initialisation so that the closed-form
# simulation is consistent with what a freshly-instantiated (untrained) ARCD
# model would produce.  Once a labtutor checkpoint is trained these constants
# can be loaded from the saved state-dict instead.
#
#   BaseDecay   λ  ~ Uniform(0.01, 0.03)  → centre 0.02 / day
#   BaseDecay   α  = sigmoid(0.0) × 1.9 + 0.1  = 1.05
#   BaseDecay   γ  = sigmoid(0.0) × 2.9 + 0.1  = 1.55
#   MasteryDecay ε  = 1e-8  (numerical guard)

_ARCD_LAMBDA_BASE = 0.02
_ARCD_ALPHA = 1.05
_ARCD_GAMMA = 1.55
_ARCD_EPSILON = 1e-8


def _arcd_decay_cascade(
    m_s: float,
    n_s: float,
    proficiency: float,
    difficulty: float,
    delta_t_days: float,
) -> float:
    """ARCD 4-stage decay cascade evaluated analytically (paper Eq. 6-11).

    Stage 1 — BaseDecay (Eq. 6):
        stability  = (1 + α · ln(1 + n_s)) · (1 + γ · p)
        λ_eff      = λ / stability
        δ^base     = exp(−λ_eff · Δt_days)

    Stage 2 — DifficultyDecay (Eq. 7):
        β_s        = clamp(0.5 + difficulty, 0.5, 2.0)  [difficulty ∈ [0,1]]
        δ^diff     = (δ^base)^β_s

    Stage 3 — RelationalDecay (Eq. 8-9):
        δ^rel      = δ^diff  (identity; prerequisite graph not available here)

    Stage 4 — MasteryDecay (Eq. 10-11):
        M_s        = clamp(1 + 4·m_s, 1.0, 5.0)
        δ^mast     = (δ^rel + ε)^(1 / M_s)

    Returns:
        δ_unified ≈ δ^mast  ∈ (0, 1]
    """
    import math

    stability = (1.0 + _ARCD_ALPHA * math.log1p(max(n_s, 0.0))) * (
        1.0 + _ARCD_GAMMA * max(proficiency, 0.0)
    )
    lam_eff = _ARCD_LAMBDA_BASE / max(stability, 1e-9)
    delta_base = math.exp(-lam_eff * max(delta_t_days, 0.0))

    beta = max(0.5, min(2.0, 0.5 + difficulty))
    delta_diff = delta_base**beta

    M = max(1.0, min(5.0, 1.0 + 4.0 * m_s))
    delta_mast = (delta_diff + _ARCD_EPSILON) ** (1.0 / M)

    return delta_mast


def _arcd_simulate_strategy(
    mastery_vec: list[float],
    decay_vec: list[float],
    target_indices: list[int],
    days: int,
    mode: str = "focus",
) -> list[dict]:
    """Forward-simulate mastery trajectories using the ARCD decay cascade.

    Replaces the legacy HLR + BKT simulator entirely.

    ARCD Physics per time-step
    --------------------------
    Step 1 — Forgetting (every skill):
        proficiency  = mean(m)                         [student-level signal]
        difficulty_s ≈ 1 − decay_vec[s]               [low retention → harder]
        δ_s          = _arcd_decay_cascade(m_s, n_s, proficiency, difficulty_s, 1.0)
        m_s         ← max(floor_s, δ_s · m_s)

    Step 2 — Learning (practiced skills only):
        n_s         ← n_s + 1                          [review count increment]
        δ_post       = _arcd_decay_cascade(…, n_s, …)  [spacing-strengthened]
        spacing_mult = 1 + 0.14 · min(gap − 1, 7)     [spaced mode only]
        Δm           = η · (1 − m_s) · δ_post · spacing_mult
        m_s         ← min(1.0, m_s + Δm)

    Modes
    -----
    focus      daily retrieval on weak skills   η=0.18  best ≤ 14 d
    spaced     every-3-day ZPD-band practice    η=0.22  best ≥ 21 d
    reinforce  daily maintenance of strong      η=0.05  weak skills erode
    """
    # ── mode configuration ──────────────────────────────────────────────────
    if mode == "focus":
        eta = 0.18
        interval = 1
        floor_frac_prac = 0.10
        floor_frac_idle = 0.10
        spacing_coeff = 0.0

    elif mode == "spaced":
        eta = 0.22
        interval = 3
        floor_frac_prac = 0.10
        floor_frac_idle = 0.08
        spacing_coeff = 0.14

    else:  # reinforce
        eta = 0.05
        interval = 1
        floor_frac_prac = 0.10
        floor_frac_idle = 0.05
        spacing_coeff = 0.0

    m = list(mastery_vec)
    n = len(m)
    review_count = [0.0] * n

    # Per-skill difficulty derived from stored ARCD decay values.
    # Low decay (high forgetting) → harder skill → higher difficulty exponent.
    raw_diff = [(1.0 - dv) for dv in decay_vec]
    difficulty = [max(0.0, min(1.0, d)) for d in raw_diff]
    while len(difficulty) < n:
        difficulty.append(0.5)

    floor_prac = [max(0.03, m[i] * floor_frac_prac) for i in range(n)]
    floor_idle = [max(0.03, m[i] * floor_frac_idle) for i in range(n)]
    last_practiced: dict[int, int] = {i: -interval for i in target_indices}

    avg0 = sum(m) / max(n, 1)
    traj: list[dict] = [{"step": 0, "avgMastery": round(avg0 * 100, 2)}]

    for day in range(1, days + 1):
        proficiency = sum(m) / max(n, 1)

        # ── select today's practiced skills ─────────────────────────────────
        if mode == "spaced":
            today_targets = [
                i
                for i in target_indices
                if (day - last_practiced.get(i, -interval)) >= interval
            ]
            if not today_targets:
                k = max(1, len(target_indices) // 3)
                offset = (day - 1) % max(1, len(target_indices))
                today_targets = (
                    target_indices[offset : offset + k] or target_indices[:k]
                )
        else:
            today_targets = target_indices

        practiced_set = set(today_targets)

        # ── Step 1: ARCD decay cascade for every skill ──────────────────────
        for s in range(n):
            delta = _arcd_decay_cascade(
                m_s=m[s],
                n_s=review_count[s],
                proficiency=proficiency,
                difficulty=difficulty[s],
                delta_t_days=1.0,
            )
            fl = floor_prac[s] if s in practiced_set else floor_idle[s]
            m[s] = max(fl, delta * m[s])

        # ── Step 2: ARCD-informed learning gain for practiced skills ─────────
        for sid in today_targets:
            review_count[sid] += 1.0
            gap = day - last_practiced.get(sid, -interval)
            spacing_mult = 1.0 + spacing_coeff * min(gap - 1, 7)
            # Post-practice δ: updated n_s → stronger stability → less forgetting
            delta_post = _arcd_decay_cascade(
                m_s=m[sid],
                n_s=review_count[sid],
                proficiency=proficiency,
                difficulty=difficulty[sid],
                delta_t_days=float(interval),
            )
            gain = eta * (1.0 - m[sid]) * delta_post * spacing_mult
            m[sid] = min(1.0, m[sid] + gain)
            last_practiced[sid] = day

        traj.append({"step": day, "avgMastery": round(sum(m) / max(n, 1) * 100, 2)})

    return traj


def _coherence_score(skill_ids: list[int], mastery_vec: list[float]) -> float:
    """Chain coherence in [0, 1] — three sub-scores matching frontend formula.

    - proximity (40%): pairs with index distance ≤ 2 (curriculum adjacency)
    - gradient  (30%): smooth mastery progression between sorted skills
    - zpd_cluster (30%): fraction inside learnable zone [0.30, 0.70]
    """
    n = len(skill_ids)
    if n < 2:
        return 0.5

    connected = sum(
        1
        for i in range(n)
        for j in range(i + 1, n)
        if abs(skill_ids[i] - skill_ids[j]) <= 2
    )
    proximity = connected / max((n * (n - 1)) // 2, 1)

    sorted_m = sorted(
        mastery_vec[s] if s < len(mastery_vec) else 0.0 for s in skill_ids
    )
    good_gaps = sum(
        1
        for i in range(1, len(sorted_m))
        if 0.05 <= sorted_m[i] - sorted_m[i - 1] <= 0.30
    )
    gradient = good_gaps / max(len(sorted_m) - 1, 1)

    zpd = sum(
        1
        for s in skill_ids
        if 0.30 <= (mastery_vec[s] if s < len(mastery_vec) else 0.0) <= 0.70
    )
    zpd_cluster = zpd / n

    return round(0.4 * proximity + 0.3 * gradient + 0.3 * zpd_cluster, 4)


# ── Mastery heuristic ──────────────────────────────────────────────────────


def _compute_mastery_heuristic(
    student_skill_rows: list[dict],
    timeline: list[dict],
    skill_names: list[str],
) -> list[dict]:
    """
    Lightweight mastery estimation when ARCD model is not yet trained.

    Formula per skill:
      m_s = correct_s / max(total_s, 1)   capped at [0.0, 1.0]
      decay = exp(-0.01 * hours_since) if practice exists else 0.5
    """
    from collections import defaultdict

    skill_stats: dict[str, dict] = defaultdict(
        lambda: {"correct": 0, "total": 0, "last_ts": None}
    )
    for ev in timeline:
        s = ev.get("skill_name")
        if not s:
            continue
        skill_stats[s]["total"] += 1
        if ev.get("response"):
            skill_stats[s]["correct"] += 1
        ts = ev.get("ts")
        if ts and (skill_stats[s]["last_ts"] is None or ts > skill_stats[s]["last_ts"]):
            skill_stats[s]["last_ts"] = ts

    now_ts = int(time.time())
    results = []
    for name in skill_names:
        st = skill_stats[name]
        total = st["total"]
        correct = st["correct"]
        mastery = correct / max(total, 1) if total > 0 else 0.0

        last_ts = st["last_ts"]
        if last_ts:
            hours_since = (now_ts - last_ts) / 3600.0
            decay = float(np.exp(-0.01 * max(hours_since, 0.0)))
        else:
            decay = 1.0 if total == 0 else 0.8

        if mastery == 0.0 and total == 0:
            status = "not_started"
        elif mastery < 0.4:
            status = "below"
        elif mastery <= 0.9:
            status = "at"
        else:
            status = "above"

        results.append(
            {
                "skill_name": name,
                "mastery": round(mastery, 4),
                "decay": round(decay, 4),
                "status": status,
                "attempt_count": total,
                "correct_count": correct,
                "last_practice_ts": last_ts,
            }
        )
    return results


# ── Main service ───────────────────────────────────────────────────────────


def _compute_mastery_arcd_model(
    registry,
    timeline: list[dict],
    skill_names: list[str],
) -> list[dict]:
    """Compute per-skill mastery using the trained ARCDModel checkpoint.

    Converts the Neo4j timeline rows into the interaction format expected by
    ``ModelRegistry.predict_mastery`` and falls back to ``mastery=0.0`` for
    any skill the model does not know about.
    """
    # Build interaction list in the format the registry expects
    interactions = [
        {
            "question_name": ev.get("question_id") or "",
            "correct": int(bool(ev.get("response"))),
            "timestamp_sec": float(ev.get("ts") or 0.0),
        }
        for ev in timeline
        if ev.get("question_id")
    ]

    # Predict mastery for the student's concept/skill names
    mastery_map: dict[str, float] = registry.predict_mastery(interactions, skill_names)

    now_ts = int(time.time())
    results = []
    for name in skill_names:
        mastery = max(0.0, min(1.0, mastery_map.get(name, 0.0)))

        # Reuse heuristic decay logic for temporal decay signal
        last_ts: int | None = None
        total_attempts = 0
        correct_count = 0
        for ev in timeline:
            if ev.get("skill_name") == name:
                total_attempts += 1
                if ev.get("response"):
                    correct_count += 1
                ts = ev.get("ts")
                if ts and (last_ts is None or ts > last_ts):
                    last_ts = ts

        if last_ts:
            hours_since = (now_ts - last_ts) / 3600.0
            decay = float(np.exp(-0.01 * max(hours_since, 0.0)))
        else:
            decay = 1.0 if total_attempts == 0 else 0.8

        if mastery == 0.0 and total_attempts == 0:
            status = "not_started"
        elif mastery < 0.4:
            status = "below"
        elif mastery <= 0.9:
            status = "at"
        else:
            status = "above"

        results.append(
            {
                "skill_name": name,
                "mastery": round(mastery, 4),
                "decay": round(decay, 4),
                "status": status,
                "attempt_count": total_attempts,
                "correct_count": correct_count,
                "last_practice_ts": last_ts,
            }
        )
    return results


# ── Main service ───────────────────────────────────────────────────────────


class CognitiveDiagnosisService:
    """ARCD-powered student modeling and adaptive learning service."""

    MODEL_VERSION = "arcd_v2"

    def __init__(self, neo4j_driver: Neo4jDriver) -> None:
        self._driver = neo4j_driver

    def _repo(self, session) -> CognitiveDiagnosisRepository:
        return CognitiveDiagnosisRepository(session)

    # ── Student events ────────────────────────────────────────────

    def create_student_event(
        self, user_id: int, event: StudentEventCreate | dict
    ) -> dict:
        payload = (
            event.model_dump() if isinstance(event, StudentEventCreate) else dict(event)
        )
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            return self._repo(session).create_student_event(user_id, payload)

    def get_student_events(
        self,
        user_id: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict]:
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            return self._repo(session).get_student_events(
                user_id=user_id,
                from_date=from_date,
                to_date=to_date,
            )

    def delete_student_event(self, user_id: int, event_id: str) -> bool:
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            return self._repo(session).delete_student_event(user_id, event_id)

    # ── Mastery inference ────────────────────────────────────────

    def compute_and_store_mastery(
        self,
        user_id: int,
        course_id: int | None = None,
    ) -> MasteryResponse:
        """
        Compute per-skill mastery + decay for a student and persist to KG.

        Uses the trained ARCD model when a checkpoint is available; falls
        back to the lightweight heuristic estimator otherwise.
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)

            existing = {
                r["skill_name"]: r for r in repo.get_student_mastery(user_id, course_id)
            }
            timeline = repo.get_student_timeline(user_id)
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            skill_names = [r["skill_name"] for r in skill_rows if r["skill_name"]]

            if not skill_names:
                return MasteryResponse(
                    user_id=user_id,
                    course_id=course_id,
                    skills=[],
                    total_skills=0,
                    computed_at=datetime.now(tz=UTC).isoformat(),
                )

            # ── Try trained ARCD model ─────────────────────────────────────────
            computed: list[dict] | None = None
            registry = get_registry()
            if registry.is_available:
                try:
                    computed = _compute_mastery_arcd_model(
                        registry, timeline, skill_names
                    )
                except Exception as exc:
                    logger.warning(
                        "ARCD model inference failed (user %d): %s — using heuristic",
                        user_id,
                        exc,
                    )

            # ── Fall back to heuristic if model unavailable or failed ─────────
            if computed is None:
                computed = _compute_mastery_heuristic(
                    list(existing.values()), timeline, skill_names
                )

            repo.upsert_mastery_batch(
                user_id, computed, model_version=self.MODEL_VERSION
            )

        mastery_skills = [SkillMastery(**m) for m in computed]
        return MasteryResponse(
            user_id=user_id,
            course_id=course_id,
            skills=mastery_skills,
            total_skills=len(mastery_skills),
            computed_at=datetime.now(tz=UTC).isoformat(),
        )

    def get_mastery(
        self, user_id: int, course_id: int | None = None
    ) -> MasteryResponse:
        """Return cached mastery from KG (does not recompute)."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            rows = repo.get_student_mastery(user_id, course_id)

        skills = [
            SkillMastery(
                skill_name=r["skill_name"],
                mastery=r.get("mastery") or 0.0,
                decay=r.get("decay") or 1.0,
                status=r.get("status") or "not_started",
                attempt_count=r.get("attempt_count") or 0,
                correct_count=r.get("correct_count") or 0,
                last_practice_ts=r.get("last_practice_ts"),
                model_version=r.get("model_version") or self.MODEL_VERSION,
            )
            for r in rows
        ]
        return MasteryResponse(
            user_id=user_id,
            course_id=course_id,
            skills=skills,
            total_skills=len(skills),
            computed_at=datetime.now(tz=UTC).isoformat(),
        )

    # ── PathGen ──────────────────────────────────────────────────

    def generate_path(
        self,
        user_id: int,
        course_id: int,
        path_length: int = 8,
    ) -> LearningPathDiagnosisResponse:
        """Generate a ZPD-calibrated learning path using PathGen."""
        from arcd_agent.agents.pathgen import PathGenConfig, PathGenerator

        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            mastery_rows = repo.get_student_mastery(user_id, course_id)
            prereq_edges = repo.get_prerequisite_edges()
            timeline = repo.get_student_timeline(user_id)
            event_end = (_today_utc_date() + timedelta(days=45)).isoformat()
            student_events = repo.get_student_events(
                user_id=user_id,
                from_date=_today_utc_date().isoformat(),
                to_date=event_end,
            )

        if not skill_rows:
            return LearningPathDiagnosisResponse(
                user_id=user_id,
                course_id=course_id,
                generated_at=datetime.now(tz=UTC).isoformat(),
            )

        # Build index
        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)

        # Build mastery and decay vectors
        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [
            mastery_map.get(s, {}).get("mastery") or 0.0 for s in skill_names
        ]
        decay_vec = [mastery_map.get(s, {}).get("decay") or 1.0 for s in skill_names]

        # Build prerequisite adjacency matrix A_pre[i,j] > 0 means i is prereq of j
        A_pre = np.zeros((n, n), dtype=np.float32)
        for edge in prereq_edges:
            i = name_to_idx.get(edge["from_skill"])
            j = name_to_idx.get(edge["to_skill"])
            if i is not None and j is not None:
                A_pre[i, j] = float(edge.get("strength") or 1.0)

        # Build hours_since from timeline
        now_ts = int(time.time())
        last_practice: dict[int, int] = {}
        for ev in timeline:
            idx = name_to_idx.get(ev.get("skill_name"))
            if (
                idx is not None
                and ev.get("ts")
                and (idx not in last_practice or ev["ts"] > last_practice[idx])
            ):
                last_practice[idx] = ev["ts"]
        hours_since = {idx: (now_ts - ts) / 3600.0 for idx, ts in last_practice.items()}

        # Run PathGen
        config = PathGenConfig(path_length=path_length)
        skill_name_map = {i: name for i, name in enumerate(skill_names)}
        generator = PathGenerator(
            config=config,
            skill_names=skill_name_map,
            A_pre=A_pre,
            decay_vector=decay_vec,
        )
        result = generator.generate(mastery_vec, hours_since)

        # Build resource hints for each step
        steps = []
        for step in result["steps"]:
            idx = step["skill_id"]
            sname = skill_names[idx] if idx < len(skill_names) else f"Skill {idx}"
            steps.append(
                PathStep(
                    rank=step["rank"],
                    skill_name=sname,
                    current_mastery=step["current_mastery"],
                    predicted_mastery_gain=step["predicted_mastery_gain"],
                    projected_mastery=step["projected_mastery"],
                    score=step["score"],
                    rationale=step.get("rationale", ""),
                )
            )

        # Build a lightweight daily schedule from the latest path
        minutes_per_day = 30
        default_step_minutes = 20
        schedule_days: list[dict] = []
        review_calendar: list[str] = []
        day_cursor = datetime.now(tz=UTC).date()
        events_by_date: dict[str, list[dict[str, Any]]] = {}
        for event in student_events:
            d = event.get("date")
            if not d:
                continue
            events_by_date.setdefault(d, []).append(event)

        step_idx = 0
        day_idx = 0
        safety_limit = max(len(steps) * 3, 14)
        while step_idx < len(steps) and day_idx < safety_limit:
            day_str = day_cursor.isoformat()
            day_events = events_by_date.get(day_str, [])
            has_exam = any(e.get("event_type") == "exam" for e in day_events)
            has_busy = any(
                e.get("event_type") in {"busy", "assignment"} for e in day_events
            )
            if has_exam:
                daily_capacity = 0
            elif has_busy:
                daily_capacity = max(10, int(minutes_per_day * 0.5))
            else:
                daily_capacity = minutes_per_day

            sessions: list[dict] = []
            used_minutes = 0
            while step_idx < len(steps) and daily_capacity > 0:
                if used_minutes + default_step_minutes > daily_capacity and sessions:
                    break
                step = steps[step_idx]
                sessions.append(step.model_dump())
                used_minutes += default_step_minutes
                step_idx += 1

            schedule_days.append(
                {
                    "date": day_str,
                    "sessions": sessions,
                    "total_minutes": used_minutes,
                    "is_review_day": bool(day_idx % 2 == 1 and sessions),
                    "student_events": day_events,
                }
            )

            if has_exam:
                review_calendar.append((day_cursor + timedelta(days=1)).isoformat())
            elif day_idx % 2 == 1 and sessions:
                review_calendar.append(day_str)

            day_cursor = day_cursor + timedelta(days=1)
            day_idx += 1

        exam_events = [e for e in student_events if e.get("event_type") == "exam"]
        assignment_events = [
            e for e in student_events if e.get("event_type") == "assignment"
        ]
        guide_parts = [
            "Prioritize the first two sessions each day, then review yesterday's weakest skill.",
        ]
        if exam_events:
            nearest_exam = sorted(exam_events, key=lambda e: e.get("date", ""))[0]
            guide_parts.append(
                f"Upcoming exam on {nearest_exam.get('date', '')}: {nearest_exam.get('title', 'Exam')}."
            )
            guide_parts.append(
                "Keep the day before the exam lighter, then schedule active recall the day after."
            )
        if assignment_events:
            nearest_assignment = sorted(
                assignment_events, key=lambda e: e.get("date", "")
            )[0]
            guide_parts.append(
                f"Deadline to watch: {nearest_assignment.get('title', 'Assignment')} ({nearest_assignment.get('date', '')})."
            )
        learning_schedule = {
            "schedule": schedule_days,
            "review_calendar": review_calendar,
            "study_guide": " ".join(guide_parts),
            "study_minutes_per_day": minutes_per_day,
            "student_events": student_events,
        }

        return LearningPathDiagnosisResponse(
            user_id=user_id,
            course_id=course_id,
            generated_at=result["generated_at"],
            path_length=result["path_length"],
            total_predicted_gain=result["total_predicted_gain"],
            steps=steps,
            zpd_range=result["zpd_range"],
            strategy=result["strategy"],
            learning_schedule=learning_schedule,
        )

    # ── RevFell ──────────────────────────────────────────────────

    def review_session(
        self,
        user_id: int,
        course_id: int,
        top_k: int = 5,
    ) -> ReviewResponse:
        """Run PCO detection and urgency-based review scheduling."""
        from arcd_agent.agents.revfell import (
            EmotionalState,
            FastReviewMode,
            PCODetector,
        )

        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            mastery_rows = repo.get_student_mastery(user_id, course_id)
            timeline = repo.get_student_timeline(user_id)
            event_end = (_today_utc_date() + timedelta(days=14)).isoformat()
            student_events = repo.get_student_events(
                user_id=user_id,
                from_date=_today_utc_date().isoformat(),
                to_date=event_end,
            )

        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)

        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [
            mastery_map.get(s, {}).get("mastery") or 0.0 for s in skill_names
        ]
        decay_vec = [mastery_map.get(s, {}).get("decay") or 1.0 for s in skill_names]

        # Convert timeline to ARCD format (skill_id int, response int)
        arcd_timeline = []
        for ev in timeline:
            idx = name_to_idx.get(ev.get("skill_name"))
            if idx is not None:
                arcd_timeline.append(
                    {"skill_id": idx, "response": 1 if ev.get("response") else 0}
                )

        detector = PCODetector()
        pco_results = detector.detect(arcd_timeline, mastery_vec, decay_vec)
        pco_skill_idxs = {sid for sid, r in pco_results.items() if r.is_pco}

        pco_skills = [
            PCOSkill(
                skill_name=skill_names[sid]
                if sid < len(skill_names)
                else f"Skill {sid}",
                failure_streak=r.failure_streak,
                mastery=r.mastery,
                decay_risk=r.decay_risk,
                why=r.why,
            )
            for sid, r in pco_results.items()
            if r.is_pco
        ]

        now_ts = int(time.time())
        last_practice = {}
        for ev in timeline:
            idx = name_to_idx.get(ev.get("skill_name"))
            if (
                idx is not None
                and ev.get("ts")
                and (idx not in last_practice or ev["ts"] > last_practice[idx])
            ):
                last_practice[idx] = ev["ts"]
        hours_since = {i: (now_ts - ts) / 3600.0 for i, ts in last_practice.items()}

        review_mode = FastReviewMode()
        candidate_k = min(max(top_k * 3, top_k), max(n, top_k))
        review_queue_raw = review_mode.rank_for_review(
            mastery_vec, hours_since, n, pco_skill_idxs, top_k=candidate_k
        )

        today = _today_utc_date()
        agenda_context: list[dict] = []
        exam_keywords: list[set[str]] = []
        for event in student_events:
            event_date = _safe_date(event.get("date"))
            if event_date is None:
                continue
            days_until = (event_date - today).days
            if days_until < 0:
                continue
            agenda_context.append(
                {
                    "id": event.get("id"),
                    "title": event.get("title", ""),
                    "date": event.get("date"),
                    "event_type": event.get("event_type", "other"),
                    "days_until": days_until,
                }
            )
            if event.get("event_type") == "exam" and days_until <= 7:
                exam_keywords.append(_tokenize(event.get("title", "")))

        boosts: dict[int, float] = {}
        if exam_keywords:
            for sid, sname in enumerate(skill_names):
                skill_tokens = _tokenize(sname)
                if not skill_tokens:
                    continue
                boost = 0.0
                for kws in exam_keywords:
                    if kws and (kws & skill_tokens):
                        boost += 0.18
                if boost > 0:
                    boosts[sid] = min(0.45, boost)

        enriched_queue = []
        for sid, urgency in review_queue_raw:
            adj_urgency = float(urgency) + boosts.get(sid, 0.0)
            enriched_queue.append((sid, adj_urgency))
        enriched_queue.sort(key=lambda x: x[1], reverse=True)
        review_queue = [
            {
                "skill_name": skill_names[sid]
                if sid < len(skill_names)
                else f"Skill {sid}",
                "urgency": round(urgency, 4),
            }
            for sid, urgency in enriched_queue[:top_k]
        ]

        emotional = EmotionalState()
        strategy = dict(emotional.teaching_strategy)
        if exam_keywords:
            strategy["agenda_note"] = (
                "Exam detected within 7 days. Prioritize exam-related skills first."
            )
        elif agenda_context:
            strategy["agenda_note"] = (
                "Upcoming events detected. Balance workload around busy days."
            )

        return ReviewResponse(
            user_id=user_id,
            pco_skills=pco_skills,
            review_queue=review_queue,
            emotional_state=emotional.state,
            teaching_strategy=strategy,
            agenda_context=agenda_context[:10],
        )

    # ── AdaEx ────────────────────────────────────────────────────

    def generate_exercise(
        self,
        user_id: int,
        skill_name: str,
        context: str = "",
    ) -> ExerciseResponse:
        """Generate an adaptive exercise for a skill using AdaEx."""
        from arcd_agent.agents.adaex import (
            DifficultyCalculator,
            ExerciseBank,
            ExerciseEvaluator,
            ExerciseGenerator,
            RefinementLoop,
        )

        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            mastery_rows = repo.get_student_mastery(user_id)
            skill_rows = repo.get_student_selected_skills(user_id)
            prereq_edges = repo.get_prerequisite_edges()

        # Find skill mastery
        mastery_map = {r["skill_name"]: r.get("mastery") or 0.0 for r in mastery_rows}
        mastery = mastery_map.get(skill_name, 0.0)

        # Find concept count for this skill
        concept_count = 1
        for r in skill_rows:
            if r["skill_name"] == skill_name:
                concept_count = len(r.get("concept_names") or []) or 1
                break

        # Build prereq matrix
        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)
        A_skill = np.zeros((n, n), dtype=np.float32)
        for edge in prereq_edges:
            i = name_to_idx.get(edge["from_skill"])
            j = name_to_idx.get(edge["to_skill"])
            if i is not None and j is not None:
                A_skill[i, j] = float(edge.get("strength") or 1.0)

        skill_idx = name_to_idx.get(skill_name, 0)
        calc = DifficultyCalculator(A_skill=A_skill)
        profile = calc.compute(
            skill_idx,
            skill_name,
            mastery,
            n_concepts=concept_count,
            max_concepts=max(concept_count, 20),
        )

        # Build LLM chain using LAB_TUTOR's LLM settings
        llm_chain = _build_llm_chain()

        bank = ExerciseBank()
        gen = ExerciseGenerator(llm_chain)
        ev_chain = _build_eval_chain()
        evaluator = ExerciseEvaluator(ev_chain)
        loop = RefinementLoop(gen, evaluator, bank, max_rounds=2)

        # Get concepts for context
        concepts = []
        for r in skill_rows:
            if r["skill_name"] == skill_name:
                concepts = list(r.get("concept_names") or [])[:8]
                break

        pkg = loop.run(profile, concepts=concepts, context=context)
        ex = pkg.exercise

        fmt = ex.format.replace("-", "_") if ex.format else "open_ended"
        if fmt not in ("multiple_choice", "open_ended", "fill_blank"):
            fmt = "open_ended"

        # Sanitize LLM output — options must be a list[str], correct_answer must be str
        raw_options: list[str] = (
            [str(o) for o in ex.options] if isinstance(ex.options, list) else []
        )
        raw_answer = ex.correct_answer
        if isinstance(raw_answer, dict):
            raw_answer = "; ".join(
                f"{k}: {v if isinstance(v, str) else ', '.join(str(x) for x in v)}"
                for k, v in raw_answer.items()
            )
        elif isinstance(raw_answer, list):
            raw_answer = "\n".join(str(x) for x in raw_answer)
        elif raw_answer is None:
            raw_answer = ""
        else:
            raw_answer = str(raw_answer)

        return ExerciseResponse(
            exercise_id=ex.exercise_id,
            skill_name=ex.skill_name,
            problem=ex.problem,
            format=fmt,
            options=raw_options,
            correct_answer=raw_answer,
            hints=ex.hints if isinstance(ex.hints, list) else [],
            concepts_tested=ex.concepts_tested
            if isinstance(ex.concepts_tested, list)
            else [],
            estimated_time_seconds=ex.estimated_time_seconds,
            difficulty_target=ex.difficulty_target,
            difficulty_band=ex.difficulty_band,
            why=ex.why,
            quality_warning=pkg.quality_warning,
        )

    # ── Interactions ─────────────────────────────────────────────

    def log_interaction(
        self,
        user_id: int,
        question_id: str,
        answered_right: bool,
        answered_at: str | None = None,
        selected_option: str | None = None,
        course_id: int | None = None,
        recompute_mastery: bool = True,
    ) -> None:
        """
        Log a student answering a question (creates ANSWERED edge).

        Feedback loop: after logging, recomputes and stores mastery so
        the KG always reflects the latest interaction state.
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            self._repo(session).create_answered(
                user_id=user_id,
                question_id=question_id,
                answered_right=answered_right,
                answered_at=answered_at,
                selected_option=selected_option,
            )

        # Closed-loop recompute: update MASTERED immediately after each interaction.
        if recompute_mastery:
            try:
                self.compute_and_store_mastery(user_id, course_id)
            except Exception:
                logger.warning(
                    "Mastery recompute after interaction failed for user %d (non-fatal)",
                    user_id,
                )

    def log_engagement(
        self,
        user_id: int,
        resource_id: str,
        resource_type: str,
        opened_at: str | None = None,
    ) -> None:
        """Log a student opening a reading/video resource."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            self._repo(session).upsert_opened_resource(
                user_id=user_id,
                resource_id=resource_id,
                resource_type=resource_type,
                opened_at=opened_at,
            )

    # ── ARCD Dashboard Portfolio ─────────────────────────────────

    def get_arcd_portfolio(self, user_id: int, course_id: int) -> dict:
        """Build full PortfolioData in the format the ARCD dashboard expects.

        Maps KG data (skills, mastery, timeline) into the hierarchical structure
        consumed by the React DataContext.
        """
        from .schemas import (
            ArcdConceptInfo,
            ArcdDatasetPortfolio,
            ArcdLearningPath,
            ArcdLearningPathStep,
            ArcdModelInfo,
            ArcdPortfolioData,
            ArcdSkillInfo,
            ArcdStudentPortfolio,
            ArcdStudentSummary,
            ArcdTimelineEntry,
        )

        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            # Use the student's selected skills as the canonical skill list so every
            # ARCD tab (journey map, radar, pathgen, twin) reflects only what the
            # student enrolled in.  The repository falls back to all course skills
            # automatically when the student has made no selection yet, so this
            # behaves identically to the old behaviour for students who haven't
            # selected any skills.
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            mastery_rows = repo.get_student_mastery(user_id, course_id)
            timeline_rows = repo.get_student_timeline(user_id, course_id)

        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)

        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [
            float(v)
            if (v := mastery_map.get(s, {}).get("mastery")) is not None
            else 0.0
            for s in skill_names
        ]

        # Build SkillInfo list: each SKILL node has its CONCEPT nodes attached directly.
        # id = index in this list = index into the mastery vector.
        # Derive stable chapter groups.
        # If chapter_name is missing, group under a single "Uncategorized" bucket instead of
        # assigning each skill its own chapter id (which fragments the UI into many buckets).
        seen_chapters: dict[str, int] = {}
        chapter_orders: dict[str, int] = {}
        uncategorized_id = 0
        next_id = 1
        for row in skill_rows:
            ch = (row.get("chapter_name") or "").strip()
            if not ch:
                continue
            if ch not in seen_chapters:
                seen_chapters[ch] = next_id
                try:
                    chapter_orders[ch] = int(row.get("chapter_order") or 9999)
                except Exception:
                    chapter_orders[ch] = 9999
                next_id += 1

        arcd_skills: list[ArcdSkillInfo] = []
        for i, row in enumerate(skill_rows):
            concept_names = row.get("concept_names") or []
            concepts = [
                ArcdConceptInfo(id=j, name_en=cname)
                for j, cname in enumerate(concept_names)
            ]
            ch_name = (row.get("chapter_name") or "").strip()
            if not ch_name:
                ch_name = "Uncategorized"
                ch_id = uncategorized_id
                ch_order = 9999
            else:
                ch_id = seen_chapters.get(ch_name, uncategorized_id)
                ch_order = chapter_orders.get(ch_name, 9999)
            arcd_skills.append(
                ArcdSkillInfo(
                    id=i,
                    chapter_id=ch_id,
                    domain_id=ch_id,
                    chapter_order=ch_order,
                    chapter_name=ch_name,
                    name=row["skill_name"],
                    concepts=concepts,
                    n_concepts=len(concept_names),
                )
            )

        # Build timeline entries with running mastery vector
        running_mastery = [0.0] * n
        arcd_timeline: list[ArcdTimelineEntry] = []
        for step_idx, ev in enumerate(timeline_rows):
            skill_idx = name_to_idx.get(ev.get("skill_name"), -1)
            if skill_idx < 0:
                continue
            response = 1 if ev.get("response") else 0
            if response:
                running_mastery[skill_idx] = min(running_mastery[skill_idx] + 0.1, 1.0)
            else:
                running_mastery[skill_idx] = max(running_mastery[skill_idx] - 0.05, 0.0)

            ts = ev.get("ts") or 0
            arcd_timeline.append(
                ArcdTimelineEntry(
                    step=step_idx,
                    timestamp=datetime.fromtimestamp(ts, tz=UTC).isoformat()
                    if ts
                    else "",
                    skill_id=skill_idx,
                    response=response,
                    predicted_prob=mastery_vec[skill_idx]
                    if skill_idx < len(mastery_vec)
                    else 0.5,
                    mastery=list(running_mastery),
                )
            )

        # Summary
        total_interactions = len(arcd_timeline)
        correct = sum(1 for e in arcd_timeline if e.response == 1)
        accuracy = correct / max(total_interactions, 1)
        avg_mastery = sum(mastery_vec) / max(n, 1)
        strongest = int(np.argmax(mastery_vec)) if mastery_vec else 0
        weakest = int(np.argmin(mastery_vec)) if mastery_vec else 0
        skills_touched = sum(1 for m in mastery_vec if m > 0)

        first_ts = arcd_timeline[0].timestamp if arcd_timeline else ""
        last_ts = arcd_timeline[-1].timestamp if arcd_timeline else ""
        unique_days = len({e.timestamp[:10] for e in arcd_timeline if e.timestamp})

        summary = ArcdStudentSummary(
            total_interactions=total_interactions,
            accuracy=round(accuracy, 4),
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            active_days=unique_days,
            avg_mastery=round(avg_mastery, 4),
            strongest_skill=strongest,
            weakest_skill=weakest,
            skills_touched=skills_touched,
        )

        # Build learning path (reuse existing method, convert format)
        arcd_learning_path = None
        try:
            path_resp = self.generate_path(user_id, course_id)
            if path_resp.steps:
                arcd_steps = []
                for ps in path_resp.steps:
                    sid = name_to_idx.get(ps.skill_name, 0)
                    arcd_steps.append(
                        ArcdLearningPathStep(
                            rank=ps.rank,
                            skill_id=sid,
                            skill_name=ps.skill_name,
                            score=ps.score,
                            predicted_mastery_gain=ps.predicted_mastery_gain,
                            current_mastery=ps.current_mastery,
                            projected_mastery=ps.projected_mastery,
                            rationale=ps.rationale,
                        )
                    )
                arcd_learning_path = ArcdLearningPath(
                    generated_at=path_resp.generated_at,
                    path_length=path_resp.path_length,
                    total_predicted_gain=path_resp.total_predicted_gain,
                    steps=arcd_steps,
                    zpd_range=path_resp.zpd_range,
                    strategy=path_resp.strategy,
                    learning_schedule=getattr(path_resp, "learning_schedule", None),
                )
        except Exception as exc:
            logger.warning(
                "PathGen unavailable for ARCD portfolio (user %d): %s", user_id, exc
            )

        # Build review session data
        review_dict = None
        try:
            review_resp = self.review_session(user_id, course_id)
            if review_resp.pco_skills or review_resp.review_queue:
                review_dict = {
                    "student_uid": str(user_id),
                    "dataset_id": f"course_{course_id}",
                    "started_at": datetime.now(tz=UTC).isoformat(),
                    "completed_at": datetime.now(tz=UTC).isoformat(),
                    "pco_skills_detected": [
                        name_to_idx.get(p.skill_name, 0) for p in review_resp.pco_skills
                    ],
                    "pco_count": len(review_resp.pco_skills),
                    "fast_reviews": [
                        {"skill_id": name_to_idx.get(rq["skill_name"], 0), **rq}
                        for rq in review_resp.review_queue
                    ],
                    "slow_thinking_plans": [],
                    "mastery_updates": [],
                    "rewards": {
                        "total_points": 0,
                        "session_points": 0,
                        "events_count": 0,
                        "current_streak": 0,
                    },
                    "needs_replan": len(review_resp.pco_skills) > 0,
                    "deviations": [],
                }
        except Exception as exc:
            logger.warning(
                "RevFell unavailable for ARCD portfolio (user %d): %s", user_id, exc
            )

        student_portfolio = ArcdStudentPortfolio(
            uid=str(user_id),
            summary=summary,
            final_mastery=mastery_vec,
            base_mastery=[0.0] * n,
            timeline=arcd_timeline,
            learning_path=arcd_learning_path,
            review_session=review_dict,
        )

        dataset = ArcdDatasetPortfolio(
            id=f"course_{course_id}",
            name=f"Course {course_id}",
            model_info=ArcdModelInfo(
                n_skills=n,
                n_questions=total_interactions,
                n_students=1,
            ),
            skills=arcd_skills,
            students=[student_portfolio],
        )

        portfolio = ArcdPortfolioData(
            generated_at=datetime.now(tz=UTC).isoformat(),
            datasets=[dataset],
        )

        return portfolio.model_dump()

    def get_arcd_twin(self, user_id: int, course_id: int) -> dict:
        """Build TwinViewerData for the ARCD digital twin dashboard."""
        from .schemas import (
            ArcdTwinConfidence,
            ArcdTwinCurrentState,
            ArcdTwinRiskForecast,
            ArcdTwinScenarioComparison,
            ArcdTwinScenarioPath,
            ArcdTwinSkillAlert,
            ArcdTwinSnapshotEntry,
            ArcdTwinViewerData,
        )

        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            mastery_rows = repo.get_student_mastery(user_id, course_id)

        skill_names = [r["skill_name"] for r in skill_rows]
        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [
            float(v)
            if (v := mastery_map.get(s, {}).get("mastery")) is not None
            else 0.0
            for s in skill_names
        ]
        decay_vec = [
            float(v) if (v := mastery_map.get(s, {}).get("decay")) is not None else 1.0
            for s in skill_names
        ]
        n = len(skill_names)

        now_ts = int(time.time())
        avg_m = sum(mastery_vec) / max(n, 1)
        above_60 = sum(1 for m in mastery_vec if m >= 0.6)
        below_40 = sum(1 for m in mastery_vec if m < 0.4)

        current = ArcdTwinCurrentState(
            mastery=mastery_vec,
            snapshot_type="live",
            timestamp=now_ts,
            hu_fresh=True,
            skill_names={str(i): name for i, name in enumerate(skill_names)},
            summary={
                "avg_mastery": round(avg_m, 4),
                "above_60pct": above_60,
                "below_40pct": below_40,
                "n_skills": n,
            },
        )

        snapshot = ArcdTwinSnapshotEntry(
            index=0,
            step=0,
            timestamp=now_ts,
            snapshot_type="live",
            avg_mastery=round(avg_m, 4),
            mastery=mastery_vec,
        )

        # ── Risk forecast via ARCD decay cascade (Eq. 6-11) ──────────────────
        HORIZON = 30
        avg_mastery_now = sum(mastery_vec) / max(n, 1)
        at_risk = []
        for i, m in enumerate(mastery_vec):
            dv = decay_vec[i] if i < len(decay_vec) else 1.0
            diff = max(0.0, min(1.0, 1.0 - dv))
            # Simulate HORIZON days without any practice (n_s stays 0)
            retained = _arcd_decay_cascade(
                m_s=m,
                n_s=0.0,
                proficiency=avg_mastery_now,
                difficulty=diff,
                delta_t_days=float(HORIZON),
            )
            predicted_decay = 1.0 - retained
            if predicted_decay > 0.30 or m < 0.40:
                priority = "HIGH" if predicted_decay > 0.55 or m < 0.25 else "MEDIUM"
                at_risk.append(
                    ArcdTwinSkillAlert(
                        skill_id=i,
                        skill_name=skill_names[i],
                        current_mastery=round(m, 4),
                        predicted_decay=round(predicted_decay, 4),
                        priority=priority,
                    )
                )

        risk_forecast = ArcdTwinRiskForecast(
            total_at_risk=len(at_risk),
            computed_at=datetime.now(tz=UTC).isoformat(),
            at_risk_skills=at_risk,
        )

        # ── PathGen recommendation for path_a ─────────────────────────────────
        # Sort skills: weak first, strong last
        sorted_weak = sorted(range(n), key=lambda i: mastery_vec[i])
        sorted_strong = sorted(range(n), key=lambda i: mastery_vec[i], reverse=True)

        # Bottom half (or at least 3) for focused-practice target set
        focus_count = max(3, n // 2)
        weak_indices = sorted_weak[: min(focus_count, n)]

        recommended_indices: list[int] = []
        recommended_schedule_summary: dict | None = None
        try:
            path_resp = self.generate_path(
                user_id, course_id, path_length=min(8, max(1, n))
            )
            skill_name_to_idx = {name: idx for idx, name in enumerate(skill_names)}
            for step in path_resp.steps:
                sid = skill_name_to_idx.get(step.skill_name)
                if sid is not None and sid not in recommended_indices:
                    recommended_indices.append(sid)
            sched = path_resp.learning_schedule or {}
            full_schedule = sched.get("schedule") or []
            recommended_schedule_summary = {
                "next_days": full_schedule[:7],
                "student_events": sched.get("student_events") or [],
                "review_calendar": (sched.get("review_calendar") or [])[:7],
            }
        except Exception as exc:
            logger.warning(
                "PathGen unavailable for ARCD twin scenario (user %d): %s", user_id, exc
            )

        if not recommended_indices:
            recommended_indices = weak_indices

        # ── Simulate three strategies via ARCD cascade ────────────────────────
        # path_a: PathGen recommended (focused daily practice on weak skills)
        traj_a = _arcd_simulate_strategy(
            mastery_vec, decay_vec, recommended_indices, HORIZON, mode="focus"
        )
        final_a = traj_a[-1]["avgMastery"] / 100.0

        # path_b: Desirable Difficulty — "challengingly learnable" band 0.25–0.60.
        # Upper bound < 0.65 ensures ZERO overlap with reinforce_indices.
        zpd_indices = sorted(
            [i for i in range(n) if 0.25 <= mastery_vec[i] <= 0.60],
            key=lambda i: mastery_vec[i],
        )
        if len(zpd_indices) < 3:
            # fallback: take the middle-third by mastery
            mid_start = n // 3
            zpd_indices = sorted_weak[mid_start : mid_start + max(3, n // 3)]
        if len(zpd_indices) < 3:
            zpd_indices = sorted_weak[: max(3, n // 2)]
        traj_b = _arcd_simulate_strategy(
            mastery_vec, decay_vec, zpd_indices, HORIZON, mode="spaced"
        )
        final_b = traj_b[-1]["avgMastery"] / 100.0

        # path_c: Conservative Reinforcement — already strong skills only (> 0.65).
        # Lower bound > 0.60 ensures ZERO overlap with zpd_indices.
        reinforce_indices = sorted(
            [i for i in range(n) if mastery_vec[i] > 0.65],
            key=lambda i: mastery_vec[i],
            reverse=True,
        )
        if len(reinforce_indices) < 3:
            reinforce_indices = sorted_strong[: max(3, n // 3)]
        traj_c = _arcd_simulate_strategy(
            mastery_vec, decay_vec, reinforce_indices, HORIZON, mode="reinforce"
        )
        final_c = traj_c[-1]["avgMastery"] / 100.0

        # ── Coherence scores ───────────────────────────────────────────────────
        coh_a = _coherence_score(recommended_indices, mastery_vec)
        coh_b = _coherence_score(zpd_indices, mastery_vec)
        coh_c = _coherence_score(reinforce_indices, mastery_vec)

        # ── Justifications ────────────────────────────────────────────────────
        def _just_a(idxs: list[int]) -> list[str]:
            gain_pct = round((final_a - avg_m) * 100, 1)
            return [
                f"Daily focused retrieval on {len(idxs)} weak skill(s) — "
                "highest per-session gain rate (η=0.18, every day).",
                f"Projected {gain_pct:+.1f}% average mastery change over {HORIZON} d "
                "(fastest gains on horizons ≤ 14 d; plateaus as weak skills approach ceiling).",
                f"Skills targeted: {', '.join(skill_names[i] for i in idxs if i < n)}.",
            ]

        def _just_b(idxs: list[int]) -> list[str]:
            gain_pct = round((final_b - avg_m) * 100, 1)
            return [
                f"Desirable Difficulty on {len(idxs)} mid-level skill(s) (mastery 25–60%): "
                "harder retrieval practice every 3 d with testing-effect bonus (η=0.22).",
                f"Projected {gain_pct:+.1f}% change over {HORIZON} d — "
                "slower start, accelerates from day 10, dominates at ≥ 21 d.",
                f"Skills targeted: {', '.join(skill_names[i] for i in idxs if i < n)}.",
            ]

        def _just_c(idxs: list[int]) -> list[str]:
            gain_pct = round((final_c - avg_m) * 100, 1)
            return [
                f"Light daily maintenance on {len(idxs)} strong skill(s) (mastery > 65%): "
                "η=0.05 prevents ARCD decay without cognitive overload.",
                f"Projected {gain_pct:+.1f}% average change over {HORIZON} d — "
                "weak/medium skills will visibly erode (trade-off: stability vs growth).",
                f"Skills maintained: {', '.join(skill_names[i] for i in idxs if i < n)}.",
            ]

        final_scores = {"path_a": final_a, "path_b": final_b, "path_c": final_c}
        best_path = max(final_scores, key=lambda k: final_scores[k])

        scenario = ArcdTwinScenarioComparison(
            horizon_days=HORIZON,
            path_a=ArcdTwinScenarioPath(
                name="PathGen Recommended",
                skills=recommended_indices,
                skill_names=[skill_names[i] for i in recommended_indices if i < n],
                avg_mastery_gain=round(final_a - avg_m, 4),
                final_avg_mastery=round(final_a, 4),
                trajectory=traj_a,
                coherence_score=coh_a,
                justification=_just_a(recommended_indices),
            ),
            path_b=ArcdTwinScenarioPath(
                name="Desirable Difficulty",
                skills=zpd_indices,
                skill_names=[skill_names[i] for i in zpd_indices if i < n],
                avg_mastery_gain=round(final_b - avg_m, 4),
                final_avg_mastery=round(final_b, 4),
                trajectory=traj_b,
                coherence_score=coh_b,
                justification=_just_b(zpd_indices),
            ),
            path_c=ArcdTwinScenarioPath(
                name="Conservative Reinforcement",
                skills=reinforce_indices,
                skill_names=[skill_names[i] for i in reinforce_indices if i < n],
                avg_mastery_gain=round(final_c - avg_m, 4),
                final_avg_mastery=round(final_c, 4),
                trajectory=traj_c,
                coherence_score=coh_c,
                justification=_just_c(reinforce_indices),
            ),
            best_path=best_path,
        )

        twin_data = ArcdTwinViewerData(
            student_id=str(user_id),
            generated_at=datetime.now(tz=UTC).isoformat(),
            dataset=f"course_{course_id}",
            current_twin=current,
            snapshot_history=[snapshot],
            risk_forecast=risk_forecast,
            scenario_comparison=scenario,
            twin_confidence=ArcdTwinConfidence(
                quality="arcd-simulated",
                description="ARCD 4-stage decay cascade (Eq. 6-11) forward simulation",
                per_skill_rmse=[0.08] * n,
            ),
            recommended_schedule_summary=recommended_schedule_summary,
        )

        return twin_data.model_dump()

    # ── Portfolio ────────────────────────────────────────────────

    def get_portfolio(self, user_id: int, course_id: int) -> PortfolioResponse:
        """Return full student portfolio: mastery + path + PCO analysis."""
        mastery_resp = self.get_mastery(user_id, course_id)
        path_resp = self.generate_path(user_id, course_id)
        review_resp = self.review_session(user_id, course_id)

        total = len(mastery_resp.skills)
        mastered = sum(1 for s in mastery_resp.skills if s.status in ("at", "above"))
        in_progress = sum(1 for s in mastery_resp.skills if s.status == "below")
        avg_mastery = sum(s.mastery for s in mastery_resp.skills) / max(total, 1)

        return PortfolioResponse(
            user_id=user_id,
            course_id=course_id,
            mastery=mastery_resp.skills,
            learning_path=path_resp,
            pco_skills=review_resp.pco_skills,
            stats={
                "total_skills": total,
                "mastered_skills": mastered,
                "in_progress_skills": in_progress,
                "not_started_skills": total - mastered - in_progress,
                "average_mastery": round(avg_mastery, 4),
                "pco_count": len(review_resp.pco_skills),
            },
            generated_at=datetime.now(tz=UTC).isoformat(),
        )

    def analyze_what_if_strategy(
        self, req: WhatIfAnalysisRequest
    ) -> WhatIfAnalysisResponse:
        """Analyze simulation options and return a strategy recommendation."""
        mastery = req.mastery_vector or []
        options = req.strategy_options or []
        if not mastery:
            best = req.recommended_strategy or "Focus on Weakest"
            return WhatIfAnalysisResponse(
                best_strategy=best,
                rationale="Not enough mastery data was provided, so a default recommendation was used.",
                action_items=[
                    "Run a simulation with current mastery data.",
                    "Compare at least two strategy trajectories.",
                    "Retry strategy advisor after data refresh.",
                ],
                generated_at=datetime.now(tz=UTC).isoformat(),
                source="rule_based",
            )

        n = len(mastery)
        below40 = sum(1 for m in mastery if m < 0.4) / max(n, 1)
        midband = sum(1 for m in mastery if 0.5 <= m < 0.7) / max(n, 1)
        above70 = sum(1 for m in mastery if m >= 0.7) / max(n, 1)
        mean = sum(mastery) / max(n, 1)
        variance = sum((m - mean) ** 2 for m in mastery) / max(n, 1)

        # Rank the actual submitted strategy options first, then apply profile-aware weighting.
        if options:
            profile_weights: dict[str, float] = {
                "Focus on Weakest": 1.0 + below40 * 0.45 - above70 * 0.1,
                "Spaced Reinforcement": 1.0 + midband * 0.35 + (variance < 0.04) * 0.1,
                "Strengthen Top Skills": 1.0 + above70 * 0.3 - below40 * 0.2,
                "Manual Selection": 1.0
                + 0.08,  # slight preference for intentional student choice
                "Balanced Mix": 1.0 + (variance >= 0.06) * 0.2,
            }

            def _weighted_score(option) -> float:
                weight = profile_weights.get(option.name, 1.0)
                base = (option.total_gain * 0.65 + option.final_avg * 0.20) * weight
                # Coherence bonus: a well-chained path gets up to +20% score boost
                coherence_bonus = getattr(option, "coherence_score", 0.0) * 0.15
                return base * (1 + coherence_bonus)

            ranked = sorted(options, key=_weighted_score, reverse=True)
            best_option = ranked[0]
            best_strategy = best_option.name
        else:
            best_strategy = req.recommended_strategy or "Spaced Reinforcement"

        if best_strategy == "Focus on Weakest":
            rationale = (
                "Your profile shows enough low-mastery skills that targeted repair is likely to deliver "
                "the strongest immediate improvement."
            )
            actions = [
                "Start with the lowest-mastery skills in your selected path.",
                "Use short, focused sessions for rapid correction.",
                "Re-run simulation after 3-5 study steps to confirm uplift.",
            ]
        elif best_strategy == "Spaced Reinforcement":
            rationale = (
                "A large share of skills are near threshold, so spaced reinforcement should improve retention "
                "and convert near-mastery into stable proficiency."
            )
            actions = [
                "Prioritize near-threshold skills in alternating review cycles.",
                "Schedule follow-up reviews every 24-48 hours.",
                "Track retention trends, not just single-step gain.",
            ]
        elif best_strategy == "Strengthen Top Skills":
            rationale = (
                "You already have strong baseline mastery, so advanced consolidation can raise high-performing "
                "skills efficiently while keeping momentum."
            )
            actions = [
                "Use challenge-level exercises for your strongest skills.",
                "Keep one short maintenance block for weaker skills.",
                "Add one stretch objective per session.",
            ]
        elif best_strategy == "Manual Selection":
            rationale = (
                "Your manually chosen skills currently produce the most relevant projected outcome, balancing "
                "student intent with measurable gain."
            )
            actions = [
                "Continue with the selected skill set for the next study block.",
                "Replace any skill that remains flat after two attempts.",
                "Re-run simulation after each block to keep the path adaptive.",
            ]
        else:
            rationale = (
                "A mixed strategy is currently the most robust option for this mastery distribution, "
                "balancing weak-skill recovery with broader progression."
            )
            actions = [
                "Split time between weak-skill repair and reinforcement.",
                "Alternate strategy emphasis each study session.",
                "Monitor both average mastery and spread.",
            ]

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key or "no-key",
                base_url=settings.llm_base_url,
            )
            options_txt = "\n".join(
                f"- {o.name}: gain={o.total_gain:.3f}, final={o.final_avg:.3f}, targets={', '.join(o.target_skills[:5])}"
                for o in req.strategy_options
            )
            prompt = (
                f"Mastery profile: below40={below40:.2f}, midband={midband:.2f}, above70={above70:.2f}, variance={variance:.3f}\n"
                f"Rule-based recommendation: {best_strategy}\n"
                f"Strategy options:\n{options_txt}\n\n"
                "Produce a concise recommendation paragraph plus three action items."
            )
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a concise learning strategy advisor.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            llm_text = (response.choices[0].message.content or "").strip()
            if llm_text:
                return WhatIfAnalysisResponse(
                    best_strategy=best_strategy,
                    rationale=llm_text,
                    action_items=actions,
                    generated_at=datetime.now(tz=UTC).isoformat(),
                    source="llm",
                )
        except Exception:
            pass

        return WhatIfAnalysisResponse(
            best_strategy=best_strategy,
            rationale=rationale,
            action_items=actions,
            generated_at=datetime.now(tz=UTC).isoformat(),
            source="rule_based",
        )


# ── LLM chain builders ─────────────────────────────────────────────────────


def _build_llm_chain():
    """Build a simple LLM chain for exercise generation using LAB_TUTOR's LLM settings."""
    import json as _json

    def chain(inputs: dict) -> dict:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key or "no-key",
                base_url=settings.llm_base_url,
            )
            prompt = inputs.get("request", "")
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an educational exercise generator. "
                            "Generate a structured exercise as JSON with keys: "
                            "problem, format, options, correct_answer, solution_steps, "
                            "hints, concepts_tested, estimated_time_seconds, difficulty_generated."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            content = response.choices[0].message.content or "{}"
            return _json.loads(content)
        except Exception as exc:
            logger.warning("LLM exercise generation failed: %s", exc)
            return {}

    return chain


def _build_eval_chain():
    """Build a simple LLM chain for exercise quality evaluation."""
    import json as _json

    def chain(inputs: dict) -> dict:
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.llm_api_key or "no-key",
                base_url=settings.llm_base_url,
            )
            prompt = inputs.get("request", "")
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an educational quality evaluator. "
                            "Score the exercise and return JSON with keys: "
                            "correctness_score (0-1), pedagogical_score (0-1), "
                            "difficulty_assessment (0-1), correctness_feedback, "
                            "pedagogical_feedback, overall_feedback, suggested_improvements (list)."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            content = response.choices[0].message.content or "{}"
            return _json.loads(content)
        except Exception as exc:
            logger.warning("LLM exercise evaluation failed: %s", exc)
            return {}

    return chain
