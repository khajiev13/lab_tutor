from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.courses.file_processing import (
    handle_docx_bytes,
    handle_txt_bytes,
    infer_file_kind,
)
from app.modules.courses.models import ExtractionStatus, FileProcessingStatus
from app.modules.courses.neo4j_repository import CourseGraphRepository
from app.modules.courses.repository import CourseRepository
from app.providers.storage import blob_service

from .llm_extractor import DocumentLLMExtractor
from .neo4j_repository import DocumentExtractionGraphRepository, MentionInput
from .schemas import ConceptExtraction

logger = logging.getLogger(__name__)


def _canonicalize_concept_name(raw_name: str | None) -> tuple[str, str]:
    """Return (canonical_lowercase, original_stripped)."""
    original = (raw_name or "").strip()
    return (original.casefold(), original)


def _build_mentions(
    *, concepts: Sequence[ConceptExtraction], source_document: str
) -> list[MentionInput]:
    """Build Neo4j mention inputs from extracted concepts.

    - `name` is canonicalized to lowercase for CONCEPT node identity
    - `original_name` preserves the extracted casing for provenance
    """
    mentions: list[MentionInput] = []
    for c in concepts:
        canonical, original = _canonicalize_concept_name(c.name)
        if not canonical:
            continue
        mentions.append(
            MentionInput(
                name=canonical,
                original_name=original,
                definition=c.definition,
                text_evidence=c.text_evidence,
                source_document=source_document,
            )
        )
    return mentions


class DocumentExtractionService:
    _db: Session
    _course_repo: CourseRepository
    _neo4j_session: Neo4jSession | None
    _graph_repo: DocumentExtractionGraphRepository | None
    _course_graph_repo: CourseGraphRepository | None
    _extractor: DocumentLLMExtractor

    def __init__(
        self, *, db: Session, neo4j_session: Neo4jSession | None = None
    ) -> None:
        self._db = db
        self._course_repo = CourseRepository(db)
        self._neo4j_session = neo4j_session
        self._graph_repo = (
            DocumentExtractionGraphRepository(neo4j_session)
            if neo4j_session is not None
            else None
        )
        self._course_graph_repo = (
            CourseGraphRepository(neo4j_session) if neo4j_session is not None else None
        )
        self._extractor = DocumentLLMExtractor(use_examples=True)

    def _set_course_status(self, course_id: int, status: ExtractionStatus) -> None:
        course = self._course_repo.get_by_id(course_id)
        if not course:
            return
        course.extraction_status = status
        self._course_repo.update(course, commit=False)

        if self._course_graph_repo is not None:
            self._course_graph_repo.upsert_course(
                course_id=course.id,
                title=course.title,
                description=course.description,
                created_at=course.created_at,
                extraction_status=course.extraction_status.value,
            )

    def run_course_extraction(self, *, course_id: int, teacher_id: int) -> None:
        """Process all course files and insert extraction results into Neo4j."""

        course = self._course_repo.get_by_id(course_id)
        if not course:
            logger.warning("Course %s not found for extraction", course_id)
            return

        files = list(self._course_repo.list_course_files(course_id))

        if not files:
            logger.info(
                "No files found for course %s; marking extraction failed", course_id
            )
            self._set_course_status(course_id, ExtractionStatus.FAILED)
            self._db.commit()
            return

        files_to_process = [
            f
            for f in files
            if f.status in {FileProcessingStatus.PENDING, FileProcessingStatus.FAILED}
        ]

        for f in files_to_process:
            try:
                self._course_repo.update_course_file_status(
                    f.id,
                    FileProcessingStatus.PROCESSING,
                    processed_at=None,
                    last_error=None,
                )

                file_bytes = blob_service.download_file(f.blob_path)
                dispatch = infer_file_kind(filename=f.filename, content_type=None)

                if dispatch.kind not in {"txt", "docx"}:
                    raise ValueError(
                        f"Unsupported file type for extraction (txt/docx only right now): {f.filename}"
                    )

                text = (
                    handle_txt_bytes(file_bytes)
                    if dispatch.kind == "txt"
                    else handle_docx_bytes(file_bytes)
                )
                result = self._extractor.extract(text=text, source_filename=f.filename)
                if not result.success:
                    raise ValueError(result.error_message or "Extraction failed")

                # Graph insertion (optional if Neo4j disabled).
                if self._graph_repo is not None:
                    content_hash = hashlib.sha256(file_bytes).hexdigest()
                    # Stable identity: prevents Neo4j duplicates when the SQL CourseFile row
                    # is deleted/recreated (new id) or when filenames differ.
                    document_id = f"doc_{course_id}_{content_hash}"
                    extracted_at = datetime.now(UTC)

                    self._graph_repo.upsert_course_document(
                        course_id=course_id,
                        teacher_id=teacher_id,
                        document_id=document_id,
                        source_filename=f.filename,
                        topic=result.extraction.topic,
                        summary=result.extraction.summary,
                        keywords=result.extraction.keywords,
                        original_text=text,
                        content_hash=content_hash,
                        extracted_at=extracted_at,
                    )

                    mentions = _build_mentions(
                        concepts=result.extraction.concepts, source_document=f.filename
                    )
                    if mentions:
                        self._graph_repo.upsert_mentions(
                            document_id=document_id,
                            mentions=mentions,
                            updated_at=extracted_at,
                        )

                self._course_repo.update_course_file_status(
                    f.id,
                    FileProcessingStatus.PROCESSED,
                    processed_at=datetime.now(UTC),
                    last_error=None,
                )

            except Exception as e:
                logger.exception("Failed to process course file %s", f.id)
                self._course_repo.update_course_file_status(
                    f.id,
                    FileProcessingStatus.FAILED,
                    processed_at=datetime.now(UTC),
                    last_error=str(e),
                )

        # Recompute final course status from per-file outcomes.
        final_files = list(self._course_repo.list_course_files(course_id))
        all_processed = all(
            f.status == FileProcessingStatus.PROCESSED for f in final_files
        )
        self._set_course_status(
            course_id,
            ExtractionStatus.FINISHED if all_processed else ExtractionStatus.FAILED,
        )
        self._db.commit()

        # After extraction finishes for all documents, run embeddings as a separate phase.
        # Best-effort: never changes extraction outcome.
        if (
            all_processed
            and self._neo4j_session is not None
            and self._graph_repo is not None
        ):
            try:
                from app.modules.embeddings.course_orchestrator import (
                    run_course_embedding_background,
                )

                run_course_embedding_background(course_id=course_id)
            except Exception:
                logger.exception("Course embedding phase failed (continuing)")


