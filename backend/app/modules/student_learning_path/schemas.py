"""Student Learning Path — Pydantic request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Request schemas ──────────────────────────────────────────


class SelectSkillsRequest(BaseModel):
    skill_names: list[str] = Field(..., min_length=1)
    source: Literal["book", "market"]


class DeselectSkillsRequest(BaseModel):
    skill_names: list[str] = Field(..., min_length=1)


class SelectJobPostingsRequest(BaseModel):
    posting_urls: list[str] = Field(..., min_length=1)


class DeselectJobPostingRequest(BaseModel):
    posting_url: str


# ── Response schemas ─────────────────────────────────────────


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    difficulty: Literal["easy", "medium", "hard"]
    options: list[str] = []
    correct_option: Literal["A", "B", "C", "D"] | None = None
    answer: str


class ReadingResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    url: str
    domain: str = ""
    snippet: str = ""
    search_content: str = ""
    search_result_url: str = ""
    search_result_domain: str = ""
    source_engine: str = ""
    source_engines: list[str] = []
    search_metadata_json: str = "[]"
    resource_type: str = ""
    final_score: float = 0.0
    concepts_covered: list[str] = []


class VideoResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    url: str
    domain: str = ""
    snippet: str = ""
    search_content: str = ""
    video_id: str = ""
    search_result_url: str = ""
    search_result_domain: str = ""
    source_engine: str = ""
    source_engines: list[str] = []
    search_metadata_json: str = "[]"
    resource_type: str = ""
    final_score: float = 0.0
    concepts_covered: list[str] = []


class ConceptRead(BaseModel):
    name: str
    description: str | None = None


class LearningPathSkill(BaseModel):
    name: str
    source: str  # "book" | "market" | "job_posting"
    description: str | None = None
    concepts: list[ConceptRead] = []
    readings: list[ReadingResourceRead] = []
    videos: list[VideoResourceRead] = []
    questions: list[QuestionRead] = []
    resource_status: Literal["loaded", "pending"] = "pending"


class LearningPathChapter(BaseModel):
    title: str
    chapter_index: int
    description: str | None = None
    learning_objectives: list[str] = []
    selected_skills: list[LearningPathSkill] = []


class LearningPathResponse(BaseModel):
    course_id: int
    course_title: str
    chapters: list[LearningPathChapter] = []
    total_selected_skills: int = 0
    skills_with_resources: int = 0


class StudentSkillBankSkill(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    is_selected: bool = False
    source: str | None = None
    peer_count: int = 0


class StudentSkillBankBookChapter(BaseModel):
    chapter_id: str
    title: str
    chapter_index: int
    skills: list[StudentSkillBankSkill] = []


class StudentSkillBankBook(BaseModel):
    book_id: str
    title: str
    authors: str | None = None
    chapters: list[StudentSkillBankBookChapter] = []


class StudentSkillBankJobPosting(BaseModel):
    url: str
    title: str
    company: str = ""
    site: str | None = None
    search_term: str | None = None
    is_interested: bool = False
    skills: list[StudentSkillBankSkill] = []


class StudentSkillBankResponse(BaseModel):
    book_skill_banks: list[StudentSkillBankBook] = []
    market_skill_bank: list[StudentSkillBankJobPosting] = []
    selected_skill_names: list[str] = []
    interested_posting_urls: list[str] = []
    peer_selection_counts: dict[str, int] = {}


class BuildProgressEvent(BaseModel):
    """SSE event for build progress."""

    skill_name: str
    phase: (
        str  # "reading" | "video" | "question" | "question_error" | "skipped" | "done"
    )
    detail: str = ""
    skills_completed: int = 0
    total_skills: int = 0


class BuildResult(BaseModel):
    total_skills: int = 0
    readings_added: int = 0
    videos_added: int = 0
    questions_added: int = 0
