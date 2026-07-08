from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OnboardingStatus = Literal[
    "needs_cv",
    "extracting",
    "needs_profile_review",
    "needs_jobs",
    "needs_skill_selection",
    "ready",
    "error",
]


class IndividualProfileRead(BaseModel):
    user_id: int
    onboarding_status: OnboardingStatus
    target_titles: list[str] = Field(default_factory=list)
    preferred_country: str | None = None
    preferred_location: str | None = None
    reviewed_at: datetime | None = None


class CVDocumentRead(BaseModel):
    id: int
    user_id: int
    original_filename: str
    content_type: str | None = None
    status: str


class CVSkillExtraction(BaseModel):
    name: str
    category: str = ""
    evidence: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class CVExperienceExtraction(BaseModel):
    title: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    summary: str = ""


class CVProfileExtraction(BaseModel):
    summary: str = ""
    skills: list[CVSkillExtraction] = Field(default_factory=list)
    experience: list[CVExperienceExtraction] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    seniority_signals: list[str] = Field(default_factory=list)
    target_title_suggestions: list[str] = Field(default_factory=list)


GraphRunStatus = Literal["interrupted", "completed"]


class IndividualGraphStartRequest(BaseModel):
    cv_document_id: int


class IndividualGraphResumeRequest(BaseModel):
    thread_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class IndividualGraphResponse(BaseModel):
    thread_id: str
    status: GraphRunStatus
    interrupt: dict[str, Any] | None = None
    target_titles: list[str] = Field(default_factory=list)
    selected_posting_urls: list[str] = Field(default_factory=list)
    selected_skill_names: list[str] = Field(default_factory=list)


class IndividualGraphStartResponse(IndividualGraphResponse):
    pass


class IndividualGraphResumeResponse(IndividualGraphResponse):
    pass


class IndividualSkillBankSkill(BaseModel):
    name: str
    description: str | None = None
    category: str | None = None
    is_selected: bool = False
    coverage: Literal["covered", "gap", "partial", "unknown"] = "unknown"


class IndividualSkillBankJobPosting(BaseModel):
    url: str
    title: str
    company: str = ""
    site: str | None = None
    search_term: str | None = None
    is_interested: bool = False
    match_score: float | None = None
    skills: list[IndividualSkillBankSkill] = Field(default_factory=list)


class IndividualSkillBanksResponse(BaseModel):
    market_skill_bank: list[IndividualSkillBankJobPosting] = Field(default_factory=list)
    selected_skill_names: list[str] = Field(default_factory=list)
    interested_posting_urls: list[str] = Field(default_factory=list)


class IndividualLearningPathResourceRead(BaseModel):
    id: str = ""
    title: str = ""
    url: str = ""
    domain: str | None = None
    snippet: str | None = None
    search_content: str | None = None
    resource_type: str | None = None
    final_score: float | None = None
    video_id: str | None = None


class IndividualLearningPathQuestionRead(BaseModel):
    id: str = ""
    text: str = ""
    difficulty: Literal["easy", "medium", "hard"]
    options: list[str] = Field(default_factory=list)


class IndividualLearningPathSkillRead(BaseModel):
    name: str
    description: str | None = None
    source: str | None = None
    selected_at: str | None = None
    readings: list[IndividualLearningPathResourceRead] = Field(default_factory=list)
    videos: list[IndividualLearningPathResourceRead] = Field(default_factory=list)
    questions: list[IndividualLearningPathQuestionRead] = Field(default_factory=list)


class IndividualLearningPathResponse(BaseModel):
    user_id: int
    selected_skills: list[IndividualLearningPathSkillRead] = Field(default_factory=list)
    total_selected_skills: int = 0
    skills_with_resources: int = 0


class SelectInterestedJobsRequest(BaseModel):
    posting_urls: list[str] = Field(default_factory=list)


class SelectIndividualSkillsRequest(BaseModel):
    skill_names: list[str] = Field(default_factory=list)
