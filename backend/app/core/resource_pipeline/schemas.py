"""Shared schemas for the resource discovery pipeline (TRA + VCE).

These are domain objects used by both the textual resource analyst and
visual content evaluator pipelines. Route-specific schemas live in their
respective modules.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

# ── Skill profile (loaded from Neo4j) ────────────────────────


@dataclass
class SkillProfile:
    """All evidence we have about a skill — used for query generation and evaluation."""

    name: str
    skill_type: str  # "book" or "market"
    description: str = ""
    chapter_title: str = ""
    chapter_summary: str = ""
    chapter_index: int = 0
    concepts: list[dict] = field(
        default_factory=list
    )  # [{name, definition, embedding?}]
    category: str = ""
    demand_pct: float = 0.0
    priority: str = ""
    status: str = ""
    job_evidence: list[str] = field(default_factory=list)
    course_level: str = "bachelor"

    def build_profile_text(self) -> str:
        """Skill-centric evidence for embedding/query generation."""
        parts = [f"Skill: {self.name}"]
        if self.description:
            parts.append(f"Description: {self.description}")
        if self.category:
            parts.append(f"Category: {self.category}")
        if self.concepts:
            concept_lines = [
                f"  - {c['name']}: {c.get('definition', '')}"
                for c in self.concepts[:10]
            ]
            parts.append("Concepts:\n" + "\n".join(concept_lines))
        if self.job_evidence:
            parts.append(
                "Job Evidence (snippets):\n"
                + "\n".join(f"  - {e[:200]}" for e in self.job_evidence[:3])
            )
        parts.append(f"Course Level: {self.course_level}")
        return "\n".join(parts)


# ── Search candidate ─────────────────────────────────────────


@dataclass
class CandidateResource:
    """A search result candidate before scoring."""

    title: str
    url: str
    snippet: str
    source_engine: str  # tavily, duckduckgo, serper
    domain: str = ""
    video_id: str = ""  # YouTube only

    def __post_init__(self):
        if not self.domain:
            self.domain = urllib.parse.urlparse(self.url).netloc.replace("www.", "")
        if not self.video_id and "youtube.com" in self.domain:
            parsed = urllib.parse.urlparse(self.url)
            qs = urllib.parse.parse_qs(parsed.query)
            self.video_id = qs.get("v", [""])[0]


# ── LLM scoring output ───────────────────────────────────────


class ResourceScore(BaseModel):
    """LLM evaluation of a single resource candidate."""

    model_config = ConfigDict(populate_by_name=True)

    recency_score: float = Field(
        ..., ge=0, le=1, validation_alias=AliasChoices("recency_score", "recency")
    )
    recency_reasoning: str = Field(
        default="", validation_alias=AliasChoices("recency_reasoning", "recency_reason")
    )
    estimated_year: int | None = Field(None)

    concept_coverage_score: float = Field(
        ...,
        ge=0,
        le=1,
        validation_alias=AliasChoices("concept_coverage_score", "concept_coverage"),
    )
    concept_coverage_reasoning: str = Field(default="")

    pedagogy_score: float = Field(
        ..., ge=0, le=1, validation_alias=AliasChoices("pedagogy_score", "pedagogy")
    )
    pedagogy_reasoning: str = Field(default="")

    depth_score: float = Field(
        ..., ge=0, le=1, validation_alias=AliasChoices("depth_score", "depth")
    )
    depth_reasoning: str = Field(default="")

    # 5th criterion — agent-specific (source_quality for TRA, production_quality for VCE)
    extra_score: float = Field(
        ...,
        ge=0,
        le=1,
        validation_alias=AliasChoices(
            "extra_score",
            "source_quality_score",
            "source_quality",
            "production_quality_score",
            "production_quality",
        ),
    )
    extra_reasoning: str = Field(
        default="",
        validation_alias=AliasChoices(
            "extra_reasoning",
            "source_quality_reasoning",
            "production_quality_reasoning",
        ),
    )

    resource_type: str = Field(default="other")
    concepts_covered: list[str] = Field(default_factory=list)


class BatchResourceScores(BaseModel):
    scores: list[ResourceScore]


# ── Pydantic query generation model ──────────────────────────


class SearchQueries(BaseModel):
    queries: list[str] = Field(..., min_length=4, max_length=6)


# ── Type aliases ─────────────────────────────────────────────

ProgressCallback = Callable[[str, str], None]  # (phase, detail)
