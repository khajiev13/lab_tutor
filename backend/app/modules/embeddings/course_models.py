from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CourseEmbeddingStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CourseEmbeddingState(Base):
    __tablename__ = "course_embeddings_state"

    course_id: Mapped[int] = mapped_column(Integer, primary_key=True)

    status: Mapped[CourseEmbeddingStatus] = mapped_column(
        Enum(CourseEmbeddingStatus, name="course_embedding_status"),
        nullable=False,
        default=CourseEmbeddingStatus.NOT_STARTED,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
