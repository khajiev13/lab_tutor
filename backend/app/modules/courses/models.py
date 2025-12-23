from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User


class ExtractionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"


class FileProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SqlEnum(
            ExtractionStatus,
            name="extraction_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ExtractionStatus.NOT_STARTED,
        nullable=False,
    )

    teacher: Mapped["User"] = relationship("User", back_populates="courses")
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )
    files: Mapped[list["CourseFile"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_course_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    course: Mapped["Course"] = relationship(back_populates="enrollments")
    student: Mapped["User"] = relationship("User", back_populates="enrollments")


class CourseFile(Base):
    __tablename__ = "course_files"
    __table_args__ = (
        UniqueConstraint("course_id", "blob_path", name="uq_course_blob_path"),
        # Detect duplicate uploads regardless of filename by hashing file bytes.
        # Note: content_hash is nullable to allow existing DBs to migrate without backfill.
        UniqueConstraint("course_id", "content_hash", name="uq_course_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    blob_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    status: Mapped[FileProcessingStatus] = mapped_column(
        SqlEnum(
            FileProcessingStatus,
            name="file_processing_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=FileProcessingStatus.PENDING,
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    course: Mapped["Course"] = relationship(back_populates="files")
