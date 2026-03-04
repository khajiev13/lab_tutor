"""Agentic chapter extraction streaming endpoint.

POST /courses/{course_id}/analysis/{run_id}/agentic

Runs the LangGraph chapter extraction pipeline for each selected book
(sequentially, 5 parallel chapter workers per book) and streams
real-time progress events as SSE.

Chapters are read from SQL (stored during the shared PDF extraction step)
instead of re-downloading and re-extracting PDFs.
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course

from ..chapter_extraction.graph import build_book_pipeline_graph
from ..chapter_extraction.repository import fresh_db, update_run
from ..chapter_extraction.state import BOOK_PIPELINE_MAX_CONCURRENCY
from ..chunking_analysis.repository import get_chapters_for_book
from ..models import (
    BookExtractionRun,
    CourseSelectedBook,
    ExtractionRunStatus,
)

logger = logging.getLogger(__name__)


def register_routes(router):
    @router.post("/courses/{course_id}/analysis/{run_id}/agentic")
    async def start_agentic_extraction(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        """Start agentic chapter extraction and stream SSE progress events.

        Processes each selected book sequentially. Within each book,
        5 chapter workers run in parallel via LangGraph's Send API.

        SSE event types:
          - ``book_started``       — new book starting, includes chapter count
          - ``agent_status``       — worker progress (extracting/evaluated/skills)
          - ``chapter_completed``  — one chapter done
          - ``chapter_error``      — one chapter failed
          - ``book_completed``     — all chapters for one book done
          - ``done``               — entire pipeline finished
          - ``error``              — fatal error, pipeline aborted
        """
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )

        # Only allow starting agentic extraction after chunking is done
        allowed = {
            ExtractionRunStatus.COMPLETED,
            ExtractionRunStatus.BOOK_PICKED,
            ExtractionRunStatus.AGENTIC_COMPLETED,
        }
        if run.status not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Run status is '{run.status.value}' — "
                    "agentic extraction requires 'completed' or 'book_picked'."
                ),
            )

        selected_books = (
            db.query(CourseSelectedBook)
            .filter(
                CourseSelectedBook.course_id == course_id,
                CourseSelectedBook.blob_path.isnot(None),
            )
            .all()
        )
        if not selected_books:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="No selected books with uploaded PDFs found.",
            )

        # Snapshot book metadata before entering async generator
        books_meta = [
            {"id": sb.id, "title": sb.title, "blob_path": sb.blob_path}
            for sb in selected_books
        ]

        # Fetch course subject (title) for domain-scoped extraction prompts
        course = db.get(Course, course_id)
        course_subject = course.title if course else "General"

        return StreamingResponse(
            _sse_generator(run_id, course_id, books_meta, course_subject),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


async def _sse_generator(
    run_id: int,
    course_id: int,
    books_meta: list[dict],
    course_subject: str,
):
    """Async generator that yields SSE-formatted strings.

    Processes books sequentially; within each book, the LangGraph
    pipeline fans out up to 5 chapter workers in parallel.
    """
    import asyncio

    # Mark run as agentic_extracting
    def _mark_status(s: ExtractionRunStatus, detail: str | None = None):
        with fresh_db() as db:
            kwargs: dict = {"status": s}
            if detail is not None:
                kwargs["progress_detail"] = detail
            update_run(db, run_id, **kwargs)

    _mark_status(
        ExtractionRunStatus.AGENTIC_EXTRACTING,
        f"Starting agentic extraction for {len(books_meta)} book(s)…",
    )

    total_books = len(books_meta)
    grand_total_chapters = 0
    grand_total_concepts = 0

    try:
        for book_idx, book in enumerate(books_meta):
            book_id = book["id"]
            book_title = book["title"]

            # Notify frontend immediately so it can show the book card
            yield _sse(
                "loading_book",
                {
                    "book_id": book_id,
                    "book_title": book_title,
                    "book_index": book_idx,
                    "total_books": total_books,
                },
            )

            # Read chapters from SQL (stored during shared extraction step)
            def _load_chapters(_bid=book_id):
                with fresh_db() as db:
                    rows = get_chapters_for_book(run_id, _bid, db)
                    return [
                        {
                            "chapter_number": ch.chapter_index,
                            "title": ch.chapter_title,
                            "sections": [
                                {
                                    "title": sec.section_title,
                                    "content": sec.section_content or "",
                                }
                                for sec in sorted(
                                    ch.sections, key=lambda s: s.section_index
                                )
                            ],
                            "content": ch.chapter_text or "",
                        }
                        for ch in rows
                    ]

            chapters = await asyncio.to_thread(_load_chapters)

            if not chapters:
                yield _sse(
                    "book_started",
                    {
                        "book_id": book_id,
                        "book_title": book_title,
                        "book_index": book_idx,
                        "total_books": total_books,
                        "total_chapters": 0,
                        "message": "No chapters detected in TOC.",
                    },
                )
                continue

            total_chapters = len(chapters)
            grand_total_chapters += total_chapters

            yield _sse(
                "book_started",
                {
                    "book_id": book_id,
                    "book_title": book_title,
                    "book_index": book_idx,
                    "total_books": total_books,
                    "total_chapters": total_chapters,
                    "chapter_titles": [ch["title"] for ch in chapters],
                },
            )

            _mark_status(
                ExtractionRunStatus.AGENTIC_EXTRACTING,
                f"Book {book_idx + 1}/{total_books}: {book_title} "
                f"({total_chapters} chapters)",
            )

            # Build and stream the pipeline graph
            pipeline = build_book_pipeline_graph()
            book_concepts = 0
            chapters_done = 0

            async for mode, chunk in pipeline.astream(
                {
                    "run_id": run_id,
                    "selected_book_id": book_id,
                    "course_subject": course_subject,
                    "book_name": book_title,
                    "book_label": book_title.replace(".pdf", ""),
                    "chapters": chapters,
                    "total_chapters": total_chapters,
                    "completed_chapters": [],
                    "errors": [],
                },
                stream_mode=["custom", "updates"],
                config={
                    "max_concurrency": BOOK_PIPELINE_MAX_CONCURRENCY,
                    "recursion_limit": 200,
                },
            ):
                if mode == "custom":
                    # Progress from get_stream_writer() in chapter_worker
                    event_type = chunk.get("type", "agent_status")
                    chunk["book_id"] = book_id
                    chunk["book_index"] = book_idx
                    yield _sse(event_type, chunk)

                    if event_type == "chapter_completed":
                        chapters_done += 1
                        book_concepts += chunk.get("concept_count", 0)

                elif mode == "updates":
                    # Just track completion — don't forward raw state
                    pass

            grand_total_concepts += book_concepts

            yield _sse(
                "book_completed",
                {
                    "book_id": book_id,
                    "book_title": book_title,
                    "book_index": book_idx,
                    "total_books": total_books,
                    "chapters_done": chapters_done,
                    "total_chapters": total_chapters,
                    "total_concepts": book_concepts,
                },
            )

        # All books done
        _mark_status(
            ExtractionRunStatus.AGENTIC_COMPLETED,
            f"Agentic extraction completed: {grand_total_chapters} chapters, "
            f"{grand_total_concepts} concepts from {total_books} book(s).",
        )

        yield _sse(
            "done",
            {
                "total_books": total_books,
                "total_chapters": grand_total_chapters,
                "total_concepts": grand_total_concepts,
            },
        )

    except Exception as e:
        logger.exception("Agentic extraction failed for run %d", run_id)
        _mark_status(ExtractionRunStatus.FAILED, f"Agentic extraction error: {e}")
        yield _sse("error", {"message": str(e)[:500]})


def _sse(event: str, data: dict) -> str:
    """Format a named SSE event.

    Always injects ``type`` into the data dict so that the frontend
    can discriminate events from the JSON payload alone (the frontend
    SSE parser only reads ``data:`` lines, not ``event:`` lines).
    """
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
