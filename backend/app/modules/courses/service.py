import logging

from fastapi import BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_session
from app.modules.auth.models import User
from app.modules.document_extraction.neo4j_repository import (
    DocumentExtractionGraphRepository,
)
from app.modules.document_extraction.service import run_course_extraction_background
from app.providers.storage import blob_service

from .models import (
    Course,
    CourseEnrollment,
    CourseFile,
    ExtractionStatus,
    FileProcessingStatus,
)
from .neo4j_repository import CourseGraphRepository
from .repository import CourseRepository
from .schemas import CourseCreate

logger = logging.getLogger(__name__)


def get_course_repository(db: Session = Depends(get_db)) -> CourseRepository:
    return CourseRepository(db)


def get_course_graph_repository(
    neo4j_session=Depends(get_neo4j_session),
) -> CourseGraphRepository | None:
    if neo4j_session is None:
        return None
    return CourseGraphRepository(neo4j_session)


def get_document_extraction_graph_repository(
    neo4j_session=Depends(get_neo4j_session),
) -> DocumentExtractionGraphRepository | None:
    if neo4j_session is None:
        return None
    return DocumentExtractionGraphRepository(neo4j_session)


class CourseService:
    def __init__(
        self,
        repo: CourseRepository,
        graph_repo: CourseGraphRepository | None,
        document_graph_repo: DocumentExtractionGraphRepository | None,
    ):
        self.repo = repo
        self.graph_repo = graph_repo
        self.document_graph_repo = document_graph_repo

    def _commit_sql(self) -> None:
        self.repo.db.commit()

    def _rollback_sql(self) -> None:
        self.repo.db.rollback()

    def _run_graph(self, fn, *, detail: str) -> None:
        if self.graph_repo is None:
            return
        try:
            fn()
        except Exception as e:
            logger.exception("Neo4j graph sync failed")
            self._rollback_sql()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail,
            ) from e

    def _run_doc_graph(self, fn, *, detail: str) -> None:
        if self.document_graph_repo is None:
            return
        try:
            fn()
        except Exception as e:
            logger.exception("Neo4j document graph sync failed")
            self._rollback_sql()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail,
            ) from e

    def create_course(self, course_in: CourseCreate, teacher: User) -> Course:
        course = Course(
            title=course_in.title,
            description=course_in.description,
            teacher_id=teacher.id,
        )
        try:
            course = self.repo.create(course, commit=False)

            self._run_graph(
                lambda: (
                    self.graph_repo.upsert_course(
                        course_id=course.id,
                        title=course.title,
                        description=course.description,
                        created_at=course.created_at,
                        extraction_status=course.extraction_status.value
                        if course.extraction_status
                        else None,
                    ),
                    self.graph_repo.link_teacher_teaches_class(
                        teacher_id=teacher.id,
                        course_id=course.id,
                    ),
                ),
                detail="Failed to sync course to Neo4j",
            )

            self._commit_sql()
            self.repo.db.refresh(course)
            return course
        except ValueError as e:
            self._rollback_sql()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    def list_courses(self) -> list[Course]:
        return list(self.repo.list())

    def list_enrolled_courses(self, student: User) -> list[Course]:
        return list(self.repo.list_enrolled(student.id))

    def get_course(self, course_id: int) -> Course:
        course = self.repo.get_by_id(course_id)
        if not course:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
            )
        return course

    def join_course(self, course_id: int, student: User) -> CourseEnrollment:
        course = self.get_course(course_id)  # Re-use logic

        existing = self.repo.get_enrollment(course_id, student.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already joined this course",
            )

        enrollment = CourseEnrollment(course_id=course.id, student_id=student.id)
        enrollment = self.repo.create_enrollment(enrollment, commit=False)

        self._run_graph(
            lambda: self.graph_repo.link_student_enrolled(
                student_id=student.id,
                course_id=course.id,
            ),
            detail="Failed to sync enrollment to Neo4j",
        )

        self._commit_sql()
        self.repo.db.refresh(enrollment)
        return enrollment

    def leave_course(self, course_id: int, student: User) -> None:
        existing = self.repo.get_enrollment(course_id, student.id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Not enrolled in this course",
            )

        self.repo.delete_enrollment(existing, commit=False)
        self._run_graph(
            lambda: self.graph_repo.unlink_student_enrolled(
                student_id=student.id,
                course_id=course_id,
            ),
            detail="Failed to sync enrollment removal to Neo4j",
        )
        self._commit_sql()

    def get_enrollment(self, course_id: int, student: User) -> CourseEnrollment | None:
        return self.repo.get_enrollment(course_id, student.id)

    def update_course(
        self, course_id: int, course_update: CourseCreate, teacher: User
    ) -> Course:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this course",
            )

        course.title = course_update.title
        if course_update.description is not None:
            course.description = course_update.description

        try:
            course = self.repo.update(course, commit=False)

            self._run_graph(
                lambda: self.graph_repo.upsert_course(
                    course_id=course.id,
                    title=course.title,
                    description=course.description,
                    created_at=course.created_at,
                    extraction_status=course.extraction_status.value
                    if course.extraction_status
                    else None,
                ),
                detail="Failed to sync course update to Neo4j",
            )

            self._commit_sql()
            self.repo.db.refresh(course)
            return course
        except ValueError as e:
            self._rollback_sql()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

    def delete_course(self, course_id: int, teacher: User) -> None:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this course",
            )

        self.repo.delete(course, commit=False)
        self._run_graph(
            lambda: self.graph_repo.delete_course(course_id=course.id),
            detail="Failed to sync course deletion to Neo4j",
        )
        self._commit_sql()

    async def upload_presentations(
        self, course_id: int, files: list[UploadFile], teacher: User
    ) -> list[str]:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to upload files for this course",
            )

        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot upload files while extraction is in progress",
            )

        uploaded_urls = []
        for file in files:
            # Sanitize course title for folder name
            safe_course_title = (
                "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
                .strip()
                .replace(" ", "_")
            )
            destination_path = f"{safe_course_title}/teacher_uploads/{file.filename}"

            try:
                await file.seek(0)
                content = await file.read()
                content_hash = blob_service.sha256_hex(content)

                existing = self.repo.get_course_file_by_content_hash(
                    course.id, content_hash
                )
                if existing is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "This file was already uploaded for this course "
                            f"(existing filename: {existing.filename})"
                        ),
                    )

                url = await blob_service.upload_bytes(content, destination_path)
                self.repo.upsert_course_file(
                    CourseFile(
                        course_id=course.id,
                        filename=file.filename,
                        blob_path=destination_path,
                        content_hash=content_hash,
                        status=FileProcessingStatus.PENDING,
                        last_error=None,
                        processed_at=None,
                    )
                )
                uploaded_urls.append(url)
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise
                if isinstance(e, ValueError) and "identical content" in str(e).lower():
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=str(e),
                    ) from e
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to upload file {file.filename}: {str(e)}",
                ) from e
        return uploaded_urls

    async def list_presentations(self, course_id: int) -> list[str]:
        course = self.get_course(course_id)

        safe_course_title = (
            "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
            .strip()
            .replace(" ", "_")
        )
        folder_path = f"{safe_course_title}/teacher_uploads/"

        try:
            files = await blob_service.list_files(folder_path)
            # Return only filenames, not full paths, to make it easier for frontend
            return [f.split("/")[-1] for f in files]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list presentations: {str(e)}",
            ) from e

    async def delete_presentation(
        self, course_id: int, filename: str, teacher: User
    ) -> None:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete files for this course",
            )

        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete files while extraction is in progress",
            )

        safe_course_title = (
            "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
            .strip()
            .replace(" ", "_")
        )
        blob_path = f"{safe_course_title}/teacher_uploads/{filename}"

        try:
            # Keep the SQL row until after graph cleanup so we can derive a stable document_id.
            course_file = self.repo.get_course_file_by_blob_path(course.id, blob_path)
            await blob_service.delete_file(blob_path)

            if course_file and self.document_graph_repo is not None:
                self._run_doc_graph(
                    lambda: [
                        # New stable IDs (by content hash) + legacy IDs (by CourseFile.id)
                        # so deletes work across old/new deployments.
                        self.document_graph_repo.delete_document_and_orphan_concepts(
                            document_id=document_id
                        )
                        for document_id in [
                            (
                                f"doc_{course.id}_{course_file.content_hash}"
                                if course_file.content_hash
                                else None
                            ),
                            f"doc_{course_file.id}",
                        ]
                        if document_id is not None
                    ],
                    detail="Failed to delete extracted document from Neo4j",
                )
            elif self.document_graph_repo is not None:
                # Fallback: if the SQL row is missing, delete by (course_id, filename).
                self._run_doc_graph(
                    lambda: self.document_graph_repo.delete_documents_by_course_and_filename_and_orphan_concepts(
                        course_id=course.id,
                        source_filename=filename,
                    ),
                    detail="Failed to delete extracted document(s) from Neo4j",
                )

            self.repo.delete_course_file_by_blob_path(course.id, blob_path)
        except HTTPException:
            # Preserve intended status codes (e.g., 503 on Neo4j failure).
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete file {filename}: {str(e)}",
            ) from e

    async def delete_all_presentations(self, course_id: int, teacher: User) -> None:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete files for this course",
            )

        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete files while extraction is in progress",
            )

        safe_course_title = (
            "".join(c for c in course.title if c.isalnum() or c in (" ", "_", "-"))
            .strip()
            .replace(" ", "_")
        )
        folder_path = f"{safe_course_title}/teacher_uploads/"

        try:
            await blob_service.delete_folder(folder_path)

            if self.document_graph_repo is not None:
                self._run_doc_graph(
                    lambda: self.document_graph_repo.delete_documents_by_course_and_orphan_concepts(
                        course_id=course.id
                    ),
                    detail="Failed to delete extracted documents from Neo4j",
                )

            self.repo.delete_course_files_by_prefix(course.id, folder_path)
        except HTTPException:
            # Preserve intended status codes (e.g., 503 on Neo4j failure).
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete presentations: {str(e)}",
            ) from e

    def list_presentation_statuses(self, course_id: int) -> list[CourseFile]:
        self.get_course(course_id)
        return list(self.repo.list_course_files(course_id))

    def start_extraction(
        self, course_id: int, teacher: User, background_tasks: BackgroundTasks
    ) -> ExtractionStatus:
        course = self.get_course(course_id)

        if course.teacher_id != teacher.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to start extraction for this course",
            )

        if course.extraction_status == ExtractionStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extraction already in progress",
            )

        course.extraction_status = ExtractionStatus.IN_PROGRESS
        self.repo.update(course, commit=False)

        self._run_graph(
            lambda: self.graph_repo.upsert_course(
                course_id=course.id,
                title=course.title,
                description=course.description,
                created_at=course.created_at,
                extraction_status=course.extraction_status.value,
            ),
            detail="Failed to sync extraction status to Neo4j",
        )

        self._commit_sql()

        # Run extraction after response is returned.
        # BackgroundTasks should be short-lived; our current scope supports text files only.
        background_tasks.add_task(
            run_course_extraction_background,
            course_id=course.id,
            teacher_id=teacher.id,
        )

        return course.extraction_status


def get_course_service(
    repo: CourseRepository = Depends(get_course_repository),
    graph_repo: CourseGraphRepository | None = Depends(get_course_graph_repository),
    document_graph_repo: DocumentExtractionGraphRepository | None = Depends(
        get_document_extraction_graph_repository
    ),
) -> CourseService:
    return CourseService(repo, graph_repo, document_graph_repo)
