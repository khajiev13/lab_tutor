from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, UploadFile, status
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session

from app.providers.storage import blob_service

from .cv_extractor import extract_cv_text
from .graph import build_individual_learning_graph
from .models import CVDocument, CVDocumentStatus, CVExtractionRun
from .neo4j_repository import select_job_postings, select_market_skills
from .repository import IndividualLearningRepository
from .schemas import (
    CVDocumentRead,
    IndividualGraphResumeResponse,
    IndividualGraphStartResponse,
    IndividualProfileRead,
)

_THREAD_ID_PATTERN = re.compile(r"^individual-(?P<user_id>\d+)-cv-(?P<cv_document_id>\d+)$")
_SERVICE_GRAPH_CHECKPOINTER = InMemorySaver()
_SERVICE_GRAPH = build_individual_learning_graph(checkpointer=_SERVICE_GRAPH_CHECKPOINTER)


def _safe_filename(filename: str) -> str:
    base = filename.strip().split("/")[-1].split("\\")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "cv"


class IndividualLearningService:
    def __init__(self, db: Session | None, neo4j_driver: Neo4jDriver | None) -> None:
        self._repo = IndividualLearningRepository(db)
        self._db = db
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

    def start_individual_graph(
        self, user_id: int, cv_document_id: int
    ) -> IndividualGraphStartResponse:
        thread_id = self._build_thread_id(user_id, cv_document_id)
        graph = self._get_graph()
        config = self._graph_config(thread_id)
        result = graph.invoke(
            {
                "user_id": user_id,
                "cv_document_id": cv_document_id,
                "profile": self._load_profile_payload(user_id, cv_document_id),
                "target_titles": [],
                "candidate_jobs": [],
                "skill_bank": [],
                "selected_posting_urls": [],
                "selected_skill_names": [],
            },
            config,
        )
        return IndividualGraphStartResponse(**self._build_graph_response(thread_id, result))

    def resume_individual_graph(
        self, user_id: int, thread_id: str, payload: dict[str, Any]
    ) -> IndividualGraphResumeResponse:
        self._validate_resume_thread(user_id, thread_id)
        graph = self._get_graph()
        config = self._graph_config(thread_id)
        result = graph.invoke(Command(resume=payload), config)
        response_data = self._build_graph_response(thread_id, result)
        if response_data["status"] == "completed":
            self._persist_selected_market_targets(
                user_id=user_id,
                run_id=thread_id,
                posting_urls=response_data["selected_posting_urls"],
                skill_names=response_data["selected_skill_names"],
            )
        return IndividualGraphResumeResponse(**response_data)

    @staticmethod
    def _build_thread_id(user_id: int, cv_document_id: int) -> str:
        return f"individual-{user_id}-cv-{cv_document_id}"

    @staticmethod
    def _graph_config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _get_graph():
        return _SERVICE_GRAPH

    def _validate_resume_thread(self, user_id: int, thread_id: str) -> int:
        cv_document_id = self._parse_thread_id(thread_id, user_id)
        if self._db is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thread does not belong to the current user",
            )
        try:
            self._load_profile_payload(user_id, cv_document_id)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Thread does not belong to the current user",
                ) from exc
            raise
        return cv_document_id

    @staticmethod
    def _parse_thread_id(thread_id: str, user_id: int) -> int:
        match = _THREAD_ID_PATTERN.fullmatch(thread_id)
        if match is None or int(match.group("user_id")) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thread does not belong to the current user",
            )
        return int(match.group("cv_document_id"))

    def _load_profile_payload(self, user_id: int, cv_document_id: int) -> dict[str, Any]:
        if self._db is None:
            return {}

        cv_document = (
            self._db.query(CVDocument)
            .filter(CVDocument.id == cv_document_id, CVDocument.user_id == user_id)
            .one_or_none()
        )
        if cv_document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV document not found",
            )

        extraction = (
            self._db.query(CVExtractionRun)
            .filter(
                CVExtractionRun.user_id == user_id,
                CVExtractionRun.cv_document_id == cv_document_id,
            )
            .order_by(CVExtractionRun.created_at.desc(), CVExtractionRun.id.desc())
            .first()
        )
        if extraction is None:
            return {}

        profile = dict(extraction.extracted_profile_json or {})
        profile.setdefault(
            "target_title_suggestions",
            list(extraction.target_title_suggestions_json or []),
        )
        return profile

    @staticmethod
    def _build_graph_response(thread_id: str, result: dict[str, Any]) -> dict[str, Any]:
        interrupts = result.get("__interrupt__") or []
        interrupt_value = interrupts[0].value if interrupts else None
        return {
            "thread_id": thread_id,
            "status": "interrupted" if interrupt_value is not None else "completed",
            "interrupt": interrupt_value,
            "target_titles": list(result.get("target_titles", [])),
            "selected_posting_urls": list(result.get("selected_posting_urls", [])),
            "selected_skill_names": list(result.get("selected_skill_names", [])),
        }

    def _persist_selected_market_targets(
        self,
        *,
        user_id: int,
        run_id: str,
        posting_urls: list[str],
        skill_names: list[str],
    ) -> None:
        if self._neo4j_driver is None:
            return

        with self._neo4j_driver.session() as session:
            if posting_urls:
                select_job_postings(
                    session,
                    user_id=user_id,
                    posting_urls=posting_urls,
                    run_id=run_id,
                )
            if skill_names:
                select_market_skills(
                    session,
                    user_id=user_id,
                    skill_names=skill_names,
                )
