from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from .schemas import ConceptMerge, MergeCluster, MergeValidationFeedback


def make_merge_key(concept_a: str, concept_b: str) -> str:
    """Deterministic string key for a concept pair (order-insensitive)."""
    a, b = sorted([concept_a, concept_b])
    return f"{a}|||{b}"


def parse_merge_key(key: str) -> tuple[str, str]:
    a, b = key.split("|||", 1)
    return (a, b)


class IterationSnapshot(BaseModel):
    iteration_number: int = Field(description="Iteration number (0-indexed)")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="ISO timestamp of this iteration",
    )
    valid_merge_count: int = Field(description="Valid merges in this iteration")
    weak_merge_count: int = Field(description="Weak merges in this iteration")
    total_merges: int = Field(description="Total accumulated valid merges")
    feedback: MergeValidationFeedback | None = Field(default=None)


class ConvergenceMetrics(BaseModel):
    # Merge metrics
    merge_count_trend: list[int] = Field(default_factory=list)
    valid_merge_trend: list[int] = Field(default_factory=list)
    weak_merge_trend: list[int] = Field(default_factory=list)
    total_merges_trend: list[int] = Field(default_factory=list)

    # New-unique discovery trends (used for convergence)
    new_unique_merges_trend: list[int] = Field(default_factory=list)

    merges_converged: bool = Field(default=False)
    is_converged: bool = Field(default=False)
    convergence_reason: str = Field(default="")

    def update_merge_trends(
        self,
        *,
        merge_count: int,
        valid_merge_count: int,
        weak_merge_count: int,
        total_merges: int,
        new_unique_merges: int = 0,
    ) -> None:
        self.merge_count_trend.append(merge_count)
        self.valid_merge_trend.append(valid_merge_count)
        self.weak_merge_trend.append(weak_merge_count)
        self.total_merges_trend.append(total_merges)
        self.new_unique_merges_trend.append(new_unique_merges)


class WorkflowConfiguration(BaseModel):
    max_iterations: int = Field(default=10, ge=1, le=20)
    enable_history_tracking: bool = Field(default=True)
    verbose_logging: bool = Field(default=True)


class ConceptNormalizationState(TypedDict):
    # Core data
    concepts: list[dict[str, str]]

    # Merge tracking
    all_merges: dict[str, ConceptMerge]
    weak_merges: dict[str, str]
    new_merge_batch: list[ConceptMerge]
    current_merge_feedback: MergeValidationFeedback | None

    # History and metrics
    iteration_history: list[IterationSnapshot]
    convergence_metrics: ConvergenceMetrics

    # Config
    iteration_count: int
    max_iterations: int

    # Metadata
    processing_start_time: float
    workflow_metadata: dict[str, Any]


class OrchestratorWorkItem(TypedDict):
    batch_id: str
    concepts: list[str]


class ConceptNormalizationOrchestratorState(TypedDict):
    # Core data
    concepts: list[dict[str, str]]
    course_id: int

    # Orchestrator/worker
    work_items: list[OrchestratorWorkItem]
    raw_clusters: list[MergeCluster]
    clusters: list[MergeCluster]

    # Metadata
    processing_start_time: float
    workflow_metadata: dict[str, Any]
