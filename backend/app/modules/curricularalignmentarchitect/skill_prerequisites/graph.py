from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import (
    api_retry_policy,
    build_cluster_fanout,
    embed_missing,
    enforce_dag,
    find_and_merge_dupes,
    judge_cluster,
    load_skills_for_clustering,
    persist,
    synthesize,
)
from .state import SkillPrerequisiteState


def build_skill_prerequisite_graph():
    """Embed -> Dedup -> Cluster -> Prerequisite judgment -> DAG -> Persist."""
    builder = StateGraph(SkillPrerequisiteState)

    builder.add_node("embed_missing", embed_missing)
    builder.add_node("find_and_merge_dupes", find_and_merge_dupes)
    builder.add_node("load_skills_for_clustering", load_skills_for_clustering)
    builder.add_node("judge_cluster", judge_cluster, retry=api_retry_policy)
    builder.add_node("synthesize", synthesize)
    builder.add_node("enforce_dag", enforce_dag)
    builder.add_node("persist", persist)

    builder.add_edge(START, "embed_missing")
    builder.add_edge("embed_missing", "find_and_merge_dupes")
    builder.add_edge("find_and_merge_dupes", "load_skills_for_clustering")
    builder.add_conditional_edges(
        "load_skills_for_clustering", build_cluster_fanout, ["judge_cluster"]
    )
    builder.add_edge("judge_cluster", "synthesize")
    builder.add_edge("synthesize", "enforce_dag")
    builder.add_edge("enforce_dag", "persist")
    builder.add_edge("persist", END)

    return builder.compile()
