"""SQLAlchemy model for persisting Market Demand Agent thread state."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MDAThreadState(Base):
    """Persisted agent state (jobs, skills, mapping, etc.) keyed by thread_id.

    This allows the StatePanel to be restored after server restarts or page
    refreshes.  When a teacher deletes a conversation, the corresponding row
    is deleted along with the LangGraph checkpoint — but Neo4j data that has
    already been integrated into the curriculum is kept.
    """

    __tablename__ = "mda_thread_state"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    state_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class MarketAnalysisRun(Base):
    """Teacher-owned durable analysis, independent of a disposable chat thread."""

    __tablename__ = "market_analysis_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    approval_contract_version: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_outcomes: Mapped[dict] = mapped_column(JSONB, default=dict)
    extraction_coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    candidate_manifest: Mapped[dict] = mapped_column(JSONB, default=dict)
    candidate_revision: Mapped[int] = mapped_column(default=0)
    selection_revision: Mapped[int] = mapped_column(default=0)
    publication_revision: Mapped[int] = mapped_column(default=0)
    selected_candidate_ids: Mapped[list] = mapped_column(JSONB, default=list)
    excluded_candidate_ids: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    selection_confirmation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    integration_review: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approved_references: Mapped[list] = mapped_column(JSONB, default=list)
    lifecycle: Mapped[str] = mapped_column(Text, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MarketVacancySnapshot(Base):
    """Complete safe provider evidence, separated from extraction input limits."""

    __tablename__ = "market_vacancy_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "provider",
            "identity",
            "content_hash",
            name="uq_market_vacancy_observation",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_analysis_runs.id"), index=True
    )
    provider: Mapped[str] = mapped_column(Text)
    native_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity: Mapped[str] = mapped_column(Text, index=True)
    content_hash: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(Text)
    source_urls: Mapped[list] = mapped_column(JSONB, default=list)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text, default="")
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    original_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill_tags: Mapped[list] = mapped_column(JSONB, default=list)
    returned_dates: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    query_membership: Mapped[list] = mapped_column(JSONB, default=list)
    demand_identity: Mapped[str] = mapped_column(Text, index=True)
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class MarketEvidenceRedaction(Base):
    """Durable cleanup intent for one removed original source, retried explicitly."""

    __tablename__ = "market_evidence_redactions"

    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_vacancy_snapshots.id"), primary_key=True
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    evidence_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    reference_states: Mapped[list] = mapped_column(JSONB, default=list)
    inactive_binding_ids: Mapped[list] = mapped_column(JSONB, default=list)
    projection_status: Mapped[str] = mapped_column(Text, default="pending")
    projection_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class CourseSkillReference(Base):
    """Stable course-owned identity; course metrics never live on shared graph nodes."""

    __tablename__ = "course_skill_references"
    __table_args__ = (
        UniqueConstraint("course_id", "target_identity", name="uq_course_skill_target"),
        UniqueConstraint("course_id", "id", name="uq_course_skill_reference_course"),
        CheckConstraint(
            "source IN ('book', 'market')", name="ck_course_skill_reference_source"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    target_identity: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    display_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    chapters: Mapped[list] = mapped_column(JSONB, default=list)
    approved_revision: Mapped[int] = mapped_column(default=0)
    projection_revision: Mapped[int] = mapped_column(default=0)
    projection_status: Mapped[str] = mapped_column(Text, default="pending")
    available_for_new_selection: Mapped[bool] = mapped_column(default=False)


class MarketSkillApproval(Base):
    """Immutable SQL intent; later revisions supersede offerings, never audit data."""

    __tablename__ = "market_skill_approvals"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "revision", name="uq_market_skill_approval_revision"
        ),
        UniqueConstraint(
            "run_id", "review_digest", name="uq_market_skill_approval_digest"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_analysis_runs.id"), index=True
    )
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column()
    review_digest: Mapped[str] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONB, default=list)
    affected_reference_ids: Mapped[list] = mapped_column(JSONB, default=list)
    withdrawal: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    projection_status: Mapped[str] = mapped_column(Text, default="pending")
    projection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now().astimezone()
    )


class CourseSkillEvidence(Base):
    """One generic immutable binding to exactly one original SQL evidence source."""

    __tablename__ = "course_skill_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "skill_reference_id"],
            ["course_skill_references.course_id", "course_skill_references.id"],
            name="fk_course_skill_evidence_reference",
        ),
        CheckConstraint(
            "(vacancy_snapshot_id IS NOT NULL) <> (onet_evidence_id IS NOT NULL)",
            name="ck_course_skill_evidence_source",
        ),
        UniqueConstraint("binding_key", name="uq_course_skill_evidence_binding"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    skill_reference_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    approval_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_skill_approvals.id"), index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_analysis_runs.id"), index=True
    )
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    mapping_relation: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    binding_key: Mapped[str] = mapped_column(Text)
    vacancy_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_vacancy_snapshots.id"), nullable=True
    )
    onet_evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("onet_evidence.id"), nullable=True
    )
