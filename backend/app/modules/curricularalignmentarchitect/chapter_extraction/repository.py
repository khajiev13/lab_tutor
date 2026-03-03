"""Data-access layer for the chapter extraction feature.

Handles saving chapter extraction results to PostgreSQL
(BookChapter → BookSection → BookConcept).
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.core.database import SessionLocal

from ..models import (
    BookChapter,
    BookConcept,
    BookExtractionRun,
    BookSection,
    ConceptRelevance,
)
from .schemas import ChapterExtraction

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


def save_chapter_extraction(
    run_id: int,
    selected_book_id: int,
    chapter_extraction: ChapterExtraction,
    chapter_index: int,
    chapter_text: str | None = None,
) -> int:
    """Persist a ChapterExtraction to BookChapter → BookSection → BookConcept.

    If a BookChapter row already exists for the given (run, book, index)
    — created by the shared PDF extraction step — it is updated in place
    with the LLM-generated summary, skills, and concepts.  Otherwise a new
    row is created (backward compat).

    Returns the BookChapter.id.
    """
    skills_data = [s.model_dump() for s in chapter_extraction.skills]

    with fresh_db() as db:
        # Try to find existing chapter row from shared extraction
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
            # Update the existing row with agentic results
            existing.chapter_title = chapter_extraction.chapter_title
            existing.total_concept_count = chapter_extraction.total_concept_count
            if chapter_text:
                existing.chapter_text = chapter_text
            existing.chapter_summary = chapter_extraction.chapter_summary or None
            existing.skills_json = json.dumps(skills_data) if skills_data else None

            # Delete old sections/concepts if re-running
            for sec in existing.sections:
                for concept in sec.concepts:
                    db.delete(concept)
                db.delete(sec)
            db.flush()

            chapter = existing
        else:
            # Create new row (backward compat / no shared extraction)
            chapter = BookChapter(
                run_id=run_id,
                selected_book_id=selected_book_id,
                chapter_title=chapter_extraction.chapter_title,
                chapter_index=chapter_index,
                total_concept_count=chapter_extraction.total_concept_count,
                chapter_text=chapter_text,
                chapter_summary=chapter_extraction.chapter_summary or None,
                skills_json=json.dumps(skills_data) if skills_data else None,
            )
            db.add(chapter)
            db.flush()

        for sec_idx, section in enumerate(chapter_extraction.sections):
            sec = BookSection(
                chapter_id=chapter.id,
                section_title=section.section_title,
                section_index=sec_idx,
                section_content=section.section_content,
            )
            db.add(sec)
            db.flush()

            for concept in section.concepts:
                db.add(
                    BookConcept(
                        section_id=sec.id,
                        run_id=run_id,
                        name=concept.name,
                        description=concept.description,
                        text_evidence=concept.text_evidence,
                        relevance=ConceptRelevance(concept.relevance.value),
                        name_embedding=concept.name_embedding,
                        evidence_embedding=concept.evidence_embedding,
                    )
                )

        db.commit()
        return chapter.id


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
