"""Pydantic schemas for chapter-level concept extraction.

Copied from the chapter_level_extraction notebook — these are the LLM
structured-output models and the assembled result types.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConceptRelevance(str, Enum):
    CORE = "core"
    SUPPLEMENTARY = "supplementary"
    TANGENTIAL = "tangential"


class Concept(BaseModel):
    """A single concept extracted from a chapter."""

    name: str = Field(description="Concise name of the concept")
    description: str = Field(
        description="1-2 sentence explanation grounded in the chapter text"
    )
    relevance: ConceptRelevance = Field(
        description="core, supplementary, or tangential"
    )
    text_evidence: str = Field(
        description="Short quote or paraphrase from the chapter text"
    )
    source_section: str = Field(
        description="Title of the section this concept primarily belongs to"
    )
    # Populated after extraction by the embedding step in chapter_worker.
    name_embedding: list[float] | None = Field(default=None, exclude=True)
    evidence_embedding: list[float] | None = Field(default=None, exclude=True)


class ChapterConceptsResult(BaseModel):
    """Output of chapter-level concept extraction (ONE LLM call per chapter)."""

    chapter_title: str = Field(description="The chapter title being analyzed")
    concepts: list[Concept] = Field(
        default_factory=list,
        description="All concepts extracted from the chapter",
    )


class SectionExtraction(BaseModel):
    """Grouped concepts for one section — used for downstream compatibility."""

    section_title: str = Field(description="Title matching a TOC section")
    concepts: list[Concept] = Field(default_factory=list)


class Skill(BaseModel):
    name: str = Field(description="Name of the skill/ability")
    description: str = Field(description="Action-oriented description")
    concept_names: list[str] = Field(default_factory=list)


class ChapterSkillsResult(BaseModel):
    """Output of chapter-level skills extraction."""

    chapter_summary: str = Field(
        description="Brief 2-3 sentence summary of the chapter"
    )
    skills: list[Skill] = Field(
        default_factory=list,
        description="Chapter-level practical skills",
    )


class ChapterExtraction(BaseModel):
    """Final assembled result: sections + skills for a full chapter."""

    chapter_title: str
    chapter_summary: str
    sections: list[SectionExtraction]
    skills: list[Skill] = Field(default_factory=list)

    @property
    def all_concepts(self) -> list[Concept]:
        return [c for s in self.sections for c in s.concepts]

    @property
    def total_concept_count(self) -> int:
        return len(self.all_concepts)


class EvaluationVerdict(str, Enum):
    APPROVED = "APPROVED"
    NEEDS_REVISION = "NEEDS_REVISION"


class ExtractionFeedback(BaseModel):
    verdict: EvaluationVerdict
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    reasoning: str
