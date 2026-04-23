from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.modules.student_learning_path.schemas import StudentSkillBankResponse


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
    snippet: str = ""
    search_content: str = ""
    search_result_url: str = ""
    search_result_domain: str = ""
    source_engine: str = ""
    source_engines: list[str] = []
    search_metadata_json: str = "[]"
    final_score: float
    resource_type: str
    concepts_covered: list[str] = []


class VideoResourceRead(BaseModel):
    title: str
    url: str
    video_id: str
    domain: str
    snippet: str = ""
    search_content: str = ""
    search_result_url: str = ""
    search_result_domain: str = ""
    source_engine: str = ""
    source_engines: list[str] = []
    search_metadata_json: str = "[]"
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
    title: str | None = None
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


class SkillSelectionRange(BaseModel):
    min_skills: int
    max_skills: int
    is_default: bool


class SkillSelectionRangeUpdate(BaseModel):
    min_skills: int = Field(ge=1, le=200)
    max_skills: int = Field(ge=1, le=200)

    @model_validator(mode="after")
    def validate_range(self) -> SkillSelectionRangeUpdate:
        if self.min_skills > self.max_skills:
            raise ValueError("min_skills must be less than or equal to max_skills")
        return self


class SkillBanksResponse(BaseModel):
    course_chapters: list[CourseChapterRead] = []
    book_skill_bank: list[BookSkillBankBook] = []
    market_skill_bank: list[MarketSkillBankJobPosting] = []
    selection_range: SkillSelectionRange


class StudentInsightTopSkill(BaseModel):
    name: str
    student_count: int = 0


class StudentInsightTopPosting(BaseModel):
    url: str
    title: str | None = None
    company: str | None = None
    student_count: int = 0


class StudentInsightStudent(BaseModel):
    id: int
    full_name: str
    email: str
    selected_skill_count: int = 0
    interested_posting_count: int = 0
    has_learning_path: bool = False


class StudentInsightsSummary(BaseModel):
    students_with_selections: int = 0
    students_with_learning_paths: int = 0
    avg_selected_skill_count: float = 0.0
    top_selected_skills: list[StudentInsightTopSkill] = []
    top_interested_postings: list[StudentInsightTopPosting] = []


class StudentInsightsOverviewResponse(BaseModel):
    summary: StudentInsightsSummary
    students: list[StudentInsightStudent] = []


class StudentInsightProfile(BaseModel):
    id: int
    full_name: str
    email: str


class LearningPathChapterStatusCounts(BaseModel):
    locked: int = 0
    quiz_required: int = 0
    learning: int = 0
    completed: int = 0


class LearningPathSummary(BaseModel):
    has_learning_path: bool = False
    total_selected_skills: int = 0
    skills_with_resources: int = 0
    chapter_status_counts: LearningPathChapterStatusCounts = Field(
        default_factory=LearningPathChapterStatusCounts
    )


class StudentInsightDetailResponse(BaseModel):
    student: StudentInsightProfile
    skill_banks: StudentSkillBankResponse
    learning_path_summary: LearningPathSummary
