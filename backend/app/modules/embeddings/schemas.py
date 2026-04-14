from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

EmbeddingStatusOut = Literal["not_started", "in_progress", "completed", "failed"]


class CourseFileEmbeddingStatus(BaseModel):
    id: int
    filename: str
    status: str
    content_hash: str | None
    processed_at: datetime | None
    last_error: str | None

    document_id: str | None
    embedding_status: EmbeddingStatusOut
    embedded_at: datetime | None
    embedding_last_error: str | None


class CourseEmbeddingStatusResponse(BaseModel):
    course_id: int
    extraction_status: str
    embedding_status: EmbeddingStatusOut
    embedding_started_at: datetime | None
    embedding_finished_at: datetime | None
    embedding_last_error: str | None

    files: list[CourseFileEmbeddingStatus]
