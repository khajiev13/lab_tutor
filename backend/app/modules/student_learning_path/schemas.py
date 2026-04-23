"""Student Learning Path — Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

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


class ResourceOpenRequest(BaseModel):
    resource_type: Literal["reading", "video"]
    url: HttpUrl


class BuildSelectedSkillRequest(BaseModel):
    name: str
    source: Literal["book", "market"]


class BuildLearningPathRequest(BaseModel):
    selected_skills: list[BuildSelectedSkillRequest] = Field(default_factory=list)


# ── Response schemas ─────────────────────────────────────────


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    difficulty: Literal["easy", "medium", "hard"]
    options: list[str] = []


class QuizQuestion(BaseModel):
    id: str
    skill_name: str
    text: str
    options: list[str] = []


class PreviousAnswer(BaseModel):
    selected_option: Literal["A", "B", "C", "D"]
    answered_right: bool
    answered_at: datetime


class ChapterQuizResponse(BaseModel):
    course_id: int
    chapter_index: int
    chapter_title: str
    questions: list[QuizQuestion] = []
    previous_answers: dict[str, PreviousAnswer] = {}


class QuizAnswerSubmission(BaseModel):
    question_id: str
    selected_option: Literal["A", "B", "C", "D"]


class QuizSubmitRequest(BaseModel):
    answers: list[QuizAnswerSubmission] = []


class QuizAnswerResult(BaseModel):
    question_id: str
    skill_name: str
    selected_option: Literal["A", "B", "C", "D"]
    answered_right: bool
    correct_option: Literal["A", "B", "C", "D"]


class QuizSubmitResponse(BaseModel):
    chapter_index: int
    results: list[QuizAnswerResult] = []
    skills_known: list[str] = []
    chapter_status_after_submit: Literal[
        "locked", "quiz_required", "learning", "completed"
    ]
    correct_count_after_submit: int = 0
    easy_question_count: int = 0
    next_chapter_unlocked: bool = False


class ReadingResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
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

    id: str
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
    is_known: bool = False


class LearningPathChapter(BaseModel):
    title: str
    chapter_index: int
    description: str | None = None
    learning_objectives: list[str] = []
    selected_skills: list[LearningPathSkill] = []
    quiz_status: Literal["locked", "quiz_required", "learning", "completed"]
    easy_question_count: int = 0
    answered_count: int = 0
    correct_count: int = 0


class LearningPathResponse(BaseModel):
    course_id: int
    course_title: str
    chapters: list[LearningPathChapter] = []
    total_selected_skills: int = 0
    skills_with_resources: int = 0


class ReadingContentResponse(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    status: Literal["ready", "failed"]
    content_markdown: str
    fallback_summary: str
    error_message: str | None = None


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


class SkillSelectionRange(BaseModel):
    min_skills: int
    max_skills: int
    is_default: bool


class PrerequisiteEdge(BaseModel):
    prerequisite_name: str
    dependent_name: str
    confidence: Literal["high", "medium", "low"] = "medium"
    reasoning: str = ""


class StudentSkillBankResponse(BaseModel):
    book_skill_banks: list[StudentSkillBankBook] = []
    market_skill_bank: list[StudentSkillBankJobPosting] = []
    selected_skill_names: list[str] = []
    interested_posting_urls: list[str] = []
    peer_selection_counts: dict[str, int] = {}
    selection_range: SkillSelectionRange
    prerequisite_edges: list[PrerequisiteEdge] = []


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


class ReadingEmbeddabilityResponse(BaseModel):
    id: str
    url: str
    embeddable: bool
    reason: str | None = None
