from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .schemas import CVDocumentRead, IndividualProfileRead
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
