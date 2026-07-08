from __future__ import annotations

from datetime import datetime
from typing import Literal

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
