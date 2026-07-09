from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    CVDocument,
    CVDocumentStatus,
    CVExtractionRun,
    IndividualJobMatchRun,
    IndividualJobSearchRun,
    IndividualLearningRun,
    IndividualProfile,
    IndividualRunStatus,
)


class IndividualLearningRepository:
    def __init__(self, db: Session | None) -> None:
        self._db = db

    def get_profile(self, user_id: int) -> IndividualProfile | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(IndividualProfile).where(IndividualProfile.user_id == user_id)
        )

    def upsert_profile_status(
        self,
        *,
        user_id: int,
        onboarding_status: str,
    ) -> IndividualProfile:
        db = self._require_db()
        profile = self.get_profile(user_id)
        if profile is None:
            profile = IndividualProfile(
                user_id=user_id,
                onboarding_status=onboarding_status,
            )
            db.add(profile)
        else:
            profile.onboarding_status = onboarding_status
        self._commit(profile)
        return profile

    def upsert_cv_document(
        self,
        *,
        user_id: int,
        blob_path: str,
        original_filename: str,
        content_type: str | None,
        content_hash: str,
        size_bytes: int,
    ) -> CVDocument:
        db = self._require_db()
        document = db.scalar(
            select(CVDocument).where(
                CVDocument.user_id == user_id,
                CVDocument.content_hash == content_hash,
            )
        )
        if document is None:
            document = CVDocument(user_id=user_id, content_hash=content_hash)
            db.add(document)
        document.blob_path = blob_path
        document.original_filename = original_filename
        document.content_type = content_type
        document.size_bytes = size_bytes
        document.status = CVDocumentStatus.PROCESSING.value
        document.error_message = None
        document.processed_at = None
        self._commit(document)
        return document

    def get_owned_cv_document(
        self,
        *,
        user_id: int,
        cv_document_id: int,
    ) -> CVDocument | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(CVDocument).where(
                CVDocument.id == cv_document_id,
                CVDocument.user_id == user_id,
            )
        )

    def get_latest_cv_document(self, user_id: int) -> CVDocument | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(CVDocument)
            .where(CVDocument.user_id == user_id)
            .order_by(CVDocument.uploaded_at.desc(), CVDocument.id.desc())
            .limit(1)
        )

    def create_cv_extraction_run(
        self,
        *,
        cv_document_id: int,
        user_id: int,
        model_provider: str,
        model_name: str,
        raw_text_hash: str,
    ) -> CVExtractionRun:
        run = CVExtractionRun(
            cv_document_id=cv_document_id,
            user_id=user_id,
            model_provider=model_provider,
            model_name=model_name,
            raw_text_hash=raw_text_hash,
            status=IndividualRunStatus.RUNNING.value,
        )
        self._require_db().add(run)
        self._commit(run)
        return run

    def get_latest_cv_extraction(
        self,
        user_id: int,
        *,
        cv_document_id: int | None = None,
    ) -> CVExtractionRun | None:
        if self._db is None:
            return None
        statement = select(CVExtractionRun).where(CVExtractionRun.user_id == user_id)
        if cv_document_id is not None:
            statement = statement.where(
                CVExtractionRun.cv_document_id == cv_document_id
            )
        return self._db.scalar(
            statement.order_by(
                CVExtractionRun.created_at.desc(), CVExtractionRun.id.desc()
            ).limit(1)
        )

    def complete_cv_extraction(
        self,
        run: CVExtractionRun,
        *,
        extracted_profile: dict,
        target_title_suggestions: list[str],
        confidence_summary: dict,
    ) -> CVExtractionRun:
        run.extracted_profile_json = extracted_profile
        run.target_title_suggestions_json = target_title_suggestions
        run.confidence_summary_json = confidence_summary
        run.status = IndividualRunStatus.COMPLETED.value
        run.error_message = None
        run.completed_at = datetime.now(UTC)
        self._commit(run)
        return run

    def set_cv_extraction_text_hash(
        self,
        run: CVExtractionRun,
        *,
        raw_text_hash: str,
    ) -> CVExtractionRun:
        run.raw_text_hash = raw_text_hash
        self._commit(run)
        return run

    def approve_profile_review(
        self,
        *,
        user_id: int,
        cv_document_id: int,
        reviewed_profile: dict,
        target_titles: list[str],
    ) -> tuple[IndividualProfile, CVExtractionRun] | None:
        document = self.get_owned_cv_document(
            user_id=user_id,
            cv_document_id=cv_document_id,
        )
        if document is None:
            return None
        extraction = self.get_latest_cv_extraction(
            user_id,
            cv_document_id=cv_document_id,
        )
        if extraction is None:
            return None

        profile = self.get_profile(user_id)
        if profile is None:
            profile = IndividualProfile(user_id=user_id)
            self._require_db().add(profile)
        profile.target_titles_json = target_titles
        profile.reviewed_at = datetime.now(UTC)
        profile.onboarding_status = "needs_jobs"
        extraction.extracted_profile_json = reviewed_profile
        extraction.target_title_suggestions_json = list(
            reviewed_profile.get("target_title_suggestions", [])
        )
        self._commit(profile, extraction)
        return profile, extraction

    def complete_cv_document(self, document: CVDocument) -> CVDocument:
        document.status = CVDocumentStatus.COMPLETED.value
        document.error_message = None
        document.processed_at = datetime.now(UTC)
        self._commit(document)
        return document

    def fail_cv_document(
        self,
        document: CVDocument,
        *,
        error_message: str,
    ) -> CVDocument:
        document.status = CVDocumentStatus.FAILED.value
        document.error_message = error_message
        document.processed_at = datetime.now(UTC)
        self._commit(document)
        return document

    def fail_cv_extraction(
        self,
        run: CVExtractionRun,
        *,
        document: CVDocument,
        error_message: str,
    ) -> None:
        now = datetime.now(UTC)
        run.status = IndividualRunStatus.FAILED.value
        run.error_message = error_message
        run.completed_at = now
        document.status = CVDocumentStatus.FAILED.value
        document.error_message = error_message
        document.processed_at = now
        self._commit(run, document)

    def create_job_search_run(
        self,
        *,
        user_id: int,
        target_titles: list[str],
        country: str,
        location: str,
    ) -> IndividualJobSearchRun:
        run = IndividualJobSearchRun(
            user_id=user_id,
            target_titles_json=target_titles,
            country=country,
            location=location,
            status=IndividualRunStatus.RUNNING.value,
        )
        self._require_db().add(run)
        self._commit(run)
        return run

    def get_or_create_job_search_run(
        self,
        *,
        user_id: int,
        workflow_thread_id: str,
        target_titles: list[str],
        country: str,
        location: str,
    ) -> IndividualJobSearchRun:
        db = self._require_db()
        existing = db.scalar(
            select(IndividualJobSearchRun).where(
                IndividualJobSearchRun.workflow_thread_id == workflow_thread_id
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise RuntimeError("Workflow thread belongs to another user")
            return existing
        run = IndividualJobSearchRun(
            user_id=user_id,
            workflow_thread_id=workflow_thread_id,
            target_titles_json=target_titles,
            country=country,
            location=location,
            status=IndividualRunStatus.RUNNING.value,
        )
        db.add(run)
        self._commit(run)
        return run

    def complete_job_search_run(
        self,
        run: IndividualJobSearchRun,
        *,
        jobs: list[dict],
        status: str,
        error_message: str | None,
    ) -> IndividualJobSearchRun:
        run.fetched_jobs_json = jobs
        run.status = status
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
        self._commit(run)
        return run

    def get_latest_job_search_run(
        self,
        user_id: int,
    ) -> IndividualJobSearchRun | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(IndividualJobSearchRun)
            .where(IndividualJobSearchRun.user_id == user_id)
            .order_by(
                IndividualJobSearchRun.created_at.desc(),
                IndividualJobSearchRun.id.desc(),
            )
            .limit(1)
        )

    def record_job_selections(
        self,
        *,
        user_id: int,
        job_search_run_id: int,
        posting_urls: list[str],
    ) -> bool:
        if self._db is None:
            return False
        run = self._db.scalar(
            select(IndividualJobSearchRun).where(
                IndividualJobSearchRun.id == job_search_run_id,
                IndividualJobSearchRun.user_id == user_id,
            )
        )
        if run is None:
            return False
        run.selected_posting_urls_json = posting_urls
        self._commit(run)
        return True

    def create_job_match_run(
        self,
        *,
        user_id: int,
        job_search_run_id: int,
    ) -> IndividualJobMatchRun:
        run = IndividualJobMatchRun(
            user_id=user_id,
            job_search_run_id=job_search_run_id,
            status=IndividualRunStatus.RUNNING.value,
        )
        self._require_db().add(run)
        self._commit(run)
        return run

    def get_or_create_job_match_run(
        self,
        *,
        user_id: int,
        job_search_run_id: int,
    ) -> IndividualJobMatchRun:
        db = self._require_db()
        existing = db.scalar(
            select(IndividualJobMatchRun).where(
                IndividualJobMatchRun.job_search_run_id == job_search_run_id
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise RuntimeError("Job match run belongs to another user")
            return existing
        run = IndividualJobMatchRun(
            user_id=user_id,
            job_search_run_id=job_search_run_id,
            status=IndividualRunStatus.RUNNING.value,
        )
        db.add(run)
        self._commit(run)
        return run

    def complete_job_match_run(
        self,
        run: IndividualJobMatchRun,
        *,
        scores: list[dict],
        skill_gaps: list[dict],
        status: str,
    ) -> IndividualJobMatchRun:
        run.scores_json = scores
        run.skill_gap_json = skill_gaps
        run.status = status
        run.completed_at = datetime.now(UTC)
        self._commit(run)
        return run

    def get_latest_job_match_run(
        self,
        user_id: int,
    ) -> IndividualJobMatchRun | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(IndividualJobMatchRun)
            .where(IndividualJobMatchRun.user_id == user_id)
            .order_by(
                IndividualJobMatchRun.created_at.desc(),
                IndividualJobMatchRun.id.desc(),
            )
            .limit(1)
        )

    def create_learning_run(
        self,
        *,
        user_id: int,
        selected_skill_names: list[str],
        run_id: str,
    ) -> IndividualLearningRun:
        run = IndividualLearningRun(
            user_id=user_id,
            selected_skill_names_json=selected_skill_names,
            status=IndividualRunStatus.RUNNING.value,
            run_id=run_id,
        )
        self._require_db().add(run)
        self._commit(run)
        return run

    def complete_learning_run(
        self,
        run: IndividualLearningRun,
        *,
        status: str,
        error_message: str | None,
    ) -> IndividualLearningRun:
        run.status = status
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
        self._commit(run)
        return run

    def get_latest_learning_run(
        self,
        user_id: int,
    ) -> IndividualLearningRun | None:
        if self._db is None:
            return None
        return self._db.scalar(
            select(IndividualLearningRun)
            .where(IndividualLearningRun.user_id == user_id)
            .order_by(
                IndividualLearningRun.created_at.desc(),
                IndividualLearningRun.id.desc(),
            )
            .limit(1)
        )

    def create_cv_document(self, cv_document: CVDocument) -> CVDocument:
        self._require_db().add(cv_document)
        self._commit(cv_document)
        return cv_document

    def _require_db(self) -> Session:
        if self._db is None:
            raise RuntimeError("Database session is required")
        return self._db

    def _commit(self, *instances: object) -> None:
        db = self._require_db()
        db.commit()
        for instance in instances:
            db.refresh(instance)
