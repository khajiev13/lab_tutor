from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import ExtractionStatus


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class CourseRead(BaseModel):
    id: int
    title: str
    description: str | None
    teacher_id: int
    created_at: datetime
    extraction_status: ExtractionStatus

    model_config = ConfigDict(from_attributes=True)


class EnrollmentRead(BaseModel):
    id: int
    course_id: int
    student_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
