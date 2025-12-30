from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ConceptMerge(BaseModel):
    """Proposed merge between two similar concepts."""

    concept_a: str = Field(description="First concept name (as stored in Neo4j)")
    concept_b: str = Field(description="Second concept name (as stored in Neo4j)")
    canonical: str = Field(description="Canonical name after merge")
    variants: list[str] = Field(description="All variant names")
    r: str = Field(description="Reasoning for merge (max ~80 chars)")


class WeakMerge(BaseModel):
    """A weak/incorrect merge proposal."""

    concept_a: str
    concept_b: str
    canonical: str
    r: str = Field(description="Original reasoning")
    w: str = Field(description="Why it's weak (max ~80 chars)")


class MergeValidationFeedback(BaseModel):
    weak_merges: list[WeakMerge] = Field(default_factory=list)
    validation_notes: str = Field(default="")
    total_validated: int = Field(default=0)
    weak_count: int = Field(default=0)


class MergeBatch(BaseModel):
    merges: list[ConceptMerge] = Field(default_factory=list)


class MergeCluster(BaseModel):
    """A merge cluster representing one canonical concept and its variants."""

    canonical: str
    variants: list[str] = Field(default_factory=list)
    r: str = Field(default="", description="Concise reasoning (max ~120 chars)")


class MergeClustersBatch(BaseModel):
    clusters: list[MergeCluster] = Field(default_factory=list)


class ConceptRelationship(BaseModel):
    """Relationship between two concepts (optional for normalization UI)."""

    s: str = Field(description="Source concept")
    t: str = Field(description="Target concept")
    rel: str = Field(description="Relationship type (string enum by config)")
    r: str = Field(description="Concise explanation (max ~80 chars)")


class RelationshipBatch(BaseModel):
    relationships: list[ConceptRelationship] = Field(default_factory=list)


class WeakRelationship(BaseModel):
    s: str
    t: str
    rel: str
    r: str = Field(description="Original reasoning from generation")
    w: str = Field(description="Why it's weak (max ~80 chars)")


class ValidationFeedback(BaseModel):
    weak_relationships: list[WeakRelationship] = Field(default_factory=list)
    validation_notes: str = Field(default="")
    total_validated: int = Field(default=0)
    weak_count: int = Field(default=0)


class NormalizationStreamEvent(BaseModel):
    type: Literal["update", "complete", "error"]
    iteration: int = Field(ge=0)
    phase: Literal["generation", "validation", "complete"]
    agent_activity: str = Field(default="")

    # Human-in-the-loop review (optional, only populated at completion)
    requires_review: bool = Field(default=False)
    review_id: str | None = Field(default=None)

    # Bank of concepts
    concepts_count: int = Field(default=0, ge=0)

    # Deltas for UI
    merges_found: int = Field(default=0, ge=0)
    relationships_found: int = Field(default=0, ge=0)
    latest_merges: list[ConceptMerge] = Field(default_factory=list)
    latest_relationships: list[ConceptRelationship] = Field(default_factory=list)

    # Totals (accumulated)
    total_merges: int = Field(default=0, ge=0)
    total_relationships: int = Field(default=0, ge=0)


class MergeProposalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MergeProposal(BaseModel):
    id: str
    concept_a: str
    concept_b: str
    canonical: str
    variants: list[str]
    r: str = Field(description="Reasoning for merge (max ~80 chars)")

    decision: MergeProposalDecision = Field(default=MergeProposalDecision.PENDING)
    comment: str = Field(default="")
    applied: bool = Field(default=False)


class NormalizationReview(BaseModel):
    id: str
    course_id: int
    status: Literal["pending", "applied"] = Field(default="pending")
    created_by_user_id: int | None = Field(default=None)
    created_at: str | None = Field(default=None)
    proposals: list[MergeProposal] = Field(default_factory=list)

    # Evidence: concept name -> definitions seen in course documents
    definitions: dict[str, list[str]] = Field(default_factory=dict)


class MergeDecisionUpdate(BaseModel):
    proposal_id: str
    decision: MergeProposalDecision
    comment: str | None = Field(default=None)


class UpdateMergeDecisionsRequest(BaseModel):
    decisions: list[MergeDecisionUpdate] = Field(default_factory=list)


class ApplyReviewResponse(BaseModel):
    review_id: str
    total_approved: int
    applied: int
    skipped: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class UpdateMergeDecisionsResponse(BaseModel):
    review_id: str
    updated: int

