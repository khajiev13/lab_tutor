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
    return {w.strip().lower() for w in text.replace("_", " ").replace("-", " ").split() if len(w.strip()) >= 4}


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

    skill_stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0, "last_ts": None})
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

        results.append({
            "skill_name": name,
            "mastery": round(mastery, 4),
            "decay": round(decay, 4),
            "status": status,
            "attempt_count": total,
            "correct_count": correct,
            "last_practice_ts": last_ts,
        })
    return results


# ── Main service ───────────────────────────────────────────────────────────


class CognitiveDiagnosisService:
    """ARCD-powered student modeling and adaptive learning service."""

    MODEL_VERSION = "arcd_v2_heuristic"

    def __init__(self, neo4j_driver: Neo4jDriver) -> None:
        self._driver = neo4j_driver

    def _repo(self, session) -> CognitiveDiagnosisRepository:
        return CognitiveDiagnosisRepository(session)

    # ── Student events ────────────────────────────────────────────

    def create_student_event(self, user_id: int, event: StudentEventCreate | dict) -> dict:
        payload = event.model_dump() if isinstance(event, StudentEventCreate) else dict(event)
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

        Currently uses the heuristic estimator; slot in the ARCD model here
        once labtutor checkpoint is trained.
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            repo = self._repo(session)

            # Load existing mastery (may be empty on first call)
            existing = {r["skill_name"]: r for r in repo.get_student_mastery(user_id, course_id)}

            # Load interaction timeline
            timeline = repo.get_student_timeline(user_id)

            # Load skill names — scoped to this student's selected skills
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

            # Compute mastery
            computed = _compute_mastery_heuristic(list(existing.values()), timeline, skill_names)

            # Persist back to KG
            repo.upsert_mastery_batch(user_id, computed, model_version=self.MODEL_VERSION)

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
                user_id=user_id, course_id=course_id,
                generated_at=datetime.now(tz=UTC).isoformat(),
            )

        # Build index
        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)

        # Build mastery and decay vectors
        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [mastery_map.get(s, {}).get("mastery") or 0.0 for s in skill_names]
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
            if idx is not None and ev.get("ts") and (idx not in last_practice or ev["ts"] > last_practice[idx]):
                last_practice[idx] = ev["ts"]
        hours_since = {
            idx: (now_ts - ts) / 3600.0 for idx, ts in last_practice.items()
        }

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
            steps.append(PathStep(
                rank=step["rank"],
                skill_name=sname,
                current_mastery=step["current_mastery"],
                predicted_mastery_gain=step["predicted_mastery_gain"],
                projected_mastery=step["projected_mastery"],
                score=step["score"],
                rationale=step.get("rationale", ""),
            ))

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
            has_busy = any(e.get("event_type") in {"busy", "assignment"} for e in day_events)
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
        assignment_events = [e for e in student_events if e.get("event_type") == "assignment"]
        guide_parts = [
            "Prioritize the first two sessions each day, then review yesterday's weakest skill.",
        ]
        if exam_events:
            nearest_exam = sorted(exam_events, key=lambda e: e.get("date", ""))[0]
            guide_parts.append(
                f"Upcoming exam on {nearest_exam.get('date', '')}: {nearest_exam.get('title', 'Exam')}."
            )
            guide_parts.append("Keep the day before the exam lighter, then schedule active recall the day after.")
        if assignment_events:
            nearest_assignment = sorted(assignment_events, key=lambda e: e.get("date", ""))[0]
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
        mastery_vec = [mastery_map.get(s, {}).get("mastery") or 0.0 for s in skill_names]
        decay_vec = [mastery_map.get(s, {}).get("decay") or 1.0 for s in skill_names]

        # Convert timeline to ARCD format (skill_id int, response int)
        arcd_timeline = []
        for ev in timeline:
            idx = name_to_idx.get(ev.get("skill_name"))
            if idx is not None:
                arcd_timeline.append({"skill_id": idx, "response": 1 if ev.get("response") else 0})

        detector = PCODetector()
        pco_results = detector.detect(arcd_timeline, mastery_vec, decay_vec)
        pco_skill_idxs = {sid for sid, r in pco_results.items() if r.is_pco}

        pco_skills = [
            PCOSkill(
                skill_name=skill_names[sid] if sid < len(skill_names) else f"Skill {sid}",
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
            if idx is not None and ev.get("ts") and (idx not in last_practice or ev["ts"] > last_practice[idx]):
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
                "skill_name": skill_names[sid] if sid < len(skill_names) else f"Skill {sid}",
                "urgency": round(urgency, 4),
            }
            for sid, urgency in enriched_queue[:top_k]
        ]

        emotional = EmotionalState()
        strategy = dict(emotional.teaching_strategy)
        if exam_keywords:
            strategy["agenda_note"] = "Exam detected within 7 days. Prioritize exam-related skills first."
        elif agenda_context:
            strategy["agenda_note"] = "Upcoming events detected. Balance workload around busy days."

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
            skill_idx, skill_name, mastery,
            n_concepts=concept_count, max_concepts=max(concept_count, 20),
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

        return ExerciseResponse(
            exercise_id=ex.exercise_id,
            skill_name=ex.skill_name,
            problem=ex.problem,
            format=fmt,
            options=ex.options,
            correct_answer=ex.correct_answer,
            hints=ex.hints,
            concepts_tested=ex.concepts_tested,
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
        is_correct: bool,
        timestamp_sec: int | None = None,
        time_spent_sec: int | None = None,
        attempt_number: int = 1,
        course_id: int | None = None,
        recompute_mastery: bool = True,
    ) -> None:
        """
        Log a student answering a question (creates ATTEMPTED edge).

        Feedback loop: after logging, recomputes and stores mastery so
        the KG always reflects the latest interaction state.
        """
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            self._repo(session).create_attempted(
                user_id=user_id,
                question_id=question_id,
                is_correct=is_correct,
                timestamp_sec=timestamp_sec,
                attempt_number=attempt_number,
                time_spent_sec=time_spent_sec,
            )

        # Closed-loop recompute: update MASTERY_OF immediately after each interaction.
        if recompute_mastery:
            try:
                self.compute_and_store_mastery(user_id, course_id)
            except Exception:
                logger.warning(
                    "Mastery recompute after interaction failed for user %d (non-fatal)", user_id
                )

    def log_engagement(
        self,
        user_id: int,
        resource_id: str,
        resource_type: str,
        progress: float = 0.0,
        duration_sec: int | None = None,
        timestamp_sec: int | None = None,
    ) -> None:
        """Log a student engaging with a reading/video resource."""
        db = settings.neo4j_database
        with self._driver.session(database=db) as session:
            self._repo(session).upsert_engages_with(
                user_id=user_id,
                resource_id=resource_id,
                resource_type=resource_type,
                progress=progress,
                duration_sec=duration_sec,
                timestamp_sec=timestamp_sec,
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
            skill_rows = repo.get_student_selected_skills(user_id, course_id)
            mastery_rows = repo.get_student_mastery(user_id, course_id)
            timeline_rows = repo.get_student_timeline(user_id)

        skill_names = [r["skill_name"] for r in skill_rows]
        name_to_idx = {n: i for i, n in enumerate(skill_names)}
        n = len(skill_names)

        mastery_map = {r["skill_name"]: r for r in mastery_rows}
        mastery_vec = [mastery_map.get(s, {}).get("mastery", 0.0) for s in skill_names]

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
            arcd_skills.append(ArcdSkillInfo(
                id=i,
                chapter_id=ch_id,
                domain_id=ch_id,
                chapter_order=ch_order,
                chapter_name=ch_name,
                name=row["skill_name"],
                concepts=concepts,
                n_concepts=len(concept_names),
            ))

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
            arcd_timeline.append(ArcdTimelineEntry(
                step=step_idx,
                timestamp=datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else "",
                skill_id=skill_idx,
                response=response,
                predicted_prob=mastery_vec[skill_idx] if skill_idx < len(mastery_vec) else 0.5,
                mastery=list(running_mastery),
            ))

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
                    arcd_steps.append(ArcdLearningPathStep(
                        rank=ps.rank,
                        skill_id=sid,
                        skill_name=ps.skill_name,
                        score=ps.score,
                        predicted_mastery_gain=ps.predicted_mastery_gain,
                        current_mastery=ps.current_mastery,
                        projected_mastery=ps.projected_mastery,
                        rationale=ps.rationale,
                    ))
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
            logger.warning("PathGen unavailable for ARCD portfolio (user %d): %s", user_id, exc)

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
                    "rewards": {"total_points": 0, "session_points": 0, "events_count": 0, "current_streak": 0},
                    "needs_replan": len(review_resp.pco_skills) > 0,
                    "deviations": [],
                }
        except Exception as exc:
            logger.warning("RevFell unavailable for ARCD portfolio (user %d): %s", user_id, exc)

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
        mastery_vec = [mastery_map.get(s, {}).get("mastery", 0.0) for s in skill_names]
        decay_vec = [mastery_map.get(s, {}).get("decay", 1.0) for s in skill_names]
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
            index=0, step=0, timestamp=now_ts,
            snapshot_type="live", avg_mastery=round(avg_m, 4), mastery=mastery_vec,
        )

        at_risk = []
        for i, (m, d) in enumerate(zip(mastery_vec, decay_vec, strict=False)):
            if d < 0.7 or m < 0.4:
                priority = "HIGH" if d < 0.5 or m < 0.2 else "MEDIUM"
                at_risk.append(ArcdTwinSkillAlert(
                    skill_id=i,
                    skill_name=skill_names[i],
                    current_mastery=round(m, 4),
                    predicted_decay=round(1.0 - d, 4),
                    priority=priority,
                ))

        risk_forecast = ArcdTwinRiskForecast(
            total_at_risk=len(at_risk),
            computed_at=datetime.now(tz=UTC).isoformat(),
            at_risk_skills=at_risk,
        )

        # Build scenario paths using real PathGen output so backend and dashboard
        # share the same recommendation source.
        weak_indices = sorted(range(n), key=lambda i: mastery_vec[i])[:min(3, n)]
        strong_indices = sorted(range(n), key=lambda i: mastery_vec[i], reverse=True)[:min(3, n)]

        recommended_indices: list[int] = []
        recommended_gain = 0.0
        recommended_schedule_summary: dict | None = None
        try:
            path_resp = self.generate_path(user_id, course_id, path_length=min(6, max(1, n)))
            skill_name_to_idx = {name: idx for idx, name in enumerate(skill_names)}
            for step in path_resp.steps:
                sid = skill_name_to_idx.get(step.skill_name)
                if sid is not None and sid not in recommended_indices:
                    recommended_indices.append(sid)
            recommended_gain = float(path_resp.total_predicted_gain or 0.0)
            sched = path_resp.learning_schedule or {}
            full_schedule = sched.get("schedule") or []
            recommended_schedule_summary = {
                "next_days": full_schedule[:7],
                "student_events": sched.get("student_events") or [],
                "review_calendar": (sched.get("review_calendar") or [])[:7],
            }
        except Exception as exc:
            logger.warning("PathGen unavailable for ARCD twin scenario (user %d): %s", user_id, exc)

        if not recommended_indices:
            recommended_indices = weak_indices
            # Fallback expected uplift if PathGen is unavailable.
            recommended_gain = 0.12

        # Projected final average mastery from cumulative predicted gain
        # distributed over the skill vector.
        projected_recommended_avg = min(1.0, avg_m + (recommended_gain / max(n, 1)))
        conservative_gain = max(0.03, recommended_gain * 0.45)
        projected_conservative_avg = min(1.0, avg_m + (conservative_gain / max(n, 1)))

        baseline_indices = [i for i in strong_indices if i not in recommended_indices]
        if not baseline_indices:
            baseline_indices = strong_indices or weak_indices

        scenario = ArcdTwinScenarioComparison(
            path_a=ArcdTwinScenarioPath(
                name="PathGen Recommended",
                skills=recommended_indices,
                skill_names=[skill_names[i] for i in recommended_indices if i < len(skill_names)],
                avg_mastery_gain=round(recommended_gain, 4),
                final_avg_mastery=round(projected_recommended_avg, 4),
            ),
            path_b=ArcdTwinScenarioPath(
                name="Conservative Reinforcement",
                skills=baseline_indices,
                skill_names=[skill_names[i] for i in baseline_indices if i < len(skill_names)],
                avg_mastery_gain=round(conservative_gain, 4),
                final_avg_mastery=round(projected_conservative_avg, 4),
            ),
            best_path="path_a" if projected_recommended_avg >= projected_conservative_avg else "path_b",
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
                quality="estimated",
                description="Heuristic-based twin (no trained model checkpoint)",
                per_skill_rmse=[0.1] * n,
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
        avg_mastery = (
            sum(s.mastery for s in mastery_resp.skills) / max(total, 1)
        )

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

    def analyze_what_if_strategy(self, req: WhatIfAnalysisRequest) -> WhatIfAnalysisResponse:
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
                "Manual Selection": 1.0 + 0.08,  # slight preference for intentional student choice
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
                    {"role": "system", "content": "You are a concise learning strategy advisor."},
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
