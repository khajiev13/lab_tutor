from __future__ import annotations

import json
import logging

import openai
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.types import RetryPolicy, Send

from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService

from .prompts import CLUSTER_PREREQ_PROMPT, DUPE_JUDGE_PROMPT
from .repository import (
    clear_skill_prerequisites,
    load_all_skills_for_course,
    load_skills_without_embeddings,
    merge_skill_into_canonical,
    write_skill_embeddings,
    write_skill_prerequisites,
)
from .schemas import ClusterPrerequisiteResult, DupeGroupVerdict
from .similarity import (
    build_concept_similarity_index,
    build_name_similarity_index,
    build_neighbor_adjacency,
    build_raw_clusters,
    collect_similarity_pairs,
    merge_candidate_clusters,
)
from .state import ClusterInput, SkillPrerequisiteState

logger = logging.getLogger(__name__)

NAME_DEDUP_THRESHOLD = 0.78
CONCEPT_DEDUP_THRESHOLD = 0.80
CLUSTER_THRESHOLD_LOW = 0.72
CLUSTER_THRESHOLD_HIGH = 0.90
CLUSTER_TOP_K = 10
CLUSTER_OVERLAP_THRESHOLD = 0.70


# ── LLM setup ──────────────────────────────────────────────────────────────


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=4096,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
    )


# ── Retry policy ────────────────────────────────────────────────────────────

RETRYABLE_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
    ConnectionError,
    TimeoutError,
)

api_retry_policy = RetryPolicy(
    initial_interval=5.0,
    backoff_factor=2.0,
    max_interval=60.0,
    max_attempts=3,
    retry_on=lambda exc: isinstance(exc, RETRYABLE_ERRORS),
)


# ── Union-Find ───────────────────────────────────────────────────────────────


def _make_union_find(items: list[str]) -> dict[str, str]:
    return {item: item for item in items}


def _find(parent: dict[str, str], x: str) -> str:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict[str, str], a: str, b: str) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[rb] = ra


def _build_groups(parent: dict[str, str]) -> list[list[str]]:
    from collections import defaultdict

    buckets: dict[str, list[str]] = defaultdict(list)
    for item in parent:
        buckets[_find(parent, item)].append(item)
    return [v for v in buckets.values() if len(v) > 1]


# ── Graph nodes ─────────────────────────────────────────────────────────────


def embed_missing(state: SkillPrerequisiteState) -> dict:
    write = get_stream_writer()
    driver = create_neo4j_driver()
    if driver is None:
        return {}

    skills = load_skills_without_embeddings(driver, state["course_id"])
    if not skills:
        driver.close()
        return {}

    names = [s["name"] for s in skills]
    embeddings = EmbeddingService().embed_documents(names)
    rows = [
        {"name": name, "embedding": emb}
        for name, emb in zip(names, embeddings, strict=True)
    ]
    write_skill_embeddings(driver, rows)
    driver.close()

    write(
        {"type": "prerequisite_progress", "phase": "embedding", "embedded": len(rows)}
    )
    return {}


