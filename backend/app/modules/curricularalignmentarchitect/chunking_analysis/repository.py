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

from ..models import (
    AnalysisStrategy,
    BookAnalysisSummary,
    BookChunk,
    BookDocumentSummaryScore,
    BookExtractionRun,
    CourseConceptCache,
    CourseDocumentSummaryCache,
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
                    ExtractionRunStatus.SCORING,
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
                    ExtractionRunStatus.SCORING,
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


def store_course_concept_cache(
    run_id: int,
    concepts: list[dict],
    db: Session,
) -> int:
    """Persist course concept cache rows for a run.

    Returns total inserted rows.
    """
    (
        db.query(CourseConceptCache)
        .filter(CourseConceptCache.run_id == run_id)
        .delete(synchronize_session=False)
    )

    for concept in concepts:
        db.add(
            CourseConceptCache(
                run_id=run_id,
                concept_name=concept["concept_name"],
                text_evidence=concept.get("text_evidence"),
                doc_topic=concept.get("doc_topic"),
                name_embedding=concept.get("name_embedding"),
                evidence_embedding=concept.get("evidence_embedding"),
            )
        )
    db.flush()
    return len(concepts)


def store_document_summary_cache(
    run_id: int,
    doc_summaries: list[dict],
    db: Session,
) -> int:
    """Persist document summary cache rows for a run.

    Returns total inserted rows.
    """
    (
        db.query(CourseDocumentSummaryCache)
        .filter(CourseDocumentSummaryCache.run_id == run_id)
        .delete(synchronize_session=False)
    )

    for ds in doc_summaries:
        db.add(
            CourseDocumentSummaryCache(
                run_id=run_id,
                document_neo4j_id=ds["document_id"],
                topic=ds.get("topic"),
                summary_text=ds.get("summary_text"),
                summary_embedding=ds.get("summary_embedding"),
            )
        )
    db.flush()
    return len(doc_summaries)


def store_book_analysis_summary(
    run_id: int,
    selected_book_id: int,
    strategy: AnalysisStrategy,
    payload: dict,
    db: Session,
) -> BookAnalysisSummary:
    """Upsert a scored summary row for a single book in a run."""
    (
        db.query(BookAnalysisSummary)
        .filter(
            BookAnalysisSummary.run_id == run_id,
            BookAnalysisSummary.selected_book_id == selected_book_id,
            BookAnalysisSummary.strategy == strategy,
        )
        .delete(synchronize_session=False)
    )

    summary = BookAnalysisSummary(
        run_id=run_id,
        selected_book_id=selected_book_id,
        strategy=strategy,
        book_title=payload["book_title"],
        s_final_name=payload.get("s_final_name", 0.0),
        s_final_evidence=payload.get("s_final_evidence", 0.0),
        total_book_concepts=payload.get("total_book_concepts", 0),
        chapter_count=payload.get("chapter_count", 0),
        novel_count_default=payload.get("novel_count_default", 0),
        overlap_count_default=payload.get("overlap_count_default", 0),
        covered_count_default=payload.get("covered_count_default", 0),
        book_unique_concepts_json=payload.get("book_unique_concepts_json"),
        course_coverage_json=payload.get("course_coverage_json"),
        topic_scores_json=payload.get("topic_scores_json"),
        sim_distribution_json=payload.get("sim_distribution_json"),
    )
    db.add(summary)
    db.flush()
    return summary


def store_book_document_summary_scores(
    summary_id: int,
    scores: list[dict],
    db: Session,
) -> int:
    """Persist per-book document summary similarity scores.

    Args:
        summary_id: The BookAnalysisSummary.id this score belongs to.
        scores: List of dicts with document_id, topic, summary_text, sim_score.

    Returns total inserted rows.
    """
    for s in scores:
        db.add(
            BookDocumentSummaryScore(
                summary_id=summary_id,
                document_neo4j_id=s["document_id"],
                topic=s.get("topic"),
                summary_text=(s.get("summary_text") or "")[:2000],
                sim_score=s.get("sim_score", 0.0),
            )
        )
    db.flush()
    return len(scores)


def get_summaries_for_run(run_id: int, db: Session) -> list[BookAnalysisSummary]:
    """Return all summaries for the given analysis run."""
    return (
        db.query(BookAnalysisSummary)
        .filter(BookAnalysisSummary.run_id == run_id)
        .order_by(BookAnalysisSummary.s_final_name.desc(), BookAnalysisSummary.id.asc())
        .all()
    )


def run_has_chunks(run_id: int, db: Session) -> bool:
    """Return True when a run has at least one stored chunk."""
    return (
        db.query(BookChunk.id).filter(BookChunk.run_id == run_id).limit(1).first()
        is not None
    )


def run_has_summaries(run_id: int, db: Session) -> bool:
    """Return True when a run has at least one scored summary."""
    return (
        db.query(BookAnalysisSummary.id)
        .filter(BookAnalysisSummary.run_id == run_id)
        .limit(1)
        .first()
        is not None
    )


def get_books_from_stored_chunks(run_id: int, db: Session) -> list[dict]:
    """Reconstruct per-book chunk payload from already persisted BookChunk rows."""
    selected_books = {
        book.id: book
        for book in (
            db.query(CourseSelectedBook)
            .join(BookChunk, BookChunk.selected_book_id == CourseSelectedBook.id)
            .filter(BookChunk.run_id == run_id)
            .distinct(CourseSelectedBook.id)
            .all()
        )
    }

    rows = (
        db.query(BookChunk)
        .filter(BookChunk.run_id == run_id)
        .order_by(BookChunk.selected_book_id.asc(), BookChunk.chunk_index.asc())
        .all()
    )

    by_book: dict[int, dict] = {}
    for row in rows:
        payload = by_book.get(row.selected_book_id)
        if payload is None:
            selected = selected_books.get(row.selected_book_id)
            payload = {
                "selected_book_id": row.selected_book_id,
                "title": selected.title if selected else f"Book {row.selected_book_id}",
                "md_text": "",
                "chunks": [],
                "chunk_embeddings": [],
            }
            by_book[row.selected_book_id] = payload

        payload["chunks"].append(row.chunk_text)
        payload["chunk_embeddings"].append(row.embedding)

    return list(by_book.values())
