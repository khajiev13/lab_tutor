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


class ReadingResourceRead(BaseModel):
    title: str
    url: str
    domain: str
    final_score: float
    resource_type: str
    concepts_covered: list[str] = []


class VideoResourceRead(BaseModel):
    title: str
    url: str
    video_id: str
    domain: str
    final_score: float
    resource_type: str
    concepts_covered: list[str] = []


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

    # Resource discovery fields
    readings: list[ReadingResourceRead] = []
    videos: list[VideoResourceRead] = []


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


# ── Skill Banks schemas ──────────────────────────────────────────


class TranscriptDocumentRead(BaseModel):
    topic: str
    source_filename: str | None = None


class CourseChapterRead(BaseModel):
    chapter_index: int
    title: str
    description: str | None = None
    learning_objectives: list[str] = []
    documents: list[TranscriptDocumentRead] = []


class BookSkillBankSkill(BaseModel):
    name: str
    description: str | None = None


class BookSkillBankChapter(BaseModel):
    chapter_index: int
    chapter_id: str
    skills: list[BookSkillBankSkill] = []


class BookSkillBankBook(BaseModel):
    book_id: str
    title: str
    authors: str | None = None
    chapters: list[BookSkillBankChapter] = []


class MarketSkillBankSkill(BaseModel):
    name: str
    category: str | None = None
    status: str | None = None
    priority: str | None = None
    demand_pct: float | None = None


class MarketSkillBankJobPosting(BaseModel):
    title: str
    company: str | None = None
    site: str | None = None
    url: str
    search_term: str | None = None
    skills: list[MarketSkillBankSkill] = []


class SkillBanksResponse(BaseModel):
    course_chapters: list[CourseChapterRead] = []
    book_skill_bank: list[BookSkillBankBook] = []
    market_skill_bank: list[MarketSkillBankJobPosting] = []
