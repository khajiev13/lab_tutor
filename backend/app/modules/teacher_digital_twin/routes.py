"""Teacher Digital Twin — FastAPI routes.

All endpoints require TEACHER role.

Routes under /teacher-twin/{course_id}/
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    ClassMasteryResponse,
    MultiSkillSimulationRequest,
    MultiSkillSimulationResponse,
    SkillDifficultyResponse,
    SkillPopularityResponse,
    SkillSimulationRequest,
    SkillSimulationResponse,
    StudentGroupsResponse,
    WhatIfRequest,
    WhatIfResponse,
)
from .service import TeacherDigitalTwinService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teacher-twin", tags=["teacher-digital-twin"])

TeacherDep = Annotated[User, Depends(require_role(UserRole.TEACHER))]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]
DbDep = Annotated[Session, Depends(get_db)]


def _get_service(driver: Neo4jDep) -> TeacherDigitalTwinService:
    if driver is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j is not configured",
        )
    return TeacherDigitalTwinService(driver)


# ── Feature 1: Skill Difficulty ────────────────────────────────────────────


@router.get("/{course_id}/skill-difficulty", response_model=SkillDifficultyResponse)
def get_skill_difficulty(
    course_id: int,
    _teacher: TeacherDep,
    driver: Neo4jDep,
) -> SkillDifficultyResponse:
    """
    Return per-skill difficulty based on actual student mastery.

    PerceivedDifficulty(s) = 1 - (1/N) * SUM m_{i,s}
    """
    return _get_service(driver).get_skill_difficulty(course_id)


# ── Feature 2: Skill Popularity ───────────────────────────────────────────


@router.get("/{course_id}/skill-popularity", response_model=SkillPopularityResponse)
def get_skill_popularity(
    course_id: int,
    _teacher: TeacherDep,
    driver: Neo4jDep,
) -> SkillPopularityResponse:
    """Return most and least popular skills by student selection count."""
    return _get_service(driver).get_skill_popularity(course_id)


# ── Feature 3: Class Mastery ───────────────────────────────────────────────


@router.get("/{course_id}/class-mastery", response_model=ClassMasteryResponse)
def get_class_mastery(
    course_id: int,
    _teacher: TeacherDep,
    driver: Neo4jDep,
) -> ClassMasteryResponse:
    """Return per-student mastery summaries and class-level statistics."""
    return _get_service(driver).get_class_mastery(course_id)


# ── Feature 4: Student Groups ──────────────────────────────────────────────


@router.get("/{course_id}/student-groups", response_model=StudentGroupsResponse)
def get_student_groups(
    course_id: int,
    _teacher: TeacherDep,
    driver: Neo4jDep,
) -> StudentGroupsResponse:
    """Group students by shared skill set and return suggested paths per group."""
    return _get_service(driver).get_student_groups(course_id)


# ── Feature 5: What-If Simulation ─────────────────────────────────────────


@router.post("/{course_id}/what-if", response_model=WhatIfResponse)
def run_what_if(
    course_id: int,
    body: WhatIfRequest,
    _teacher: TeacherDep,
    driver: Neo4jDep,
) -> WhatIfResponse:
    """
    Run a what-if forward simulation.

    Manual mode: teacher specifies skill names + hypothetical mastery values.
    Automatic mode: system identifies struggling skills and ranks interventions
      ClassGain(s_k) = SUM_{i} (min(1, m_{i,s_k} + Delta) - m_{i,s_k})
    """
    return _get_service(driver).run_what_if(course_id, body)


# ── Feature 6: Skill Simulation ────────────────────────────────────────────


@router.post("/{course_id}/simulate-skill", response_model=SkillSimulationResponse)
def simulate_skill(
    course_id: int,
    body: SkillSimulationRequest,
    teacher: TeacherDep,
    driver: Neo4jDep,
) -> SkillSimulationResponse:
    """Generate an adaptive exercise for a single skill at a given mastery level (backward compat)."""
    return _get_service(driver).simulate_skill(
        course_id, body.skill_name, body.simulated_mastery
    )


@router.post(
    "/{course_id}/simulate-skills", response_model=MultiSkillSimulationResponse
)
def simulate_multiple_skills(
    course_id: int,
    body: MultiSkillSimulationRequest,
    teacher: TeacherDep,
    driver: Neo4jDep,
) -> MultiSkillSimulationResponse:
    """
    Simulate multiple skills simultaneously.

    Returns per-skill exercises + a coherence analysis showing how closely
    the selected skills are co-selected by students and a recommended
    teaching order.
    """
    return _get_service(driver).simulate_multiple_skills(course_id, body)


# ── Student drilldown (teacher-scoped, read-only) ──────────────────────────


@router.get("/{course_id}/student/{student_id}/portfolio")
def get_student_portfolio(
    course_id: int,
    student_id: int,
    teacher: TeacherDep,
    driver: Neo4jDep,
) -> dict:
    """Return a student's ARCD portfolio (teacher read-only, requires TEACHES_CLASS)."""
    return _get_service(driver).get_student_portfolio(teacher.id, student_id, course_id)


@router.get("/{course_id}/student/{student_id}/twin")
def get_student_twin(
    course_id: int,
    student_id: int,
    teacher: TeacherDep,
    driver: Neo4jDep,
) -> dict:
    """Return a student's digital twin data (teacher read-only, requires TEACHES_CLASS)."""
    return _get_service(driver).get_student_twin(teacher.id, student_id, course_id)
