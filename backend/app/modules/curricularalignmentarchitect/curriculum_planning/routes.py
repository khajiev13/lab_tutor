from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import require_neo4j_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course

from .schemas import ChapterPlanResponse, SaveChapterPlanRequest
from .service import TeacherCurriculumPlanner

router = APIRouter(prefix="/courses", tags=["chapter_plan"])


def _get_owned_course(course_id: int, teacher: User, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None or course.teacher_id != teacher.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


@router.post(
    "/{course_id}/chapter-plan/generate",
    response_model=ChapterPlanResponse,
)
def generate_chapter_plan(
    course_id: int,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> ChapterPlanResponse:
    course = _get_owned_course(course_id, teacher, db)
    planner = TeacherCurriculumPlanner(neo4j_session)
    return planner.generate_plan(course_id, course.title)


@router.get(
    "/{course_id}/chapter-plan",
    response_model=ChapterPlanResponse,
)
def get_chapter_plan(
    course_id: int,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> ChapterPlanResponse:
    _get_owned_course(course_id, teacher, db)
    planner = TeacherCurriculumPlanner(neo4j_session)
    return planner.get_plan(course_id)


@router.put(
    "/{course_id}/chapter-plan",
    response_model=ChapterPlanResponse,
)
def save_chapter_plan(
    course_id: int,
    body: SaveChapterPlanRequest,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    db: Session = Depends(get_db),
    neo4j_session: Neo4jSession = Depends(require_neo4j_session),
) -> ChapterPlanResponse:
    _get_owned_course(course_id, teacher, db)
    planner = TeacherCurriculumPlanner(neo4j_session)
    return planner.save_plan(course_id, body.chapters)
