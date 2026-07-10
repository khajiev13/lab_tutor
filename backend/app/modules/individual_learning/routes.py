from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import (
    CVDocumentRead,
    IndividualBuildResponse,
    IndividualGraphResumeRequest,
    IndividualGraphResumeResponse,
    IndividualGraphStartRequest,
    IndividualGraphStartResponse,
    IndividualLearningPathResponse,
    IndividualProfileRead,
    IndividualSkillBanksResponse,
    SelectIndividualSkillsRequest,
    SelectInterestedJobsRequest,
)
from .service import IndividualLearningService

router = APIRouter(prefix="/individual-learning", tags=["individual-learning"])
INDIVIDUAL_ROLE = UserRole.INDIVIDUAL

IndividualDep = Annotated[User, Depends(require_role(INDIVIDUAL_ROLE))]
DbDep = Annotated[Session, Depends(get_db)]
Neo4jDep = Annotated[Neo4jDriver | None, Depends(get_neo4j_driver)]


def get_individual_learning_service(
    db: DbDep,
    driver: Neo4jDep,
) -> IndividualLearningService:
    return IndividualLearningService(db, driver)


ServiceDep = Annotated[
    IndividualLearningService,
    Depends(get_individual_learning_service),
]


@router.get("/profile", response_model=IndividualProfileRead)
def get_profile(
    user: IndividualDep,
    service: ServiceDep,
) -> IndividualProfileRead:
    return service.get_profile(user.id)


@router.post("/cv", response_model=CVDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_cv(
    user: IndividualDep,
    service: ServiceDep,
    file: UploadFile = File(...),
) -> CVDocumentRead:
    return await service.upload_cv(user.id, file)


@router.post("/cv/{document_id}/retry", response_model=CVDocumentRead)
async def retry_cv_document(
    document_id: int,
    user: IndividualDep,
    service: ServiceDep,
) -> CVDocumentRead:
    return await service.retry_cv_document(user.id, document_id)


@router.post("/graph/start", response_model=IndividualGraphStartResponse)
def start_individual_graph(
    body: IndividualGraphStartRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> IndividualGraphStartResponse:
    return service.start_individual_graph(
        user.id,
        body.cv_document_id,
    )


@router.post("/graph/resume", response_model=IndividualGraphResumeResponse)
def resume_individual_graph(
    body: IndividualGraphResumeRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> IndividualGraphResumeResponse:
    return service.resume_individual_graph(
        user.id,
        body.thread_id,
        body.payload,
    )


@router.get("/skill-banks", response_model=IndividualSkillBanksResponse)
def get_skill_banks(
    user: IndividualDep,
    service: ServiceDep,
) -> IndividualSkillBanksResponse:
    return service.get_skill_banks(user.id)


@router.post("/interested-jobs")
def select_interested_jobs(
    body: SelectInterestedJobsRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> dict[str, int]:
    try:
        count = service.select_interested_jobs(user.id, body.posting_urls)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"postings_linked": count}


@router.post("/select-skills", status_code=status.HTTP_200_OK)
def select_skills(
    body: SelectIndividualSkillsRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> dict[str, int]:
    try:
        count = service.select_skills(user.id, body.skill_names)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return {"selected": count}


@router.delete("/select-skills")
def deselect_skills(
    body: SelectIndividualSkillsRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> dict[str, int]:
    count = service.deselect_skills(user.id, body.skill_names)
    return {"deselected": count}


@router.post(
    "/build",
    response_model=IndividualBuildResponse,
    status_code=status.HTTP_200_OK,
)
def build_learning_path(
    body: SelectIndividualSkillsRequest,
    user: IndividualDep,
    service: ServiceDep,
) -> dict[str, str]:
    try:
        return service.build_learning_path(user.id, body.skill_names)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/path", response_model=IndividualLearningPathResponse)
def get_learning_path(
    user: IndividualDep,
    service: ServiceDep,
) -> IndividualLearningPathResponse:
    return IndividualLearningPathResponse.model_validate(
        service.get_learning_path(user.id)
    )
