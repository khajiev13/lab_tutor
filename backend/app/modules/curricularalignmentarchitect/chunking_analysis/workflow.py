"""LangGraph orchestration for paragraph-level chunking analysis."""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.settings import settings

from ..models import BookExtractionRun, ExtractionRunStatus
from .nodes import (
    chunk_paragraphs,
    embed_doc_summaries,
    embed_single_book,
    extract_pdf,
    fan_out_embeddings,
    score_concepts,
)
from .repository import (
    create_run,
    fresh_db,
    get_active_run,
    get_latest_run,
    run_has_chunks,
    run_has_summaries,
    update_run,
)
from .state import ChunkingState

logger = logging.getLogger(__name__)


def build_chunking_graph():
    """Build the ChunkingComparison workflow graph."""
    builder = StateGraph(ChunkingState)

    builder.add_node("extract_pdf", extract_pdf)
    builder.add_node("chunk_paragraphs", chunk_paragraphs)
    builder.add_node("embed_single_book", embed_single_book)
    builder.add_node("embed_doc_summaries", embed_doc_summaries)
    builder.add_node("score_concepts", score_concepts)

    builder.add_edge(START, "extract_pdf")
    builder.add_edge("extract_pdf", "chunk_paragraphs")
    builder.add_conditional_edges(
        "chunk_paragraphs",
        fan_out_embeddings,
        ["embed_single_book", "embed_doc_summaries"],
    )
    builder.add_edge("embed_single_book", "score_concepts")
    builder.add_edge("embed_doc_summaries", "score_concepts")
    builder.add_edge("score_concepts", END)

    return builder.compile()


def create_run_and_launch(
    course_id: int,
    db: Session,
    background_tasks: BackgroundTasks,
) -> BookExtractionRun:
    """Create a BookExtractionRun and enqueue the workflow via BackgroundTasks."""
    active = get_active_run(course_id, db)
    if active:
        raise ValueError(
            f"An analysis run is already in progress (run {active.id}, "
            f"status={active.status.value})"
        )

    latest = get_latest_run(course_id, db)
    if (
        latest
        and latest.status
        in (ExtractionRunStatus.COMPLETED, ExtractionRunStatus.BOOK_PICKED)
        and run_has_chunks(latest.id, db)
        and not run_has_summaries(latest.id, db)
    ):
        update_run(
            db,
            latest.id,
            status=ExtractionRunStatus.SCORING,
            progress_detail="Queued scoring from stored chunk embeddings",
            error_message=None,
        )
        background_tasks.add_task(_run_scoring_only, latest.id, course_id)
        db.refresh(latest)
        return latest

    run = create_run(
        db,
        course_id=course_id,
        status=ExtractionRunStatus.PENDING,
        embedding_model=settings.embedding_model,
        embedding_dims=settings.embedding_dims or 2048,
        progress_detail="Queued",
    )

    background_tasks.add_task(_run_workflow, run.id, course_id)
    return run


def _run_workflow(run_id: int, course_id: int) -> None:
    """Execute the chunking workflow (called by BackgroundTasks)."""
    try:
        graph = build_chunking_graph()
        graph.invoke({"run_id": run_id, "course_id": course_id})
    except Exception as exc:
        logger.exception("Chunking workflow failed for run %d", run_id)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Failed",
            )


def _run_scoring_only(run_id: int, course_id: int) -> None:
    """Execute only scoring for a run that already has persisted chunk embeddings."""
    try:
        score_concepts({"run_id": run_id, "course_id": course_id})
    except Exception as exc:
        logger.exception("Scoring-only workflow failed for run %d", run_id)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Failed",
            )
