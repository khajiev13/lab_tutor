from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class SkillSource(StrEnum):
    BOOK = "book"
    MARKET_DEMAND = "market_demand"


class JobPostingRead(BaseModel):
    url: str
    title: str | None = None
    company: str | None = None
    site: str | None = None


class ConceptRead(BaseModel):
    name: str
    description: str | None = None


class SkillRead(BaseModel):
    name: str
    source: SkillSource
    description: str | None = None
    concepts: list[ConceptRead] = []

    # Market-demand-only fields
    category: str | None = None
    frequency: int | None = None
    demand_pct: float | None = None
    priority: str | None = None
    status: str | None = None
    reasoning: str | None = None
    rationale: str | None = None
    created_at: str | None = None
    job_postings: list[JobPostingRead] = []


class SectionRead(BaseModel):
    section_index: int
    title: str
    concepts: list[ConceptRead] = []


class ChapterRead(BaseModel):
    chapter_index: int
    title: str
    summary: str | None = None
    sections: list[SectionRead] = []
    skills: list[SkillRead] = []


class CurriculumResponse(BaseModel):
    course_id: int
    book_title: str | None = None
    book_authors: str | None = None
    chapters: list[ChapterRead] = []


class ChangelogEntry(BaseModel):
    timestamp: str
    agent: str
    action: str
    details: str
    chapter: str | None = None
    skill_name: str | None = None


class CurriculumWithChangelog(BaseModel):
    curriculum: CurriculumResponse
    changelog: list[ChangelogEntry] = []
