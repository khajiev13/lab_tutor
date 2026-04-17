"""synthgen.interaction_simulator — IRT 2PL interaction simulation.

Simulates student-question interactions using the 2-Parameter Logistic model:

    P(correct | θ, a, b) = σ(a · (θ − b))

where:
    θ = student ability
    a = item discrimination
    b = item difficulty
    σ = sigmoid function

Produces a DataFrame with columns required by the ARCD training pipeline:
    student_id, question_id, skill_id, correct, score,
    timestamp_sec, attempt_num, is_repeat
"""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd
from scipy.special import expit as sigmoid  # type: ignore

from .config import SynthGenConfig

logger = logging.getLogger(__name__)


def _simulate_student_interactions(
    student: dict,
    questions: list[dict],
    skill_to_qs: dict[str, list[dict]],
    student_skills: list[str],
    n_interactions: int,
    base_ts: int,
    sim_seconds: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Generate exactly ``n_interactions`` IRT-2PL rows for one student.

    Only ``student_skills`` (a per-student subset of the full skill catalogue)
    are sampled.  Skills outside this subset receive no interactions.
    """
    uid = student["student_id"]
    theta = student["theta"]

    start_offset = int(rng.uniform(0, sim_seconds * 0.10))
    current_ts = base_ts + start_offset

    attempt_counts: dict[str, int] = {}
    focus = 1.0

    skill_probs = rng.dirichlet(np.ones(len(student_skills)))
    skill_sequence = rng.choice(student_skills, size=n_interactions, p=skill_probs, replace=True)

    rows: list[dict] = []
    for skill_id in skill_sequence:
        pool = skill_to_qs[skill_id]
        q = rng.choice(pool)
        qid = q["question_id"]

        a = float(q["discrimination"])
        b = float(q["difficulty"])
        p_correct = float(sigmoid(a * (theta - b)))
        p_effective = np.clip(p_correct * focus, 0.05, 0.95)
        correct = int(rng.random() < p_effective)

        focus = focus * 0.97 if correct else min(focus * 1.05, 1.5)

        attempt_num = attempt_counts.get(qid, 0) + 1
        attempt_counts[qid] = attempt_num

        gap = int(rng.exponential(300))
        current_ts = min(current_ts + gap, base_ts + sim_seconds)

        rows.append(
            {
                "student_id": uid,
                "question_id": qid,
                "skill_id": skill_id,
                "correct": correct,
                "score": float(correct),
                "timestamp_sec": current_ts,
                "attempt_num": attempt_num,
                "is_repeat": attempt_num > 1,
            }
        )
    return rows


def simulate_interactions(
    students: list[dict],
    questions: list[dict],
    cfg: SynthGenConfig,
) -> pd.DataFrame:
    """Run IRT 2PL interaction simulation.

    Each student is randomly assigned a personal subset of skills
    (``cfg.min_student_skills`` … ``cfg.max_student_skills``) and only
    practises questions from those skills.  The selection is stored back onto
    each student dict as ``student["selected_skills"]``.

    Two-phase strategy that guarantees every student has a minimum interaction
    count, preventing the Pareto early-stop problem where only the first N
    students receive any data:

    - Phase 1: every student receives exactly ``min_per`` interactions.
    - Phase 2: any remaining budget is distributed proportionally to each
      student's Pareto-sampled ``seq_len``.

    Returns a DataFrame sorted by timestamp_sec.
    """
    rng = np.random.default_rng(cfg.random_seed + 2)

    skill_to_qs: dict[str, list[dict]] = {}
    for q in questions:
        for sid in q["skill_ids"]:
            skill_to_qs.setdefault(sid, []).append(q)

    all_skills = list(skill_to_qs.keys())
    if not all_skills:
        raise ValueError("No skills with questions found. Run question generation first.")

    sim_seconds = cfg.sim_days * 86_400
    base_ts = int(time.time()) - sim_seconds
    target = cfg.target_interactions
    n = len(students)

    # ── Phase 1: guaranteed minimum per student ───────────────────────────
    min_per = max(100, target // (2 * n))
    phase1_total = min_per * n

    # ── Phase 2: extra budget proportional to seq_len ─────────────────────
    extra_budget = max(0, target - phase1_total)
    seq_lens = np.array([s["seq_len"] for s in students], dtype=float)
    seq_lens_norm = seq_lens / seq_lens.sum()
    extra_per = (seq_lens_norm * extra_budget).astype(int)
    counts = np.maximum(min_per + extra_per, min_per)

    # ── Per-student skill selection ────────────────────────────────────────
    n_skills_min = min(cfg.min_student_skills, len(all_skills))
    n_skills_max = min(cfg.max_student_skills, len(all_skills))

    rows: list[dict] = []
    for student, n_itr in zip(students, counts, strict=False):
        n_selected = int(rng.integers(n_skills_min, n_skills_max + 1))
        student_skills = list(
            rng.choice(all_skills, size=n_selected, replace=False)
        )
        student["selected_skills"] = student_skills

        rows.extend(
            _simulate_student_interactions(
                student, questions, skill_to_qs, student_skills,
                int(n_itr), base_ts, sim_seconds, rng,
            )
        )

    df = pd.DataFrame(rows).sort_values("timestamp_sec").reset_index(drop=True)
    logger.info(
        "Simulated %d interactions across %d students "
        "(target=%d, skills per student: %d–%d)",
        len(df),
        df["student_id"].nunique(),
        target,
        n_skills_min,
        n_skills_max,
    )
    return df


def compute_mastery_ground_truth(
    students: list[dict],
    questions: list[dict],
    interactions_df: pd.DataFrame,
    cfg: SynthGenConfig,
) -> pd.DataFrame:
    """Compute IRT-derived mastery per (student, skill) with temporal decay.

    mastery = sigmoid(θ − mean_b_skill) × decay_factor

    Returns DataFrame with columns:
        student_id, skill_id, mastery, decay, status,
        attempt_count, correct_count, last_practice_ts
    """
    from scipy.special import expit as sigmoid  # local re-import for clarity

    DECAY_RATE = 0.01  # per day

    skill_to_qs = {}
    for q in questions:
        for sid in q["skill_ids"]:
            skill_to_qs.setdefault(sid, []).append(q)

    all_skills = list(skill_to_qs.keys())
    now_ts = int(interactions_df["timestamp_sec"].max()) if len(interactions_df) else 0

    # Last interaction timestamp per (student, skill)
    last_ts_map: dict[tuple, int] = {}
    attempt_map: dict[tuple, int] = {}
    correct_map: dict[tuple, int] = {}

    for _, row in interactions_df.iterrows():
        key = (row["student_id"], row["skill_id"])
        if key not in last_ts_map or row["timestamp_sec"] > last_ts_map[key]:
            last_ts_map[key] = int(row["timestamp_sec"])
        attempt_map[key] = attempt_map.get(key, 0) + 1
        correct_map[key] = correct_map.get(key, 0) + int(row["correct"])

    # Mean difficulty per skill
    skill_mean_b = {
        sid: float(np.mean([float(q["difficulty"]) for q in qs]))
        for sid, qs in skill_to_qs.items()
    }

    mastery_rows = []
    for student in students:
        uid = student["student_id"]
        theta = student["theta"]
        for skill_id in all_skills:
            raw_mastery = float(sigmoid(theta - skill_mean_b[skill_id]))
            key = (uid, skill_id)
            last_ts = last_ts_map.get(key, 0)
            delta_days = max(0.0, (now_ts - last_ts) / 86_400)
            decay = float(np.exp(-DECAY_RATE * delta_days))
            mastery = raw_mastery * decay
            att = attempt_map.get(key, 0)
            cor = correct_map.get(key, 0)
            if att == 0:
                status = "not_started"
            elif mastery >= 0.7:
                status = "mastered"
            elif mastery >= 0.4:
                status = "in_progress"
            else:
                status = "struggling"
            mastery_rows.append(
                {
                    "student_id": uid,
                    "skill_id": skill_id,
                    "mastery": round(mastery, 4),
                    "decay": round(decay, 4),
                    "status": status,
                    "attempt_count": att,
                    "correct_count": cor,
                    "last_practice_ts": last_ts if last_ts > 0 else None,
                }
            )

    return pd.DataFrame(mastery_rows)
