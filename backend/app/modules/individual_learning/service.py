from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable
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
from .models import IndividualRunStatus
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
from .repository import IndividualLearningRepository
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
    r"^individual-(?P<user_id>\d+)-cv-(?P<cv_document_id>\d+)$"
)


def _safe_filename(filename: str) -> str:
    base = filename.strip().split("/")[-1].split("\\")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "cv"


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

    def get_profile(self, user_id: int) -> IndividualProfileRead:
        profile = self._repo.get_profile(user_id)
        if profile is None:
            return IndividualProfileRead(user_id=user_id, onboarding_status="needs_cv")

        document = self._repo.get_latest_cv_document(user_id)
        extraction = self._repo.get_latest_cv_extraction(user_id)
        thread_id = (
            self._build_thread_id(user_id, document.id)
            if document is not None and extraction is not None
            else None
        )
        pending_interrupt: dict[str, Any] | None = None
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
        if pending_interrupt is not None:
            if pending_interrupt.get("kind") == "review_profile_and_roles":
                next_step = "review_profile"
            elif pending_interrupt.get("kind") == "choose_jobs_and_skills":
                next_step = "select_jobs_and_skills"

        return IndividualProfileRead(
            user_id=user_id,
            onboarding_status=profile.onboarding_status,
            target_titles=list(profile.target_titles_json or []),
            preferred_country=profile.preferred_country,
            preferred_location=profile.preferred_location,
            reviewed_at=profile.reviewed_at,
            cv_document_id=document.id if document is not None else None,
            extraction_run_id=extraction.id if extraction is not None else None,
            active_thread_id=thread_id,
            next_step=next_step,
            extracted_profile=(
                dict(extraction.extracted_profile_json or {})
                if extraction is not None
                else None
            ),
            pending_interrupt=pending_interrupt,
        )

    @staticmethod
    def _get_snapshot_interrupt(snapshot: Any) -> dict[str, Any] | None:
        for task in getattr(snapshot, "tasks", ()):
            for graph_interrupt in getattr(task, "interrupts", ()):
                value = getattr(graph_interrupt, "value", None)
                if isinstance(value, dict):
                    return dict(value)
        return None

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
            return get_individual_learning_path(session, user_id=user_id)

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
        if not is_supported_cv_file(
            filename=filename,
            content_type=file.content_type,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF and DOCX CV files are supported",
            )

        content_hash = self._storage.sha256_hex(content)
        safe_filename = _safe_filename(filename)
        blob_path = f"users/{user_id}/cv/{content_hash}/{safe_filename}"

        try:
            await self._storage.upload_bytes(content, blob_path)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload CV file {filename}: {exc}",
            ) from exc

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
                filename=filename,
                content_type=file.content_type,
                data=content,
            )
        except ValueError as exc:
            error_message = str(exc)[:1000] or type(exc).__name__
            self._repo.fail_cv_extraction(
                extraction_run,
                document=cv_document,
                error_message=error_message,
            )
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="error",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            ) from exc
        except Exception as exc:
            error_message = str(exc)[:1000] or type(exc).__name__
            self._repo.fail_cv_extraction(
                extraction_run,
                document=cv_document,
                error_message=error_message,
            )
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="error",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse CV file",
            ) from exc

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
            error_message = str(exc)[:1000] or type(exc).__name__
            self._repo.fail_cv_extraction(
                extraction_run,
                document=cv_document,
                error_message=error_message,
            )
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="error",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to extract a structured CV profile",
            ) from exc

        profile_payload = extracted_profile.model_dump(mode="json")
        self._repo.complete_cv_extraction(
            extraction_run,
            extracted_profile=profile_payload,
            target_title_suggestions=list(extracted_profile.target_title_suggestions),
            confidence_summary=dict(extracted_profile.confidence_summary),
        )
        self._repo.complete_cv_document(cv_document)
        self._repo.upsert_profile_status(
            user_id=user_id,
            onboarding_status="needs_profile_review",
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
                "thread_id": thread_id,
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
        return IndividualGraphStartResponse(
            **self._build_graph_response(thread_id, result)
        )

    def resume_individual_graph(
        self, user_id: int, thread_id: str, payload: dict[str, Any]
    ) -> IndividualGraphResumeResponse:
        cv_document_id = self._validate_resume_thread(user_id, thread_id)
        graph = self._get_graph()
        config = self._graph_config(thread_id)
        resume_payload = dict(payload)
        snapshot = graph.get_state(config)
        if "review_profile_and_roles" in snapshot.next:
            resume_payload = self._approve_profile_review(
                user_id=user_id,
                cv_document_id=cv_document_id,
                payload=resume_payload,
                checkpoint_profile=dict(snapshot.values.get("profile", {})),
            )
        elif "choose_jobs_and_skills" in snapshot.next:
            resume_payload = self._persist_checkpointed_selections(
                user_id=user_id,
                payload=resume_payload,
                checkpoint_state=dict(snapshot.values),
            )
        result = graph.invoke(Command(resume=resume_payload), config)
        response_data = self._build_graph_response(thread_id, result)
        return IndividualGraphResumeResponse(**response_data)

    @staticmethod
    def _build_thread_id(user_id: int, cv_document_id: int) -> str:
        return f"individual-{user_id}-cv-{cv_document_id}"

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
        )

    def _run_job_search(self, state: dict[str, Any]) -> dict[str, Any]:
        user_id = int(state["user_id"])
        target_titles = self._clean_target_titles(state.get("target_titles", []))
        profile = self._repo.get_profile(user_id)
        country = (profile.preferred_country if profile is not None else None) or ""
        location = (profile.preferred_location if profile is not None else None) or ""
        search_run = self._repo.get_or_create_job_search_run(
            user_id=user_id,
            workflow_thread_id=str(state["thread_id"]),
            target_titles=target_titles,
            country=country,
            location=location,
        )

        errors: list[str] = []
        jobs_by_url: dict[str, dict[str, Any]] = {}
        for title in target_titles:
            try:
                found_jobs = self._job_searcher([title], country, location)
            except Exception as exc:
                errors.append(f"{title}: {str(exc)[:200] or type(exc).__name__}")
                continue
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
            try:
                extracted = self._market_skill_extractor([raw_job])
                skills = self._normalize_market_skills(extracted.get(url, []))
            except Exception as exc:
                errors.append(
                    f"{job['title'] or url}: {str(exc)[:200] or type(exc).__name__}"
                )
                skills = []
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
            }
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

        if not candidate_jobs and not errors:
            errors.append("No usable job postings were found")
        run_status = (
            IndividualRunStatus.FAILED.value
            if not candidate_jobs
            else IndividualRunStatus.PARTIAL.value
            if errors
            else IndividualRunStatus.COMPLETED.value
        )
        error_message = "; ".join(errors) or None
        self._repo.complete_job_search_run(
            search_run,
            jobs=candidate_jobs,
            status=run_status,
            error_message=error_message,
        )
        match_run = self._repo.get_or_create_job_match_run(
            user_id=user_id,
            job_search_run_id=search_run.id,
        )
        self._repo.complete_job_match_run(
            match_run,
            scores=scores,
            skill_gaps=skill_gaps,
            status=run_status,
        )

        if run_status == IndividualRunStatus.FAILED.value:
            self._repo.upsert_profile_status(
                user_id=user_id,
                onboarding_status="needs_jobs",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No usable job postings were found",
            )

        driver = self._require_neo4j_driver()
        try:
            with driver.session() as session:
                upsert_job_postings_and_market_skills(
                    session,
                    jobs=candidate_jobs,
                    skills_by_job_url=skills_by_job_url,
                )
        except Exception as exc:
            projection_error = (
                f"Graph projection: {str(exc)[:200] or type(exc).__name__}"
            )
            combined_error = "; ".join(filter(None, [error_message, projection_error]))
            self._repo.complete_job_search_run(
                search_run,
                jobs=candidate_jobs,
                status=IndividualRunStatus.PARTIAL.value,
                error_message=combined_error,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Job results could not be projected to the knowledge graph",
            ) from exc

        self._repo.upsert_profile_status(
            user_id=user_id,
            onboarding_status="needs_skill_selection",
        )
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
        payload: dict[str, Any],
        checkpoint_profile: dict[str, Any],
    ) -> dict[str, Any]:
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
        persisted = self._repo.approve_profile_review(
            user_id=user_id,
            cv_document_id=cv_document_id,
            reviewed_profile=reviewed_profile.model_dump(mode="json"),
            target_titles=target_titles,
        )
        if persisted is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV extraction not found",
            )
        _, extraction = persisted

        driver = self._require_neo4j_driver()
        with driver.session() as session:
            upsert_cv_skills(
                session,
                user_id=user_id,
                skills=[
                    CVSkillExtraction.model_validate(skill)
                    for skill in reviewed_profile.skills
                ],
                cv_document_id=cv_document_id,
                extraction_run_id=extraction.id,
            )

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
        with driver.session() as session:
            jobs_written = select_job_postings(
                session,
                user_id=user_id,
                posting_urls=posting_urls,
                run_id=str(job_search_run_id),
            )
            skills_written = select_candidate_market_skills(
                session,
                user_id=user_id,
                skill_names=skill_names,
                posting_urls=posting_urls,
                job_search_run_id=str(job_search_run_id),
                match_run_id=str(job_match_run_id),
            )
        if jobs_written != len(posting_urls) or skills_written != len(skill_names):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate graph projection is incomplete; retry job search",
            )

        if not self._repo.record_job_selections(
            user_id=user_id,
            job_search_run_id=job_search_run_id,
            posting_urls=posting_urls,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Job search run does not belong to the current user",
            )
        self._repo.upsert_profile_status(
            user_id=user_id,
            onboarding_status="ready",
        )
        return {
            **payload,
            "selected_posting_urls": posting_urls,
            "selected_skill_names": skill_names,
        }

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

    def _load_profile_payload(
        self, user_id: int, cv_document_id: int
    ) -> dict[str, Any]:
        if self._db is None:
            return {}
        cv_document = self._repo.get_owned_cv_document(
            user_id=user_id,
            cv_document_id=cv_document_id,
        )
        if cv_document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CV document not found",
            )

        extraction = self._repo.get_latest_cv_extraction(
            user_id,
            cv_document_id=cv_document_id,
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
