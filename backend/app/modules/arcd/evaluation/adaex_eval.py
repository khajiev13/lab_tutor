"""
src/evaluation/adaex_eval.py — AdaEx difficulty calibration metrics and baselines.

Extracted from scripts/eval_adaex.py so that the evaluation logic is
importable as a library.

Contains:
    DifficultyCalculator          — Standalone (no-LLM) difficulty target computer
    simulated_p_correct           — IRT-like correct-response probability model
    ideal_zpd_range               — Ideal difficulty window for a student
    adaex_difficulty              — AdaEx strategy wrapper
    fixed_medium_difficulty       — Baseline: always 0.50
    inverse_mastery_difficulty    — Baseline: 1 - mastery
    random_difficulty             — Baseline: uniform random
    evaluate_difficulty_strategy  — Aggregate multi-metric evaluation
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

# ── Difficulty calculator ─────────────────────────────────────────────


class DifficultyCalculator:
    """Standalone difficulty target calculator (no LLM dependency).

    Implements the AdaEx formula:
        d*(u, s) = α·(1 - m_u,s) + β·(prereq_depth_s / max_depth)
                   + γ·(n_concepts_s / max_concepts)

    Args:
        alpha:   Mastery component weight (default 0.55).
        beta:    Prerequisite depth weight (default 0.20).
        gamma:   Concept complexity weight (default 0.25).
        A_skill: Optional prerequisite adjacency matrix used to compute
                 per-skill prerequisite depth.
    """

    BANDS: list[tuple[float, str]] = [
        (0.30, "easy"),
        (0.55, "medium"),
        (0.80, "hard"),
        (1.01, "challenge"),
    ]

    def __init__(
        self, alpha: float = 0.55, beta: float = 0.20, gamma: float = 0.25, A_skill=None
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self._prereq_counts: dict[int, int] = {}
        self._p_max = 1
        if A_skill is not None:
            n = A_skill.shape[0]
            for s in range(n):
                self._prereq_counts[s] = int(np.sum(A_skill[:, s] > 0))
            self._p_max = max(1, max(self._prereq_counts.values(), default=1))

    def compute(
        self, skill_id: int, mastery: float, n_concepts: int = 1, max_concepts: int = 20
    ) -> float:
        """Compute the target difficulty d*(u, s) ∈ [0, 1].

        Args:
            skill_id:     Integer skill index.
            mastery:      Current student mastery for this skill (0–1).
            n_concepts:   Number of concepts covered by the exercise.
            max_concepts: Maximum concepts seen in this dataset (for normalisation).

        Returns:
            Target difficulty in [0.0, 1.0].
        """
        inv_mastery = 1.0 - mastery
        prereq_depth = self._prereq_counts.get(skill_id, 0)
        prereq_norm = prereq_depth / self._p_max
        complexity = min(1.0, n_concepts / max(1, max_concepts))
        d_star = (
            self.alpha * inv_mastery + self.beta * prereq_norm + self.gamma * complexity
        )
        return float(max(0.0, min(1.0, d_star)))

    @staticmethod
    def band_label(d: float) -> str:
        """Return the difficulty band label for value d."""
        for threshold, label in DifficultyCalculator.BANDS:
            if d < threshold:
                return label
        return "challenge"


# ── IRT-like simulation ───────────────────────────────────────────────


def simulated_p_correct(
    mastery: float,
    difficulty: float,
    noise_std: float = 0.05,
    rng: np.random.Generator | None = None,
) -> float:
    """Simulate P(correct) using an IRT-like sigmoid model.

    P(correct) = σ(a · (mastery − difficulty) + ε)
    where a = 4.0 (discrimination) and ε ~ N(0, noise_std).

    Args:
        mastery:    Student mastery level (0–1).
        difficulty: Exercise difficulty (0–1).
        noise_std:  Standard deviation of Gaussian noise on the logit.
        rng:        Optional RNG for reproducibility.

    Returns:
        Simulated probability of correct response (0–1).
    """
    if rng is None:
        rng = np.random.default_rng()
    a = 4.0
    noise = rng.normal(0, noise_std)
    logit = a * (mastery - difficulty) + noise
    return float(1.0 / (1.0 + np.exp(-logit)))


def ideal_zpd_range(mastery: float) -> tuple[float, float]:
    """Compute the ideal difficulty range for a student's current mastery.

    Based on Vygotsky's ZPD: difficulty should be slightly above mastery
    but not so far that P(correct) drops below ~0.30.

    Returns:
        ``(lo, hi)`` tuple of ideal difficulty bounds.
    """
    lo = max(0.0, mastery - 0.15)
    hi = min(1.0, mastery + 0.30)
    return lo, hi


# ── Strategy functions ────────────────────────────────────────────────


def adaex_difficulty(
    calc: DifficultyCalculator,
    skill_id: int,
    mastery: float,
    n_concepts: int = 1,
    max_concepts: int = 20,
) -> float:
    """AdaEx target difficulty — delegates to DifficultyCalculator.compute."""
    return calc.compute(skill_id, mastery, n_concepts, max_concepts)


def fixed_medium_difficulty(skill_id: int, mastery: float, **kwargs) -> float:
    """Baseline: always assign difficulty 0.50 regardless of mastery."""
    return 0.50


def inverse_mastery_difficulty(skill_id: int, mastery: float, **kwargs) -> float:
    """Baseline: d = 1 − mastery (no prerequisite or complexity adjustment)."""
    return 1.0 - mastery


def random_difficulty(
    skill_id: int, mastery: float, rng: np.random.Generator | None = None, **kwargs
) -> float:
    """Baseline: uniform random difficulty in [0, 1]."""
    if rng is None:
        rng = np.random.default_rng()
    return float(rng.uniform(0, 1))


# ── Aggregate evaluation ──────────────────────────────────────────────


def evaluate_difficulty_strategy(
    strategy_fn: Callable,
    mastery_arr: np.ndarray,
    decay_arr: np.ndarray,
    A: np.ndarray,
    calc: DifficultyCalculator,
    n_concepts_arr: np.ndarray,
    max_concepts: int,
    rng: np.random.Generator,
    **kwargs,
) -> dict:
    """Evaluate a difficulty assignment strategy across N students and S skills.

    Computes four metrics:
        zpd_alignment:        Fraction of (student, skill) pairs where d* ∈ ideal ZPD range.
        calibration_error:    Mean |P(correct | d*) − 0.65| (ideal P(correct) target).
        prereq_correlation:   Spearman-like correlation between d* and prereq chain depth.
        cross_student_variance: Mean per-student σ of difficulty assignments.

    Args:
        strategy_fn:   Callable accepting ``(calc, skill_id, mastery, n_concepts, max_concepts)``
                       for AdaEx, or ``(skill_id, mastery, **kwargs)`` for baselines.
        mastery_arr:   (N, S) array of student mastery values.
        decay_arr:     (N, S) array of retention decay values (not used by all strategies).
        A:             (S, S) prerequisite adjacency matrix.
        calc:          DifficultyCalculator instance.
        n_concepts_arr: (S,) array of concept counts per skill.
        max_concepts:  Maximum concept count for normalisation.
        rng:           NumPy RNG for reproducible simulation.
        **kwargs:      Extra arguments forwarded to strategy_fn.

    Returns:
        Dict with keys ``zpd_alignment``, ``calibration_error``,
        ``prereq_correlation``, ``cross_student_variance``.
    """
    N, S = mastery_arr.shape
    parents = {s: set(np.where(A[:, s] > 0)[0]) for s in range(S)}

    zpd_aligned: list[float] = []
    calibration_errors: list[float] = []
    prereq_correlations: list[float] = []
    student_variances: list[float] = []

    use_calc = kwargs.get("use_calc", False)

    for i in range(N):
        mastery = mastery_arr[i]
        difficulties: list[float] = []

        for s in range(S):
            if use_calc:
                d = strategy_fn(
                    calc, s, float(mastery[s]), int(n_concepts_arr[s]), max_concepts
                )
            elif (
                "rng"
                in getattr(
                    strategy_fn, "__code__", type("", (), {"co_varnames": ()})()
                ).co_varnames
            ):
                d = strategy_fn(s, float(mastery[s]), rng=rng)
            else:
                d = strategy_fn(s, float(mastery[s]))
            difficulties.append(d)

            lo, hi = ideal_zpd_range(float(mastery[s]))
            zpd_aligned.append(1.0 if lo <= d <= hi else 0.0)

            p_correct = simulated_p_correct(float(mastery[s]), d, rng=rng)
            calibration_errors.append(abs(p_correct - 0.65))

        d_arr = np.array(difficulties)
        prereq_depths = np.array([len(parents.get(s, set())) for s in range(S)])
        if np.std(d_arr) > 0 and np.std(prereq_depths) > 0:
            corr = np.corrcoef(d_arr, prereq_depths)[0, 1]
            prereq_correlations.append(float(corr) if not np.isnan(corr) else 0.0)

        student_variances.append(float(np.std(d_arr)))

    return {
        "zpd_alignment": float(np.mean(zpd_aligned)),
        "calibration_error": float(np.mean(calibration_errors)),
        "prereq_correlation": float(np.mean(prereq_correlations))
        if prereq_correlations
        else 0.0,
        "cross_student_variance": float(np.mean(student_variances)),
    }
