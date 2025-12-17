from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Course, CourseEnrollment


class CourseRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, course: Course) -> Course:
        self.db.add(course)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Course with this title already exists")
        self.db.refresh(course)
        return course

    def get_by_id(self, course_id: int) -> Course | None:
        return self.db.scalar(select(Course).where(Course.id == course_id))

    def list(self) -> Sequence[Course]:
        return self.db.scalars(select(Course).order_by(Course.created_at.desc())).all()

    def list_enrolled(self, student_id: int) -> Sequence[Course]:
        return self.db.scalars(
            select(Course)
            .join(CourseEnrollment)
            .where(CourseEnrollment.student_id == student_id)
            .order_by(CourseEnrollment.created_at.desc())
        ).all()

    def update(self, course: Course) -> Course:
        self.db.add(course)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError("Course with this title already exists")
        self.db.refresh(course)
        return course

    def delete(self, course: Course) -> None:
        self.db.delete(course)
        self.db.commit()

    def get_enrollment(self, course_id: int, student_id: int) -> CourseEnrollment | None:
        return self.db.scalar(
            select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.student_id == student_id
            )
        )

    def create_enrollment(self, enrollment: CourseEnrollment) -> CourseEnrollment:
        self.db.add(enrollment)
        self.db.commit()
        self.db.refresh(enrollment)
        return enrollment

    def delete_enrollment(self, enrollment: CourseEnrollment) -> None:
        self.db.delete(enrollment)
        self.db.commit()

