"""API routes for the book-selection feature (background tasks + polling)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    BookCandidateRead,
    CourseSelectedBookRead,
    ManualUploadResponse,
    SelectBooksRequest,
    SelectedBookManualUploadResponse,
    SessionRead,
    StartSessionRequest,
)
from .service import BookSelectionService, get_book_selection_service

router = APIRouter(prefix="/book-selection", tags=["book_selection"])


# ── helpers ─────────────────────────────────────────────────────


def _get_service(db: Session = Depends(get_db)) -> BookSelectionService:
    return get_book_selection_service(db)


# ── 1. POST  /book-selection/sessions ──────────────────────────


@router.post(
    "/sessions",
    response_model=SessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    course_id: int,
    body: StartSessionRequest,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Create a new book-selection session for a course."""
    return service.start_session(course_id, body)


# ── 2. POST  /book-selection/sessions/{session_id}/run ─────────


@router.post(
    "/sessions/{session_id}/run",
    response_model=SessionRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_discovery(
    session_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Kick off discovery + scoring in a background task.

    Returns immediately with 202. Poll GET /sessions/{id} for progress.
    """
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    asyncio.create_task(service.run_discovery_and_scoring(session_id))
    return service.get_session(session_id)


# ── 2b. POST /book-selection/sessions/{session_id}/resume ──────


@router.post(
    "/sessions/{session_id}/resume",
    response_model=SessionRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_scoring(
    session_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Resume scoring in a background task.

    Returns immediately with 202. Poll GET /sessions/{id} for progress.
    """
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    asyncio.create_task(service.resume_scoring(session_id))
    return service.get_session(session_id)


# ── 3. GET  /book-selection/sessions/{session_id} ──────────────


@router.get("/sessions/{session_id}", response_model=SessionRead)
def get_session(
    session_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Get session details and status."""
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


# ── 4. GET  /book-selection/sessions/{session_id}/books ────────


@router.get("/sessions/{session_id}/books", response_model=list[BookCandidateRead])
def get_session_books(
    session_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Get all candidate books for a session (scored/ranked)."""
    return service.get_session_books(session_id)


# ── 5. POST  /book-selection/sessions/{session_id}/select ──────


@router.post("/sessions/{session_id}/select", status_code=status.HTTP_202_ACCEPTED)
async def select_books(
    session_id: int,
    body: SelectBooksRequest,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Mark books as selected and start download phase in background.

    Returns immediately with 202. Poll GET /sessions/{id} for progress.
    """
    session = service.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    asyncio.create_task(service.run_select_and_download(session_id, body.book_ids))
    return {"status": "accepted", "session_id": session_id}


# ── 6. POST  /book-selection/sessions/{session_id}/books/{book_id}/upload ──


@router.post(
    "/sessions/{session_id}/books/{book_id}/upload",
    response_model=ManualUploadResponse,
)
async def upload_book(
    session_id: int,
    book_id: int,
    file: UploadFile,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Upload a book PDF manually (for failed-download fallback)."""
    try:
        return await service.upload_book_manually(session_id, book_id, file)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ── 7. POST  /book-selection/courses/{course_id}/books/upload ──


@router.post(
    "/courses/{course_id}/books/upload",
    response_model=BookCandidateRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_custom_book(
    course_id: int,
    file: UploadFile,
    title: str = Form(...),
    authors: str | None = Form(None),
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Upload a custom book not discovered by the agent."""
    try:
        return await service.upload_custom_book(course_id, file, title, authors)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e


# ── 8. GET  /book-selection/courses/{course_id}/books ──────────


@router.get(
    "/courses/{course_id}/books",
    response_model=list[BookCandidateRead],
)
def get_course_books(
    course_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Get all books associated with a course (from any session)."""
    return service.get_course_books(course_id)


# ── 9. GET  /book-selection/courses/{course_id}/session ────────


@router.get(
    "/courses/{course_id}/session",
    response_model=SessionRead | None,
)
def get_latest_session(
    course_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Get the latest session for a course (or null)."""
    return service.get_latest_session(course_id)


# ══════════════════════════════════════════════════════════════════
# Course Selected Books endpoints
# ══════════════════════════════════════════════════════════════════


# ── 10. GET  /book-selection/courses/{course_id}/selected-books ──


@router.get(
    "/courses/{course_id}/selected-books",
    response_model=list[CourseSelectedBookRead],
)
def get_course_selected_books(
    course_id: int,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Get all selected books for a course (from course_selected_books table)."""
    return service.get_course_selected_books(course_id)


# ── 11. POST  /book-selection/selected-books/{id}/upload ─────────


@router.post(
    "/selected-books/{selected_book_id}/upload",
    response_model=SelectedBookManualUploadResponse,
)
async def upload_to_selected_book(
    selected_book_id: int,
    file: UploadFile,
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Upload a PDF for a failed selected book."""
    try:
        return await service.upload_to_selected_book(selected_book_id, file)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# ── 12. POST  /book-selection/courses/{course_id}/selected-books/upload ──


@router.post(
    "/courses/{course_id}/selected-books/upload",
    response_model=CourseSelectedBookRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_custom_selected_book(
    course_id: int,
    file: UploadFile,
    title: str = Form(...),
    authors: str | None = Form(None),
    _teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: BookSelectionService = Depends(_get_service),
):
    """Upload a custom book directly to the course selected books."""
    try:
        return await service.upload_custom_selected_book(
            course_id, file, title, authors
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
