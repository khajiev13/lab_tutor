"""SQLAlchemy model for persisting Market Demand Agent thread state."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Text, func
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
