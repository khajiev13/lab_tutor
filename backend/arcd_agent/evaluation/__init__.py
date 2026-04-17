"""
src/evaluation — Reusable evaluation utilities for ARCD components.

Modules:
    pathgen_eval  — PathGen algorithm variants and controlled simulation metrics
    adaex_eval    — AdaEx difficulty calibration metrics and baselines

Usage::

    from src.evaluation.pathgen_eval import pathgen_v2, evaluate_path
    from src.evaluation.adaex_eval import DifficultyCalculator, evaluate_difficulty_strategy
"""

from arcd_agent.evaluation.adaex_eval import (
    DifficultyCalculator as AdaExDifficultyCalculator,
)
from arcd_agent.evaluation.adaex_eval import (
    adaex_difficulty,
    evaluate_difficulty_strategy,
    fixed_medium_difficulty,
    ideal_zpd_range,
    inverse_mastery_difficulty,
    random_difficulty,
    simulated_p_correct,
)
from arcd_agent.evaluation.pathgen_eval import (
    evaluate_path,
    lowest_first_path,
    pathgen,
    pathgen_v2,
    pathgen_v2_with_explanations,
    random_path,
    sequential_path,
    topological_order,
)

__all__ = [
    # pathgen
    "topological_order",
    "pathgen",
    "pathgen_v2",
    "pathgen_v2_with_explanations",
    "random_path",
    "sequential_path",
    "lowest_first_path",
    "evaluate_path",
    # adaex
    "AdaExDifficultyCalculator",
    "simulated_p_correct",
    "ideal_zpd_range",
    "adaex_difficulty",
    "fixed_medium_difficulty",
    "inverse_mastery_difficulty",
    "random_difficulty",
    "evaluate_difficulty_strategy",
]
