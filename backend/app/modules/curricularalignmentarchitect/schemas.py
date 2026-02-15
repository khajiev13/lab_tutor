"""API-facing Pydantic DTOs for the book-selection feature."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BookStatus, DownloadStatus, SessionStatus

# ═══════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════


class WeightsConfig(BaseModel):
    """The 7 scoring weight values coming from the frontend config panel."""

    C_topic: float = Field(..., ge=0, le=1)
    C_struc: float = Field(..., ge=0, le=1)
    C_scope: float = Field(..., ge=0, le=1)
    C_pub: float = Field(..., ge=0, le=1)
    C_auth: float = Field(..., ge=0, le=1)
    C_time: float = Field(..., ge=0, le=1)
    W_prac: float = Field(..., ge=0, le=1, description="Practicality weight (blends into S_final)")

    @model_validator(mode="after")
    def check_sum(self) -> WeightsConfig:
        total = self.C_topic + self.C_struc + self.C_scope + self.C_pub + self.C_auth + self.C_time
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Core weights must sum to 1.0 (got {total:.6f}). "
                "Adjust so C_topic + C_struc + C_scope + C_pub + C_auth + C_time = 1.0"
            )
        return self

    def to_weights_dict(self) -> dict[str, float]:
        return {
            "C_topic": self.C_topic,
            "C_struc": self.C_struc,
            "C_scope": self.C_scope,
            "C_pub": self.C_pub,
            "C_auth": self.C_auth,
            "C_time": self.C_time,
            "W_prac": self.W_prac,
        }


class CourseLevelEnum(str, Enum):
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class StartSessionRequest(BaseModel):
    course_level: CourseLevelEnum = CourseLevelEnum.BACHELOR
    weights: WeightsConfig


class SelectBooksRequest(BaseModel):
    book_ids: list[int] = Field(..., max_length=5, description="Select up to 5 books")


# ═══════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════


class SessionRead(BaseModel):
    id: int
    course_id: int
    thread_id: str
    status: SessionStatus
    course_level: str
    weights_json: str | None = None
    progress_scored: int = 0
    progress_total: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookCandidateRead(BaseModel):
    id: int
    session_id: int
    course_id: int
    title: str
    authors: str | None
    publisher: str | None
    year: str | None
    s_final: float | None
    scores_json: str | None
    selected_by_teacher: bool
    download_status: DownloadStatus
    download_error: str | None
    blob_path: str | None
    source_url: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManualUploadResponse(BaseModel):
    book_id: int
    blob_path: str


# ═══════════════════════════════════════════════════════════════
# Course Selected Books schemas
# ═══════════════════════════════════════════════════════════════


class CourseSelectedBookRead(BaseModel):
    id: int
    course_id: int
    source_book_id: int | None
    title: str
    authors: str | None
    publisher: str | None
    year: str | None
    status: BookStatus
    blob_path: str | None
    blob_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SelectedBookManualUploadResponse(BaseModel):
    id: int
    blob_path: str
    blob_url: str | None
    status: BookStatus


# ═══════════════════════════════════════════════════════════════
# SSE Stream event schemas
# ═══════════════════════════════════════════════════════════════


class StreamEventType(str, Enum):
    PHASE_UPDATE = "phase_update"
    DISCOVERY_PROGRESS = "discovery_progress"
    SCORING_PROGRESS = "scoring_progress"
    BOOKS_READY = "books_ready"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETE = "download_complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    type: StreamEventType
    phase: str = ""
    message: str = ""
    progress: int | None = None
    total: int | None = None
    data: dict | None = None
