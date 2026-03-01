from datetime import UTC, datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SessionStatus(str, Enum):
    CONFIGURING = "configuring"
    DISCOVERING = "discovering"
    SCORING = "scoring"
    AWAITING_REVIEW = "awaiting_review"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    SUCCESS = "success"
    FAILED = "failed"
    MANUAL_UPLOAD = "manual_upload"


class BookStatus(str, Enum):
    """Status of a book in the course_selected_books table."""

    DOWNLOADED = "downloaded"
    UPLOADED = "uploaded"
    FAILED = "failed"
    CORRUPTED_PDF = "corrupted_pdf"


class BookSelectionSession(Base):
    __tablename__ = "book_selection_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(
            SessionStatus,
            name="book_session_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=SessionStatus.CONFIGURING,
        nullable=False,
    )
    weights_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_level: Mapped[str] = mapped_column(
        String(20), default="bachelor", nullable=False
    )
    discovered_books_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_scored: Mapped[int] = mapped_column(default=0, nullable=False)
    progress_total: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    books: Mapped[list["CourseBook"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class CourseBook(Base):
    __tablename__ = "course_books"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_selection_sessions.id"), nullable=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    s_final: Mapped[float | None] = mapped_column(nullable=True)
    scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_by_teacher: Mapped[bool] = mapped_column(default=False, nullable=False)
    download_status: Mapped[DownloadStatus] = mapped_column(
        SqlEnum(
            DownloadStatus,
            name="book_download_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=DownloadStatus.PENDING,
        nullable=False,
    )
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    session: Mapped["BookSelectionSession"] = relationship(back_populates="books")


class CourseSelectedBook(Base):
    """Final books associated with a course — promoted from candidates or custom uploads."""

    __tablename__ = "course_selected_books"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    source_book_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_books.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[BookStatus] = mapped_column(
        SqlEnum(
            BookStatus,
            name="book_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BookStatus.FAILED,
        nullable=False,
    )
    blob_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    blob_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Book Analysis models (dual-strategy: agentic + chunking)
# ---------------------------------------------------------------------------

# 2048 is the maximum dimension actually returned by text-embedding-v4.
# The provider allowlist is [64, 128, 256, 512, 768, 1024, 1536, 2048].
EMBEDDING_DIMS = 2048


class ExtractionRunStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    CHAPTER_EXTRACTED = "chapter_extracted"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    BOOK_PICKED = "book_picked"
    AGENTIC_EXTRACTING = "agentic_extracting"
    AGENTIC_COMPLETED = "agentic_completed"


class AnalysisStrategy(str, Enum):
    CHUNKING = "chunking"
    AGENTIC = "agentic"


class ConceptRelevance(str, Enum):
    CORE = "core"
    SUPPLEMENTARY = "supplementary"
    TANGENTIAL = "tangential"


class BookExtractionRun(Base):
    """One row per teacher-triggered analysis."""

    __tablename__ = "book_extraction_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"), nullable=False, index=True
    )
    status: Mapped[ExtractionRunStatus] = mapped_column(
        SqlEnum(
            ExtractionRunStatus,
            name="extraction_run_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ExtractionRunStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str] = mapped_column(
        String(100), default="text-embedding-v4", nullable=False
    )
    embedding_dims: Mapped[int] = mapped_column(
        Integer, default=EMBEDDING_DIMS, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    chapters: Mapped[list["BookChapter"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["BookChunk"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    course_concepts: Mapped[list["CourseConceptCache"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    document_summaries: Mapped[list["CourseDocumentSummaryCache"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    summaries: Mapped[list["BookAnalysisSummary"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    chapter_summaries: Mapped[list["ChapterAnalysisSummary"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BookChapter(Base):
    """One chapter extracted from a selected book (agentic strategy)."""

    __tablename__ = "book_chapters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    selected_book_id: Mapped[int] = mapped_column(
        ForeignKey("course_selected_books.id"), nullable=False, index=True
    )
    chapter_title: Mapped[str] = mapped_column(String(500), nullable=False)
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False)
    total_concept_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chapter_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapter_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="chapters")
    sections: Mapped[list["BookSection"]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )


class BookSection(Base):
    """One section within a chapter (agentic strategy)."""

    __tablename__ = "book_sections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("book_chapters.id"), nullable=False, index=True
    )
    section_title: Mapped[str] = mapped_column(String(500), nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    chapter: Mapped["BookChapter"] = relationship(back_populates="sections")
    concepts: Mapped[list["BookConcept"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class BookConcept(Base):
    """Individual concept extracted from a book section (agentic strategy)."""

    __tablename__ = "book_concepts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    section_id: Mapped[int] = mapped_column(
        ForeignKey("book_sections.id"), nullable=False, index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[ConceptRelevance] = mapped_column(
        SqlEnum(
            ConceptRelevance,
            name="concept_relevance",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    name_embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    evidence_embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    section: Mapped["BookSection"] = relationship(back_populates="concepts")


class BookChunk(Base):
    """Paragraph-level text chunk from a book PDF (chunking strategy)."""

    __tablename__ = "book_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    selected_book_id: Mapped[int] = mapped_column(
        ForeignKey("course_selected_books.id"), nullable=False, index=True
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="chunks")


class CourseConceptCache(Base):
    """Course concept embeddings cached per analysis run."""

    __tablename__ = "course_concept_caches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    concept_name: Mapped[str] = mapped_column(String(500), nullable=False)
    text_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    evidence_embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="course_concepts")


class CourseDocumentSummaryCache(Base):
    """Course document summaries + embeddings cached per analysis run."""

    __tablename__ = "course_document_summary_caches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    document_neo4j_id: Mapped[str] = mapped_column(String(500), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_embedding = mapped_column(Vector(EMBEDDING_DIMS), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="document_summaries")


class BookAnalysisSummary(Base):
    """Scored analysis results — one row per (run × book × strategy)."""

    __tablename__ = "book_analysis_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    selected_book_id: Mapped[int] = mapped_column(
        ForeignKey("course_selected_books.id"), nullable=False, index=True
    )
    strategy: Mapped[AnalysisStrategy] = mapped_column(
        SqlEnum(
            AnalysisStrategy,
            name="analysis_strategy",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    book_title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Scalar summary
    s_final_name: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    s_final_evidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_book_concepts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chapter_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Default-threshold snapshot (novel_thr=0.35, covered_thr=0.55)
    novel_count_default: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overlap_count_default: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    covered_count_default: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # JSON blobs — sim_max per concept, no tier stored
    book_unique_concepts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_coverage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sim_distribution_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="summaries")
    document_summary_scores: Mapped[list["BookDocumentSummaryScore"]] = relationship(
        back_populates="summary", cascade="all, delete-orphan"
    )


class BookDocumentSummaryScore(Base):
    """Per-book similarity score for a course document summary."""

    __tablename__ = "book_document_summary_scores"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    summary_id: Mapped[int] = mapped_column(
        ForeignKey("book_analysis_summaries.id"), nullable=False, index=True
    )
    document_neo4j_id: Mapped[str] = mapped_column(String(500), nullable=False)
    topic: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sim_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    summary: Mapped["BookAnalysisSummary"] = relationship(
        back_populates="document_summary_scores"
    )


class ChapterAnalysisSummary(Base):
    """Chapter-level analysis results — one row per (run × book).

    Stores pre-computed concept-to-concept similarity data from the agentic
    extraction pipeline.  Richer than BookAnalysisSummary because it carries
    full chapter/section/skill structure alongside coverage metrics.
    """

    __tablename__ = "chapter_analysis_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("book_extraction_runs.id"), nullable=False, index=True
    )
    selected_book_id: Mapped[int] = mapped_column(
        ForeignKey("course_selected_books.id"), nullable=False, index=True
    )
    book_title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Scalar summaries
    total_core_concepts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_supplementary_concepts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_skills: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chapters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Aggregate similarity scores
    s_final_name: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    s_final_evidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    s_final_weighted: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    s_chapter_lecture: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Default-threshold snapshot (novel_thr=0.35, covered_thr=0.55)
    novel_count_default: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overlap_count_default: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    covered_count_default: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # JSON blobs — full structured data for the frontend dashboard
    chapter_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_coverage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    book_unique_concepts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sim_distribution_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    run: Mapped["BookExtractionRun"] = relationship(back_populates="chapter_summaries")
