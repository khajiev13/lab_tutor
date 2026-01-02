from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Course, CourseEnrollment, CourseFile, FileProcessingStatus


class CourseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, course: Course, *, commit: bool = True) -> Course:
        self.db.add(course)
        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except IntegrityError as err:
            self.db.rollback()
            raise ValueError("Course with this title already exists") from err
        self.db.refresh(course)
        return course

    def get_by_id(self, course_id: int) -> Course | None:
        return self.db.scalar(select(Course).where(Course.id == course_id))

    def list(self) -> Sequence[Course]:
        return self.db.scalars(select(Course).order_by(Course.created_at.desc())).all()

    def list_by_teacher(self, teacher_id: int) -> Sequence[Course]:
        return self.db.scalars(
            select(Course)
            .where(Course.teacher_id == teacher_id)
            .order_by(Course.created_at.desc())
        ).all()

    def list_enrolled(self, student_id: int) -> Sequence[Course]:
        return self.db.scalars(
            select(Course)
            .join(CourseEnrollment)
            .where(CourseEnrollment.student_id == student_id)
            .order_by(CourseEnrollment.created_at.desc())
        ).all()

    def update(self, course: Course, *, commit: bool = True) -> Course:
        self.db.add(course)
        try:
            if commit:
                self.db.commit()
            else:
                self.db.flush()
        except IntegrityError as err:
            self.db.rollback()
            raise ValueError("Course with this title already exists") from err
        self.db.refresh(course)
        return course

    def delete(self, course: Course, *, commit: bool = True) -> None:
        self.db.delete(course)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def get_enrollment(
        self, course_id: int, student_id: int
    ) -> CourseEnrollment | None:
        return self.db.scalar(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.student_id == student_id,
            )
        )

    def create_enrollment(
        self, enrollment: CourseEnrollment, *, commit: bool = True
    ) -> CourseEnrollment:
        self.db.add(enrollment)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        self.db.refresh(enrollment)
        return enrollment

    def delete_enrollment(
        self, enrollment: CourseEnrollment, *, commit: bool = True
    ) -> None:
        self.db.delete(enrollment)
        if commit:
            self.db.commit()
        else:
            self.db.flush()

    def upsert_course_file(self, course_file: CourseFile) -> CourseFile:
        """Insert or update a course file row by (course_id, blob_path)."""
        existing = self.db.scalar(
            select(CourseFile).where(
                CourseFile.course_id == course_file.course_id,
                CourseFile.blob_path == course_file.blob_path,
            )
        )
        if existing:
            existing.filename = course_file.filename
            existing.content_hash = course_file.content_hash or existing.content_hash
            # Keep existing uploaded_at if present
            existing.uploaded_at = existing.uploaded_at or course_file.uploaded_at
            self.db.add(existing)
            self.db.commit()
            self.db.refresh(existing)
            return existing

        self.db.add(course_file)
        try:
            self.db.commit()
        except IntegrityError as err:
            self.db.rollback()
            # Rare race: re-select and return (or raise a duplicate-by-hash error).
            existing = self.db.scalar(
                select(CourseFile).where(
                    CourseFile.course_id == course_file.course_id,
                    CourseFile.blob_path == course_file.blob_path,
                )
            )
            if existing:
                return existing
            if course_file.content_hash:
                existing_by_hash = self.get_course_file_by_content_hash(
                    course_file.course_id, course_file.content_hash
                )
                if existing_by_hash:
                    raise ValueError(
                        "File with identical content already exists in this course"
                    ) from err
            raise
        self.db.refresh(course_file)
        return course_file

    def get_course_file_by_content_hash(
        self, course_id: int, content_hash: str
    ) -> CourseFile | None:
        return self.db.scalar(
            select(CourseFile).where(
                CourseFile.course_id == course_id,
                CourseFile.content_hash == content_hash,
            )
        )

    def list_course_files(self, course_id: int) -> Sequence[CourseFile]:
        return self.db.scalars(
            select(CourseFile)
            .where(CourseFile.course_id == course_id)
            .order_by(CourseFile.uploaded_at.desc())
        ).all()

    def get_course_file_by_blob_path(
        self, course_id: int, blob_path: str
    ) -> CourseFile | None:
        return self.db.scalar(
            select(CourseFile).where(
                CourseFile.course_id == course_id,
                CourseFile.blob_path == blob_path,
            )
        )

    def delete_course_file_by_blob_path(self, course_id: int, blob_path: str) -> None:
        existing = self.get_course_file_by_blob_path(course_id, blob_path)
        if existing:
            self.db.delete(existing)
            self.db.commit()

    def delete_course_files_by_prefix(self, course_id: int, blob_prefix: str) -> int:
        files = self.db.scalars(
            select(CourseFile).where(
                CourseFile.course_id == course_id,
                CourseFile.blob_path.startswith(blob_prefix),
            )
        ).all()
        deleted = 0
        for f in files:
            self.db.delete(f)
            deleted += 1
        if deleted:
            self.db.commit()
        return deleted

    def update_course_file_status(
        self,
        course_file_id: int,
        status: FileProcessingStatus,
        *,
        processed_at: datetime | None = None,
        last_error: str | None = None,
    ) -> CourseFile:
        course_file = self.db.get(CourseFile, course_file_id)
        if not course_file:
            raise ValueError("Course file not found")
        course_file.status = status
        course_file.last_error = last_error
        course_file.processed_at = processed_at
        self.db.add(course_file)
        self.db.commit()
        self.db.refresh(course_file)
        return course_file
