from __future__ import annotations

import re

from fastapi import HTTPException, UploadFile, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.providers.storage import blob_service

from .cv_extractor import extract_cv_text
from .models import CVDocument, CVDocumentStatus
from .repository import IndividualLearningRepository
from .schemas import CVDocumentRead, IndividualProfileRead


def _safe_filename(filename: str) -> str:
    base = filename.strip().split("/")[-1].split("\\")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "cv"


class IndividualLearningService:
    def __init__(self, db: Session | None, neo4j_driver: Neo4jDriver | None) -> None:
        self._repo = IndividualLearningRepository(db)
        self._neo4j_driver = neo4j_driver

    def get_profile(self, user_id: int) -> IndividualProfileRead:
        profile = self._repo.get_profile(user_id)
        if profile is None:
            return IndividualProfileRead(user_id=user_id, onboarding_status="needs_cv")

        return IndividualProfileRead(
            user_id=user_id,
            onboarding_status=profile.onboarding_status,
            target_titles=list(profile.target_titles_json or []),
            preferred_country=profile.preferred_country,
            preferred_location=profile.preferred_location,
            reviewed_at=profile.reviewed_at,
        )

    async def upload_cv(self, user_id: int, file: UploadFile) -> CVDocumentRead:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CV filename is required",
            )

        await file.seek(0)
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CV file is empty",
            )

        try:
            extract_cv_text(
                filename=filename,
                content_type=file.content_type,
                data=content,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        content_hash = blob_service.sha256_hex(content)
        safe_filename = _safe_filename(filename)
        blob_path = f"users/{user_id}/cv/{content_hash}/{safe_filename}"

        try:
            await blob_service.upload_bytes(content, blob_path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload CV file {filename}: {exc}",
            ) from exc

        cv_document = self._repo.create_cv_document(
            CVDocument(
                user_id=user_id,
                blob_path=blob_path,
                original_filename=filename,
                content_type=file.content_type,
                content_hash=content_hash,
                size_bytes=len(content),
                status=CVDocumentStatus.UPLOADED.value,
            )
        )

        return CVDocumentRead(
            id=cv_document.id,
            user_id=cv_document.user_id,
            original_filename=cv_document.original_filename,
            content_type=cv_document.content_type,
            status=cv_document.status,
        )
