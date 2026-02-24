"""Chunking analysis endpoints."""

from __future__ import annotations

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..chunking_analysis.graph import create_run_and_launch
from ..chunking_analysis.repository import (
    get_latest_run,
    get_summaries_for_run,
    pick_book,
)
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
