"""Evaluation helpers for PathGen path-selection strategies."""

from __future__ import annotations

import numpy as np

from app.modules.arcd_agent.agents.pathgen import PathGenConfig, PathGenerator


def _normalize_path(path: list[int] | tuple[int, ...] | np.ndarray) -> list[int]:
    seen: set[int] = set()
    normalized: list[int] = []
    for raw in path:
        skill_id = int(raw)
        if skill_id in seen:
            continue
        seen.add(skill_id)
        normalized.append(skill_id)
    return normalized


def _zpd_score(mastery: float, zpd_lo: float = 0.40, zpd_hi: float = 0.90) -> float:
    if zpd_lo <= mastery <= zpd_hi:
        return 1.0
    distance = zpd_lo - mastery if mastery < zpd_lo else mastery - zpd_hi
    return float(max(0.0, 1.0 - distance / 0.5))


def _prereq_strength(
    skill_id: int,
    mastery_vec: np.ndarray,
    A_pre: np.ndarray,
    threshold: float = 0.60,
) -> float:
    prereqs = np.where(A_pre[: mastery_vec.shape[0], skill_id] > 0)[0]
    if len(prereqs) == 0:
        return 1.0
    satisfied = sum(1 for prereq_id in prereqs if mastery_vec[prereq_id] >= threshold)
    return float(satisfied / len(prereqs))


def _unlock_potential(skill_id: int, mastery_vec: np.ndarray, A_pre: np.ndarray) -> float:
    downstream = np.where(A_pre[skill_id, : mastery_vec.shape[0]] > 0)[0]
    if len(downstream) == 0:
        return 0.0
    return float(np.sum(mastery_vec[downstream] < 0.60))


def pathgen_v2(
    mastery_vec: np.ndarray | list[float],
    decay_vec: np.ndarray | list[float],
    A_pre: np.ndarray,
    K: int = 8,
) -> list[int]:
    """Generate a PathGen-ranked list of skill IDs."""
    mastery = np.clip(np.asarray(mastery_vec, dtype=np.float32), 0.0, 1.0)
    decay = np.clip(np.asarray(decay_vec, dtype=np.float32), 0.0, 1.0)
    generator = PathGenerator(
        config=PathGenConfig(path_length=max(K, 0)),
        A_pre=np.asarray(A_pre, dtype=np.float32),
        decay_vector=decay.tolist(),
    )
    path = generator.generate(mastery=mastery.tolist())
    return [int(step["skill_id"]) for step in path.get("steps", [])]


def random_path(
    mastery_vec: np.ndarray | list[float],
    decay_vec: np.ndarray | list[float],
    A_pre: np.ndarray,
    K: int = 8,
    rng: np.random.Generator | None = None,
) -> list[int]:
    """Sample a random list of unique skill IDs."""
    mastery = np.asarray(mastery_vec, dtype=np.float32)
    if mastery.size == 0 or K <= 0:
        return []
    generator = rng or np.random.default_rng()
    sample_size = min(K, mastery.shape[0])
    return generator.choice(mastery.shape[0], size=sample_size, replace=False).tolist()


def evaluate_path(
    path: list[int] | tuple[int, ...] | np.ndarray,
    mastery_vec: np.ndarray | list[float],
    decay_vec: np.ndarray | list[float],
    A_pre: np.ndarray,
    rng: np.random.Generator | None = None,
) -> dict[str, float]:
    """Score a path on ZPD fit, prerequisite quality, gain, and unlock potential."""
    mastery = np.clip(np.asarray(mastery_vec, dtype=np.float32), 0.0, 1.0)
    decay = np.clip(np.asarray(decay_vec, dtype=np.float32), 0.0, 1.0)
    prereq = np.asarray(A_pre, dtype=np.float32)
    skill_path = [sid for sid in _normalize_path(path) if 0 <= sid < mastery.shape[0]]

    if not skill_path:
        return {
            "zpd_align": 0.0,
            "prereq_sat": 0.0,
            "proj_gain": 0.0,
            "decay_cov": 0.0,
            "unlock_pot": 0.0,
        }

    zpd_scores: list[float] = []
    prereq_scores: list[float] = []
    gain_scores: list[float] = []
    decay_scores: list[float] = []
    unlock_scores: list[float] = []

    for skill_id in skill_path:
        zpd = _zpd_score(float(mastery[skill_id]))
        prereq_strength = _prereq_strength(skill_id, mastery, prereq)
        decay_urgency = float(1.0 - decay[skill_id]) if skill_id < decay.shape[0] else 0.0
        gain = zpd * (0.5 + 0.5 * prereq_strength) * (0.25 + 0.75 * (1.0 - mastery[skill_id]))

        zpd_scores.append(zpd)
        prereq_scores.append(prereq_strength)
        gain_scores.append(float(gain))
        decay_scores.append(decay_urgency)
        unlock_scores.append(_unlock_potential(skill_id, mastery, prereq))

    return {
        "zpd_align": float(np.mean(zpd_scores)),
        "prereq_sat": float(np.mean(prereq_scores)),
        "proj_gain": float(np.mean(gain_scores)),
        "decay_cov": float(np.mean(decay_scores)),
        "unlock_pot": float(np.sum(unlock_scores)),
    }
