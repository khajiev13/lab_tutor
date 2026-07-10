from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Any

from fastapi import HTTPException, UploadFile, status
from langgraph.types import Command
from neo4j import Driver as Neo4jDriver
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.resource_pipeline.neo4j_repository import write_resources
from app.core.resource_pipeline.schemas import SkillProfile
from app.core.settings import settings
from app.modules.question_generation.service import generate_questions_for_skill
from app.modules.textualresourceanalyst.config import (
    RELATIONSHIP as READING_RELATIONSHIP,
)
from app.modules.textualresourceanalyst.config import RESOURCE_LABEL as READING_LABEL
from app.modules.textualresourceanalyst.service import fetch_readings_for_skill
from app.modules.visualcontentevaluator.config import RELATIONSHIP as VIDEO_RELATIONSHIP
from app.modules.visualcontentevaluator.config import RESOURCE_LABEL as VIDEO_LABEL
from app.modules.visualcontentevaluator.service import fetch_videos_for_skill
from app.providers.storage import blob_service

from .checkpoint import get_individual_learning_checkpointer
from .cv_extractor import (
    StructuredCVProfileExtractor,
    extract_cv_text,
    is_supported_cv_file,
)
from .graph import build_individual_learning_graph
from .job_matcher import score_market_skill_coverage
from .job_search import extract_market_skills_for_jobs, search_jobs_for_titles
from .models import CVDocument, CVDocumentStatus, CVExtractionRun, IndividualRunStatus
from .neo4j_repository import (
    deselect_market_skills,
    get_individual_learning_path,
    get_individual_skill_bank,
    get_market_skill_profiles,
    get_selected_market_skill_names,
    get_selected_market_skill_profiles,
    resolve_interested_market_skill_names,
    select_candidate_market_skills,
    select_job_postings,
    select_market_skills,
    upsert_cv_skills,
    upsert_job_postings_and_market_skills,
    write_market_skill_questions,
)
from .repository import CVAttemptSupersededError, IndividualLearningRepository
from .schemas import (
    CVDocumentRead,
    CVProfileExtraction,
    CVSkillExtraction,
    IndividualGraphResumeResponse,
    IndividualGraphStartResponse,
    IndividualProfileRead,
    IndividualSkillBankJobPosting,
    IndividualSkillBankSkill,
    IndividualSkillBanksResponse,
)

_THREAD_ID_PATTERN = re.compile(
    r"^individual-(?P<user_id>\d+)-cv-(?P<cv_document_id>\d+)"
    r"-extraction-(?P<extraction_run_id>\d+)$"
)
MAX_CV_UPLOAD_BYTES = 10 * 1024 * 1024
CV_UPLOAD_CHUNK_BYTES = 64 * 1024
CV_ATTEMPT_STALE_AFTER = timedelta(hours=1)
WORKFLOW_OPERATION_STALE_AFTER = timedelta(hours=1)
WORKFLOW_LEASE_HEARTBEAT_SECONDS = 30.0
_SAFE_CV_PARSE_ERRORS = frozenset(
    {
        "Only PDF and DOCX CV files are supported",
        "Invalid PDF CV file",
        "PDF CV exceeds the page limit",
        "CV text exceeds the character limit",
        "DOCX CV exceeds safe archive limits",
        "Invalid docx file (cannot read word/document.xml)",
        "Invalid docx XML",
        "CV text is too short to analyze",
    }
)


class _WorkflowLeaseHeartbeat:
    """Renew a workflow lease with short, independent DB transactions."""

    def __init__(
        self,
        *,
        bind: Any,
        extraction_run_id: int,
        user_id: int,
        operation_token: str,
        interval_seconds: float,
    ) -> None:
        self._bind = bind
        self._extraction_run_id = extraction_run_id
        self._user_id = user_id
        self._operation_token = operation_token
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._ownership_uncertain = Event()
        self._thread = Thread(
            target=self._run,
            name="individual-workflow-lease-heartbeat",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    def assert_owned(self) -> None:
        if self._ownership_uncertain.is_set():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow operation ownership is uncertain",
            )

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                with Session(bind=self._bind) as db:
                    renewed = IndividualLearningRepository(db).renew_workflow_operation(
                        extraction_run_id=self._extraction_run_id,
                        user_id=self._user_id,
                        operation_token=self._operation_token,
                        now=datetime.now(UTC),
                    )
            except Exception:
                self._ownership_uncertain.set()
                return
            if not renewed:
                self._ownership_uncertain.set()
                return


