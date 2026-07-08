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