def _process_course_file_background(
    *,
    course_id: int,
    teacher_id: int,
    course_file_id: int,
    filename: str,
    blob_path: str,
    neo4j_driver,
) -> None:
    """Process a single CourseFile in isolation (own SQLAlchemy + Neo4j sessions).

    This is used by the BackgroundTasks entrypoint to safely run multiple file
    extractions concurrently without sharing sessions across threads.
    """

    db = SessionLocal()
    neo4j_session: Neo4jSession | None = None
    try:
        repo = CourseRepository(db)

        # Mark processing early so the UI reflects progress.
        repo.update_course_file_status(
            course_file_id,
            FileProcessingStatus.PROCESSING,
            processed_at=None,
            last_error=None,
        )

        file_bytes = blob_service.download_file(blob_path)
        dispatch = infer_file_kind(filename=filename, content_type=None)

        if dispatch.kind not in {"txt", "docx"}:
            raise ValueError(
                "Unsupported file type for extraction (txt/docx only right now): "
                f"{filename}"
            )

        text = (
            handle_txt_bytes(file_bytes)
            if dispatch.kind == "txt"
            else handle_docx_bytes(file_bytes)
        )

        extractor = DocumentLLMExtractor(use_examples=True)
        result = extractor.extract(text=text, source_filename=filename)
        if not result.success:
            raise ValueError(result.error_message or "Extraction failed")

        # Graph insertion (optional if Neo4j disabled).
        if neo4j_driver is not None:
            neo4j_session = neo4j_driver.session(database=settings.neo4j_database)
            graph_repo = DocumentExtractionGraphRepository(neo4j_session)

            content_hash = hashlib.sha256(file_bytes).hexdigest()
            # Stable identity: prevents Neo4j duplicates when the SQL CourseFile row
            # is deleted/recreated (new id) or when filenames differ.
            document_id = f"doc_{course_id}_{content_hash}"
            extracted_at = datetime.now(UTC)

            graph_repo.upsert_course_document(
                course_id=course_id,
                teacher_id=teacher_id,
                document_id=document_id,
                source_filename=filename,
                topic=result.extraction.topic,
                summary=result.extraction.summary,
                keywords=result.extraction.keywords,
                original_text=text,
                content_hash=content_hash,
                extracted_at=extracted_at,
            )

            mentions = _build_mentions(
                concepts=result.extraction.concepts, source_document=filename
            )
            if mentions:
                graph_repo.upsert_mentions(
                    document_id=document_id,
                    mentions=mentions,
                    updated_at=extracted_at,
                )

        repo.update_course_file_status(
            course_file_id,
            FileProcessingStatus.PROCESSED,
            processed_at=datetime.now(UTC),
            last_error=None,
        )

    except Exception as e:
        logger.exception("Failed to process course file %s", course_file_id)
        try:
            CourseRepository(db).update_course_file_status(
                course_file_id,
                FileProcessingStatus.FAILED,
                processed_at=datetime.now(UTC),
                last_error=str(e),
            )
        except Exception:
            logger.exception("Failed to mark course file %s failed", course_file_id)
    finally:
        try:
            if neo4j_session is not None:
                neo4j_session.close()
        finally:
            db.close()


