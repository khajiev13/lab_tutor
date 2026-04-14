"""Chapter-level analysis endpoints.

Serves pre-computed chapter-level concept-to-concept similarity data
for the recommendation dashboard.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..chapter_extraction.scoring import (
    compute_all_books_chapter_analysis,
    get_chapter_summaries_for_run,
)
from ..models import BookExtractionRun
from ..schemas import ChapterAnalysisSummaryRead


def register_routes(router):
    @router.post(
        "/courses/{course_id}/analysis/{run_id}/chapter-scoring",
        response_model=list[ChapterAnalysisSummaryRead],
    )
    def trigger_chapter_scoring(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ) -> list[ChapterAnalysisSummaryRead]:
        """Compute chapter-level concept similarity for all books in a run.

        Reads from BookChapter → BookSection → BookConcept and
        CourseConceptCache tables; computes cosine similarities and
        persists ChapterAnalysisSummary rows.
        """
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )
        try:
            summaries = compute_all_books_chapter_analysis(run_id, db)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return summaries

    @router.get(
        "/courses/{course_id}/analysis/{run_id}/chapter-summaries",
        response_model=list[ChapterAnalysisSummaryRead],
    )
    def get_chapter_summaries(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ) -> list[ChapterAnalysisSummaryRead]:
        """Return pre-computed chapter-level analysis summaries for a run."""
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )
        return get_chapter_summaries_for_run(run_id, db)
