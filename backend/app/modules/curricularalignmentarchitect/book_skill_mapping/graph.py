"""LangGraph graph builder for book skill → course chapter mapping."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import api_retry_policy, load_and_fan_out, map_chapter, persist_all
from .state import BookSkillMappingState


def build_book_skill_mapping_graph():
    """Fan-out per book chapter: each chapter's skills mapped in parallel.

    Compiled with max_concurrency=5 to match chapter_extraction pattern.
    """
    builder = StateGraph(BookSkillMappingState)
    builder.add_node("map_chapter", map_chapter, retry=api_retry_policy)
    builder.add_node("persist_all", persist_all)

    builder.add_conditional_edges(START, load_and_fan_out, ["map_chapter"])
    builder.add_edge("map_chapter", "persist_all")
    builder.add_edge("persist_all", END)

    return builder.compile()
