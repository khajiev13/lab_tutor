"""Evaluation helpers for AdaEx difficulty-selection strategies."""

from __future__ import annotations

import numpy as np

from app.modules.arcd_agent.agents.adaex import DifficultyCalculator


def _prereq_profile(A_pre: np.ndarray, n_skills: int) -> np.ndarray:
    if A_pre.size == 0:
        return np.zeros(n_skills, dtype=np.float32)
    profile = np.asarray(A_pre, dtype=np.float32)
    if profile.ndim != 2:
        return np.zeros(n_skills, dtype=np.float32)
    return np.sum(profile[:n_skills, :n_skills] > 0, axis=0).astype(np.float32)


def _complexity_profile(
    n_skills: int,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
) -> np.ndarray:
    complexity = np.ones(n_skills, dtype=np.float32)
    if len(n_concepts_arr) >= n_skills:
        complexity = np.asarray(n_concepts_arr[:n_skills], dtype=np.float32)
    return np.clip(complexity / max(max_concepts, 1), 0.0, 1.0)


def _expected_difficulty(
    mastery_vec: np.ndarray,
    A_pre: np.ndarray,
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
) -> np.ndarray:
    mastery = np.clip(np.asarray(mastery_vec, dtype=np.float32), 0.0, 1.0)
    n_skills = mastery.shape[0]
    prereq_depth = _prereq_profile(A_pre, n_skills)
    prereq_norm = prereq_depth / max(float(prereq_depth.max(initial=0.0)), 1.0)
    complexity = _complexity_profile(n_skills, n_concepts_arr, max_concepts)
    return np.clip(
        calc.alpha * (1.0 - mastery)
        + calc.beta * prereq_norm
        + calc.gamma * complexity,
        0.0,
        1.0,
    )


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if x.size == 0 or y.size == 0:
        return 0.0
    if np.allclose(x, x[0]) or np.allclose(y, y[0]):
        return 0.0
    corr = np.corrcoef(x, y)[0, 1]
    return float(0.0 if np.isnan(corr) else corr)


def adaex_difficulty(
    mastery_vec: np.ndarray | list[float],
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Return AdaEx target difficulty for every skill."""
    mastery = np.clip(np.asarray(mastery_vec, dtype=np.float32), 0.0, 1.0)
    n_skills = mastery.shape[0]
    concept_counts = np.ones(n_skills, dtype=np.int32)
    if len(n_concepts_arr) >= n_skills:
        concept_counts = np.asarray(n_concepts_arr[:n_skills], dtype=np.int32)

    targets = np.zeros(n_skills, dtype=np.float32)
    for skill_id in range(n_skills):
        profile = calc.compute(
            skill_id=skill_id,
            skill_name=f"Skill {skill_id}",
            mastery=float(mastery[skill_id]),
            n_concepts=int(concept_counts[skill_id]),
            max_concepts=max_concepts,
        )
        targets[skill_id] = profile.target_d
    return targets


def fixed_medium_difficulty(
    mastery_vec: np.ndarray | list[float],
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Baseline strategy that assigns a constant medium difficulty."""
    mastery = np.asarray(mastery_vec, dtype=np.float32)
    return np.full(mastery.shape[0], 0.5, dtype=np.float32)


def random_difficulty(
    mastery_vec: np.ndarray | list[float],
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Baseline strategy that samples difficulty uniformly at random."""
    mastery = np.asarray(mastery_vec, dtype=np.float32)
    generator = rng or np.random.default_rng()
    return generator.uniform(0.0, 1.0, size=mastery.shape[0]).astype(np.float32)


def evaluate_difficulty_strategy(
    strategy_fn,
    mastery_arr: np.ndarray,
    decay_arr: np.ndarray,
    A_pre: np.ndarray,
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray | list[int],
    max_concepts: int,
    rng: np.random.Generator,
    use_calc: bool = False,
) -> dict[str, float]:
    """Score a difficulty strategy against AdaEx's intended target profile."""
    mastery = np.clip(np.asarray(mastery_arr, dtype=np.float32), 0.0, 1.0)
    if mastery.ndim != 2:
        raise ValueError("mastery_arr must have shape (n_students, n_skills)")

    assigned: list[np.ndarray] = []
    expected: list[np.ndarray] = []

    for mastery_vec in mastery:
        assigned_vec = np.clip(
            np.asarray(
                strategy_fn(mastery_vec, calc, n_concepts_arr, max_concepts, rng),
                dtype=np.float32,
            ),
            0.0,
            1.0,
        )
        if assigned_vec.shape[0] != mastery_vec.shape[0]:
            raise ValueError("strategy_fn returned a vector with the wrong shape")
        assigned.append(assigned_vec)
        expected.append(
            _expected_difficulty(
                mastery_vec, np.asarray(A_pre), calc, n_concepts_arr, max_concepts
            )
        )

    assigned_arr = np.stack(assigned, axis=0)
    expected_arr = np.stack(expected, axis=0)
    abs_gap = np.abs(assigned_arr - expected_arr)

    prereq_depth = _prereq_profile(np.asarray(A_pre), mastery.shape[1])
    skill_mean_difficulty = assigned_arr.mean(axis=0)
    zpd_target_gap = np.abs(np.clip(assigned_arr + mastery - 1.0, -1.0, 1.0))

    return {
        "zpd_alignment": float(1.0 - np.mean(zpd_target_gap)),
        "calibration_error": float(np.mean(abs_gap)),
        "prereq_correlation": _safe_corr(skill_mean_difficulty, prereq_depth),
        "cross_student_variance": float(np.mean(np.var(assigned_arr, axis=0))),
        "mean_difficulty": float(np.mean(assigned_arr)),
    }
