"""Explicit SQL setup for tests that start downstream course workflows."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.courses.models import (
    Course,
    CourseFile,
    ExtractionStatus,
    FileProcessingStatus,
)


def seed_ready_materials(course_id: int) -> None:
    """Give a committed test course one fully inserted source document."""
    with SessionLocal() as db:
        course = db.get(Course, course_id)
        assert course is not None
        if db.scalar(select(CourseFile.id).where(CourseFile.course_id == course_id)):
            return
        course.extraction_status = ExtractionStatus.FINISHED
        db.add(
            CourseFile(
                course_id=course_id,
                filename="curriculum.txt",
                blob_path=f"courses/{course_id}/curriculum.txt",
                status=FileProcessingStatus.PROCESSED,
                processed_at=datetime.now(UTC),
            )
        )
        db.commit()
