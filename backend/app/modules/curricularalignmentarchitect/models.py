from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SessionStatus(str, Enum):
    CONFIGURING = "configuring"
    DISCOVERING = "discovering"
    SCORING = "scoring"
    AWAITING_REVIEW = "awaiting_review"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    SUCCESS = "success"
    FAILED = "failed"
    MANUAL_UPLOAD = "manual_upload"


class BookStatus(str, Enum):
    """Status of a book in the course_selected_books table."""

    DOWNLOADED = "downloaded"
    UPLOADED = "uploaded"
    FAILED = "failed"


class BookSelectionSession(Base):
    __tablename__ = "book_selection_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(
            SessionStatus,
            name="book_session_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=SessionStatus.CONFIGURING,
        nullable=False,
    )
    weights_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_level: Mapped[str] = mapped_column(
        String(20), default="bachelor", nullable=False
    )
    discovered_books_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_scored: Mapped[int] = mapped_column(default=0, nullable=False)
    progress_total: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    books: Mapped[list["CourseBook"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class CourseBook(Base):
    __tablename__ = "course_books"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("book_selection_sessions.id"), nullable=False
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    s_final: Mapped[float | None] = mapped_column(nullable=True)
    scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_by_teacher: Mapped[bool] = mapped_column(default=False, nullable=False)
    download_status: Mapped[DownloadStatus] = mapped_column(
        SqlEnum(
            DownloadStatus,
            name="book_download_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DownloadStatus.PENDING,
        nullable=False,
    )
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    session: Mapped["BookSelectionSession"] = relationship(back_populates="books")


class CourseSelectedBook(Base):
    """Final books associated with a course — promoted from candidates or custom uploads."""

    __tablename__ = "course_selected_books"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    source_book_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_books.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[BookStatus] = mapped_column(
        SqlEnum(
            BookStatus,
            name="book_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BookStatus.FAILED,
        nullable=False,
    )
    blob_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    blob_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
