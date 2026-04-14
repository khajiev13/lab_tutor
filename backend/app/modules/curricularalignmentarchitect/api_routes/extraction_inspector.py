"""Extraction inspector endpoints — human-in-the-loop PDF review.

Allows teachers to:
1. Trigger extraction-only (stop after chapter extraction, before chunking)
2. Preview extracted chapters/sections/content
3. Approve extraction to continue the pipeline
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.settings import settings
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..chunking_analysis.nodes import extract_pdf
from ..chunking_analysis.repository import (
    fresh_db,
    get_chapters_for_book,
    update_run,
)
from ..chunking_analysis.workflow import (
    _run_chunking_from_chapters,
)
from ..chunking_analysis.workflow import (
    create_run as create_run_row,
)
from ..models import (
    BookExtractionRun,
    CourseSelectedBook,
    ExtractionRunStatus,
)
from ..schemas import BookExtractionRunRead

logger = logging.getLogger(__name__)


def register_routes(router):
    @router.post(
        "/courses/{course_id}/analysis/extract-only",
        response_model=BookExtractionRunRead,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def trigger_extraction_only(
        course_id: int,
        background_tasks: BackgroundTasks,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        """Start PDF extraction only — stops at CHAPTER_EXTRACTED for inspection."""
        active = (
            db.query(BookExtractionRun)
            .filter(
                BookExtractionRun.course_id == course_id,
                BookExtractionRun.status.in_(
                    [
                        ExtractionRunStatus.PENDING,
                        ExtractionRunStatus.EXTRACTING,
                        ExtractionRunStatus.CHUNKING,
                        ExtractionRunStatus.EMBEDDING,
                        ExtractionRunStatus.SCORING,
                    ]
                ),
            )
            .first()
        )
        if active:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"An analysis run is already in progress (run {active.id}).",
            )

        # Check if there's already a CHAPTER_EXTRACTED run we can reuse
        existing = (
            db.query(BookExtractionRun)
            .filter(
                BookExtractionRun.course_id == course_id,
                BookExtractionRun.status == ExtractionRunStatus.CHAPTER_EXTRACTED,
            )
            .order_by(BookExtractionRun.id.desc())
            .first()
        )
        if existing:
            return BookExtractionRunRead.model_validate(existing)

        run = create_run_row(
            db,
            course_id=course_id,
            status=ExtractionRunStatus.PENDING,
            embedding_model=settings.embedding_model,
            embedding_dims=settings.embedding_dims or 2048,
            progress_detail="Queued — extraction only",
        )

        background_tasks.add_task(_run_extraction_only, run.id, course_id)
        return BookExtractionRunRead.model_validate(run)

    @router.get(
        "/courses/{course_id}/analysis/{run_id}/extraction-preview",
    )
    def get_extraction_preview(
        course_id: int,
        run_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        """Return extracted chapters with sections and content for inspection."""
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )

        # Allow preview at any status after extraction
        if run.status == ExtractionRunStatus.PENDING:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Extraction has not started yet.",
            )

        selected_books = (
            db.query(CourseSelectedBook)
            .filter(
                CourseSelectedBook.course_id == course_id,
                CourseSelectedBook.blob_path.isnot(None),
            )
            .all()
        )

        books_preview = []
        for sb in selected_books:
            chapters = get_chapters_for_book(run_id, sb.id, db)
            chapters_data = []
            total_sections = 0
            total_content_chars = 0

            for ch in chapters:
                sections_data = []
                for sec in sorted(ch.sections, key=lambda s: s.section_index):
                    content = sec.section_content or ""
                    sections_data.append(
                        {
                            "section_title": sec.section_title,
                            "section_index": sec.section_index,
                            "content": content,
                            "content_length": len(content),
                            "has_content": len(content.strip()) > 0,
                        }
                    )
                    total_content_chars += len(content)

                total_sections += len(sections_data)
                chapter_content = ch.chapter_text or ""
                chapters_data.append(
                    {
                        "chapter_title": ch.chapter_title,
                        "chapter_index": ch.chapter_index,
                        "content": chapter_content,
                        "content_length": len(chapter_content),
                        "sections": sections_data,
                        "section_count": len(sections_data),
                        "has_content": len(chapter_content.strip()) > 0,
                    }
                )

            books_preview.append(
                {
                    "book_id": sb.id,
                    "book_title": sb.title,
                    "authors": sb.authors,
                    "status": sb.status.value if sb.status else None,
                    "chapters": chapters_data,
                    "total_chapters": len(chapters_data),
                    "total_sections": total_sections,
                    "total_content_chars": total_content_chars,
                }
            )

        return {
            "run_id": run_id,
            "run_status": run.status.value,
            "progress_detail": run.progress_detail,
            "books": books_preview,
        }

    @router.post(
        "/courses/{course_id}/analysis/{run_id}/approve-extraction",
        response_model=BookExtractionRunRead,
    )
    async def approve_extraction(
        course_id: int,
        run_id: int,
        background_tasks: BackgroundTasks,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        """Approve extracted chapters and continue to chunking pipeline."""
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )

        allowed = {
            ExtractionRunStatus.CHAPTER_EXTRACTED,
            ExtractionRunStatus.COMPLETED,
            ExtractionRunStatus.BOOK_PICKED,
        }
        if run.status not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Run status is '{run.status.value}' — "
                    "can only approve at 'chapter_extracted', 'completed', or 'book_picked'."
                ),
            )

        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.CHUNKING,
            progress_detail="Approved by teacher — starting chunking…",
            error_message=None,
        )
        db.refresh(run)

        background_tasks.add_task(_run_chunking_from_chapters, run_id, course_id)
        return BookExtractionRunRead.model_validate(run)


def _run_extraction_only(run_id: int, course_id: int) -> None:
    """Execute only the PDF extraction step, then stop."""
    try:
        extract_pdf({"run_id": run_id, "course_id": course_id})
        # Status is already set to CHAPTER_EXTRACTED by extract_pdf node
    except Exception as exc:
        logger.exception("Extraction-only failed for run %d", run_id)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Extraction failed",
            )
