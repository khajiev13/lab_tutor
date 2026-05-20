from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DupeGroupVerdict(BaseModel):
    are_duplicates: bool
    canonical_name: str | None = None
    skill_names_to_merge: list[str] = Field(default_factory=list)
    reasoning: str


class PrerequisiteEdge(BaseModel):
    prerequisite_skill: str
    dependent_skill: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str


class ClusterPrerequisiteResult(BaseModel):
    edges: list[PrerequisiteEdge]


class PrerequisiteReviewStatus(StrEnum):
    NOT_STARTED = "not_started"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    STALE = "stale"


class PrerequisiteDraftEdge(BaseModel):
    prerequisite_name: str
    dependent_name: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    source: Literal["ai", "teacher"] = "ai"


class PrerequisiteSkillRead(BaseModel):
    name: str
    source: str
    chapter_title: str | None = None


class PrerequisiteValidationRead(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    cycle_path: list[str] = Field(default_factory=list)


class PrerequisiteReviewMetadata(BaseModel):
    edge_count: int
    generated_edge_count: int
    added_edge_count: int
    removed_edge_count: int
    isolated_skill_count: int
    last_generated_at: datetime | None = None
    last_invalidated_at: datetime | None = None
    approved_at: datetime | None = None


class PrerequisiteReviewRead(BaseModel):
    course_id: int
    status: PrerequisiteReviewStatus
    is_rebuilding: bool
    skills: list[PrerequisiteSkillRead]
    draft_edges: list[PrerequisiteDraftEdge]
    isolated_skills: list[str]
    validation: PrerequisiteValidationRead
    metadata: PrerequisiteReviewMetadata


class PrerequisiteReviewUpdate(BaseModel):
    draft_edges: list[PrerequisiteDraftEdge]
    isolated_skills_viewed: bool = False
