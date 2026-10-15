from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from .models import ExtractionStatus, FileProcessingStatus
from .repository import CourseRepository
from .schemas import MaterialsReadinessRead


class MaterialsReadinessService:
    def __init__(self, repository: CourseRepository) -> None:
        self._repository = repository

    def get_readiness(self, course_id: int, teacher_id: int) -> MaterialsReadinessRead:
        course = self._repository.get_by_id(course_id)
        if course is None or course.teacher_id != teacher_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")

        files = self._repository.list_course_files(course_id)
        processed_files = sum(
            file.status == FileProcessingStatus.PROCESSED for file in files
        )
        if not files:
            readiness_status = "no_materials"
            message = "Upload and process course materials before running agents."
        elif any(file.status == FileProcessingStatus.FAILED for file in files):
            readiness_status = "failed"
            message = (
                "Some course materials failed to process. "
                "Retry the failed upload or extraction before running agents."
            )
        elif processed_files != len(files):
            # Uploading a pending file can leave the aggregate status as FAILED.
            # Current file outcomes distinguish waiting work from a failed run.
            readiness_status = "processing"
            message = (
                "Course materials are not fully processed. "
                "Finish extraction before running agents."
            )
        elif course.extraction_status == ExtractionStatus.FAILED:
            readiness_status = "failed"
            message = (
                "Course extraction failed. Retry extraction before running agents."
            )
        elif course.extraction_status != ExtractionStatus.FINISHED:
            readiness_status = "processing"
            message = "Course materials are still being inserted. Wait for extraction to finish."
        else:
            readiness_status = "ready"
            message = "All course materials are processed. Agents are available."

        return MaterialsReadinessRead(
            ready=readiness_status == "ready",
            status=readiness_status,
            message=message,
            total_files=len(files),
            processed_files=processed_files,
        )

    def require_ready(self, course_id: int, teacher_id: int) -> None:
        readiness = self.get_readiness(course_id, teacher_id)
        if not readiness.ready:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={"code": "materials_not_ready", **readiness.model_dump()},
            )


def get_materials_readiness_service(
    db: Session = Depends(get_db),
) -> MaterialsReadinessService:
    return MaterialsReadinessService(CourseRepository(db))


def require_materials_ready(
    course_id: int,
    teacher: User = Depends(require_role(UserRole.TEACHER)),
    service: MaterialsReadinessService = Depends(get_materials_readiness_service),
) -> None:
    service.require_ready(course_id, teacher.id)
