"""Student Learning Path API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import fastapi_users, require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    BuildLearningPathRequest,
    DeselectJobPostingRequest,
    DeselectSkillsRequest,
    LearningPathResponse,
    SelectJobPostingsRequest,
    SelectSkillsRequest,
    StudentSkillBankResponse,
)
from .service import StudentLearningPathService, get_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student-learning-path", tags=["student-learning-path"])

StudentDep = Annotated[User, Depends(require_role(UserRole.STUDENT))]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]
DbDep = Annotated[Session, Depends(get_db)]


def _get_service(db: DbDep, driver: Neo4jDep) -> StudentLearningPathService:
    if driver is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j is not configured"
        )
    return StudentLearningPathService(db, driver)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps({"type": event, **data}, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ── Skill Banks ──────────────────────────────────────────────


@router.get("/{course_id}/skill-banks", response_model=StudentSkillBankResponse)
def get_skill_banks(
    course_id: int,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> StudentSkillBankResponse:
    """Skill banks with selection overlay + peer counts."""
    service = _get_service(db, driver)
    return service.get_skill_banks(student.id, course_id)


# ── Skill Selection ──────────────────────────────────────────


@router.post("/{course_id}/select-skills", status_code=status.HTTP_200_OK)
def select_skills(
    course_id: int,
    body: SelectSkillsRequest,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict:
    """Select book or market skills."""
    service = _get_service(db, driver)
    count = service.select_skills(student.id, course_id, body.skill_names, body.source)
    return {"selected": count}


@router.delete("/{course_id}/deselect-skills")
def deselect_skills(
    course_id: int,
    body: DeselectSkillsRequest,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict:
    """Deselect skills."""
    service = _get_service(db, driver)
    count = service.deselect_skills(student.id, course_id, body.skill_names)
    return {"deselected": count}


# ── Job Posting Selection ────────────────────────────────────


@router.post("/{course_id}/select-job-postings", status_code=status.HTTP_200_OK)
def select_job_postings(
    course_id: int,
    body: SelectJobPostingsRequest,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict:
    """Select job postings (creates transitive SELECTED_SKILL)."""
    service = _get_service(db, driver)
    count = service.select_job_postings(student.id, course_id, body.posting_urls)
    return {"postings_linked": count}


@router.delete("/{course_id}/deselect-job-posting")
def deselect_job_posting(
    course_id: int,
    body: DeselectJobPostingRequest,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict:
    """Remove job posting interest + orphaned skills."""
    service = _get_service(db, driver)
    count = service.deselect_job_posting(student.id, course_id, body.posting_url)
    return {"orphans_deleted": count}


# ── Build Learning Path ──────────────────────────────────────


@router.post("/{course_id}/build", status_code=status.HTTP_202_ACCEPTED)
async def build_learning_path(
    course_id: int,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
    body: BuildLearningPathRequest | None = None,
) -> dict:
    """'Build My Learning Path' — launches LangGraph pipeline. Returns run_id."""
    service = _get_service(db, driver)
    try:
        run_id, _ = await service.build_learning_path(
            student.id,
            course_id,
            body.selected_skills if body else [],
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"run_id": run_id, "status": "started"}


@router.get("/{course_id}/build/stream/{run_id}")
async def stream_build_progress(
    course_id: int,
    run_id: str,
    token: str | None = None,
    _user: User | None = Depends(
        fastapi_users.current_user(active=True, optional=True)
    ),
):
    """SSE stream of build progress events.

    EventSource cannot set Authorization headers, so the frontend passes the
    JWT as a ``?token=`` query parameter.  We first try the standard Bearer
    header (via optional ``current_user``) and fall back to validating the
    query-string token manually.
    """
    if _user is None and token:
        import jwt as pyjwt

        from app.core.settings import settings as _settings

        try:
            payload = pyjwt.decode(
                token,
                _settings.secret_key,
                algorithms=[_settings.algorithm],
                audience="fastapi-users:auth",
            )
            user_id = int(payload["sub"])
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

                user_db = SQLAlchemyUserDatabase(session, User)
                _user = await user_db.get(user_id)
        except Exception:
            logger.warning("SSE token validation failed for run %s", run_id)

    if _user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    queue = get_queue(run_id)
    if queue is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Run not found")

    async def _generate() -> AsyncGenerator[str, None]:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue

            if item is None:
                yield _sse("stream_end", {})
                break

            event_type = item.get("type", "skill_progress")
            yield _sse(event_type, item)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Run-Id": run_id,
        },
    )


# ── Read Learning Path ───────────────────────────────────────


@router.get("/{course_id}/path", response_model=LearningPathResponse)
def get_learning_path(
    course_id: int,
    student: StudentDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict:
    """Read the personalized learning path."""
    service = _get_service(db, driver)
    return service.get_learning_path(student.id, course_id)
