"""Shared recommendation DTOs.

Defines the output schema for all recommendation agents.
The plugin architecture allows multiple agents (book_gap_analysis,
pedagogy, assessment) to each produce a ``RecommendationReport`` —
all aggregated into a single ``RecommendationResponse``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

# ── Enums ─────────────────────────────────────────────────────


class RecommendationCategory(StrEnum):
    MISSING_CONCEPT = "missing_concept"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    SUGGESTED_SKILL = "suggested_skill"
    STRUCTURAL = "structural"


class RecommendationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Recommendation items ──────────────────────────────────────


class BookEvidence(BaseModel):
    """Where in the book this recommendation originates."""

    chapter_title: str | None = None
    section_title: str | None = None
    text_evidence: str | None = None


class RecommendationItem(BaseModel):
    """A single actionable recommendation for the teacher."""

    category: RecommendationCategory = Field(
        default=RecommendationCategory.MISSING_CONCEPT,
        description="Category of the recommendation",
    )
    priority: RecommendationPriority
    title: str = Field(description="Short headline for the recommendation")
    description: str = Field(description="Detailed explanation of the gap")
    rationale: str = Field(
        default="",
        description="Why this matters for the course",
    )
    book_evidence: BookEvidence | None = Field(
        default=None,
        description="Source location in the book",
    )
    affected_teacher_document: str | None = Field(
        default=None,
        description="Filename or topic of the teacher document most affected",
    )
    suggested_action: str = Field(
        default="",
        description="Concrete next step the teacher should take",
    )

    @field_validator("priority", mode="before")
    @classmethod
    def _normalise_priority(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v

    @field_validator("category", mode="before")
    @classmethod
    def _normalise_category(cls, v: str) -> str:
        return v.lower() if isinstance(v, str) else v


# ── Report / Response wrappers ────────────────────────────────


class RecommendationReport(BaseModel):
    """Output of a single recommendation agent."""

    source: str = Field(
        description="Agent that produced this report, e.g. 'book_gap_analysis'"
    )
    course_id: int
    book_title: str
    summary: str = Field(description="Executive summary of findings")
    recommendations: list[RecommendationItem] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    """Top-level API response wrapping one or more agent reports."""

    reports: list[RecommendationReport] = Field(default_factory=list)
