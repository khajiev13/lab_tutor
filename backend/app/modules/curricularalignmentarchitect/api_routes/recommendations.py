"""Recommendation generation SSE endpoint.

POST .../recommendations  → streams real-time SSE events as the LLM
generates recommendations from ChapterAnalysisSummary + Neo4j teacher docs.

SSE event types:
  - ``started``     — gathering data, includes gap counts
  - ``analyzing``   — LLM call in progress
  - ``report``      — full RecommendationReport JSON
  - ``done``        — pipeline finished
  - ``error``       — something went wrong
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.neo4j import get_neo4j_session
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..models import BookExtractionRun, ChapterAnalysisSummary
from ..recommendations.service import RecommendationService

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    """Format a named SSE event."""
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def register_routes(router):
    @router.post(
        "/courses/{course_id}/analysis/{run_id}/books/{selected_book_id}/recommendations",
    )
    def generate_recommendations(
        course_id: int,
        run_id: int,
        selected_book_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
        db: Session = Depends(get_db),
        neo4j_session: Neo4jSession | None = Depends(get_neo4j_session),
    ):
        """Stream LLM-driven content recommendations as SSE events.

        Uses the pre-computed ChapterAnalysisSummary (book concepts with
        similarity scores) and Neo4j teacher documents to advise on what
        to add/improve in uploaded materials.

        Requires that chapter-scoring has been run first.
        """
        # Validate run exists and belongs to the course
        run = db.get(BookExtractionRun, run_id)
        if run is None or run.course_id != course_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail="Analysis run not found"
            )

        # Validate ChapterAnalysisSummary exists
        summary = (
            db.query(ChapterAnalysisSummary)
            .filter(
                ChapterAnalysisSummary.run_id == run_id,
                ChapterAnalysisSummary.selected_book_id == selected_book_id,
            )
            .first()
        )
        if summary is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Chapter analysis not found for this book. "
                    "Run chapter-scoring first."
                ),
            )

        service = RecommendationService(db, neo4j_session)

        def _stream():
            for event_type, event_data in service.stream_recommendations(
                course_id, run_id, selected_book_id
            ):
                yield _sse(event_type, event_data)

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
