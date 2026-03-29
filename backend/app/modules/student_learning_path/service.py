"""Student Learning Path — business logic layer."""

from __future__ import annotations

import asyncio
import logging
import uuid

from neo4j import Driver as Neo4jDriver
from sqlalchemy.orm import Session as SQLSession

from app.core.settings import settings
from app.modules.courses.repository import CourseRepository

from . import neo4j_repository
from .graph import learning_path_graph

logger = logging.getLogger(__name__)

# ── In-memory run tracking ────────────────────────────────────

_active_runs: dict[str, asyncio.Queue] = {}


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
        enrollment = self._course_repo.get_enrollment(student_id, course_id)
        if enrollment is None:
            raise ValueError(
                f"Student {student_id} is not enrolled in course {course_id}"
            )

    def select_skills(
        self, student_id: int, course_id: int, skill_names: list[str], source: str
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.select_skills(
                session, student_id, skill_names, source
            )

    def deselect_skills(
        self, student_id: int, course_id: int, skill_names: list[str]
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.deselect_skills(session, student_id, skill_names)

    def select_job_postings(
        self, student_id: int, course_id: int, posting_urls: list[str]
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.select_job_postings(
                session, student_id, posting_urls
            )

    def deselect_job_posting(
        self, student_id: int, course_id: int, posting_url: str
    ) -> int:
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()
        with driver.session(database=settings.neo4j_database) as session:
            return neo4j_repository.deselect_job_posting(
                session, student_id, posting_url
            )

    def get_skill_banks(self, student_id: int, course_id: int) -> dict:
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

    async def build_learning_path(
        self, student_id: int, course_id: int
    ) -> tuple[str, asyncio.Queue]:
        """Launch the LangGraph pipeline. Returns (run_id, progress_queue)."""
        self._validate_enrollment(student_id, course_id)
        driver = self._require_neo4j()

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
            _active_runs.pop(run_id, None)
