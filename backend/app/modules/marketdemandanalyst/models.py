"""SQLAlchemy model for persisting Market Demand Agent thread state."""

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
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
