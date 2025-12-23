from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

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

logger = logging.getLogger(__name__)


class DocumentExtractionService:
    def __init__(self, *, db: Session, neo4j_session=None) -> None:
        self.db = db
        self.course_repo = CourseRepository(db)
        self.neo4j_session = neo4j_session
        self.graph_repo = (
            DocumentExtractionGraphRepository(neo4j_session)
            if neo4j_session is not None
            else None
        )
        self.course_graph_repo = (
            CourseGraphRepository(neo4j_session) if neo4j_session is not None else None
        )
        self.extractor = DocumentLLMExtractor(use_examples=True)

    def _set_course_status(self, course_id: int, status: ExtractionStatus) -> None:
        course = self.course_repo.get_by_id(course_id)
        if not course:
            return
        course.extraction_status = status
        self.course_repo.update(course, commit=False)

        if self.course_graph_repo is not None:
            self.course_graph_repo.upsert_course(
                course_id=course.id,
                title=course.title,
                description=course.description,
                created_at=course.created_at,
                extraction_status=course.extraction_status.value,
            )

    def run_course_extraction(self, *, course_id: int, teacher_id: int) -> None:
        """Process all course files and insert extraction results into Neo4j."""

        course = self.course_repo.get_by_id(course_id)
        if not course:
            logger.warning("Course %s not found for extraction", course_id)
            return

        any_success = False
        files = list(self.course_repo.list_course_files(course_id))

        if not files:
            logger.info(
                "No files found for course %s; marking extraction failed", course_id
            )
            self._set_course_status(course_id, ExtractionStatus.FAILED)
            self.db.commit()
            return

        for f in files:
            try:
                self.course_repo.update_course_file_status(
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
                result = self.extractor.extract(text=text, source_filename=f.filename)
                if not result.success:
                    raise ValueError(result.error_message or "Extraction failed")

                any_success = True

                # Graph insertion (optional if Neo4j disabled).
                if self.graph_repo is not None:
                    content_hash = hashlib.sha256(file_bytes).hexdigest()
                    # Stable identity: prevents Neo4j duplicates when the SQL CourseFile row
                    # is deleted/recreated (new id) or when filenames differ.
                    document_id = f"doc_{course_id}_{content_hash}"
                    extracted_at = datetime.now(UTC)

                    self.graph_repo.upsert_course_document(
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

                    mentions: list[MentionInput] = []
                    for c in result.extraction.concepts:
                        name = (c.name or "").strip()
                        if not name:
                            continue
                        mentions.append(
                            {
                                "name": name,
                                "original_name": name,
                                "definition": c.definition,
                                "text_evidence": c.text_evidence,
                                "source_document": f.filename,
                            }
                        )
                    if mentions:
                        self.graph_repo.upsert_mentions(
                            document_id=document_id,
                            mentions=mentions,
                            updated_at=extracted_at,
                        )

                self.course_repo.update_course_file_status(
                    f.id,
                    FileProcessingStatus.PROCESSED,
                    processed_at=datetime.now(UTC),
                    last_error=None,
                )

            except Exception as e:
                logger.exception("Failed to process course file %s", f.id)
                self.course_repo.update_course_file_status(
                    f.id,
                    FileProcessingStatus.FAILED,
                    processed_at=datetime.now(UTC),
                    last_error=str(e),
                )

        self._set_course_status(
            course_id,
            ExtractionStatus.FINISHED if any_success else ExtractionStatus.FAILED,
        )
        self.db.commit()


def run_course_extraction_background(*, course_id: int, teacher_id: int) -> None:
    """BackgroundTasks entrypoint (creates its own SQL + Neo4j sessions)."""

    db = SessionLocal()
    driver = None
    try:
        driver = create_neo4j_driver()
        neo4j_session = (
            driver.session(database=settings.neo4j_database) if driver is not None else None
        )
        try:
            svc = DocumentExtractionService(db=db, neo4j_session=neo4j_session)
            svc.run_course_extraction(course_id=course_id, teacher_id=teacher_id)
        finally:
            if neo4j_session is not None:
                neo4j_session.close()
    except Exception as e:
        logger.exception("Extraction background task failed")
        try:
            repo = CourseRepository(db)
            course = repo.get_by_id(course_id)
            if course:
                course.extraction_status = ExtractionStatus.FAILED
                repo.update(course, commit=False)
            # If we failed before per-file processing (e.g., missing LLM credentials),
            # mark all course files failed with a helpful error for the UI.
            msg = str(e) or "Extraction failed"
            try:
                files = list(repo.list_course_files(course_id))
                for f in files:
                    if f.status != FileProcessingStatus.PROCESSED:
                        repo.update_course_file_status(
                            f.id,
                            FileProcessingStatus.FAILED,
                            processed_at=datetime.now(UTC),
                            last_error=msg,
                        )
            finally:
                db.commit()
        except Exception:
            logger.exception("Failed to mark course extraction as failed")
    finally:
        try:
            db.close()
        finally:
            if driver is not None:
                driver.close()

