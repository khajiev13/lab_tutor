from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    CourseLevel,
    CourseMarketGateStatus,
    CoursePublicationStatus,
    ExtractionStatus,
    FileProcessingStatus,
)

GateStatus = Literal["locked", "ready", "complete", "blocked"]
AvailabilityStatus = Literal["draft", "published", "publishing_paused"]
NextActionId = Literal["book", "market", "prerequisites", "publish", "none"]


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    level: CourseLevel = Field(default=CourseLevel.BACHELOR)


class CourseRead(BaseModel):
    id: int
    title: str
    description: str | None
    level: CourseLevel
    publication_status: CoursePublicationStatus
    market_gate_status: CourseMarketGateStatus
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


class CourseFileRead(BaseModel):
    id: int
    course_id: int
    filename: str
    blob_path: str
    content_hash: str | None = None
    uploaded_at: datetime
    status: FileProcessingStatus
    last_error: str | None
    processed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UploadPresentationsResponse(BaseModel):
    uploaded_files: list[str]


class StartExtractionResponse(BaseModel):
    message: str
    status: ExtractionStatus


class ReadinessNextAction(BaseModel):
    id: NextActionId
    label: str
    route: str | None = None


class ReadinessGate(BaseModel):
    id: Literal["book", "market", "prerequisites", "publish"]
    label: str
    status: GateStatus
    route: str | None = None
    detail: str


class PrerequisiteReviewSummary(BaseModel):
    status: str
    edge_count: int
    isolated_skill_count: int
    last_generated_at: datetime | None = None


class CourseReadinessRead(BaseModel):
    course_id: int
    publication_status: CoursePublicationStatus
    availability_status: AvailabilityStatus
    can_publish: bool
    blockers: list[str]
    next_action: ReadinessNextAction
    gates: list[ReadinessGate]
    prerequisite_review: PrerequisiteReviewSummary
