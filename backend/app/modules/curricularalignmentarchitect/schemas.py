"""API-facing Pydantic DTOs for the book-selection feature."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    AnalysisStrategy,
    BookStatus,
    DownloadStatus,
    ExtractionRunStatus,
    SessionStatus,
)

# ═══════════════════════════════════════════════════════════════
# Request schemas
# ═══════════════════════════════════════════════════════════════


class WeightsConfig(BaseModel):
    """The 7 scoring weight values coming from the frontend config panel."""

    C_topic: float = Field(..., ge=0, le=1)
    C_struc: float = Field(..., ge=0, le=1)
    C_scope: float = Field(..., ge=0, le=1)
    C_pub: float = Field(..., ge=0, le=1)
    C_auth: float = Field(..., ge=0, le=1)
    C_time: float = Field(..., ge=0, le=1)
    W_prac: float = Field(
        ..., ge=0, le=1, description="Practicality weight (blends into S_final)"
    )

    @model_validator(mode="after")
    def check_sum(self) -> WeightsConfig:
        total = (
            self.C_topic
            + self.C_struc
            + self.C_scope
            + self.C_pub
            + self.C_auth
            + self.C_time
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Core weights must sum to 1.0 (got {total:.6f}). "
                "Adjust so C_topic + C_struc + C_scope + C_pub + C_auth + C_time = 1.0"
            )
        return self

    def to_weights_dict(self) -> dict[str, float]:
        return {
            "C_topic": self.C_topic,
            "C_struc": self.C_struc,
            "C_scope": self.C_scope,
            "C_pub": self.C_pub,
            "C_auth": self.C_auth,
            "C_time": self.C_time,
            "W_prac": self.W_prac,
        }


class CourseLevelEnum(str, Enum):
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


class StartSessionRequest(BaseModel):
    course_level: CourseLevelEnum = CourseLevelEnum.BACHELOR
    weights: WeightsConfig


class SelectBooksRequest(BaseModel):
    book_ids: list[int] = Field(..., max_length=5, description="Select up to 5 books")


# ═══════════════════════════════════════════════════════════════
# Response schemas
# ═══════════════════════════════════════════════════════════════


class SessionRead(BaseModel):
    id: int
    course_id: int
    thread_id: str
    status: SessionStatus
    course_level: str
    weights_json: str | None = None
    progress_scored: int = 0
    progress_total: int = 0
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookCandidateRead(BaseModel):
    id: int
    session_id: int
    course_id: int
    title: str
    authors: str | None
    publisher: str | None
    year: str | None
    s_final: float | None
    scores_json: str | None
    selected_by_teacher: bool
    download_status: DownloadStatus
    download_error: str | None
    blob_path: str | None
    source_url: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManualUploadResponse(BaseModel):
    book_id: int
    blob_path: str


# ═══════════════════════════════════════════════════════════════
# Course Selected Books schemas
# ═══════════════════════════════════════════════════════════════


class CourseSelectedBookRead(BaseModel):
    id: int
    course_id: int
    source_book_id: int | None
    title: str
    authors: str | None
    publisher: str | None
    year: str | None
    status: BookStatus
    blob_path: str | None
    blob_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SelectedBookManualUploadResponse(BaseModel):
    id: int
    blob_path: str
    blob_url: str | None
    status: BookStatus


# ═══════════════════════════════════════════════════════════════
# SSE Stream event schemas
# ═══════════════════════════════════════════════════════════════


class StreamEventType(str, Enum):
    PHASE_UPDATE = "phase_update"
    DISCOVERY_PROGRESS = "discovery_progress"
    SCORING_PROGRESS = "scoring_progress"
    BOOKS_READY = "books_ready"
    DOWNLOAD_PROGRESS = "download_progress"
    DOWNLOAD_COMPLETE = "download_complete"
    ERROR = "error"


class StreamEvent(BaseModel):
    type: StreamEventType
    phase: str = ""
    message: str = ""
    progress: int | None = None
    total: int | None = None
    data: dict | None = None


# ═══════════════════════════════════════════════════════════════
# Book Analysis schemas
# ═══════════════════════════════════════════════════════════════


class BookExtractionRunRead(BaseModel):
    id: int
    course_id: int
    status: ExtractionRunStatus
    error_message: str | None = None
    progress_detail: str | None = None
    embedding_model: str
    embedding_dims: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentSummaryItem(BaseModel):
    """One course document summary scored against a book."""

    document_id: str
    topic: str | None = None
    summary_text: str | None = None
    sim_score: float


class ConceptCoverageItem(BaseModel):
    """Course→book direction: one course concept's best match in a book."""

    concept_name: str
    doc_topic: str | None = None
    sim_max: float
    best_match: str | None = None


class BookUniqueConceptItem(BaseModel):
    """Book→course direction: one book concept's best match to course."""

    name: str
    chapter_title: str | None = None
    section_title: str | None = None
    sim_max: float
    best_course_match: str | None = None


class SimBucket(BaseModel):
    """One bucket of a similarity-score histogram."""

    bucket_start: float
    bucket_end: float
    count: int


class BookAnalysisSummaryRead(BaseModel):
    id: int
    run_id: int
    selected_book_id: int
    strategy: AnalysisStrategy
    book_title: str

    # Scalars
    s_final_name: float
    s_final_evidence: float
    total_book_concepts: int
    chapter_count: int

    # Default-threshold snapshot
    novel_count_default: int
    overlap_count_default: int
    covered_count_default: int

    # Deserialised JSON blobs
    book_unique_concepts: list[BookUniqueConceptItem] = Field(default_factory=list)
    course_coverage: list[ConceptCoverageItem] = Field(default_factory=list)
    topic_scores: dict[str, float] = Field(default_factory=dict)
    sim_distribution: list[SimBucket] = Field(default_factory=list)
    # From relationship (BookDocumentSummaryScore rows)
    document_summaries: list[DocumentSummaryItem] = Field(default_factory=list)

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def deserialise_json_blobs(cls, data: dict | object) -> dict | object:
        """Deserialise JSON text columns into typed Python objects."""
        import json

        # Handle both dict and ORM object
        def _get(obj: dict | object, key: str) -> str | None:
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        def _set(obj: dict | object, key: str, value: object) -> None:
            if isinstance(obj, dict):
                obj[key] = value
            else:
                object.__setattr__(obj, key, value)

        mapping = {
            "book_unique_concepts_json": "book_unique_concepts",
            "course_coverage_json": "course_coverage",
            "topic_scores_json": "topic_scores",
            "sim_distribution_json": "sim_distribution",
        }
        for json_key, target_key in mapping.items():
            raw = _get(data, json_key)
            if raw and isinstance(raw, str):
                _set(data, target_key, json.loads(raw))
            elif raw and not isinstance(raw, str):
                _set(data, target_key, raw)

        # Map relational document_summary_scores → document_summaries
        scores = _get(data, "document_summary_scores")
        if scores:
            _set(
                data,
                "document_summaries",
                [
                    {
                        "document_id": getattr(s, "document_neo4j_id", None)
                        or (s.get("document_neo4j_id") if isinstance(s, dict) else ""),
                        "topic": getattr(s, "topic", None)
                        if not isinstance(s, dict)
                        else s.get("topic"),
                        "summary_text": getattr(s, "summary_text", None)
                        if not isinstance(s, dict)
                        else s.get("summary_text"),
                        "sim_score": getattr(s, "sim_score", 0.0)
                        if not isinstance(s, dict)
                        else s.get("sim_score", 0.0),
                    }
                    for s in scores
                ],
            )

        return data
