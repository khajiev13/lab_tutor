"""Student Learning Path — business logic layer."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import HTTPException, status
from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session as SQLSession

from app.core.settings import settings
from app.modules.courses.neo4j_repository import CourseGraphRepository
from app.modules.courses.repository import CourseRepository

from . import neo4j_repository
from .graph import learning_path_graph
from . import reader_extractor
from .schemas import (
    BuildSelectedSkillRequest,
    ChapterQuizResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    ReadingContentResponse,
    ResourceOpenRequest,
    StudentSkillBankResponse,
)

logger = logging.getLogger(__name__)

# ── In-memory run tracking ────────────────────────────────────

_active_runs: dict[str, asyncio.Queue] = {}
READING_CACHE_READY_TTL = timedelta(days=30)
READING_CACHE_FAILED_TTL = timedelta(hours=24)
DEFAULT_READING_FALLBACK_SUMMARY = (
    "We could not generate an in-app preview for this resource. Open the original "
    "source to keep studying."
)


def get_queue(run_id: str) -> asyncio.Queue | None:
    return _active_runs.get(run_id)


class StudentLearningPathService:
    """Orchestrates skill selection and learning path building."""

    def __init__(
        self,
        db: SQLSession,
        neo4j_driver: Neo4jDriver | None,
    ) -> None:
        self._db = db
        self._neo4j = neo4j_driver
        self._course_repo = CourseRepository(db)

    def _require_neo4j(self) -> Neo4jDriver:
        if self._neo4j is None:
            raise RuntimeError("Neo4j is not configured")
        return self._neo4j

    def _validate_enrollment(self, student_id: int, course_id: int) -> None:
        """Ensure student is enrolled in the course."""
        enrollment = self._course_repo.get_enrollment(course_id, student_id)
        if enrollment is None:
            logger.warning(
                "Student learning path enrollment denied: student_id=%s course_id=%s",
                student_id,
                course_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Student is not enrolled in this course",
            )

    def _group_selected_skills_by_source(
        self,
        selected_skills: list[BuildSelectedSkillRequest],
    ) -> dict[str, list[str]]:
        selected_by_name: dict[str, str] = {}
        for skill in selected_skills:
            selected_by_name[skill.name] = skill.source

        grouped: dict[str, list[str]] = defaultdict(list)
        for skill_name, source in selected_by_name.items():
            grouped[source].append(skill_name)
        return grouped

    @staticmethod
    def _build_fallback_summary(resource: dict) -> str:
        snippets: list[str] = []

        for field_name in ("snippet", "search_content"):
            value = " ".join(str(resource.get(field_name, "") or "").split())
            if not value:
                continue

            normalized = value.casefold()
            if any(
                normalized == existing.casefold()
                or normalized in existing.casefold()
                for existing in snippets
            ):
                continue

            snippets = [
                existing
                for existing in snippets
                if existing.casefold() not in normalized
            ]
            snippets.append(value)

        return "\n\n".join(snippets) if snippets else DEFAULT_READING_FALLBACK_SUMMARY

    @staticmethod
    def _parse_reader_extracted_at(value: str | None) -> datetime | None:
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _resolve_resource_domain(resource: dict) -> str:
        domain = str(resource.get("domain", "") or "").strip()
        if domain:
            return domain
        return urlparse(str(resource.get("url", "") or "")).netloc

    @classmethod
    def _build_reading_content_response(
        cls,
        resource: dict,
        *,
        status_name: str,
        content_markdown: str,
        fallback_summary: str,
        error_message: str | None,
    ) -> ReadingContentResponse:
        return ReadingContentResponse(
            id=str(resource.get("id", "")),
            title=str(resource.get("title", "") or "Untitled reading"),
            url=str(resource.get("url", "")),
            domain=cls._resolve_resource_domain(resource),
            status=status_name,
            content_markdown=content_markdown,
            fallback_summary=fallback_summary,
            error_message=error_message,
        )

    @classmethod
    def _get_cached_reading_content_response(
        cls,
        resource: dict,
        *,
        fallback_summary: str,
    ) -> ReadingContentResponse | None:
        extracted_at = cls._parse_reader_extracted_at(
            resource.get("reader_extracted_at")
        )
        if extracted_at is None:
            return None

        now = datetime.now(UTC)
        reader_status = str(resource.get("reader_status", "") or "")
        cached_markdown = str(resource.get("reader_content_markdown", "") or "")
        cached_error = str(resource.get("reader_error", "") or "")

        if (
            reader_status == "ready"
            and cached_markdown
            and extracted_at >= now - READING_CACHE_READY_TTL
        ):
            return cls._build_reading_content_response(
                resource,
                status_name="ready",
                content_markdown=cached_markdown,
                fallback_summary=fallback_summary,
                error_message=None,
            )

        if (
            reader_status == "failed"
            and extracted_at >= now - READING_CACHE_FAILED_TTL
        ):
            return cls._build_reading_content_response(
                resource,
                status_name="failed",
                content_markdown="",
                fallback_summary=fallback_summary,
                error_message=(
                    cached_error
                    or "We could not extract readable article content from this source."
                ),
            )

        return None

    def select_skills(
        self, student_id: int, course_id: int, skill_names: list[str], source: str
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.select_skills(
                session, student_id, course_id, skill_names, source
            )

    def deselect_skills(
        self, student_id: int, course_id: int, skill_names: list[str]
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.deselect_skills(
                session, student_id, course_id, skill_names
            )

    def select_job_postings(
        self, student_id: int, course_id: int, posting_urls: list[str]
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.select_job_postings(
                session, student_id, course_id, posting_urls
            )

    def deselect_job_posting(
        self, student_id: int, course_id: int, posting_url: str
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.deselect_job_posting(
                session, student_id, course_id, posting_url
            )

    def record_resource_open(
        self,
        student_id: int,
        course_id: int,
        payload: ResourceOpenRequest,
    ) -> None:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            neo4j_repository.record_resource_open(
                session,
                student_id=student_id,
                resource_type=payload.resource_type,
                url=str(payload.url),
            )

    def get_skill_banks(
        self, student_id: int, course_id: int
    ) -> StudentSkillBankResponse:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.get_student_skill_banks(
                session, student_id, course_id
            )

    def get_learning_path(self, student_id: int, course_id: int) -> dict:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.get_learning_path(session, student_id, course_id)

    async def get_reading_content(
        self,
        student_id: int,
        course_id: int,
        resource_id: str,
    ) -> ReadingContentResponse:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            resource = neo4j_repository.get_accessible_reading_resource(
                session,
                student_id=student_id,
                course_id=course_id,
                resource_id=resource_id,
            )
            if resource is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Reading resource not found",
                )

            fallback_summary = self._build_fallback_summary(resource)
            cached_response = self._get_cached_reading_content_response(
                resource,
                fallback_summary=fallback_summary,
            )
            if cached_response is not None:
                return cached_response

            try:
                extraction = await reader_extractor.extract_reading_markdown(
                    str(resource.get("url", ""))
                )
            except Exception:
                logger.exception(
                    "Reading extraction failed unexpectedly for resource_id=%s",
                    resource_id,
                )
                extraction = reader_extractor.ReaderExtractionFailure(
                    error_code="unexpected_error",
                    error_message="We could not extract this source right now.",
                )

            extracted_at = datetime.now(UTC).isoformat()
            if extraction.status == "ready":
                neo4j_repository.persist_reading_reader_cache(
                    session,
                    resource_id=resource_id,
                    reader_status="ready",
                    reader_content_markdown=extraction.content_markdown,
                    reader_error="",
                    reader_extracted_at=extracted_at,
                )
                return self._build_reading_content_response(
                    resource,
                    status_name="ready",
                    content_markdown=extraction.content_markdown,
                    fallback_summary=fallback_summary,
                    error_message=None,
                )

            neo4j_repository.persist_reading_reader_cache(
                session,
                resource_id=resource_id,
                reader_status="failed",
                reader_content_markdown="",
                reader_error=extraction.error_message,
                reader_extracted_at=extracted_at,
            )
            return self._build_reading_content_response(
                resource,
                status_name="failed",
                content_markdown="",
                fallback_summary=fallback_summary,
                error_message=extraction.error_message,
            )

    def _get_chapter_quiz_status(
        self,
        session,
        student_id: int,
        course_id: int,
        chapter_index: int,
    ) -> tuple[str | None, dict[str, int]]:
        progress_rows = neo4j_repository.get_chapter_quiz_progress(
            session,
            student_id,
            course_id,
        )
        status_by_chapter = neo4j_repository.resolve_quiz_statuses(progress_rows)
        progress_map = {row["chapter_index"]: row for row in progress_rows}
        progress = progress_map.get(chapter_index)
        if progress is None:
            return None, {"easy_question_count": 0, "answered_count": 0, "correct_count": 0}

        return status_by_chapter.get(chapter_index), progress

    @staticmethod
    def _find_next_eligible_chapter_index(
        progress_rows: list[dict],
        chapter_index: int,
    ) -> int | None:
        for row in sorted(progress_rows, key=lambda item: item["chapter_index"]):
            if row["chapter_index"] <= chapter_index:
                continue
            if int(row.get("easy_question_count", 0) or 0) > 0:
                return row["chapter_index"]
        return None

    def get_chapter_quiz(
        self,
        student_id: int,
        course_id: int,
        chapter_index: int,
    ) -> ChapterQuizResponse:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            quiz_status, _progress = self._get_chapter_quiz_status(
                session,
                student_id,
                course_id,
                chapter_index,
            )
            if quiz_status is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chapter quiz not found",
                )
            if quiz_status == "locked":
                raise ValueError("Chapter quiz is locked")

            chapter_quiz = neo4j_repository.get_chapter_easy_questions(
                session,
                student_id,
                course_id,
                chapter_index,
            )
            if not chapter_quiz["questions"]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chapter quiz not found",
                )

            return ChapterQuizResponse(
                course_id=course_id,
                chapter_index=chapter_index,
                chapter_title=chapter_quiz["chapter_title"],
                questions=chapter_quiz["questions"],
                previous_answers=chapter_quiz["previous_answers"],
            )

    def submit_chapter_quiz(
        self,
        student_id: int,
        course_id: int,
        chapter_index: int,
        payload: QuizSubmitRequest,
    ) -> QuizSubmitResponse:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            progress_before = neo4j_repository.get_chapter_quiz_progress(
                session,
                student_id,
                course_id,
            )
            status_before = neo4j_repository.resolve_quiz_statuses(progress_before)
            progress_before_map = {
                row["chapter_index"]: row for row in progress_before
            }
            progress_before_row = progress_before_map.get(chapter_index)
            if progress_before_row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chapter quiz not found",
                )
            quiz_status = status_before.get(chapter_index)
            if quiz_status is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chapter quiz not found",
                )
            if quiz_status == "locked":
                raise ValueError("Chapter quiz is locked")

            chapter_quiz = neo4j_repository.get_chapter_easy_questions(
                session,
                student_id,
                course_id,
                chapter_index,
            )
            expected_question_ids = {
                question["id"] for question in chapter_quiz["questions"]
            }
            submitted_question_ids = {answer.question_id for answer in payload.answers}
            if not expected_question_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Chapter quiz not found",
                )
            if (
                len(payload.answers) != len(expected_question_ids)
                or submitted_question_ids != expected_question_ids
            ):
                raise ValueError(
                    "Quiz submission must include every easy question in the chapter"
                )

            results = neo4j_repository.submit_chapter_answers(
                session,
                student_id,
                course_id,
                chapter_index,
                [
                    {
                        "question_id": answer.question_id,
                        "selected_option": answer.selected_option,
                    }
                    for answer in payload.answers
                ],
            )
            progress_after = neo4j_repository.get_chapter_quiz_progress(
                session,
                student_id,
                course_id,
            )
            status_after = neo4j_repository.resolve_quiz_statuses(progress_after)
            progress_after_map = {row["chapter_index"]: row for row in progress_after}
            chapter_progress_after = progress_after_map.get(
                chapter_index,
                {"easy_question_count": 0, "correct_count": 0},
            )
            next_eligible_chapter_index = self._find_next_eligible_chapter_index(
                progress_after,
                chapter_index,
            )
            skills_known = [
                result["skill_name"] for result in results if result["answered_right"]
            ]
            return QuizSubmitResponse(
                chapter_index=chapter_index,
                results=results,
                skills_known=skills_known,
                chapter_status_after_submit=status_after.get(
                    chapter_index, "learning"
                ),
                correct_count_after_submit=int(
                    chapter_progress_after.get("correct_count", 0) or 0
                ),
                easy_question_count=int(
                    chapter_progress_after.get("easy_question_count", 0) or 0
                ),
                next_chapter_unlocked=(
                    next_eligible_chapter_index is not None
                    and status_before.get(next_eligible_chapter_index) == "locked"
                    and status_after.get(next_eligible_chapter_index) != "locked"
                ),
            )

    async def build_learning_path(
        self,
        student_id: int,
        course_id: int,
        selected_skills: list[BuildSelectedSkillRequest] | None = None,
    ) -> tuple[str, asyncio.Queue]:
        """Launch the LangGraph pipeline. Returns (run_id, progress_queue)."""
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()

        with driver.session(database=settings.neo4j_database) as session:
            persisted_selected_skills = neo4j_repository.get_selected_skills(
                session,
                student_id,
                course_id,
            )
            if not persisted_selected_skills:
                grouped_selected_skills = self._group_selected_skills_by_source(
                    selected_skills or []
                )
                if not grouped_selected_skills:
                    raise ValueError("Select at least one skill before building")

                selection_range = CourseGraphRepository(
                    session
                ).get_skill_selection_range(course_id=course_id)
                selected_skill_count = sum(
                    len(skill_names) for skill_names in grouped_selected_skills.values()
                )
                min_skills = int(selection_range["min_skills"])
                max_skills = int(selection_range["max_skills"])
                if (
                    selected_skill_count < min_skills
                    or selected_skill_count > max_skills
                ):
                    raise ValueError(
                        f"Select between {min_skills} and {max_skills} skills before building"
                    )

                for source in ("book", "market"):
                    skill_names = grouped_selected_skills.get(source, [])
                    if skill_names:
                        neo4j_repository.select_skills(
                            session,
                            student_id,
                            course_id,
                            skill_names,
                            source,
                        )

                persisted_selected_skills = neo4j_repository.get_selected_skills(
                    session,
                    student_id,
                    course_id,
                )
                if not persisted_selected_skills:
                    raise ValueError("Select at least one valid skill before building")

        run_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _active_runs[run_id] = queue

        # Run in background
        asyncio.create_task(
            self._run_pipeline(run_id, student_id, course_id, driver, queue)
        )

        return run_id, queue

    async def _run_pipeline(
        self,
        run_id: str,
        student_id: int,
        course_id: int,
        driver: Neo4jDriver,
        queue: asyncio.Queue,
    ) -> None:
        """Execute the LangGraph pipeline and forward stream events to the queue."""
        try:
            loop = asyncio.get_event_loop()

            # Run the sync graph in a thread
            def _invoke():
                results = []
                for chunk in learning_path_graph.stream(
                    {
                        "student_id": student_id,
                        "course_id": course_id,
                        "neo4j_driver": driver,
                        "skills_to_process": [],
                        "results": [],
                    },
                    stream_mode="custom",
                ):
                    results.append(chunk)
                    # Forward to async queue (thread-safe)
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                return results

            await asyncio.to_thread(_invoke)

        except Exception:
            logger.exception("Learning path build failed for run %s", run_id)
            await queue.put({"type": "error", "detail": "Build failed"})
        finally:
            await queue.put(None)  # Signal stream end
            # Delay cleanup so the client has time to connect and drain events.
            # When all skills are skipped the pipeline finishes in milliseconds,
            # before the frontend can open the SSE stream.
            await asyncio.sleep(30)
            _active_runs.pop(run_id, None)