def _finalize_course_extraction_status_background(
    *, course_id: int, neo4j_driver
) -> None:
    """Recompute and persist Course.extraction_status after file processing."""

    db = SessionLocal()
    neo4j_session: Neo4jSession | None = None
    try:
        repo = CourseRepository(db)
        course = repo.get_by_id(course_id)
        if not course:
            return

        final_files = list(repo.list_course_files(course_id))
        all_processed = bool(final_files) and all(
            f.status == FileProcessingStatus.PROCESSED for f in final_files
        )
        course.extraction_status = (
            ExtractionStatus.FINISHED if all_processed else ExtractionStatus.FAILED
        )
        repo.update(course, commit=False)

        if neo4j_driver is not None:
            neo4j_session = neo4j_driver.session(database=settings.neo4j_database)
            CourseGraphRepository(neo4j_session).upsert_course(
                course_id=course.id,
                title=course.title,
                description=course.description,
                created_at=course.created_at,
                extraction_status=course.extraction_status.value,
            )

        db.commit()

        # After extraction finishes for all documents, run embeddings as a separate phase.
        # Best-effort: never changes extraction outcome.
        if (
            course.extraction_status == ExtractionStatus.FINISHED
            and neo4j_session is not None
        ):
            try:
                from app.modules.embeddings.course_orchestrator import (
                    run_course_embedding_background,
                )

                run_course_embedding_background(course_id=course_id)
            except Exception:
                logger.exception("Course embedding phase failed (continuing)")
    finally:
        try:
            if neo4j_session is not None:
                neo4j_session.close()
        finally:
            db.close()


def run_course_extraction_background(*, course_id: int, teacher_id: int) -> None:
    """BackgroundTasks entrypoint (creates its own SQL + Neo4j sessions)."""

    driver = None
    try:
        driver = create_neo4j_driver()

        # Discover which files need processing (single-threaded; do not reuse this
        # session across worker threads).
        with SessionLocal() as db:
            repo = CourseRepository(db)
            course = repo.get_by_id(course_id)
            if not course:
                logger.warning("Course %s not found for extraction", course_id)
                return

            files = list(repo.list_course_files(course_id))
            if not files:
                logger.info(
                    "No files found for course %s; marking extraction failed", course_id
                )
                course.extraction_status = ExtractionStatus.FAILED
                repo.update(course, commit=False)
                db.commit()
                return

            files_to_process = [
                (f.id, f.filename, f.blob_path)
                for f in files
                if f.status
                in {FileProcessingStatus.PENDING, FileProcessingStatus.FAILED}
            ]

        # Process files concurrently (bounded).
        if files_to_process:
            with ThreadPoolExecutor(
                max_workers=settings.extraction_workers
            ) as executor:
                futures = [
                    executor.submit(
                        _process_course_file_background,
                        course_id=course_id,
                        teacher_id=teacher_id,
                        course_file_id=file_id,
                        filename=filename,
                        blob_path=blob_path,
                        neo4j_driver=driver,
                    )
                    for (file_id, filename, blob_path) in files_to_process
                ]
                for fut in as_completed(futures):
                    # Ensure unexpected exceptions are surfaced and handled by outer try.
                    fut.result()

        # Recompute final course status from per-file outcomes.
        _finalize_course_extraction_status_background(
            course_id=course_id, neo4j_driver=driver
        )
    except Exception as e:
        logger.exception("Extraction background task failed")
        try:
            with SessionLocal() as db:
                repo = CourseRepository(db)
                course = repo.get_by_id(course_id)
                if course:
                    course.extraction_status = ExtractionStatus.FAILED
                    repo.update(course, commit=False)

                # If we failed before per-file processing (e.g., missing LLM credentials),
                # mark all course files failed with a helpful error for the UI.
                msg = str(e) or "Extraction failed"
                files = list(repo.list_course_files(course_id))
                for f in files:
                    if f.status != FileProcessingStatus.PROCESSED:
                        repo.update_course_file_status(
                            f.id,
                            FileProcessingStatus.FAILED,
                            processed_at=datetime.now(UTC),
                            last_error=msg,
                        )
                db.commit()
        except Exception:
            logger.exception("Failed to mark course extraction as failed")
    finally:
        if driver is not None:
            driver.close()
