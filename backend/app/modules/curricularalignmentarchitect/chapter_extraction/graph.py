"""LangGraph graph builders for chapter-level concept extraction."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    api_retry_policy,
    assign_chapters,
    chapter_worker,
    evaluate_chapter,
    extract_chapter_concepts,
    should_continue,
    synthesize_results,
)
from .state import (
    BookPipelineState,
    ChapterExtractionState,
)


def build_chapter_extraction_graph():
    """Inner graph: extract → evaluate → (revise | end) for one chapter."""
    builder = StateGraph(ChapterExtractionState)
    builder.add_node("extract", extract_chapter_concepts, retry=api_retry_policy)
    builder.add_node("evaluate", evaluate_chapter, retry=api_retry_policy)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        should_continue,
        {"revise": "extract", "end": END},
    )

    return builder.compile()


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

    return builder.compile(
        # checkpointer=None — stateless, no persistence needed
    )
