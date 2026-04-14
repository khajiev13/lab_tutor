"""Data-access layer for the chapter skills extraction feature."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

from ..models import BookChapter, BookExtractionRun
from .schemas import Skill

logger = logging.getLogger(__name__)


@contextmanager
def fresh_db() -> Generator[Session, None, None]:
    """Yield a short-lived DB session for background/streaming operations."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        raise
    finally:
        try:
            db.close()
        except Exception:
            logger.debug("Suppressed error closing DB session", exc_info=True)


def update_run(db: Session, run_id: int, **kwargs) -> None:
    """Update fields on a BookExtractionRun and commit."""
    run = db.get(BookExtractionRun, run_id)
    if run:
        for k, v in kwargs.items():
            setattr(run, k, v)
        db.commit()


def save_chapter_skills(
    run_id: int,
    selected_book_id: int,
    chapter_index: int,
    chapter_title: str,
    chapter_summary: str,
    skills: list[Skill],
) -> int:
    """Persist chapter skills to the BookChapter row.

    Updates an existing BookChapter (created during shared PDF extraction)
    with the LLM-generated summary and skills JSON, then marks it as
    agentic_processed so resume logic can skip it on retry.

    Returns the BookChapter.id.
    """
    skills_data = [s.model_dump() for s in skills]

    with fresh_db() as db:
        existing = (
            db.query(BookChapter)
            .filter(
                BookChapter.run_id == run_id,
                BookChapter.selected_book_id == selected_book_id,
                BookChapter.chapter_index == chapter_index,
            )
            .first()
        )

        if existing:
            existing.chapter_title = chapter_title
            existing.chapter_summary = chapter_summary or None
            existing.skills_json = json.dumps(skills_data) if skills_data else None
            existing.total_concept_count = sum(len(s.concepts) for s in skills)
            existing.agentic_processed = True
            db.commit()
            return existing.id
        else:
            chapter = BookChapter(
                run_id=run_id,
                selected_book_id=selected_book_id,
                chapter_title=chapter_title,
                chapter_index=chapter_index,
                chapter_summary=chapter_summary or None,
                skills_json=json.dumps(skills_data) if skills_data else None,
                total_concept_count=sum(len(s.concepts) for s in skills),
                agentic_processed=True,
            )
            db.add(chapter)
            db.commit()
            return chapter.id


def get_completed_chapter_indices(run_id: int, book_id: int, db: Session) -> set[int]:
    """Return chapter indices already agentic-processed for this run + book."""
    rows = (
        db.query(BookChapter.chapter_index)
        .filter(
            BookChapter.run_id == run_id,
            BookChapter.selected_book_id == book_id,
            BookChapter.agentic_processed.is_(True),
        )
        .all()
    )
    return {row.chapter_index for row in rows}


def get_agentic_chapter_counts(run_id: int, db: Session) -> dict[int, dict]:
    """Return per-book chapter completion counts.

    Returns ``{selected_book_id: {total: N, completed: M, title: str}}``.
    """
    from ..models import CourseSelectedBook

    chapters = db.query(BookChapter).filter(BookChapter.run_id == run_id).all()
    result: dict[int, dict] = {}
    for ch in chapters:
        book_id = ch.selected_book_id
        if book_id not in result:
            book = db.get(CourseSelectedBook, book_id)
            result[book_id] = {
                "title": book.title if book else "Unknown",
                "completed": 0,
                "total": 0,
            }
        result[book_id]["completed"] += 1

    return result