def find_and_merge_dupes(state: SkillPrerequisiteState) -> dict:
    """Sequential dedup: find groups, LLM-judge each, merge confirmed dupes."""
    write = get_stream_writer()
    driver = create_neo4j_driver()
    if driver is None:
        return {"merged_skill_names": []}

    skills = load_all_skills_for_course(driver, state["course_id"])
    if not skills:
        driver.close()
        return {"merged_skill_names": []}

    skill_by_name = {s["name"]: s for s in skills}
    parent = _make_union_find(list(skill_by_name))

    name_skill_names, name_sim_matrix = build_name_similarity_index(skills)
    name_candidate_pairs = collect_similarity_pairs(
        name_skill_names,
        name_sim_matrix,
        threshold_low=NAME_DEDUP_THRESHOLD,
        threshold_high=1.01,
    )
    for first, second in name_candidate_pairs:
        _union(parent, first, second)

    concept_skill_names, concept_sim_matrix = build_concept_similarity_index(skills)
    concept_candidate_pairs = collect_similarity_pairs(
        concept_skill_names,
        concept_sim_matrix,
        threshold_low=CONCEPT_DEDUP_THRESHOLD,
        threshold_high=1.01,
    )
    for first, second in concept_candidate_pairs:
        _union(parent, first, second)

    union_candidate_pairs = name_candidate_pairs | concept_candidate_pairs
    groups = _build_groups(parent)
    logger.info(
        (
            "Course %d dedup candidate pairs: name=%d concept=%d union=%d "
            "candidate_groups=%d"
        ),
        state["course_id"],
        len(name_candidate_pairs),
        len(concept_candidate_pairs),
        len(union_candidate_pairs),
        len(groups),
    )

    llm = _build_llm().with_structured_output(DupeGroupVerdict, method="json_mode")
    merged_names: set[str] = set()
    groups_judged = 0

    for group_names in groups:
        group_skills = [skill_by_name[n] for n in group_names if n in skill_by_name]
        if len(group_skills) < 2:
            continue
        groups_judged += 1

        skills_json = json.dumps(
            [
                {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "chapter": s.get("chapter_title", ""),
                    "concepts": s.get("concepts", []),
                }
                for s in group_skills
            ],
            ensure_ascii=False,
            indent=2,
        )
        try:
            verdict: DupeGroupVerdict = llm.invoke(
                DUPE_JUDGE_PROMPT.format(skills_json=skills_json)
            )
            if (
                verdict.are_duplicates
                and verdict.canonical_name
                and verdict.skill_names_to_merge
            ):
                if verdict.canonical_name not in skill_by_name:
                    logger.warning(
                        "Dupe judge returned unknown canonical skill '%s' for course %d",
                        verdict.canonical_name,
                        state["course_id"],
                    )
                    continue
                names_to_merge = [
                    name
                    for name in verdict.skill_names_to_merge
                    if name != verdict.canonical_name and name in skill_by_name
                ]
                if not names_to_merge:
                    continue
                merge_skill_into_canonical(
                    driver,
                    verdict.canonical_name,
                    names_to_merge,
                )
                merged_names.update(names_to_merge)
        except Exception:
            logger.warning("Dupe judgment failed for a group — skipping", exc_info=True)

    driver.close()
    logger.info(
        "Course %d dedup judged %d groups and merged %d skills",
        state["course_id"],
        groups_judged,
        len(merged_names),
    )

    write(
        {
            "type": "prerequisite_progress",
            "phase": "dedup",
            "merged": len(merged_names),
        }
    )
    return {"merged_skill_names": sorted(merged_names)}


def load_skills_for_clustering(state: SkillPrerequisiteState) -> dict:
    """Regular node: reload skills from Neo4j post-merge and store in state."""
    driver = create_neo4j_driver()
    if driver is None:
        return {"_clusterable_skills": []}

    skills = load_all_skills_for_course(driver, state["course_id"])
    driver.close()

    merged = set(state.get("merged_skill_names", []))
    skills = [s for s in skills if s["name"] not in merged]

    # Store in a temporary state key via a side-channel — we pass via state update
    # but ClusterInput will receive individual clusters in the fan-out below.
    # We use a private key to communicate to build_cluster_fanout.
    return {"_clusterable_skills": skills}


def build_cluster_fanout(state: SkillPrerequisiteState) -> list[Send]:
    """Conditional edge function: build clusters and fan out to judge_cluster."""
    skills = state.get("_clusterable_skills", [])  # type: ignore[typeddict-item]
    if not skills:
        driver = create_neo4j_driver()
        if driver is None:
            return []
        skills = load_all_skills_for_course(driver, state["course_id"])
        driver.close()
        merged = set(state.get("merged_skill_names", []))
        skills = [s for s in skills if s["name"] not in merged]

    skill_by_name = {s["name"]: s for s in skills}
    name_skill_names, name_sim_matrix = build_name_similarity_index(skills)
    neighbors = build_neighbor_adjacency(
        name_skill_names,
        name_sim_matrix,
        threshold_low=CLUSTER_THRESHOLD_LOW,
        threshold_high=CLUSTER_THRESHOLD_HIGH,
        top_k=CLUSTER_TOP_K,
    )
    raw_clusters = build_raw_clusters(neighbors)
    final_clusters = [
        cluster
        for cluster in merge_candidate_clusters(
            raw_clusters,
            overlap_threshold=CLUSTER_OVERLAP_THRESHOLD,
        )
        if len(cluster) >= 2
    ]

    sends = []
    for cluster_names in final_clusters:
        cluster_skills = [skill_by_name[n] for n in cluster_names if n in skill_by_name]
        if len(cluster_skills) < 2:
            continue
        sends.append(
            Send(
                "judge_cluster",
                ClusterInput(cluster=cluster_skills, prereq_edges=[]),
            )
        )

    logger.info(
        "Course %d built %d raw clusters and %d final clusters for prerequisite judgment",
        state["course_id"],
        len(raw_clusters),
        len(sends),
    )
    return sends


