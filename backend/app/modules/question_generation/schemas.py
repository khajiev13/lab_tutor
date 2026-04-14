"""Question generation schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GeneratedQuestion(BaseModel):
    """A single generated question."""

    text: str = Field(..., description="The question text")
    difficulty: Literal["easy", "medium", "hard"]
    options: list[str] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Exactly four answer options in A/B/C/D order",
    )
    correct_option: Literal["A", "B", "C", "D"]
    answer: str = Field(..., description="The model answer")


class QuestionSet(BaseModel):
    """LLM output: exactly 3 questions per skill."""

    questions: list[GeneratedQuestion] = Field(..., min_length=3, max_length=3)
