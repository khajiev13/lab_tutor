"""SSE endpoint for skill prerequisite pipeline.

POST /courses/{course_id}/skill-prerequisites/build
GET  /courses/{course_id}/skill-prerequisites
"""

from __future__ import annotations

import asyncio
import json

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import create_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.courses.repository import CourseRepository

from ..skill_prerequisites.repository import get_skill_prerequisites
from ..skill_prerequisites.review_repository import PrerequisiteReviewRepository
from ..skill_prerequisites.review_service import (
    Neo4jPrerequisiteReviewRepository,
    PrerequisiteReviewService,
)
from ..skill_prerequisites.schemas import (
    PrerequisiteReviewRead,
    PrerequisiteReviewUpdate,
)
from ..skill_prerequisites.service import (
    run_skill_prerequisites,
    schedule_skill_prerequisite_rebuild,
)


def _review_service(db: Session) -> PrerequisiteReviewService:
    driver = create_neo4j_driver()
    if driver is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is not configured",
        )
    return PrerequisiteReviewService(
        CourseRepository(db),
        PrerequisiteReviewRepository(db),
        Neo4jPrerequisiteReviewRepository(driver),
    )


def _require_teacher_course(db: Session, course_id: int, teacher_id: int) -> None:
    course = CourseRepository(db).get_by_id(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="Course access denied")


def register_routes(router):
    @router.post("/courses/{course_id}/skill-prerequisites/build")
    async def build_skill_prerequisites(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        _require_teacher_course(db, course_id, teacher.id)
        PrerequisiteReviewRepository(db).mark_rebuilding(course_id)
        db.commit()

        q: asyncio.Queue[str | None] = asyncio.Queue()
        asyncio.create_task(_run_background(course_id, q))

        async def stream():
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    yield item
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/courses/{course_id}/skill-prerequisites")
    def get_prerequisites(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        driver = create_neo4j_driver()
        if driver is None:
            return {"edges": []}
        edges = get_skill_prerequisites(driver, course_id)
        driver.close()
        return {"edges": edges}

    @router.get(
        "/courses/{course_id}/skill-prerequisites/review",
        response_model=PrerequisiteReviewRead,
    )
    def get_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        try:
            service.require_teacher(course_id, teacher.id)
            review = service.get_review(course_id)
            db.commit()
            return review
        finally:
            service.close()

    @router.put(
        "/courses/{course_id}/skill-prerequisites/review",
        response_model=PrerequisiteReviewRead,
    )
    def save_prerequisite_review(
        course_id: int,
        update: PrerequisiteReviewUpdate,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        try:
            service.require_teacher(course_id, teacher.id)
            review = service.save_teacher_draft(
                course_id,
                update.draft_edges,
                update.isolated_skills_viewed,
            )
            db.commit()
            return review
        finally:
            service.close()

    @router.post(
        "/courses/{course_id}/skill-prerequisites/approve",
        response_model=PrerequisiteReviewRead,
    )
    def approve_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        service = _review_service(db)
        try:
            review = service.approve(course_id, teacher.id)
            db.commit()
            return review
        finally:
            service.close()

    @router.post(
        "/courses/{course_id}/skill-prerequisites/regenerate",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def regenerate_prerequisite_review(
        course_id: int,
        teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
    ):
        _require_teacher_course(db, course_id, teacher.id)
        PrerequisiteReviewRepository(db).mark_rebuilding(course_id)
        db.commit()
        schedule_skill_prerequisite_rebuild(course_id, "manual_regenerate")
        return {"message": "Skill prerequisite regeneration scheduled"}


async def _run_background(course_id: int, queue: asyncio.Queue[str | None]):
    async def emit_event(event_type: str, payload: dict) -> None:
        await queue.put(_sse(event_type, payload))

    await run_skill_prerequisites(course_id, emit_event=emit_event)
    await queue.put(None)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"