class IndividualLearningService:
    def __init__(
        self,
        db: Session | None,
        neo4j_driver: Neo4jDriver | None,
        *,
        storage: Any | None = None,
        cv_text_extractor: Callable[..., str] | None = None,
        cv_profile_extractor: Any | None = None,
        graph_checkpointer: Any | None = None,
        job_searcher: Callable[[list[str], str, str], list[dict]] | None = None,
        market_skill_extractor: Callable[[list[dict]], dict[str, list[dict]]]
        | None = None,
        reading_fetcher: Callable[[SkillProfile], list[Any]] | None = None,
        video_fetcher: Callable[[SkillProfile], list[Any]] | None = None,
        question_generator: Callable[..., list[Any]] | None = None,
        resource_writer: Callable[..., int] | None = None,
        question_writer: Callable[..., int] | None = None,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repo = IndividualLearningRepository(db)
        self._db = db
        self._neo4j_driver = neo4j_driver
        self._storage = storage if storage is not None else blob_service
        self._cv_text_extractor = cv_text_extractor or extract_cv_text
        self._cv_profile_extractor = cv_profile_extractor
        self._graph_checkpointer = graph_checkpointer
        self._job_searcher = job_searcher or search_jobs_for_titles
        self._market_skill_extractor = (
            market_skill_extractor or extract_market_skills_for_jobs
        )
        self._reading_fetcher = reading_fetcher
        self._video_fetcher = video_fetcher
        self._question_generator = question_generator
        self._resource_writer = resource_writer
        self._question_writer = question_writer
        self._run_id_factory = run_id_factory or (lambda: str(uuid.uuid4()))
        self._workflow_lease_heartbeat: _WorkflowLeaseHeartbeat | None = None

    def get_profile(self, user_id: int) -> IndividualProfileRead:
        profile = self._repo.get_profile(user_id)
        if profile is None:
            return IndividualProfileRead(user_id=user_id, onboarding_status="needs_cv")

        document, extraction = self._repo.get_cv_lifecycle(user_id=user_id)
        lifecycle_completed = (
            document is not None
            and document.status == CVDocumentStatus.COMPLETED.value
            and extraction is not None
            and extraction.status == IndividualRunStatus.COMPLETED.value
        )
        thread_id = (
            self._build_thread_id(user_id, document.id, extraction.id)
            if lifecycle_completed and extraction is not None
            else None
        )
        pending_interrupt: dict[str, Any] | None = None
        snapshot = None
        if thread_id is not None:
            graph = self._get_graph()
            snapshot = graph.get_state(self._graph_config(thread_id))
            pending_interrupt = self._get_snapshot_interrupt(snapshot)

        next_step_by_status = {
            "needs_cv": "upload_cv",
            "extracting": "wait_for_extraction",
            "needs_profile_review": "review_profile",
            "needs_jobs": "search_jobs",
            "needs_skill_selection": "select_jobs_and_skills",
            "ready": "learning_path",
            "error": "retry_cv",
        }
        next_step = next_step_by_status.get(profile.onboarding_status, "upload_cv")
        snapshot_next = tuple(getattr(snapshot, "next", ()))
        if snapshot_next == ("search_jobs",):
            next_step = "search_jobs"
        elif pending_interrupt is not None:
            if pending_interrupt.get("kind") == "review_profile_and_roles":
                next_step = "review_profile"
            elif pending_interrupt.get("kind") == "choose_jobs_and_skills":
                next_step = "select_jobs_and_skills"
        elif document is not None and not lifecycle_completed:
            if (
                document.status == CVDocumentStatus.FAILED.value
                or extraction is not None
                and extraction.status == IndividualRunStatus.FAILED.value
                or not self._cv_attempt_is_active(profile)
            ):
                next_step = "retry_cv"
            else:
                next_step = "wait_for_extraction"

        return IndividualProfileRead(
            user_id=user_id,
            onboarding_status=profile.onboarding_status,
            target_titles=list(profile.target_titles_json or []),
            preferred_country=profile.preferred_country,
            preferred_location=profile.preferred_location,
            reviewed_at=profile.reviewed_at,
            cv_document_id=document.id if document is not None else None,
            extraction_run_id=extraction.id if lifecycle_completed else None,
            active_thread_id=thread_id,
            next_step=next_step,
            extracted_profile=(
                dict(extraction.extracted_profile_json or {})
                if lifecycle_completed and extraction is not None
                else None
            ),
            pending_interrupt=pending_interrupt,
        )

    @staticmethod
    def _cv_attempt_is_active(profile: Any) -> bool:
        started_at = getattr(profile, "cv_attempt_started_at", None)
        return bool(
            getattr(profile, "cv_attempt_token", None)
            and started_at is not None
            and started_at > datetime.now(UTC) - CV_ATTEMPT_STALE_AFTER
        )

    @staticmethod
    def _get_snapshot_interrupt(snapshot: Any) -> dict[str, Any] | None:
        interrupts = IndividualLearningService._get_snapshot_interrupts(snapshot)
        return interrupts[0] if interrupts else None

    @staticmethod
    def _get_snapshot_interrupts(snapshot: Any) -> list[dict[str, Any]]:
        interrupts: list[dict[str, Any]] = []
        for task in getattr(snapshot, "tasks", ()):
            for graph_interrupt in getattr(task, "interrupts", ()):
                value = getattr(graph_interrupt, "value", None)
                if isinstance(value, dict):
                    interrupts.append(dict(value))
        return interrupts

    def get_skill_banks(self, user_id: int) -> IndividualSkillBanksResponse:
        driver = self._require_neo4j_driver()
        with driver.session() as session:
            raw_bank = get_individual_skill_bank(session, user_id=user_id)

        cv_skill_names = self._list_cv_skill_names(user_id)
        selected_skill_names = list(raw_bank["selected_skill_names"])
        selected_skill_set = {name.casefold() for name in selected_skill_names}
        interested_urls = list(raw_bank["interested_posting_urls"])
        interested_url_set = set(interested_urls)

        postings: list[IndividualSkillBankJobPosting] = []
        for posting in raw_bank["postings"]:
            skills = list(posting.get("skills") or [])
            skill_names = [
                str(skill.get("name", "")).strip()
                for skill in skills
                if str(skill.get("name", "")).strip()
            ]
            coverage_by_name = {
                score.skill_name: score
                for score in score_market_skill_coverage(
                    cv_skill_names=cv_skill_names,
                    market_skill_names=skill_names,
                )
            }
            postings.append(
                IndividualSkillBankJobPosting(
                    url=str(posting.get("url", "")),
                    title=str(posting.get("title", "")),
                    company=str(posting.get("company", "")),
                    site=posting.get("site"),
                    search_term=posting.get("search_term"),
                    is_interested=str(posting.get("url", "")) in interested_url_set,
                    match_score=posting.get("match_score"),
                    skill_extraction_status=posting.get(
                        "skill_extraction_status", "completed"
                    ),
                    skill_extraction_error=posting.get("skill_extraction_error"),
                    skills=[
                        IndividualSkillBankSkill(
                            name=skill_name,
                            description=skill.get("description"),
                            category=skill.get("category"),
                            is_selected=skill_name.casefold() in selected_skill_set,
                            coverage=coverage_by_name.get(skill_name).coverage
                            if coverage_by_name.get(skill_name) is not None
                            else "unknown",
                        )
                        for skill_name, skill in (
                            (
                                str(skill.get("name", "")).strip(),
                                skill,
                            )
                            for skill in skills
                        )
                        if skill_name
                    ],
                )
            )

        return IndividualSkillBanksResponse(
            market_skill_bank=postings,
            selected_skill_names=selected_skill_names,
            interested_posting_urls=interested_urls,
        )

    def select_interested_jobs(self, user_id: int, posting_urls: list[str]) -> int:
        cleaned_posting_urls = list(
            dict.fromkeys(url.strip() for url in posting_urls if url.strip())
        )
        if not cleaned_posting_urls:
            return 0

        search_run = self._repo.get_latest_job_search_run(user_id)
        candidate_urls = {
            str(job.get("url", "")).strip()
            for job in (search_run.fetched_jobs_json if search_run is not None else [])
            if isinstance(job, dict) and str(job.get("url", "")).strip()
        }
        if search_run is None or any(
            url not in candidate_urls for url in cleaned_posting_urls
        ):
            raise ValueError("Select only jobs from your latest candidate search")

        driver = self._require_neo4j_driver()
        with driver.session() as session:
            selected_count = select_job_postings(
                session,
                user_id=user_id,
                posting_urls=cleaned_posting_urls,
                run_id=str(search_run.id),
            )
        if selected_count != len(cleaned_posting_urls):
            raise ValueError("Candidate job projection is incomplete; retry job search")
        if not self._repo.record_job_selections(
            user_id=user_id,
            job_search_run_id=search_run.id,
            posting_urls=cleaned_posting_urls,
        ):
            raise ValueError("Job search run does not belong to the current user")
        return selected_count

    def validate_selected_skill_names(self, skill_names: list[str]) -> None:
        if not skill_names:
            raise ValueError("Select at least one market skill before building")
        if len(skill_names) > 20:
            raise ValueError("Select no more than 20 market skills before building")

    def select_skills(
        self,
        user_id: int,
        skill_names: list[str],
        source: str = "individual_market_skill",
    ) -> int:
        cleaned_skill_names = self._clean_skill_names(skill_names)
        if not cleaned_skill_names:
            self.validate_selected_skill_names(cleaned_skill_names)

        driver = self._require_neo4j_driver()
        with driver.session() as session:
            resolved_skill_names = resolve_interested_market_skill_names(
                session,
                user_id=user_id,
                skill_names=cleaned_skill_names,
            )
            if len(resolved_skill_names) != len(cleaned_skill_names):
                raise ValueError(
                    "Select only market skills sourced from your interested jobs"
                )
            combined_skill_names = self._combine_selected_skill_names(
                get_selected_market_skill_names(session, user_id=user_id),
                resolved_skill_names,
            )
            self.validate_selected_skill_names(combined_skill_names)
            if not resolved_skill_names:
                return 0
            return select_market_skills(
                session,
                user_id=user_id,
                skill_names=resolved_skill_names,
                source=source,
            )

    def deselect_skills(self, user_id: int, skill_names: list[str]) -> int:
        cleaned_skill_names = self._clean_skill_names(skill_names)
        if not cleaned_skill_names:
            return 0

        driver = self._require_neo4j_driver()
        with driver.session() as session:
            return deselect_market_skills(
                session,
                user_id=user_id,
                skill_names=cleaned_skill_names,
            )

    def build_learning_path(
        self,
        user_id: int,
        selected_skill_names: list[str],
    ) -> dict[str, str]:
        cleaned_skill_names = self._clean_skill_names(selected_skill_names)

        driver = self._require_neo4j_driver()
        with driver.session() as session:
            if cleaned_skill_names:
                resolved_skill_names = resolve_interested_market_skill_names(
                    session,
                    user_id=user_id,
                    skill_names=cleaned_skill_names,
                )
                if len(resolved_skill_names) != len(cleaned_skill_names):
                    raise ValueError("Select only valid market skills before building")

                combined_skill_names = self._combine_selected_skill_names(
                    get_selected_market_skill_names(session, user_id=user_id),
                    resolved_skill_names,
                )
                self.validate_selected_skill_names(combined_skill_names)
                select_market_skills(
                    session,
                    user_id=user_id,
                    skill_names=resolved_skill_names,
                    source="individual_market_skill",
                )
                selected_skills = get_market_skill_profiles(
                    session,
                    skill_names=resolved_skill_names,
                )
                if len(selected_skills) != len(resolved_skill_names):
                    raise ValueError("Select only valid market skills before building")
            else:
                persisted_skill_names = get_selected_market_skill_names(
                    session,
                    user_id=user_id,
                )
                self.validate_selected_skill_names(persisted_skill_names)
                selected_skills = get_selected_market_skill_profiles(
                    session,
                    user_id=user_id,
                )

        if not selected_skills:
            raise ValueError("Select at least one valid market skill before building")

        selected_names = [str(skill.get("name", "")) for skill in selected_skills]
        learning_run = self._repo.create_learning_run(
            user_id=user_id,
            selected_skill_names=selected_names,
            run_id=self._run_id_factory(),
        )
        errors: list[str] = []
        successful_steps = 0
        reading_fetcher = self._reading_fetcher or fetch_readings_for_skill
        video_fetcher = self._video_fetcher or fetch_videos_for_skill
        question_generator = self._question_generator or generate_questions_for_skill
        resource_writer = self._resource_writer or write_resources
        question_writer = self._question_writer or write_market_skill_questions

        for skill in selected_skills:
            skill_profile = self._build_market_skill_profile(skill)
            try:
                readings = reading_fetcher(skill_profile)
                if readings:
                    with driver.session() as session:
                        resource_writer(
                            session,
                            skill_profile.name,
                            skill_profile.skill_type,
                            readings,
                            READING_LABEL,
                            READING_RELATIONSHIP,
                        )
                successful_steps += 1
            except Exception as exc:
                errors.append(
                    f"{skill_profile.name} readings: "
                    f"{str(exc)[:200] or type(exc).__name__}"
                )

            try:
                videos = video_fetcher(skill_profile)
                if videos:
                    with driver.session() as session:
                        resource_writer(
                            session,
                            skill_profile.name,
                            skill_profile.skill_type,
                            videos,
                            VIDEO_LABEL,
                            VIDEO_RELATIONSHIP,
                        )
                successful_steps += 1
            except Exception as exc:
                errors.append(
                    f"{skill_profile.name} videos: "
                    f"{str(exc)[:200] or type(exc).__name__}"
                )

            try:
                questions = question_generator(
                    skill_profile.name,
                    skill_profile.description,
                    skill_profile.concepts,
                    skill_profile.course_level,
                )
                if questions:
                    with driver.session() as session:
                        question_writer(
                            session,
                            skill_profile.name,
                            questions,
                        )
                successful_steps += 1
            except Exception as exc:
                errors.append(
                    f"{skill_profile.name} questions: "
                    f"{str(exc)[:200] or type(exc).__name__}"
                )

        run_status = (
            IndividualRunStatus.FAILED.value
            if errors and successful_steps == 0
            else IndividualRunStatus.PARTIAL.value
            if errors
            else IndividualRunStatus.COMPLETED.value
        )
        self._repo.complete_learning_run(
            learning_run,
            status=run_status,
            error_message="; ".join(errors) or None,
        )
        return {"status": run_status, "run_id": learning_run.run_id}

    def get_learning_path(self, user_id: int) -> dict[str, object]:
        driver = self._require_neo4j_driver()
        with driver.session() as session:
            learning_path = dict(get_individual_learning_path(session, user_id=user_id))

        latest_run = self._repo.get_latest_learning_run(user_id)
        selected_skill_snapshot = {
            str(skill.get("name", "")).strip().casefold()
            for skill in learning_path.get("selected_skills", [])
            if isinstance(skill, dict) and str(skill.get("name", "")).strip()
        }
        latest_run_snapshot = (
            {
                str(name).strip().casefold()
                for name in getattr(latest_run, "selected_skill_names_json", [])
                if str(name).strip()
            }
            if latest_run is not None
            else set()
        )
        build_status: str | None = None
        build_run_id: str | None = None
        build_error: str | None = None
        if latest_run is not None and latest_run_snapshot == selected_skill_snapshot:
            build_run_id = latest_run.run_id
            if latest_run.status == IndividualRunStatus.COMPLETED.value:
                build_status = IndividualRunStatus.COMPLETED.value
            elif latest_run.status == IndividualRunStatus.PARTIAL.value:
                build_status = IndividualRunStatus.PARTIAL.value
                build_error = (
                    "Some resources could not be generated; retry to complete the path"
                )
            elif latest_run.status == IndividualRunStatus.FAILED.value:
                build_status = IndividualRunStatus.FAILED.value
                build_error = "Resource generation failed; retry"
            else:
                build_status = IndividualRunStatus.FAILED.value
                build_error = "Resource generation was interrupted; retry"

        learning_path.update(
            {
                "build_status": build_status,
                "build_run_id": build_run_id,
                "build_error": build_error,
            }
        )
        return learning_path

    async def upload_cv(self, user_id: int, file: UploadFile) -> CVDocumentRead:
        filename = (file.filename or "").strip()
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CV filename is required",
            )
        if not is_supported_cv_file(
            filename=filename,
            content_type=file.content_type,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF and DOCX CV files are supported",
            )

        content = await self._read_cv_upload(file)
        content_hash = self._storage.sha256_hex(content)
        blob_path = f"users/{user_id}/cv/{content_hash}/document"
        attempt_token = str(uuid.uuid4())
        now = datetime.now(UTC)
        if not self._repo.claim_cv_attempt(
            user_id=user_id,
            attempt_token=attempt_token,
            now=now,
            stale_before=now - CV_ATTEMPT_STALE_AFTER,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CV processing is already in progress",
            )
        try:
            try:
                await self._storage.upload_bytes(content, blob_path)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="CV storage is temporarily unavailable; retry",
                ) from exc
            self._renew_cv_attempt_or_raise(
                user_id=user_id,
                attempt_token=attempt_token,
            )

            cv_document = self._repo.upsert_cv_document(
                user_id=user_id,
                blob_path=blob_path,
                original_filename=filename,
                content_type=file.content_type,
                content_hash=content_hash,
                size_bytes=len(content),
            )
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="extracting",
            )
            return await self._process_cv_document(
                user_id=user_id,
                cv_document=cv_document,
                content=content,
                attempt_token=attempt_token,
            )
        finally:
            self._repo.release_cv_attempt(
                user_id=user_id,
                attempt_token=attempt_token,
            )

    async def retry_cv_document(
        self,
        user_id: int,
        cv_document_id: int,
    ) -> CVDocumentRead:
        document = self._repo.get_owned_cv_document(
            user_id=user_id,
            cv_document_id=cv_document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV document not found",
            )
        if document.status not in {
            CVDocumentStatus.FAILED.value,
            CVDocumentStatus.PROCESSING.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only a failed CV document can be retried",
            )

        attempt_token = str(uuid.uuid4())
        now = datetime.now(UTC)
        if not self._repo.claim_cv_attempt(
            user_id=user_id,
            attempt_token=attempt_token,
            now=now,
            stale_before=now - CV_ATTEMPT_STALE_AFTER,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CV processing is already in progress",
            )
        try:
            document = self._repo.get_owned_cv_document(
                user_id=user_id,
                cv_document_id=cv_document_id,
            )
            if document is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="CV document not found",
                )
            current_document = self._repo.get_latest_cv_document(user_id)
            if current_document is None or current_document.id != document.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="CV document is stale; reload the current profile",
                )
            if document.status not in {
                CVDocumentStatus.FAILED.value,
                CVDocumentStatus.PROCESSING.value,
            }:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only a failed CV document can be retried",
                )

            try:
                content = await asyncio.to_thread(
                    self._storage.download_bytes,
                    document.blob_path,
                    max_bytes=MAX_CV_UPLOAD_BYTES,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Stored CV file exceeds the upload size limit",
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="CV storage is temporarily unavailable; retry",
                ) from exc

            if (
                not content
                or len(content) > MAX_CV_UPLOAD_BYTES
                or self._storage.sha256_hex(content) != document.content_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stored CV file is invalid; upload the CV again",
                )
            self._renew_cv_attempt_or_raise(
                user_id=user_id,
                attempt_token=attempt_token,
            )

            document = self._repo.upsert_cv_document(
                user_id=user_id,
                blob_path=document.blob_path,
                original_filename=document.original_filename,
                content_type=document.content_type,
                content_hash=document.content_hash,
                size_bytes=len(content),
            )
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="extracting",
            )
            return await self._process_cv_document(
                user_id=user_id,
                cv_document=document,
                content=content,
                attempt_token=attempt_token,
            )
        finally:
            self._repo.release_cv_attempt(
                user_id=user_id,
                attempt_token=attempt_token,
            )

    async def _read_cv_upload(self, file: UploadFile) -> bytes:
        await file.seek(0)
        chunks: list[bytes] = []
        total_bytes = 0
        while True:
            chunk = await file.read(CV_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_CV_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="CV file exceeds the upload size limit",
                )
            chunks.append(chunk)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CV file is empty",
            )
        return b"".join(chunks)

    async def _process_cv_document(
        self,
        *,
        user_id: int,
        cv_document: CVDocument,
        content: bytes,
        attempt_token: str,
    ) -> CVDocumentRead:
        profile_extractor = self._cv_profile_extractor
        extraction_run = self._repo.create_cv_extraction_run(
            cv_document_id=cv_document.id,
            user_id=user_id,
            model_provider=str(
                getattr(profile_extractor, "model_provider", "openai-compatible")
            ),
            model_name=str(
                getattr(profile_extractor, "model_name", settings.llm_model)
            ),
            raw_text_hash="",
        )

        try:
            extracted_text = await asyncio.to_thread(
                self._cv_text_extractor,
                filename=cv_document.original_filename,
                content_type=cv_document.content_type,
                data=content,
            )
        except ValueError as exc:
            raw_error = str(exc)
            error_message = (
                raw_error
                if raw_error in _SAFE_CV_PARSE_ERRORS
                else "CV file could not be parsed safely"
            )
            self._fail_cv_attempt(
                extraction_run,
                document=cv_document,
                user_id=user_id,
                error_message=error_message,
                attempt_token=attempt_token,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            ) from exc
        except Exception as exc:
            self._fail_cv_attempt(
                extraction_run,
                document=cv_document,
                user_id=user_id,
                error_message="CV parser failed",
                attempt_token=attempt_token,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse CV file",
            ) from exc

        self._renew_cv_attempt_or_raise(
            user_id=user_id,
            attempt_token=attempt_token,
        )

        self._repo.set_cv_extraction_text_hash(
            extraction_run,
            raw_text_hash=hashlib.sha256(extracted_text.encode("utf-8")).hexdigest(),
        )

        try:
            if profile_extractor is None:
                profile_extractor = StructuredCVProfileExtractor()
            extracted_profile = CVProfileExtraction.model_validate(
                await asyncio.to_thread(profile_extractor.extract, extracted_text)
            )
        except Exception as exc:
            error_message = "Structured CV extraction failed"
            self._fail_cv_attempt(
                extraction_run,
                document=cv_document,
                user_id=user_id,
                error_message=error_message,
                attempt_token=attempt_token,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to extract a structured CV profile",
            ) from exc

        try:
            self._repo.complete_cv_lifecycle(
                document=cv_document,
                extraction=extraction_run,
                user_id=user_id,
                extracted_profile=extracted_profile.model_dump(mode="json"),
                target_title_suggestions=list(
                    extracted_profile.target_title_suggestions
                ),
                confidence_summary=dict(extracted_profile.confidence_summary),
                attempt_token=attempt_token,
            )
        except CVAttemptSupersededError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CV processing attempt was superseded",
            ) from exc
        except Exception as exc:
            completion_state = self._repo.get_cv_lifecycle_completion_state(
                user_id=user_id,
                cv_document_id=cv_document.id,
                extraction_run_id=extraction_run.id,
            )
            if completion_state is not True:
                if completion_state is False:
                    self._fail_cv_attempt(
                        extraction_run,
                        document=cv_document,
                        user_id=user_id,
                        error_message="CV finalization failed",
                        attempt_token=attempt_token,
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to finalize CV processing",
                ) from exc

        return CVDocumentRead(
            id=cv_document.id,
            user_id=cv_document.user_id,
            original_filename=cv_document.original_filename,
            content_type=cv_document.content_type,
            status=cv_document.status,
        )

    def _fail_cv_attempt(
        self,
        extraction_run: CVExtractionRun,
        *,
        document: CVDocument,
        user_id: int,
        error_message: str,
        attempt_token: str,
    ) -> None:
        try:
            self._repo.fail_cv_lifecycle(
                extraction_run,
                document=document,
                user_id=user_id,
                error_message=error_message,
                attempt_token=attempt_token,
            )
        except CVAttemptSupersededError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CV processing attempt was superseded",
            ) from exc

    def _renew_cv_attempt_or_raise(
        self,
        *,
        user_id: int,
        attempt_token: str,
    ) -> None:
        if not self._repo.renew_cv_attempt(
            user_id=user_id,
            attempt_token=attempt_token,
            now=datetime.now(UTC),
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="CV processing attempt was superseded",
            )

    @contextmanager
    def _workflow_operation(
        self,
        *,
        extraction_run_id: int,
        user_id: int,
    ) -> Iterator[None]:
        operation_token = str(uuid.uuid4())
        now = datetime.now(UTC)
        if not self._repo.claim_workflow_operation(
            extraction_run_id=extraction_run_id,
            user_id=user_id,
            operation_token=operation_token,
            now=now,
            stale_before=now - WORKFLOW_OPERATION_STALE_AFTER,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow operation is already in progress",
            )

        heartbeat: _WorkflowLeaseHeartbeat | None = None
        heartbeat_started = False
        try:
            if self._db is not None:
                heartbeat = _WorkflowLeaseHeartbeat(
                    bind=self._db.get_bind(),
                    extraction_run_id=extraction_run_id,
                    user_id=user_id,
                    operation_token=operation_token,
                    interval_seconds=WORKFLOW_LEASE_HEARTBEAT_SECONDS,
                )
                self._workflow_lease_heartbeat = heartbeat
                heartbeat.start()
                heartbeat_started = True
                heartbeat.assert_owned()
            yield
            self._assert_workflow_owned()
            if heartbeat_started and heartbeat is not None:
                heartbeat.stop()
                heartbeat_started = False
                heartbeat.assert_owned()
            if not self._repo.renew_workflow_operation(
                extraction_run_id=extraction_run_id,
                user_id=user_id,
                operation_token=operation_token,
                now=datetime.now(UTC),
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Workflow operation was superseded",
                )
        finally:
            if heartbeat_started and heartbeat is not None:
                heartbeat.stop()
            self._workflow_lease_heartbeat = None
            self._repo.release_workflow_operation(
                extraction_run_id=extraction_run_id,
                user_id=user_id,
                operation_token=operation_token,
            )

    def _assert_workflow_owned(self) -> None:
        heartbeat = self._workflow_lease_heartbeat
        if heartbeat is not None:
            heartbeat.assert_owned()

    def start_individual_graph(
        self, user_id: int, cv_document_id: int
    ) -> IndividualGraphStartResponse:
        document, extraction = self._repo.get_cv_lifecycle(
            user_id=user_id,
            cv_document_id=cv_document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV document not found",
            )
        current_document, current_extraction = self._repo.get_cv_lifecycle(
            user_id=user_id,
        )
        if (
            current_document is None
            or current_document.id != document.id
            or (current_extraction is None) != (extraction is None)
            or current_extraction is not None
            and extraction is not None
            and current_extraction.id != extraction.id
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow attempt is stale; reload the current profile",
            )
        if (
            document.status != CVDocumentStatus.COMPLETED.value
            or extraction is None
            or extraction.status != IndividualRunStatus.COMPLETED.value
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "CV processing is incomplete; retry extraction or upload the CV again"
                ),
            )

        thread_id = self._build_thread_id(
            user_id,
            cv_document_id,
            extraction.id,
        )
        with self._workflow_operation(
            extraction_run_id=extraction.id,
            user_id=user_id,
        ):
            self._assert_workflow_owned()
            graph = self._get_graph()
            config = self._graph_config(thread_id)
            self._assert_workflow_owned()
            snapshot = graph.get_state(config)
            self._assert_workflow_owned()
            snapshot_values = getattr(snapshot, "values", {})
            if (
                isinstance(snapshot_values, dict)
                and snapshot_values.get("thread_id") == thread_id
            ):
                return IndividualGraphStartResponse(
                    **self._build_graph_snapshot_response(thread_id, snapshot)
                )
            self._assert_workflow_owned()
            result = graph.invoke(
                {
                    "thread_id": thread_id,
                    "user_id": user_id,
                    "cv_document_id": cv_document_id,
                    "profile": self._profile_payload_from_extraction(extraction),
                    "target_titles": [],
                    "candidate_jobs": [],
                    "skill_bank": [],
                    "selected_posting_urls": [],
                    "selected_skill_names": [],
                },
                config,
            )
            self._assert_workflow_owned()
            return IndividualGraphStartResponse(
                **self._build_graph_response(thread_id, result)
            )

    def resume_individual_graph(
        self, user_id: int, thread_id: str, payload: dict[str, Any]
    ) -> IndividualGraphResumeResponse:
        cv_document_id, extraction_run_id = self._validate_resume_thread(
            user_id,
            thread_id,
        )
        with self._workflow_operation(
            extraction_run_id=extraction_run_id,
            user_id=user_id,
        ):
            self._assert_workflow_owned()
            graph = self._get_graph()
            config = self._graph_config(thread_id)
            resume_payload = dict(payload)
            self._assert_workflow_owned()
            snapshot = graph.get_state(config)
            self._assert_workflow_owned()
            resume_stage = self._resolve_resume_stage(snapshot)
            if resume_stage == "review_profile_and_roles":
                if "approved" not in resume_payload:
                    self._raise_stale_resume_conflict()
                resume_payload = self._approve_profile_review(
                    user_id=user_id,
                    cv_document_id=cv_document_id,
                    extraction_run_id=extraction_run_id,
                    payload=resume_payload,
                    checkpoint_profile=dict(snapshot.values.get("profile", {})),
                )
            elif resume_stage == "search_jobs":
                if (
                    resume_payload.get("approved") is not True
                    or "target_titles" not in resume_payload
                ):
                    self._raise_stale_resume_conflict()
            elif resume_stage == "choose_jobs_and_skills":
                if (
                    "selected_posting_urls" not in resume_payload
                    or "selected_skill_names" not in resume_payload
                ):
                    self._raise_stale_resume_conflict()
                resume_payload = self._persist_checkpointed_selections(
                    user_id=user_id,
                    payload=resume_payload,
                    checkpoint_state=dict(snapshot.values),
                )
            self._assert_workflow_owned()
            result = graph.invoke(Command(resume=resume_payload), config)
            self._assert_workflow_owned()
            response_data = self._build_graph_response(thread_id, result)
            return IndividualGraphResumeResponse(**response_data)

    def _resolve_resume_stage(self, snapshot: Any) -> str:
        next_nodes = tuple(getattr(snapshot, "next", ()))
        if len(next_nodes) != 1:
            self._raise_stale_resume_conflict()
        stage = next_nodes[0]
        expected_interrupt_kinds = {
            "review_profile_and_roles": "review_profile_and_roles",
            "choose_jobs_and_skills": "choose_jobs_and_skills",
        }
        if stage == "search_jobs":
            if self._get_snapshot_interrupts(snapshot):
                self._raise_stale_resume_conflict()
            return stage
        expected_kind = expected_interrupt_kinds.get(stage)
        if expected_kind is None:
            self._raise_stale_resume_conflict()
        interrupts = self._get_snapshot_interrupts(snapshot)
        if len(interrupts) != 1 or interrupts[0].get("kind") != expected_kind:
            self._raise_stale_resume_conflict()
        return stage

    @staticmethod
    def _raise_stale_resume_conflict() -> None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow state changed; reload the current profile",
        )

    @staticmethod
    def _build_thread_id(
        user_id: int,
        cv_document_id: int,
        extraction_run_id: int,
    ) -> str:
        return (
            f"individual-{user_id}-cv-{cv_document_id}-extraction-{extraction_run_id}"
        )

    @staticmethod
    def _graph_config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    def _get_graph(self):
        checkpointer = self._graph_checkpointer
        if checkpointer is None:
            checkpointer = get_individual_learning_checkpointer()
        return build_individual_learning_graph(
            checkpointer=checkpointer,
            job_search_node=self._run_job_search,
            ownership_guard=self._assert_workflow_owned,
        )

    def _run_job_search(self, state: dict[str, Any]) -> dict[str, Any]:
        self._assert_workflow_owned()
        user_id = int(state["user_id"])
        target_titles = self._clean_target_titles(state.get("target_titles", []))
        profile = self._repo.get_profile(user_id)
        country = (profile.preferred_country if profile is not None else None) or ""
        location = (profile.preferred_location if profile is not None else None) or ""
        self._assert_workflow_owned()
        search_run = self._repo.get_or_create_job_search_run(
            user_id=user_id,
            workflow_thread_id=str(state["thread_id"]),
            target_titles=target_titles,
            country=country,
            location=location,
        )
        self._assert_workflow_owned()

        errors: list[str] = []
        jobs_by_url: dict[str, dict[str, Any]] = {}
        for title in target_titles:
            self._assert_workflow_owned()
            try:
                found_jobs = self._job_searcher([title], country, location)
            except Exception:
                self._assert_workflow_owned()
                errors.append(f"{title}: job search failed")
                continue
            self._assert_workflow_owned()
            for raw_job in found_jobs:
                job = self._normalize_job(raw_job, search_term=title)
                if job is not None:
                    jobs_by_url[job["url"]] = {"raw": raw_job, "job": job}

        profile_payload = state.get("profile", {})
        cv_skill_names = [
            str(skill.get("name", "")).strip()
            for skill in profile_payload.get("skills", [])
            if isinstance(skill, dict) and str(skill.get("name", "")).strip()
        ]
        skills_by_job_url: dict[str, list[dict[str, str]]] = {}
        candidate_jobs: list[dict[str, Any]] = []
        scores: list[dict[str, Any]] = []
        skill_gaps: list[dict[str, Any]] = []

        for entry in jobs_by_url.values():
            raw_job = entry["raw"]
            job = entry["job"]
            url = job["url"]
            self._assert_workflow_owned()
            try:
                extracted = self._market_skill_extractor([raw_job])
                skills = self._normalize_market_skills(extracted.get(url, []))
                skill_extraction_status = "completed"
                skill_extraction_error = None
            except Exception:
                self._assert_workflow_owned()
                errors.append(f"{job['title'] or url}: skill extraction failed")
                skills = []
                skill_extraction_status = "failed"
                skill_extraction_error = "Skill extraction is temporarily unavailable"
            self._assert_workflow_owned()
            skills_by_job_url[url] = skills

            coverage = score_market_skill_coverage(
                cv_skill_names=cv_skill_names,
                market_skill_names=[skill["name"] for skill in skills],
            )
            coverage_by_name = {item.skill_name: item for item in coverage}
            covered_count = sum(item.coverage == "covered" for item in coverage)
            match_score = (
                round((covered_count / len(coverage)) * 100, 2) if coverage else 0.0
            )
            candidate_skills = [
                {
                    **skill,
                    "coverage": coverage_by_name[skill["name"]].coverage,
                }
                for skill in skills
            ]
            candidate = {
                **job,
                "match_score": match_score,
                "skills": candidate_skills,
                "skill_extraction_status": skill_extraction_status,
            }
            if skill_extraction_error is not None:
                candidate["skill_extraction_error"] = skill_extraction_error
            candidate_jobs.append(candidate)
            scores.append(
                {
                    "job_url": url,
                    "match_score": match_score,
                    "covered_skills": covered_count,
                    "total_skills": len(coverage),
                }
            )
            skill_gaps.extend(
                {
                    "job_url": url,
                    **item.model_dump(mode="json"),
                }
                for item in coverage
            )

        candidate_jobs.sort(
            key=lambda job: (
                -float(job["match_score"]),
                str(job["title"]).casefold(),
                str(job["url"]),
            )
        )
        score_order = {job["url"]: index for index, job in enumerate(candidate_jobs)}
        scores.sort(key=lambda item: score_order[item["job_url"]])

        failure_detail: str | None = None
        if not candidate_jobs:
            failure_detail = "No usable job postings were found"
        elif not any(job.get("skills") for job in candidate_jobs):
            failure_detail = (
                "No usable market skills were extracted; retry job search or edit "
                "target titles"
            )
        if failure_detail is not None and failure_detail not in errors:
            errors.append(failure_detail)
        run_status = (
            IndividualRunStatus.FAILED.value
            if failure_detail is not None
            else IndividualRunStatus.PARTIAL.value
            if errors
            else IndividualRunStatus.COMPLETED.value
        )
        error_message = "; ".join(errors) or None
        self._assert_workflow_owned()
        self._repo.complete_job_search_run(
            search_run,
            jobs=candidate_jobs,
            status=run_status,
            error_message=error_message,
        )
        self._assert_workflow_owned()
        match_run = self._repo.get_or_create_job_match_run(
            user_id=user_id,
            job_search_run_id=search_run.id,
            workflow_thread_id=str(state["thread_id"]),
        )
        self._assert_workflow_owned()
        self._repo.complete_job_match_run(
            match_run,
            scores=scores,
            skill_gaps=skill_gaps,
            status=run_status,
        )
        self._assert_workflow_owned()

        if run_status == IndividualRunStatus.FAILED.value:
            self._assert_workflow_owned()
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="needs_jobs",
            )
            self._assert_workflow_owned()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=failure_detail or "No usable job postings were found",
            )

        driver = self._require_neo4j_driver()
        self._assert_workflow_owned()
        try:
            with driver.session() as session:
                self._assert_workflow_owned()
                upsert_job_postings_and_market_skills(
                    session,
                    jobs=candidate_jobs,
                    skills_by_job_url=skills_by_job_url,
                )
                self._assert_workflow_owned()
        except HTTPException:
            raise
        except Exception as exc:
            self._assert_workflow_owned()
            projection_error = (
                f"Graph projection: {str(exc)[:200] or type(exc).__name__}"
            )
            combined_error = "; ".join(filter(None, [error_message, projection_error]))
            self._assert_workflow_owned()
            self._repo.complete_job_search_run(
                search_run,
                jobs=candidate_jobs,
                status=IndividualRunStatus.PARTIAL.value,
                error_message=combined_error,
            )
            self._assert_workflow_owned()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Job results could not be projected to the knowledge graph",
            ) from exc

        self._assert_workflow_owned()
        self._repo.upsert_profile_status(
            user_id=user_id,
            onboarding_status="needs_skill_selection",
        )
        self._assert_workflow_owned()
        return {
            "candidate_jobs": candidate_jobs,
            "skill_bank": self._derive_skill_bank(candidate_jobs),
            "job_search_run_id": search_run.id,
            "job_match_run_id": match_run.id,
        }

    @staticmethod
    def _normalize_job(
        raw_job: object,
        *,
        search_term: str,
    ) -> dict[str, Any] | None:
        if not isinstance(raw_job, dict):
            return None
        url = str(raw_job.get("url", "") or "").strip()
        if not url:
            return None
        return {
            "url": url,
            "title": str(raw_job.get("title", "") or "").strip(),
            "company": str(raw_job.get("company", "") or "").strip(),
            "site": str(raw_job.get("site", "") or "").strip() or None,
            "search_term": str(raw_job.get("search_term", "") or search_term).strip(),
            "country": str(raw_job.get("country", "") or "").strip(),
            "location": str(raw_job.get("location", "") or "").strip(),
            "description": str(raw_job.get("description", "") or "").strip(),
        }

    @staticmethod
    def _normalize_market_skills(raw_skills: object) -> list[dict[str, str]]:
        if not isinstance(raw_skills, list):
            return []
        skills: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_skill in raw_skills:
            if not isinstance(raw_skill, dict):
                continue
            name = " ".join(str(raw_skill.get("name", "")).split())
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            skills.append(
                {
                    "name": name,
                    "category": str(raw_skill.get("category", "") or "").strip(),
                    "description": str(raw_skill.get("description", "") or "").strip(),
                }
            )
        return skills

    @staticmethod
    def _derive_skill_bank(
        candidate_jobs: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        skills: list[dict[str, str]] = []
        seen: set[str] = set()
        for job in candidate_jobs:
            for skill in job.get("skills", []):
                name = str(skill.get("name", "")).strip()
                if not name or name.casefold() in seen:
                    continue
                seen.add(name.casefold())
                skills.append(
                    {
                        "name": name,
                        "category": str(skill.get("category", "") or ""),
                        "description": str(skill.get("description", "") or ""),
                    }
                )
        return skills

    def _approve_profile_review(
        self,
        *,
        user_id: int,
        cv_document_id: int,
        extraction_run_id: int,
        payload: dict[str, Any],
        checkpoint_profile: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_workflow_owned()
        if payload.get("approved") is not True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile approval is required before job search",
            )
        raw_target_titles = payload.get("target_titles", [])
        if not isinstance(raw_target_titles, list) or any(
            not isinstance(title, str) for title in raw_target_titles
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target titles must be a list of text values",
            )
        if len(raw_target_titles) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select no more than 10 target titles",
            )
        target_titles = self._clean_target_titles(raw_target_titles)
        if not target_titles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Select at least one target title",
            )

        try:
            reviewed_profile = CVProfileExtraction.model_validate(
                payload.get("profile", checkpoint_profile)
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reviewed profile is invalid",
            ) from exc
        reviewed_profile = reviewed_profile.model_copy(
            update={"skills": self._normalize_cv_skills(reviewed_profile.skills)}
        )
        self._assert_workflow_owned()
        persisted = self._repo.approve_profile_review(
            user_id=user_id,
            cv_document_id=cv_document_id,
            extraction_run_id=extraction_run_id,
            reviewed_profile=reviewed_profile.model_dump(mode="json"),
            target_titles=target_titles,
        )
        self._assert_workflow_owned()
        if persisted is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV extraction not found",
            )
        _, extraction = persisted

        driver = self._require_neo4j_driver()
        self._assert_workflow_owned()
        try:
            with driver.session() as session:
                self._assert_workflow_owned()
                written_count = upsert_cv_skills(
                    session,
                    user_id=user_id,
                    skills=list(reviewed_profile.skills),
                    cv_document_id=cv_document_id,
                    extraction_run_id=extraction.id,
                )
                self._assert_workflow_owned()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CV skill projection is incomplete; retry approval",
            ) from exc
        if written_count != len(reviewed_profile.skills):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="CV skill projection is incomplete; retry approval",
            )

        self._assert_workflow_owned()
        return {
            **payload,
            "approved": True,
            "profile": reviewed_profile.model_dump(mode="json"),
            "target_titles": target_titles,
        }

    def _persist_checkpointed_selections(
        self,
        *,
        user_id: int,
        payload: dict[str, Any],
        checkpoint_state: dict[str, Any],
    ) -> dict[str, Any]:
        self._assert_workflow_owned()
        raw_urls = payload.get("selected_posting_urls", [])
        raw_skills = payload.get("selected_skill_names", [])
        if (
            not isinstance(raw_urls, list)
            or any(not isinstance(url, str) for url in raw_urls)
            or not isinstance(raw_skills, list)
            or any(not isinstance(skill, str) for skill in raw_skills)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selections must come from the checkpointed candidates",
            )
        posting_urls = list(
            dict.fromkeys(url.strip() for url in raw_urls if url.strip())
        )
        skill_names = self._clean_skill_names(raw_skills)
        if not posting_urls or not skill_names or len(skill_names) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selections must come from the checkpointed candidates",
            )

        candidate_jobs = [
            job
            for job in checkpoint_state.get("candidate_jobs", [])
            if isinstance(job, dict)
        ]
        candidates_by_url = {
            str(job.get("url", "")).strip(): job
            for job in candidate_jobs
            if str(job.get("url", "")).strip()
        }
        if any(url not in candidates_by_url for url in posting_urls):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selections must come from the checkpointed candidates",
            )

        available_skills = {
            str(skill.get("name", "")).strip()
            for url in posting_urls
            for skill in candidates_by_url[url].get("skills", [])
            if isinstance(skill, dict) and str(skill.get("name", "")).strip()
        }
        if any(skill not in available_skills for skill in skill_names):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selections must come from the checkpointed candidates",
            )

        job_search_run_id = checkpoint_state.get("job_search_run_id")
        job_match_run_id = checkpoint_state.get("job_match_run_id")
        if not isinstance(job_search_run_id, int) or not isinstance(
            job_match_run_id, int
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job workflow state is incomplete; restart job search",
            )

        driver = self._require_neo4j_driver()
        self._assert_workflow_owned()
        with driver.session() as session:
            self._assert_workflow_owned()
            jobs_written = select_job_postings(
                session,
                user_id=user_id,
                posting_urls=posting_urls,
                run_id=str(job_search_run_id),
            )
            self._assert_workflow_owned()
            skills_written = select_candidate_market_skills(
                session,
                user_id=user_id,
                skill_names=skill_names,
                posting_urls=posting_urls,
                job_search_run_id=str(job_search_run_id),
                match_run_id=str(job_match_run_id),
            )
            self._assert_workflow_owned()
        if jobs_written != len(posting_urls) or skills_written != len(skill_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate graph projection is incomplete; retry job search",
            )

        self._assert_workflow_owned()
        if not self._repo.record_job_selections(
            user_id=user_id,
            job_search_run_id=job_search_run_id,
            posting_urls=posting_urls,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job search run does not belong to the current user",
            )
        self._assert_workflow_owned()
        self._repo.upsert_profile_status(
            user_id=user_id,
            onboarding_status="ready",
        )
        self._assert_workflow_owned()
        return {
            **payload,
            "selected_posting_urls": posting_urls,
            "selected_skill_names": skill_names,
        }

    def _validate_resume_thread(self, user_id: int, thread_id: str) -> tuple[int, int]:
        cv_document_id, extraction_run_id = self._parse_thread_id(thread_id, user_id)
        if self._db is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thread does not belong to the current user",
            )
        document, extraction = self._repo.get_cv_lifecycle(
            user_id=user_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thread does not belong to the current user",
            )
        if (
            document.id != cv_document_id
            or extraction is None
            or extraction.id != extraction_run_id
            or document.status != CVDocumentStatus.COMPLETED.value
            or extraction.status != IndividualRunStatus.COMPLETED.value
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow attempt is stale; reload the current profile",
            )
        return cv_document_id, extraction_run_id

    @staticmethod
    def _parse_thread_id(thread_id: str, user_id: int) -> tuple[int, int]:
        match = _THREAD_ID_PATTERN.fullmatch(thread_id)
        if match is None or int(match.group("user_id")) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thread does not belong to the current user",
            )
        return (
            int(match.group("cv_document_id")),
            int(match.group("extraction_run_id")),
        )

    def _load_profile_payload(
        self,
        user_id: int,
        cv_document_id: int,
        extraction_run_id: int | None = None,
    ) -> dict[str, Any]:
        if self._db is None:
            return {}
        cv_document, extraction = self._repo.get_cv_lifecycle(
            user_id=user_id,
            cv_document_id=cv_document_id,
        )
        if cv_document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV document not found",
            )

        if extraction is None:
            return {}
        if extraction_run_id is not None and extraction.id != extraction_run_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow attempt is stale; reload the current profile",
            )

        return self._profile_payload_from_extraction(extraction)

    @staticmethod
    def _profile_payload_from_extraction(
        extraction: CVExtractionRun,
    ) -> dict[str, Any]:
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

    @staticmethod
    def _build_graph_snapshot_response(
        thread_id: str,
        snapshot: Any,
    ) -> dict[str, Any]:
        values = dict(getattr(snapshot, "values", {}) or {})
        interrupt_value = IndividualLearningService._get_snapshot_interrupt(snapshot)
        has_pending_work = bool(getattr(snapshot, "next", ()))
        return {
            "thread_id": thread_id,
            "status": (
                "interrupted"
                if interrupt_value is not None or has_pending_work
                else "completed"
            ),
            "interrupt": interrupt_value,
            "target_titles": list(values.get("target_titles", [])),
            "selected_posting_urls": list(values.get("selected_posting_urls", [])),
            "selected_skill_names": list(values.get("selected_skill_names", [])),
        }

    @staticmethod
    def _clean_skill_names(skill_names: list[str]) -> list[str]:
        cleaned_skill_names: list[str] = []
        seen: set[str] = set()
        for raw_name in skill_names:
            name = raw_name.strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned_skill_names.append(name)
        return cleaned_skill_names

    @staticmethod
    def _normalize_cv_skills(
        skills: list[CVSkillExtraction],
    ) -> list[CVSkillExtraction]:
        normalized: list[CVSkillExtraction] = []
        seen: set[str] = set()
        for skill in skills:
            name = " ".join(skill.name.split())
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            normalized.append(skill.model_copy(update={"name": name}))
        return normalized

    @staticmethod
    def _clean_target_titles(raw_titles: object) -> list[str]:
        if not isinstance(raw_titles, list):
            return []
        titles: list[str] = []
        seen: set[str] = set()
        for raw_title in raw_titles:
            if not isinstance(raw_title, str):
                continue
            title = " ".join(raw_title.split())[:120]
            if not title:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            titles.append(title)
        return titles

    @staticmethod
    def _combine_selected_skill_names(
        persisted_skill_names: list[str],
        requested_skill_names: list[str],
    ) -> list[str]:
        combined_skill_names: list[str] = []
        seen: set[str] = set()
        for skill_name in [*persisted_skill_names, *requested_skill_names]:
            key = skill_name.casefold()
            if key in seen:
                continue
            seen.add(key)
            combined_skill_names.append(skill_name)
        return combined_skill_names

    @staticmethod
    def _build_market_skill_profile(skill: dict[str, Any]) -> SkillProfile:
        concepts = [
            concept
            for concept in skill.get("concepts", [])
            if isinstance(concept, dict) and concept.get("name")
        ]
        job_evidence = [
            str(evidence)[:500]
            for evidence in skill.get("job_evidence", [])
            if evidence
        ]
        return SkillProfile(
            name=str(skill.get("name", "")),
            skill_type="market",
            description=str(skill.get("description", "") or ""),
            concepts=concepts,
            category=str(skill.get("category", "") or ""),
            job_evidence=job_evidence,
            course_level="bachelor",
        )

    def _list_cv_skill_names(self, user_id: int) -> list[str]:
        if self._db is None:
            return []
        extraction = self._repo.get_latest_cv_extraction(user_id)
        if extraction is None:
            return []

        extracted_profile = extraction.extracted_profile_json or {}
        skills = extracted_profile.get("skills")
        if not isinstance(skills, list):
            return []

        unique_names: set[str] = set()
        cv_skill_names: list[str] = []
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name", "")).strip()
            if not name:
                continue
            key = name.casefold()
            if key in unique_names:
                continue
            unique_names.add(key)
            cv_skill_names.append(name)
        return cv_skill_names

    def _require_neo4j_driver(self) -> Neo4jDriver:
        if self._neo4j_driver is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Neo4j is not configured",
            )
        return self._neo4j_driver
