"""Book selection endpoints (sessions, scoring, downloads, uploads)."""

from __future__ import annotations

import asyncio

from fastapi import Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..schemas import (
    BookCandidateRead,
    CourseSelectedBookRead,
    ManualUploadResponse,
    SelectBooksRequest,
    SelectedBookManualUploadResponse,
    SessionRead,
    StartSessionRequest,
)
from ..service import BookSelectionService, get_book_selection_service


def _get_service(db: Session = Depends(get_db)) -> BookSelectionService:
    return get_book_selection_service(db)


def register_routes(router):
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
        return service.start_session(course_id, body)

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
        session = service.get_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        asyncio.create_task(service.run_discovery_and_scoring(session_id))
        return service.get_session(session_id)

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
        session = service.get_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        asyncio.create_task(service.resume_scoring(session_id))
        return service.get_session(session_id)

    @router.post(
        "/sessions/{session_id}/rediscover",
        response_model=SessionRead,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def rediscover_books(
        session_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        session = service.get_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.status not in ("awaiting_review", "failed"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot rediscover from status '{session.status}'",
            )
        asyncio.create_task(service.rediscover_books(session_id))
        return service.get_session(session_id)

    @router.get("/sessions/{session_id}", response_model=SessionRead)
    def get_session(
        session_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        session = service.get_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    @router.get("/sessions/{session_id}/books", response_model=list[BookCandidateRead])
    def get_session_books(
        session_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        return service.get_session_books(session_id)

    @router.post("/sessions/{session_id}/select", status_code=status.HTTP_202_ACCEPTED)
    async def select_books(
        session_id: int,
        body: SelectBooksRequest,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        session = service.get_session(session_id)
        if session is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        asyncio.create_task(service.run_select_and_download(session_id, body.book_ids))
        return {"status": "accepted", "session_id": session_id}

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
        try:
            return await service.upload_book_manually(session_id, book_id, file)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e

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
        try:
            return await service.upload_custom_book(course_id, file, title, authors)
        except ValueError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e

    @router.get(
        "/courses/{course_id}/books",
        response_model=list[BookCandidateRead],
    )
    def get_course_books(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        return service.get_course_books(course_id)

    @router.get(
        "/courses/{course_id}/session",
        response_model=SessionRead | None,
    )
    def get_latest_session(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        return service.get_latest_session(course_id)

    @router.get(
        "/courses/{course_id}/selected-books",
        response_model=list[CourseSelectedBookRead],
    )
    def get_course_selected_books(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        return service.get_course_selected_books(course_id)

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
        try:
            return await service.upload_to_selected_book(selected_book_id, file)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e

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
        try:
            return await service.upload_custom_selected_book(
                course_id, file, title, authors
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e

    @router.patch(
        "/selected-books/{selected_book_id}/ignore",
        response_model=CourseSelectedBookRead,
    )
    def ignore_selected_book(
        selected_book_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        service: BookSelectionService = Depends(_get_service),
    ):
        try:
            return service.ignore_selected_book(selected_book_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e)) from e
