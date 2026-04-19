"""
ARCD Agent modules — reusable domain logic for tutoring agents.

Modules:
    learnfell     — Learning Fellow: PCODetector, FastReviewMode, MasterySync, EmotionalState
    adaex         — Adaptive Exercise: DifficultyCalculator, ExerciseBank, generation pipeline
    pathgen       — Path Generator: PrerequisiteFilter, ZPDFilter, ScoringEngine
    orchestrator  — Multi-agent LangGraph cycle (assess → pathgen → review → exercises)
"""

from .adaex import (
    DifficultyCalculator,
    DifficultyProfile,
    EvalResult,
    Exercise,
    ExerciseBank,
    ExercisePackage,
    RefinementLoop,
)
from .learnfell import (
    EmotionalState,
    FastReviewMode,
    MasterySync,
    PCODetector,
    PCOResult,
)
from .orchestrator import ARCDOrchestrator, OrchestratorState, build_orchestrator
from .pathgen import (
    PathGenConfig,
    PathGenerator,
    PrerequisiteFilter,
    ScoringEngine,
    ZPDFilter,
)

__all__ = [
    # learnfell
    "PCOResult",
    "PCODetector",
    "FastReviewMode",
    "MasterySync",
    "EmotionalState",
    # adaex
    "DifficultyProfile",
    "Exercise",
    "EvalResult",
    "ExercisePackage",
    "DifficultyCalculator",
    "ExerciseBank",
    "RefinementLoop",
    # pathgen
    "PathGenConfig",
    "PrerequisiteFilter",
    "ZPDFilter",
    "ScoringEngine",
    "PathGenerator",
    # orchestrator
    "OrchestratorState",
    "ARCDOrchestrator",
    "build_orchestrator",
]