def judge_cluster(state: ClusterInput) -> dict:
    llm = _build_llm().with_structured_output(
        ClusterPrerequisiteResult, method="json_mode"
    )
    cluster = sorted(state["cluster"], key=lambda s: s.get("chapter_index", 0))

    skills_json = json.dumps(
        [
            {
                "name": s["name"],
                "description": s.get("description", ""),
                "chapter_title": s.get("chapter_title", ""),
                "chapter_index": s.get("chapter_index", 0),
                "concepts": s.get("concepts", []),
            }
            for s in cluster
        ],
        ensure_ascii=False,
        indent=2,
    )

    prompt = CLUSTER_PREREQ_PROMPT.format(skills_json=skills_json)
    result: ClusterPrerequisiteResult = llm.invoke(prompt)
    return {"prereq_edges": [e.model_dump() for e in result.edges]}


def synthesize(state: SkillPrerequisiteState) -> dict:
    """Dedup accumulated edges — keep highest confidence per (prereq, dependent) pair."""
    _confidence_rank = {"high": 2, "medium": 1, "low": 0}
    best: dict[tuple[str, str], dict] = {}

    for edge in state.get("prereq_edges", []):
        key = (edge["prerequisite_skill"], edge["dependent_skill"])
        existing = best.get(key)
        if existing is None or _confidence_rank.get(
            edge["confidence"], -1
        ) > _confidence_rank.get(existing["confidence"], -1):
            best[key] = edge

    # Write to final_edges to avoid double-adding via the operator.add reducer on prereq_edges
    return {"final_edges": list(best.values())}


def enforce_dag(state: SkillPrerequisiteState) -> dict:
    """Filter to high/medium, detect cycles via Kahn's, apply transitive reduction."""
    _confidence_rank = {"high": 2, "medium": 1, "low": 0}

    edges = [
        e
        for e in state.get("final_edges", [])
        if e.get("confidence") in ("high", "medium")
    ]

    # ── Cycle removal via Kahn's ────────────────────────────────────────────

    def _remove_cycles(edge_list: list[dict]) -> list[dict]:
        for _ in range(len(edge_list) + 1):
            nodes: set[str] = set()
            for e in edge_list:
                nodes.add(e["prerequisite_skill"])
                nodes.add(e["dependent_skill"])

            in_degree: dict[str, int] = {n: 0 for n in nodes}
            for e in edge_list:
                in_degree[e["dependent_skill"]] += 1

            queue = [n for n, d in in_degree.items() if d == 0]
            visited: set[str] = set()
            while queue:
                node = queue.pop()
                visited.add(node)
                for e in edge_list:
                    if e["prerequisite_skill"] == node:
                        in_degree[e["dependent_skill"]] -= 1
                        if in_degree[e["dependent_skill"]] == 0:
                            queue.append(e["dependent_skill"])

            cycle_nodes = nodes - visited
            if not cycle_nodes:
                break

            # Remove the lowest-confidence edge involving cycle nodes
            cycle_edges = [
                e
                for e in edge_list
                if e["prerequisite_skill"] in cycle_nodes
                or e["dependent_skill"] in cycle_nodes
            ]
            if not cycle_edges:
                break
            worst = min(
                cycle_edges, key=lambda e: _confidence_rank.get(e["confidence"], -1)
            )
            edge_list = [e for e in edge_list if e is not worst]

        return edge_list

    edges = _remove_cycles(edges)

    # ── Transitive reduction ────────────────────────────────────────────────

    def _reachable_without(src: str, dst: str, edge_list: list[dict]) -> bool:
        """Return True if dst is reachable from src without using the direct edge src→dst."""
        adj: dict[str, list[str]] = {}
        for e in edge_list:
            if e["prerequisite_skill"] == src and e["dependent_skill"] == dst:
                continue
            adj.setdefault(e["prerequisite_skill"], []).append(e["dependent_skill"])

        visited: set[str] = set()
        stack = [src]
        while stack:
            node = stack.pop()
            if node == dst:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adj.get(node, []))
        return False

    reduced: list[dict] = []
    for edge in edges:
        if not _reachable_without(
            edge["prerequisite_skill"], edge["dependent_skill"], edges
        ):
            reduced.append(edge)

    return {"final_edges": reduced}


def persist(state: SkillPrerequisiteState) -> dict:
    write = get_stream_writer()
    driver = create_neo4j_driver()
    if driver is None:
        return {}

    final_edges = state.get("final_edges", [])
    normalized = [
        {
            "prereq_name": e["prerequisite_skill"],
            "dependent_name": e["dependent_skill"],
            "confidence": e["confidence"],
            "reasoning": e["reasoning"],
        }
        for e in final_edges
    ]

    clear_skill_prerequisites(driver, state["course_id"])
    written = write_skill_prerequisites(driver, normalized)
    driver.close()

    write({"type": "prerequisite_completed", "edges_written": written})
    logger.info("Course %d: wrote %d PREREQUISITE edges.", state["course_id"], written)
    return {}
