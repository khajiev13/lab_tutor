"""Versioned market skill review boundary contracts."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

JobSource = Literal["indeed", "linkedin", "headhunter"]
EvidenceSource = Literal["jobs", "onet"]


class SourceOutcome(BaseModel):
    status: Literal["idle", "loading", "success", "empty", "partial", "error"] = "idle"
    received_count: int = 0
    usable_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class SkillCategory(BaseModel):
    category_id: str
    label: str


class SkillCandidate(BaseModel):
    candidate_id: UUID
    display_name: str
    category_id: str
    original_labels: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    job_metrics: dict[str, Any] = Field(default_factory=dict)
    onet_associations: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_reasons: list[str] = Field(default_factory=list)
    posting_support: Literal["supported", "missing"] = "missing"
    qualifying_posting_links: list[str] = Field(default_factory=list)


class RecommendationChange(BaseModel):
    candidate_id: UUID
    action: Literal["add", "remove"]
    reason: str


class RecommendationProposal(BaseModel):
    id: UUID
    candidate_revision: int
    base_selection_revision: int
    changes: list[RecommendationChange]


class SkillReview(BaseModel):
    run_id: UUID | None = None
    candidate_revision: int = 0
    selection_revision: int = 0
    categories: list[SkillCategory] = Field(default_factory=list)
    candidates: list[SkillCandidate] = Field(default_factory=list)
    selected_candidate_ids: list[UUID] = Field(default_factory=list)
    excluded_candidate_ids: list[UUID] = Field(default_factory=list)
    recommendations: list[RecommendationProposal] = Field(default_factory=list)
    source_outcomes: dict[str, SourceOutcome] = Field(default_factory=dict)
    extraction_coverage: dict[str, Any] = Field(default_factory=dict)
    integration_review: dict[str, Any] | None = None
    publication_revision: int = 0
    approved_references: list[dict[str, Any]] = Field(default_factory=list)


class SkillReviewDraft(BaseModel):
    run_id: UUID
    expected_candidate_revision: int = Field(ge=0)
    expected_selection_revision: int = Field(ge=0)
    selected_candidate_ids: list[UUID]
    excluded_candidate_ids: list[UUID]
