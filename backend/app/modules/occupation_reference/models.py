from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OnetRelease(Base):
    __tablename__ = "onet_releases"
    __table_args__ = (
        CheckConstraint("status = 'ready'", name="ck_onet_release_ready"),
        Index(
            "uq_onet_one_active_release",
            "active",
            unique=True,
            postgresql_where=text("active = true"),
        ),
    )

    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class OnetOccupation(Base):
    __tablename__ = "onet_occupations"

    release: Mapped[str] = mapped_column(
        ForeignKey("onet_releases.version"), primary_key=True
    )
    soc_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    alternate_titles: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    source_rows: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)


class OnetEvidence(Base):
    __tablename__ = "onet_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["release", "soc_code"],
            ["onet_occupations.release", "onet_occupations.soc_code"],
            name="fk_onet_evidence_occupation",
        ),
        UniqueConstraint("release", "source_key", name="uq_onet_evidence_source_key"),
        CheckConstraint(
            "family IN ('essential', 'transferable', 'software')",
            name="ck_onet_evidence_family",
        ),
        CheckConstraint(
            "(family = 'software') = (workplace_example IS NOT NULL)",
            name="ck_onet_evidence_example",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    release: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    soc_code: Mapped[str] = mapped_column(String(10), nullable=False)
    family: Mapped[str] = mapped_column(String(20), nullable=False)
    element_id: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    workplace_example: Mapped[str | None] = mapped_column(Text, nullable=True)
    ratings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    flags: Mapped[dict[str, bool | None]] = mapped_column(JSONB, nullable=False)
    source_rows: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
