"""Data-access layer for the chunking-analysis feature.

Encapsulates every PostgreSQL interaction so the LangGraph workflow nodes
and route handlers never touch SQLAlchemy directly.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

from .models import (
    BookChunk,
    BookExtractionRun,
    CourseSelectedBook,
    ExtractionRunStatus,
)

logger = logging.getLogger(__name__)


# ── Standalone session for background tasks ─────────────────────


@contextmanager
def fresh_db() -> Generator[Session, None, None]:
    """Yield a short-lived DB session (for use outside request scope)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            logger.debug("Suppressed error closing DB session", exc_info=True)


# ── Low-level helper ────────────────────────────────────────────


def update_run(db: Session, run_id: int, **kwargs: Any) -> None:
    """Update arbitrary fields on a BookExtractionRun and commit."""
    run = db.get(BookExtractionRun, run_id)
    if run:
        for k, v in kwargs.items():
            setattr(run, k, v)
        db.commit()


# ── Queries used by route handlers ──────────────────────────────


def get_latest_run(course_id: int, db: Session) -> BookExtractionRun | None:
    """Return the most recent extraction run for a course (or None)."""
    return (
        db.query(BookExtractionRun)
        .filter(BookExtractionRun.course_id == course_id)
        .order_by(desc(BookExtractionRun.created_at))
        .first()
    )


def get_active_run(course_id: int, db: Session) -> BookExtractionRun | None:
    """Return an in-progress run for a course (or None)."""
    return (
        db.query(BookExtractionRun)
        .filter(
            BookExtractionRun.course_id == course_id,
            BookExtractionRun.status.in_(
                [
                    ExtractionRunStatus.PENDING,
                    ExtractionRunStatus.EXTRACTING,
                    ExtractionRunStatus.EMBEDDING,
                ]
            ),
        )
        .first()
    )


def create_run(db: Session, **kwargs: Any) -> BookExtractionRun:
    """Insert a new BookExtractionRun and return it (committed)."""
    run = BookExtractionRun(**kwargs)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def pick_book(run_id: int, selected_book_id: int, db: Session) -> BookExtractionRun:
    """Mark a book as picked for a completed run."""
    run = db.get(BookExtractionRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")
    if run.status not in (
        ExtractionRunStatus.COMPLETED,
        ExtractionRunStatus.BOOK_PICKED,
    ):
        raise ValueError(
            f"Run must be COMPLETED to pick a book (current: {run.status.value})"
        )
    run.status = ExtractionRunStatus.BOOK_PICKED
    db.commit()
    db.refresh(run)
    return run


def recover_orphaned_runs(db: Session) -> int:
    """Mark any in-progress runs as FAILED (called on server startup)."""
    orphans = (
        db.query(BookExtractionRun)
        .filter(
            BookExtractionRun.status.in_(
                [
                    ExtractionRunStatus.PENDING,
                    ExtractionRunStatus.EXTRACTING,
                    ExtractionRunStatus.EMBEDDING,
                ]
            )
        )
        .all()
    )
    for run in orphans:
        run.status = ExtractionRunStatus.FAILED
        run.error_message = "Server restarted while analysis was in progress"
        run.progress_detail = "Failed (server restart)"
    if orphans:
        db.commit()
    return len(orphans)


# ── Queries used by workflow nodes ──────────────────────────────


def get_selected_books_with_blobs(
    course_id: int, db: Session
) -> list[CourseSelectedBook]:
    """Return all selected books for a course that have a blob_path."""
    return (
        db.query(CourseSelectedBook)
        .filter(
            CourseSelectedBook.course_id == course_id,
            CourseSelectedBook.blob_path.isnot(None),
        )
        .all()
    )


def store_chunks(
    run_id: int,
    books: list[dict],
    db: Session,
) -> int:
    """Persist BookChunk rows for every book's chunks + embeddings.

    Returns the total number of chunks stored.
    """
    total = 0
    for book in books:
        for idx, (text, emb) in enumerate(
            zip(book["chunks"], book["chunk_embeddings"], strict=True)
        ):
            db.add(
                BookChunk(
                    run_id=run_id,
                    selected_book_id=book["selected_book_id"],
                    chunk_text=text,
                    chunk_index=idx,
                    embedding=emb,
                )
            )
        total += len(book["chunks"])
        db.flush()
    return total
