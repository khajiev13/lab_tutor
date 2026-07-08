from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    CVDocumentRead,
    IndividualGraphResumeRequest,
    IndividualGraphResumeResponse,
    IndividualGraphStartRequest,
    IndividualGraphStartResponse,
    IndividualProfileRead,
    IndividualSkillBanksResponse,
    SelectInterestedJobsRequest,
)
from .service import IndividualLearningService

router = APIRouter(prefix="/individual-learning", tags=["individual-learning"])
INDIVIDUAL_ROLE = UserRole.INDIVIDUAL

IndividualDep = Annotated[User, Depends(require_role(INDIVIDUAL_ROLE))]
DbDep = Annotated[Session, Depends(get_db)]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]


def _get_service(db: DbDep, driver: Neo4jDep) -> IndividualLearningService:
    return IndividualLearningService(db, driver)


@router.get("/profile", response_model=IndividualProfileRead)
def get_profile(
    user: IndividualDep, db: DbDep, driver: Neo4jDep
) -> IndividualProfileRead:
    return _get_service(db, driver).get_profile(user.id)


@router.post("/cv", response_model=CVDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    user: IndividualDep,
    db: DbDep,
    driver: Neo4jDep,
    file: UploadFile = File(...),
) -> CVDocumentRead:
    return await _get_service(db, driver).upload_cv(user.id, file)


@router.post("/graph/start", response_model=IndividualGraphStartResponse)
def start_individual_graph(
    body: IndividualGraphStartRequest,
    user: IndividualDep,
    db: DbDep,
    driver: Neo4jDep,
) -> IndividualGraphStartResponse:
    return _get_service(db, driver).start_individual_graph(
        user.id,
        body.cv_document_id,
    )


@router.post("/graph/resume", response_model=IndividualGraphResumeResponse)
def resume_individual_graph(
    body: IndividualGraphResumeRequest,
    user: IndividualDep,
    db: DbDep,
    driver: Neo4jDep,
) -> IndividualGraphResumeResponse:
    return _get_service(db, driver).resume_individual_graph(
        user.id,
        body.thread_id,
        body.payload,
    )


@router.get("/skill-banks", response_model=IndividualSkillBanksResponse)
def get_skill_banks(
    user: IndividualDep,
    db: DbDep,
    driver: Neo4jDep,
) -> IndividualSkillBanksResponse:
    return _get_service(db, driver).get_skill_banks(user.id)


@router.post("/interested-jobs")
def select_interested_jobs(
    body: SelectInterestedJobsRequest,
    user: IndividualDep,
    db: DbDep,
    driver: Neo4jDep,
) -> dict[str, int]:
    count = _get_service(db, driver).select_interested_jobs(user.id, body.posting_urls)
    return {"postings_linked": count}
