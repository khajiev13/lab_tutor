from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.document_extraction.neo4j_repository import (
    DocumentExtractionGraphRepository,
)

from .course_repository import CourseEmbeddingStateRepository
from .orchestrator import EmbeddingOrchestrator

logger = logging.getLogger(__name__)


def _embed_one_course_document_background(
    *,
    document_id: str,
    course_id: int,
    content_hash: str | None,
    document_text: str,
    mentions,
    neo4j_driver,
) -> None:
    db = SessionLocal()
    neo4j_session: Neo4jSession | None = None
    try:
        neo4j_session = neo4j_driver.session(database=settings.neo4j_database)
        EmbeddingOrchestrator(
            db=db, neo4j_session=neo4j_session
        ).embed_document_and_mentions(
            document_id=document_id,
            course_id=course_id,
            content_hash=content_hash,
            document_text=document_text,
            mentions=mentions,
        )
    finally:
        try:
            if neo4j_session is not None:
                neo4j_session.close()
        finally:
            db.close()


def run_course_embedding_background(*, course_id: int) -> None:
    """Run the course-level embeddings phase with bounded concurrency.

    Uses the same worker count as extraction (settings.extraction_workers).
    Creates isolated SQLAlchemy + Neo4j sessions per worker thread.
    """

    driver = None
    try:
        driver = create_neo4j_driver()
        if driver is None:
            return

        # Discover which extracted docs exist (single-threaded).
        with driver.session(database=settings.neo4j_database) as neo4j_session:
            docs = DocumentExtractionGraphRepository(
                neo4j_session
            ).list_course_documents_with_mentions(course_id=course_id)

        with SessionLocal() as db:
            CourseEmbeddingStateRepository(db).mark_in_progress(course_id=course_id)

        if not docs:
            with SessionLocal() as db:
                CourseEmbeddingStateRepository(db).mark_completed(course_id=course_id)
            return

        errors: list[Exception] = []
        with ThreadPoolExecutor(max_workers=settings.extraction_workers) as executor:
            futures = [
                executor.submit(
                    _embed_one_course_document_background,
                    document_id=d.document_id,
                    course_id=d.course_id,
                    content_hash=d.content_hash,
                    document_text=d.original_text or "",
                    mentions=d.mentions,
                    neo4j_driver=driver,
                )
                for d in docs
            ]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

        with SessionLocal() as db:
            repo = CourseEmbeddingStateRepository(db)
            if errors:
                repo.mark_failed(course_id=course_id, error=str(errors[0]))
            else:
                repo.mark_completed(course_id=course_id)
    except Exception as e:
        logger.exception("Course embedding background task failed")
        try:
            with SessionLocal() as db:
                CourseEmbeddingStateRepository(db).mark_failed(
                    course_id=course_id, error=str(e)
                )
        except Exception:
            logger.exception("Failed to persist course embedding failure state")
    finally:
        if driver is not None:
            driver.close()


class CourseEmbeddingOrchestrator:
    _db: Session
    _neo4j_session: Neo4jSession
    _course_state_repo: CourseEmbeddingStateRepository
    _graph_repo: DocumentExtractionGraphRepository
    _doc_orchestrator: EmbeddingOrchestrator

    def __init__(
        self,
        *,
        db: Session,
        neo4j_session: Neo4jSession,
        course_state_repo: CourseEmbeddingStateRepository | None = None,
        graph_repo: DocumentExtractionGraphRepository | None = None,
        doc_orchestrator: EmbeddingOrchestrator | None = None,
    ) -> None:
        self._db = db
        self._neo4j_session = neo4j_session
        self._course_state_repo = course_state_repo or CourseEmbeddingStateRepository(
            db
        )
        self._graph_repo = graph_repo or DocumentExtractionGraphRepository(
            neo4j_session
        )
        self._doc_orchestrator = doc_orchestrator or EmbeddingOrchestrator(
            db=db, neo4j_session=neo4j_session
        )

    def embed_course(self, *, course_id: int) -> bool:
        """Embeds all extracted documents for a course.

        Returns True if any embeddings were generated/written, False if everything was skipped.
        """

        self._course_state_repo.mark_in_progress(course_id=course_id)

        try:
            docs = self._graph_repo.list_course_documents_with_mentions(
                course_id=course_id
            )
            if not docs:
                # No extracted docs; treat as completed (nothing to do).
                self._course_state_repo.mark_completed(course_id=course_id)
                return False

            any_ran = False
            for d in docs:
                doc_text = d.original_text or ""
                # If a doc has no mentions, we still embed the doc.
                did = self._doc_orchestrator.embed_document_and_mentions(
                    document_id=d.document_id,
                    course_id=d.course_id,
                    content_hash=d.content_hash,
                    document_text=doc_text,
                    mentions=d.mentions,
                )
                any_ran = any_ran or did

            self._course_state_repo.mark_completed(course_id=course_id)
            return any_ran

        except Exception as e:
            logger.exception("Course embedding failed for course_id=%s", course_id)
            try:
                self._course_state_repo.mark_failed(course_id=course_id, error=str(e))
            except Exception:
                logger.exception("Failed to persist course embedding failure state")
            raise
