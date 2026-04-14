"""Cognitive Diagnosis — FastAPI routes.

New endpoints under /diagnosis/:
  POST /diagnosis/mastery/{user_id}           — compute + store mastery
  GET  /diagnosis/mastery/{user_id}           — read cached mastery
  GET  /diagnosis/path/{user_id}/{course_id}  — PathGen learning path
  POST /diagnosis/review/{user_id}/{course_id}— RevFell review session
  POST /diagnosis/exercise/{user_id}          — AdaEx adaptive exercise
  GET  /diagnosis/portfolio/{user_id}/{course_id} — full portfolio
  POST /diagnosis/interactions                — log ATTEMPTED event
  POST /diagnosis/engagements                 — log ENGAGES_WITH event
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Driver as Neo4jDriver

from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    ExerciseRequest,
    ExerciseResponse,
    LearningPathDiagnosisResponse,
    LogEngagementRequest,
    LogInteractionRequest,
    MasteryResponse,
    PortfolioResponse,
    ReviewRequest,
    ReviewResponse,
    StudentEventCreate,
    StudentEventResponse,
    StudentEventsListResponse,
    WhatIfAnalysisRequest,
    WhatIfAnalysisResponse,
)
from .service import CognitiveDiagnosisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["cognitive-diagnosis"])

StudentDep = Annotated[User, Depends(require_role(UserRole.STUDENT))]
AnyUserDep = Annotated[User, Depends(require_role(UserRole.STUDENT))]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]


def _get_service(driver: Neo4jDep) -> CognitiveDiagnosisService:
    if driver is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail="Neo4j is not configured"
        )
    return CognitiveDiagnosisService(driver)


# ── Mastery ────────────────────────────────────────────────────────────────


@router.post(
    "/mastery/{course_id}",
    response_model=MasteryResponse,
    summary="Compute and store per-skill mastery",
)
def compute_mastery(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
) -> MasteryResponse:
    """Run ARCD inference for the current student, write MASTERY_OF edges to KG."""
    svc = _get_service(driver)
    return svc.compute_and_store_mastery(student.id, course_id)


@router.get(
    "/mastery/{course_id}",
    response_model=MasteryResponse,
    summary="Read cached mastery from KG",
)
def get_mastery(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
) -> MasteryResponse:
    """Return the most recent MASTERY_OF snapshot stored in the KG."""
    svc = _get_service(driver)
    return svc.get_mastery(student.id, course_id)


# ── Learning Path ──────────────────────────────────────────────────────────


@router.get(
    "/path/{course_id}",
    response_model=LearningPathDiagnosisResponse,
    summary="Generate ZPD-calibrated learning path (PathGen)",
)
def get_learning_path(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
    path_length: int = 8,
) -> LearningPathDiagnosisResponse:
    """Use PathGen to generate a personalized learning path from current mastery."""
    svc = _get_service(driver)
    return svc.generate_path(student.id, course_id, path_length=path_length)


# ── Review ─────────────────────────────────────────────────────────────────


@router.post(
    "/review/{course_id}",
    response_model=ReviewResponse,
    summary="RevFell: PCO detection + urgency-based review",
)
def review_session(
    course_id: int,
    body: ReviewRequest,
    student: StudentDep,
    driver: Neo4jDep,
) -> ReviewResponse:
    """Detect confused/forgotten skills and produce a prioritised review queue."""
    svc = _get_service(driver)
    return svc.review_session(student.id, course_id, top_k=body.top_k)


# ── Exercise ───────────────────────────────────────────────────────────────


@router.post(
    "/exercise",
    response_model=ExerciseResponse,
    summary="AdaEx: generate adaptive exercise for a skill",
)
def generate_exercise(
    body: ExerciseRequest,
    student: StudentDep,
    driver: Neo4jDep,
) -> ExerciseResponse:
    """Generate a quality-gated adaptive exercise calibrated to student mastery."""
    svc = _get_service(driver)
    return svc.generate_exercise(student.id, body.skill_name, context=body.context)


# ── Portfolio ──────────────────────────────────────────────────────────────


@router.get(
    "/portfolio/{course_id}",
    response_model=PortfolioResponse,
    summary="Full student portfolio: mastery + path + PCO analysis",
)
def get_portfolio(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
) -> PortfolioResponse:
    """Comprehensive student learning profile including mastery, path, and risk indicators."""
    svc = _get_service(driver)
    return svc.get_portfolio(student.id, course_id)


# ── ARCD Dashboard endpoints ─────────────────────────────────────────────


@router.get(
    "/arcd-portfolio/{course_id}",
    summary="ARCD dashboard portfolio (PortfolioData format)",
)
def get_arcd_portfolio(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
) -> dict:
    """Return full portfolio in the format the ARCD dashboard expects."""
    svc = _get_service(driver)
    return svc.get_arcd_portfolio(student.id, course_id)


@router.get(
    "/arcd-twin/{course_id}",
    summary="ARCD digital twin viewer data (TwinViewerData format)",
)
def get_arcd_twin(
    course_id: int,
    student: StudentDep,
    driver: Neo4jDep,
) -> dict:
    """Return twin viewer data in the format the ARCD dashboard expects."""
    svc = _get_service(driver)
    return svc.get_arcd_twin(student.id, course_id)


# ── Interaction Logging ────────────────────────────────────────────────────


@router.post(
    "/what-if-analysis",
    response_model=WhatIfAnalysisResponse,
    summary="Analyze what-if strategy options and return best recommendation",
)
def what_if_analysis(
    body: WhatIfAnalysisRequest,
    _student: AnyUserDep,
    driver: Neo4jDep,
) -> WhatIfAnalysisResponse:
    """Return strategic recommendation for what-if simulation options."""
    svc = _get_service(driver)
    return svc.analyze_what_if_strategy(body)


@router.post(
    "/student-events",
    response_model=StudentEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a student calendar event",
)
def create_student_event(
    body: StudentEventCreate,
    student: StudentDep,
    driver: Neo4jDep,
) -> StudentEventResponse:
    """Create a student event used by schedule, path, and review planning."""
    svc = _get_service(driver)
    return svc.create_student_event(student.id, body)


@router.get(
    "/student-events",
    response_model=StudentEventsListResponse,
    summary="List student calendar events",
)
def list_student_events(
    student: StudentDep,
    driver: Neo4jDep,
    from_date: str | None = None,
    to_date: str | None = None,
) -> StudentEventsListResponse:
    """Return student events optionally filtered by date window."""
    svc = _get_service(driver)
    events = svc.get_student_events(student.id, from_date=from_date, to_date=to_date)
    return StudentEventsListResponse(events=events)


@router.delete(
    "/student-events/{event_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a student calendar event",
)
def delete_student_event(
    event_id: str,
    student: StudentDep,
    driver: Neo4jDep,
) -> dict:
    """Delete one student event by ID."""
    svc = _get_service(driver)
    deleted = svc.delete_student_event(student.id, event_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Event not found")
    return {"deleted": True, "event_id": event_id}


@router.post(
    "/interactions",
    status_code=status.HTTP_201_CREATED,
    summary="Log student answering a question (ATTEMPTED)",
)
def log_interaction(
    body: LogInteractionRequest,
    student: StudentDep,
    driver: Neo4jDep,
    course_id: int | None = None,
) -> dict:
    """
    Create an (USER:STUDENT)-[:ATTEMPTED]->(QUESTION) edge.
    Automatically recomputes and stores mastery (closed feedback loop).
    """
    svc = _get_service(driver)
    svc.log_interaction(
        user_id=student.id,
        question_id=body.question_id,
        is_correct=body.is_correct,
        timestamp_sec=body.timestamp_sec,
        time_spent_sec=body.time_spent_sec,
        attempt_number=body.attempt_number,
        course_id=course_id,
        recompute_mastery=True,
    )
    return {"logged": True, "question_id": body.question_id}


@router.post(
    "/engagements",
    status_code=status.HTTP_201_CREATED,
    summary="Log student engaging with a reading/video resource (ENGAGES_WITH)",
)
def log_engagement(
    body: LogEngagementRequest,
    student: StudentDep,
    driver: Neo4jDep,
) -> dict:
    """
    Create/update an (USER:STUDENT)-[:ENGAGES_WITH]->(READING_RESOURCE|VIDEO_RESOURCE) edge.
    """
    svc = _get_service(driver)
    svc.log_engagement(
        user_id=student.id,
        resource_id=body.resource_id,
        resource_type=body.resource_type,
        progress=body.progress,
        duration_sec=body.duration_sec,
        timestamp_sec=body.timestamp_sec,
    )
    return {"logged": True, "resource_id": body.resource_id}
