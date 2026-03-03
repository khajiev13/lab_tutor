"""Recommendation orchestration service.

Gathers data via the repository, dispatches to registered agents,
and yields SSE events for real-time streaming to the frontend.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from .agents.book_gap_analysis import stream_book_gap_analysis
from .repository import RecommendationRepository

logger = logging.getLogger(__name__)


class RecommendationService:
    """Orchestrates recommendation generation across all agents."""

    def __init__(self, db: Session, neo4j_session: Neo4jSession | None = None):
        self.repo = RecommendationRepository(db, neo4j_session)

    def stream_recommendations(
        self,
        course_id: int,
        run_id: int,
        selected_book_id: int,
    ) -> Generator[tuple[str, dict], None, None]:
        """Yield (event_type, data) tuples for SSE streaming.

        Events emitted:
          started   — data gathering complete, includes gap counts
          analyzing — LLM call about to start
          token     — partial text chunk from the LLM (streamed word-by-word)
          report    — full validated RecommendationReport as JSON
          done      — all agents finished
          error     — something went wrong
        """
        # Phase 1: gather data
        data = self.repo.gather_recommendation_data(course_id, run_id, selected_book_id)
        if data is None:
            yield "error", {"message": "Chapter analysis data not found."}
            return

        yield (
            "started",
            {
                "book_title": data.book_title,
                "novel_count": len(data.novel_concepts),
                "overlap_count": len(data.overlap_concepts),
                "weak_course_count": len(data.weak_course_concepts),
                "skill_count": len(data.skills),
                "teacher_doc_count": len(data.teacher_documents),
            },
        )

        # Phase 2: stream agents
        reports: list[dict] = []

        # Agent 1: Book Gap Analysis (streaming)
        yield (
            "analyzing",
            {
                "agent": "book_gap_analysis",
                "message": "Analyzing gaps between book and teacher materials…",
            },
        )

        try:
            for event_type, event_data in stream_book_gap_analysis(data, course_id):
                if event_type == "token":
                    yield "token", event_data
                elif event_type == "report":
                    reports.append(event_data)
                    yield "report", event_data
                elif event_type == "error":
                    yield "error", {"agent": "book_gap_analysis", **event_data}
        except Exception as exc:
            logger.exception("Book gap analysis failed")
            yield (
                "error",
                {
                    "agent": "book_gap_analysis",
                    "message": str(exc)[:500],
                },
            )

        # Future agents would be streamed here

        yield (
            "done",
            {
                "total_reports": len(reports),
                "total_recommendations": sum(
                    len(r.get("recommendations", [])) for r in reports
                ),
            },
        )
