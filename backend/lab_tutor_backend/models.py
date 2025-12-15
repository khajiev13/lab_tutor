from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"


class ExtractionStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, name="user_role"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    courses: Mapped[list["Course"]] = relationship(
        back_populates="teacher", cascade="all, delete"
    )
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        SqlEnum(
            ExtractionStatus,
            name="extraction_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ExtractionStatus.NOT_STARTED,
        nullable=False,
    )

    teacher: Mapped[User] = relationship(back_populates="courses")
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "student_id", name="uq_course_student"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    course: Mapped["Course"] = relationship(back_populates="enrollments")
    student: Mapped["User"] = relationship(back_populates="enrollments")
