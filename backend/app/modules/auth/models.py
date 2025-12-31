from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy import DateTime, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.courses.models import Course, CourseEnrollment


class UserRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"


class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, name="user_role"), nullable=False, default=UserRole.STUDENT
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    courses: Mapped[list["Course"]] = relationship(
        "Course", back_populates="teacher", cascade="all, delete"
    )
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        "CourseEnrollment",
        back_populates="student",
        cascade="all, delete-orphan",
    )
