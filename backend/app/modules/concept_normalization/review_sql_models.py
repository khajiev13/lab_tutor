from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .schemas import MergeProposalDecision


class ConceptNormalizationReviewItem(Base):
    """Single-table staging area for human-in-the-loop merge review.

    We intentionally keep this out of Neo4j: Neo4j should only store the knowledge graph
    (e.g., :CONCEPT nodes). Review state is transient and lives in SQL until applied.
    """

    __tablename__ = "concept_normalization_review_items"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_norm_review_proposal_id"),
        Index("ix_norm_review_course_id", "course_id"),
        Index("ix_norm_review_review_id", "review_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Review identity / scope
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    review_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    # Proposal payload
    proposal_id: Mapped[str] = mapped_column(String(80), nullable=False)
    concept_a: Mapped[str] = mapped_column(String(255), nullable=False)
    concept_b: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical: Mapped[str] = mapped_column(String(255), nullable=False)
    variants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    r: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Human decision
    decision: Mapped[MergeProposalDecision] = mapped_column(
        SqlEnum(
            MergeProposalDecision,
            name="normalization_merge_decision",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=MergeProposalDecision.PENDING,
        nullable=False,
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
