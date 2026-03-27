"""LangGraph graph builder for chapter-level skills extraction."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import api_retry_policy, assign_chapters, chapter_worker, synthesize_results
from .state import BookPipelineState


def build_book_pipeline_graph():
    """Outer graph: fan-out chapters via Send → chapter_worker → synthesize.

    Compiled with ``max_concurrency=5`` to enforce 5 parallel workers.
    """
    builder = StateGraph(BookPipelineState)
    builder.add_node("chapter_worker", chapter_worker, retry=api_retry_policy)
    builder.add_node("synthesize", synthesize_results)

    builder.add_conditional_edges(START, assign_chapters, ["chapter_worker"])
    builder.add_edge("chapter_worker", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()
