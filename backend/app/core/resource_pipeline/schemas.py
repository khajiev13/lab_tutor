"""Shared schemas for the resource discovery pipeline (TRA + VCE).

These are domain objects used by both the textual resource analyst and
visual content evaluator pipelines. Route-specific schemas live in their
respective modules.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


def _domain_for_url(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.replace("www.", "")


def extract_youtube_video_id(url: str) -> str:
    """Extract a YouTube video id from common watch/embed/share URL shapes."""
    if not url:
        return ""

    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    path = parsed.path.strip("/")

    if domain in {"youtube.com", "m.youtube.com"}:
        params = urllib.parse.parse_qs(parsed.query)
        if path == "watch":
            return params.get("v", [""])[0]
        if path.startswith("embed/"):
            return path.split("/", 1)[1].split("/", 1)[0]
        if path.startswith("shorts/"):
            return path.split("/", 1)[1].split("/", 1)[0]

    if domain == "youtu.be":
        return path.split("/", 1)[0]

    if domain == "youtube-nocookie.com" and path.startswith("embed/"):
        return path.split("/", 1)[1].split("/", 1)[0]

    return ""


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
    search_content: str = ""
    source_engines: list[str] = field(default_factory=list)
    search_metadata: list[dict[str, Any]] = field(default_factory=list)
    search_result_url: str = ""
    search_result_domain: str = ""

    def __post_init__(self):
        self.url = self.url.strip()
        self.search_result_url = (self.search_result_url or self.url).strip()
        if not self.domain:
            self.domain = _domain_for_url(self.url)
        if not self.search_result_domain:
            self.search_result_domain = _domain_for_url(self.search_result_url)
        if not self.source_engines:
            self.source_engines = [self.source_engine] if self.source_engine else []
        elif self.source_engine and self.source_engine not in self.source_engines:
            self.source_engines.insert(0, self.source_engine)
        if not self.search_content:
            self.search_content = self.snippet
        if not self.video_id:
            self.video_id = extract_youtube_video_id(
                self.url
            ) or extract_youtube_video_id(self.search_result_url)

    def merge(self, other: CandidateResource) -> None:
        """Merge another hit for the same canonical resource into this candidate."""
        if not self.title and other.title:
            self.title = other.title
        if len(other.snippet) > len(self.snippet):
            self.snippet = other.snippet
        if len(other.search_content) > len(self.search_content):
            self.search_content = other.search_content
        if not self.video_id and other.video_id:
            self.video_id = other.video_id
        if (not self.search_result_url or self.search_result_url == self.url) and (
            other.search_result_url and other.search_result_url != other.url
        ):
            self.search_result_url = other.search_result_url
            self.search_result_domain = other.search_result_domain
        for engine in other.source_engines:
            if engine not in self.source_engines:
                self.source_engines.append(engine)
        self.search_metadata.extend(other.search_metadata)

    def text_for_embedding(self) -> str:
        parts = [self.title, self.snippet]
        if self.search_content and self.search_content != self.snippet:
            parts.append(self.search_content[:2000])
        if self.search_result_url and self.search_result_url != self.url:
            parts.append(f"Original search result URL: {self.search_result_url}")
        return ". ".join(part for part in parts if part)

    def metadata_json(self) -> str:
        return json.dumps(self.search_metadata, ensure_ascii=True, sort_keys=True)


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
