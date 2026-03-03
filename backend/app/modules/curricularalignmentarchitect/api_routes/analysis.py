"""Chunking analysis endpoints."""

from __future__ import annotations

import asyncio
import json

from fastapi import BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..chunking_analysis.graph import create_run_and_launch
from ..chunking_analysis.repository import (
    fresh_db,
    get_chunk_embedding_progress,
    get_latest_run,
    get_summaries_for_run,
    pick_book,
)
from ..curriculum_graph.service import CurriculumGraphService
from ..models import BookExtractionRun
from ..schemas import BookAnalysisSummaryRead, BookExtractionRunRead


def register_routes(router):
    @router.post(
        "/courses/{course_id}/analysis",
        response_model=BookExtractionRunRead,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_analysis(
        course_id: int,
        background_tasks: BackgroundTasks,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        try:
            run = create_run_and_launch(course_id, db, background_tasks)
        except ValueError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return run

    @router.get(
        "/courses/{course_id}/analysis/latest",
        response_model=BookExtractionRunRead | None,
    )
    def get_latest_analysis(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        return get_latest_run(course_id, db)

    @router.get(
        "/courses/{course_id}/analysis/{run_id}/summaries",
        response_model=list[BookAnalysisSummaryRead],
    )
    def get_analysis_summaries(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )
        return get_summaries_for_run(run_id, db)

    @router.post(
        "/courses/{course_id}/analysis/{run_id}/pick/{selected_book_id}",
        response_model=BookExtractionRunRead,
    )
    def pick_analysis_book(
        course_id: int,
        run_id: int,
        selected_book_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        try:
            return pick_book(run_id, selected_book_id, db)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    @router.get("/courses/{course_id}/analysis/{run_id}/embedding-progress")
    async def stream_embedding_progress(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        """SSE stream of per-book chunk-embedding progress.

        Sends one JSON event every 2 seconds with the shape::

            {"status": "embedding", "books": [
                {"selected_book_id": 1, "title": "...",
                 "total_chunks": 900, "embedded_chunks": 450},
                ...
            ]}

        Stops automatically once the run leaves the embedding stage
        (completed, scoring, failed, etc.).

        Uses its own short-lived sessions so the request-scoped session
        is never held open for the entire SSE stream lifetime.
        """
        # Validate once — open and close a short-lived session immediately
        # so we never hold a pooled connection for the stream duration.
        with fresh_db() as db:
            run = db.get(BookExtractionRun, run_id)
            if run is None or run.course_id != course_id:
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
                )

        def _poll_progress() -> tuple[list[dict], str]:
            """Synchronous DB poll — executed in a worker thread."""
            with fresh_db() as session:
                progress = get_chunk_embedding_progress(run_id, session)
                current_run = session.get(BookExtractionRun, run_id)
                run_status = current_run.status.value if current_run else "failed"
            return progress, run_status

        async def event_stream():
            while True:
                progress, run_status = await asyncio.to_thread(_poll_progress)

                payload = json.dumps({"status": run_status, "books": progress})
                yield f"data: {payload}\n\n"

                if run_status not in (
                    "pending",
                    "extracting",
                    "chunking",
                    "embedding",
                ):
                    break

                await asyncio.sleep(2)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post(
        "/courses/{course_id}/analysis/{run_id}/build-curriculum/{selected_book_id}",
    )
    async def build_curriculum(
        course_id: int,
        run_id: int,
        selected_book_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        """Stream curriculum graph construction progress via SSE."""
        service = CurriculumGraphService()

        async def sse_generator():
            async for event in service.build_curriculum(
                course_id, run_id, selected_book_id
            ):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
