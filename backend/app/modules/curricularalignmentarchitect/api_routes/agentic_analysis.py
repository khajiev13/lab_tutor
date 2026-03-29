"""Agentic chapter extraction streaming endpoint.

POST /courses/{course_id}/analysis/{run_id}/agentic

Runs the LangGraph chapter extraction pipeline for each selected book
(sequentially, 5 parallel chapter workers per book) and streams
real-time progress events as SSE.

Chapters are read from SQL (stored during the shared PDF extraction step)
instead of re-downloading and re-extracting PDFs.
"""

from __future__ import annotations

import asyncio
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
from ..chapter_extraction.repository import (
    fresh_db,
    get_completed_chapter_indices,
    update_run,
)
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
            ExtractionRunStatus.FAILED,  # Allow retry if a previous background run failed
            ExtractionRunStatus.AGENTIC_EXTRACTING,  # Allow resume of cancelled run
        }
        if run.status not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Run status is '{run.status.value}' — "
                    "agentic extraction requires 'completed', 'book_picked', or 'failed'."
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

        import asyncio

        q: asyncio.Queue[str | None] = asyncio.Queue()
        # Start the heavy extraction in a background task shielded from HTTP cancellation
        asyncio.create_task(
            _run_extraction_background(run_id, course_id, books_meta, course_subject, q)
        )

        async def stream_from_queue():
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    yield item
            except asyncio.CancelledError:
                # Client disconnected (e.g., timeout). Background task keeps running!
                logger.info(
                    "Client disconnected from SSE; background extraction continues."
                )

        return StreamingResponse(
            stream_from_queue(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


async def _run_extraction_background(
    run_id: int,
    course_id: int,
    books_meta: list[dict],
    course_subject: str,
    queue: asyncio.Queue[str | None],
):
    """Background task for extraction, shielded from client disconnects."""
    import asyncio

    # Mark run as agentic_extracting
    def _mark_status(
        s: ExtractionRunStatus, detail: str | None = None, error: str | None = None
    ):
        with fresh_db() as db:
            kwargs: dict = {"status": s}
            if detail is not None:
                kwargs["progress_detail"] = detail
            if error is not None:
                kwargs["error_message"] = error
            update_run(db, run_id, **kwargs)

    _mark_status(
        ExtractionRunStatus.AGENTIC_EXTRACTING,
        detail=f"Starting agentic extraction for {len(books_meta)} book(s)…",
    )

    total_books = len(books_meta)
    grand_total_chapters = 0
    grand_total_concepts = 0

    try:
        for book_idx, book in enumerate(books_meta):
            book_id = book["id"]
            book_title = book["title"]

            # Notify frontend immediately so it can show the book card
            await queue.put(
                _sse(
                    "loading_book",
                    {
                        "book_id": book_id,
                        "book_title": book_title,
                        "book_index": book_idx,
                        "total_books": total_books,
                    },
                )
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
                await queue.put(
                    _sse(
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
                )
                continue

            total_chapters = len(chapters)
            grand_total_chapters += total_chapters

            # Resume support: skip chapters already saved from a previous run
            def _load_completed_indices(_bid=book_id):
                with fresh_db() as db:
                    return get_completed_chapter_indices(run_id, _bid, db)

            completed_indices = await asyncio.to_thread(_load_completed_indices)
            pending_chapters = [
                ch for ch in chapters if ch["chapter_number"] not in completed_indices
            ]

            if not pending_chapters:
                # All chapters already done — skip pipeline entirely
                logger.info(
                    "Book '%s': all %d chapters already completed, skipping pipeline.",
                    book_title,
                    total_chapters,
                )
                await queue.put(
                    _sse(
                        "book_completed",
                        {
                            "book_id": book_id,
                            "book_title": book_title,
                            "book_index": book_idx,
                            "total_books": total_books,
                            "chapters_done": total_chapters,
                            "total_chapters": total_chapters,
                            "total_concepts": 0,
                            "resumed": True,
                        },
                    )
                )
                continue

            if completed_indices:
                logger.info(
                    "Book '%s': resuming — %d/%d chapters already done, %d remaining.",
                    book_title,
                    len(completed_indices),
                    total_chapters,
                    len(pending_chapters),
                )

            await queue.put(
                _sse(
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
            )

            _mark_status(
                ExtractionRunStatus.AGENTIC_EXTRACTING,
                f"Book {book_idx + 1}/{total_books}: {book_title} "
                f"({len(pending_chapters)}/{total_chapters} chapters remaining)",
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
                    "chapters": pending_chapters,
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
                    await queue.put(_sse(event_type, chunk))

                    if event_type == "chapter_completed":
                        chapters_done += 1
                        book_concepts += chunk.get("concept_count", 0)

                elif mode == "updates":
                    # Just track completion — don't forward raw state
                    pass

            grand_total_concepts += book_concepts

            await queue.put(
                _sse(
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
            )

        # All books done
        _mark_status(
            ExtractionRunStatus.AGENTIC_COMPLETED,
            detail=f"Agentic extraction completed: {grand_total_chapters} chapters, "
            f"{grand_total_concepts} concepts from {total_books} book(s).",
        )

        # Auto-trigger book skill mapping now that skills are extracted
        await queue.put(_sse("skill_mapping_started", {"course_id": course_id}))
        try:
            from ..book_skill_mapping.graph import build_book_skill_mapping_graph

            mapping_graph = build_book_skill_mapping_graph()
            async for mode, chunk in mapping_graph.astream(
                {"course_id": course_id, "mappings": [], "errors": []},
                stream_mode=["custom", "updates"],
                config={"max_concurrency": 5},
            ):
                if mode == "custom":
                    event_type = chunk.get("type", "skill_mapping_progress")
                    chunk["auto_triggered"] = True
                    await queue.put(_sse(event_type, chunk))
        except Exception as e:
            logger.warning(
                "Auto book skill mapping failed for course %d: %s", course_id, e
            )
            # Don't fail the whole extraction — mapping is best-effort

        await queue.put(
            _sse(
                "done",
                {
                    "total_books": total_books,
                    "total_chapters": grand_total_chapters,
                    "total_concepts": grand_total_concepts,
                },
            )
        )
        await queue.put(None)  # EOF
    except asyncio.CancelledError:
        # Task was explicitly cancelled, propagate it to ensure clean resource release
        logger.info("Background extraction task was cancelled.")
        await queue.put(None)
    except Exception as e:
        logger.exception("Agentic extraction failed for run %d", run_id)
        _mark_status(
            ExtractionRunStatus.FAILED, detail="Agentic extraction error", error=str(e)
        )
        await queue.put(_sse("error", {"message": str(e)[:500]}))
        await queue.put(None)


def _sse(event: str, data: dict) -> str:
    """Format a named SSE event.

    Always injects ``type`` into the data dict so that the frontend
    can discriminate events from the JSON payload alone (the frontend
    SSE parser only reads ``data:`` lines, not ``event:`` lines).
    """
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
