"""Pydantic schemas for chapter-level skills extraction."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SkillConcept(BaseModel):
    """A concept that underpins a skill — extracted inline alongside the skill."""

    name: str = Field(description="Concise concept name (a domain term)")
    description: str = Field(
        description="1-2 sentence definition grounded in the chapter"
    )


class Skill(BaseModel):
    """A practical, learnable ability extracted from a chapter."""

    name: str = Field(description="Action-oriented skill name starting with a verb")
    description: str = Field(
        description="What the student can DO after mastering this skill"
    )
    concepts: list[SkillConcept] = Field(
        default_factory=list,
        description="Domain concepts required to perform this skill",
    )


class ChapterSkillsResult(BaseModel):
    """Output of chapter-level skills extraction (one LLM call per chapter)."""

    chapter_summary: str = Field(
        description="2-3 sentence summary of the chapter's main topics"
    )
    skills: list[Skill] = Field(
        default_factory=list,
        description="Practical skills learnable from this chapter",
    )


class SkillsJudgeVerdict(StrEnum):
    APPROVED = "APPROVED"
    NEEDS_REVISION = "NEEDS_REVISION"


class SkillsJudgeFeedback(BaseModel):
    """Output of the Karpathy-style skills judge."""

    verdict: SkillsJudgeVerdict
    issues: list[str] = Field(
        default_factory=list,
        description="Specific problems to fix if verdict is NEEDS_REVISION",
    )
    reasoning: str = Field(description="Brief explanation of the verdict")
