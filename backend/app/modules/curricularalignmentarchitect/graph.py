"""Combined CurricularAlignmentArchitect graph.

Composes book selection and chunking analysis into a single sequential workflow.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.core.database import SessionLocal
from app.core.settings import settings

from .book_selection.graph import build_book_selection_graph
from .book_selection.state import WorkflowState
from .chunking_analysis.graph import build_chunking_graph
from .chunking_analysis.repository import create_run, get_active_run, update_run
from .models import ExtractionRunStatus

logger = logging.getLogger(__name__)


class CAAWorkflowState(WorkflowState, total=False):
    analysis_run_id: int
    analysis_status: str


def _run_chunking_analysis(state: CAAWorkflowState) -> dict:
    """Run chunking analysis after book selection/download phase."""
    course_id = state.get("course_id")
    if not course_id:
        return {"analysis_status": "skipped"}

    with SessionLocal() as db:
        run_id = state.get("analysis_run_id")
        if not run_id:
            active = get_active_run(course_id, db)
            if active:
                run_id = active.id
            else:
                run = create_run(
                    db,
                    course_id=course_id,
                    status=ExtractionRunStatus.PENDING,
                    embedding_model=settings.embedding_model,
                    embedding_dims=settings.embedding_dims or 2048,
                    progress_detail="Queued from combined workflow",
                )
                run_id = run.id

    try:
        chunking_graph = build_chunking_graph()
        chunking_graph.invoke({"run_id": run_id, "course_id": course_id})
        return {
            "analysis_run_id": run_id,
            "analysis_status": "completed",
        }
    except Exception as exc:
        logger.exception("Combined workflow chunking phase failed for run %s", run_id)
        with SessionLocal() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Failed",
            )
        return {
            "analysis_run_id": run_id,
            "analysis_status": "failed",
        }


async def build_caa_workflow(*, checkpointer=None):
    """Build full CAA workflow: book selection -> chunking analysis."""
    book_selection_graph = await build_book_selection_graph(checkpointer=checkpointer)

    builder = StateGraph(CAAWorkflowState)
    builder.add_node("book_selection", book_selection_graph)
    builder.add_node("chunking_analysis", _run_chunking_analysis)

    builder.add_edge(START, "book_selection")
    builder.add_edge("book_selection", "chunking_analysis")
    builder.add_edge("chunking_analysis", END)

    return builder.compile(checkpointer=checkpointer)
