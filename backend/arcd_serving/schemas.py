"""Pydantic v2 request and response schemas for the ARCD serving API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── Shared sub-models ─────────────────────────────────────────────────────────


class Interaction(BaseModel):
    question_name: str
    correct: int = Field(..., ge=0, le=1)
    timestamp_sec: float = 0.0


# ── Request bodies ────────────────────────────────────────────────────────────


class MasteryRequest(BaseModel):
    interactions: list[Interaction] = Field(
        ..., description="Ordered interaction history (oldest first)"
    )
    concept_names: list[str] | None = Field(
        default=None,
        description="Skill names to return. Defaults to all skills in vocab.",
    )
    seq_len: int = Field(default=50, ge=1, le=512)


class PredictRequest(BaseModel):
    interactions: list[Interaction] = Field(
        ..., description="Ordered interaction history (oldest first)"
    )
    target_questions: list[str] = Field(
        ..., description="Question names to predict P(correct) for"
    )
    seq_len: int = Field(default=50, ge=1, le=512)


class NextQuestionRequest(BaseModel):
    interactions: list[Interaction] = Field(
        ..., description="Ordered interaction history (oldest first)"
    )
    candidate_questions: list[str] = Field(
        ..., description="Pool of candidate question names to pick from"
    )
    strategy: Literal["max_uncertainty", "max_information"] = "max_uncertainty"
    seq_len: int = Field(default=50, ge=1, le=512)


# ── Response bodies ───────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    checkpoint_loaded: bool
    model_version: str
    best_val_auc: float


class InfoResponse(BaseModel):
    n_skills: int
    n_questions: int
    n_students: int
    concept_names: list[str]
    device: str


class MasteryResponse(BaseModel):
    mastery: dict[str, float]


class PredictResponse(BaseModel):
    predictions: list[dict[str, float | str]]


class NextQuestionResponse(BaseModel):
    recommended_question: str
    p_correct: float
    alternatives: list[dict[str, float | str]]
