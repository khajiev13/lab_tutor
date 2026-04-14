"""LangGraph workflow builder for the book-selection pipeline V3.

Exports:
    build_workflow()        — full orchestrator (with HITL interrupt)
    build_discovery_graph() — discovery sub-graph
    build_scoring_graph()   — per-book scoring sub-graph
    build_download_graph()  — per-book download sub-graph
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from .nodes import (
    deduplicate_books,
    discover_books,
    dl_attempt_download,
    dl_extract_urls,
    dl_retry_feedback,
    dl_route_after_download,
    dl_search_agent,
    dl_search_route,
    dl_search_tools,
    download_book_node,
    fan_out_downloads,
    fan_out_scoring,
    fan_out_searches,
    fetch_course,
    generate_queries,
    hitl_review,
    res_agent,
    res_route,
    res_tools,
    score_book_node,
    score_node,
    search_and_extract,
)
from .state import (
    DiscoveryState,
    DownloadState,
    ScoringState,
    WorkflowState,
)

logger = logging.getLogger(__name__)

# Async checkpointer — uses PostgreSQL for HITL workflows + crash recovery.
# Initialized lazily because AsyncPostgresSaver.from_conn_string is async.
_ASYNC_CHECKPOINTER: AsyncPostgresSaver | None = None


def _get_checkpoint_db_url() -> str:
    """Derive a psycopg-compatible URL from the app's DATABASE_URL."""
    from app.core.settings import settings

    url = settings.database_url
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    # Strip any SQLAlchemy dialect suffix so psycopg gets a plain URL.
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url.removeprefix(prefix)
    return url


async def _get_async_checkpointer() -> AsyncPostgresSaver:
    """Lazily initialize the async PostgreSQL checkpointer."""
    global _ASYNC_CHECKPOINTER  # noqa: PLW0603
    if _ASYNC_CHECKPOINTER is None:
        conn_string = _get_checkpoint_db_url()
        conn = await AsyncConnection.connect(
            conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row
        )
        _ASYNC_CHECKPOINTER = AsyncPostgresSaver(conn=conn)
        await _ASYNC_CHECKPOINTER.setup()
    return _ASYNC_CHECKPOINTER


# ═══════════════════════════════════════════════════════════════
# Discovery Sub-Graph (map-reduce via Send)
# ═══════════════════════════════════════════════════════════════


def build_discovery_graph():
    dg = StateGraph(DiscoveryState)
    dg.add_node("generate_queries", generate_queries)
    dg.add_node("search_and_extract", search_and_extract)
    dg.add_node("deduplicate_books", deduplicate_books)

    dg.add_edge(START, "generate_queries")
    dg.add_conditional_edges("generate_queries", fan_out_searches)
    dg.add_edge("search_and_extract", "deduplicate_books")
    dg.add_edge("deduplicate_books", END)

    return dg.compile()


# ═══════════════════════════════════════════════════════════════
# Scoring Sub-Graph (research ReAct + structured scoring)
# ═══════════════════════════════════════════════════════════════


def build_scoring_graph():
    sb = StateGraph(ScoringState)
    sb.add_node("research", res_agent)
    sb.add_node("tools", res_tools)
    sb.add_node("score", score_node)

    sb.add_edge(START, "research")
    sb.add_conditional_edges(
        "research", res_route, {"tools": "tools", "score": "score"}
    )
    sb.add_edge("tools", "research")
    sb.add_edge("score", END)

    return sb.compile()


# ═══════════════════════════════════════════════════════════════
# Download Sub-Graph (search → extract URLs → download)
# ═══════════════════════════════════════════════════════════════


def build_download_graph():
    dlg = StateGraph(DownloadState)
    dlg.add_node("dl_search", dl_search_agent)
    dlg.add_node("dl_tools", dl_search_tools)
    dlg.add_node("extract_urls", dl_extract_urls)
    dlg.add_node("attempt_download", dl_attempt_download)
    dlg.add_node("retry_feedback", dl_retry_feedback)

    dlg.add_edge(START, "dl_search")
    dlg.add_conditional_edges(
        "dl_search",
        dl_search_route,
        {"dl_tools": "dl_tools", "extract_urls": "extract_urls"},
    )
    dlg.add_edge("dl_tools", "dl_search")
    dlg.add_edge("extract_urls", "attempt_download")
    dlg.add_conditional_edges(
        "attempt_download",
        dl_route_after_download,
        {"end": END, "retry": "retry_feedback"},
    )
    dlg.add_edge("retry_feedback", "dl_search")

    return dlg.compile()


# ═══════════════════════════════════════════════════════════════
# Main Workflow (with HITL interrupt)
# ═══════════════════════════════════════════════════════════════


async def build_book_selection_graph(*, checkpointer=None):
    """Build and compile the main book-selection workflow.

    Args:
        checkpointer: LangGraph checkpointer for HITL interrupt/resume.
                      Defaults to shared AsyncPostgresSaver backed by the app's PostgreSQL.
    """
    if checkpointer is None:
        checkpointer = await _get_async_checkpointer()

    builder = StateGraph(WorkflowState)
    builder.add_node("fetch_course", fetch_course)
    builder.add_node("discover_books", discover_books)
    builder.add_node("score_book", score_book_node)
    builder.add_node("hitl_review", hitl_review)
    builder.add_node("download_book", download_book_node)

    builder.add_edge(START, "fetch_course")
    builder.add_edge("fetch_course", "discover_books")
    builder.add_conditional_edges("discover_books", fan_out_scoring)
    builder.add_edge("score_book", "hitl_review")
    builder.add_conditional_edges("hitl_review", fan_out_downloads)
    builder.add_edge("download_book", END)

    return builder.compile(checkpointer=checkpointer)


async def build_workflow(*, checkpointer=None):
    """Backward-compatible alias for existing service imports."""
    return await build_book_selection_graph(checkpointer=checkpointer)
