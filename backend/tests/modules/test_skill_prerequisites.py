from __future__ import annotations

import numpy as np

from app.modules.curricularalignmentarchitect.skill_prerequisites import nodes
from app.modules.curricularalignmentarchitect.skill_prerequisites.prompts import (
    CLUSTER_PREREQ_PROMPT,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.schemas import (
    DupeGroupVerdict,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.similarity import (
    build_concept_similarity_index,
    build_name_similarity_index,
    build_neighbor_adjacency,
    build_raw_clusters,
    collect_similarity_pairs,
    merge_candidate_clusters,
    normalize_concepts,
)


class FakeDriver:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeStructuredLLM:
    def __init__(self, verdicts: list[DupeGroupVerdict]):
        self._verdicts = list(verdicts)

    def with_structured_output(self, *_args, **_kwargs):
        return self

    def invoke(self, _prompt):
        return self._verdicts.pop(0)


def _base_state() -> dict:
    return {
        "course_id": 2,
        "merged_skill_names": [],
        "prereq_edges": [],
        "final_edges": [],
        "_clusterable_skills": [],
    }


def test_normalize_concepts_lowercases_strips_and_deduplicates():
    assert normalize_concepts([" SQL ", "sql", " Joins", "", "JOINS "]) == [
        "sql",
        "joins",
    ]


def test_name_similarity_candidates_and_zero_vectors_are_safe():
    skills = [
        {"name": "A", "name_embedding": [0.0, 0.0]},
        {"name": "B", "name_embedding": [1.0, 0.0]},
        {"name": "C", "name_embedding": None},
    ]

    names, sim_matrix = build_name_similarity_index(skills)

    assert names == ["A", "B"]
    assert sim_matrix.shape == (2, 2)
    assert np.isfinite(sim_matrix).all()
    assert collect_similarity_pairs(
        names,
        sim_matrix,
        threshold_low=0.0,
        threshold_high=1.01,
    ) == {("A", "B")}


def test_concept_similarity_candidates_use_normalized_multi_hot_cosine():
    skills = [
        {"name": "A", "concepts": [" SQL ", "JOINS"]},
        {"name": "B", "concepts": ["sql", "joins"]},
        {"name": "C", "concepts": ["spark"]},
        {"name": "D", "concepts": []},
    ]

    names, sim_matrix = build_concept_similarity_index(skills)
    pairs = collect_similarity_pairs(
        names,
        sim_matrix,
        threshold_low=0.80,
        threshold_high=1.01,
    )

    assert set(names) == {"A", "B", "C"}
    assert pairs == {("A", "B")}


def test_merge_candidate_clusters_drops_subsets_and_merges_high_overlap():
    subset = frozenset({"a", "b", "c"})
    base = frozenset({"a", "b", "c", "d", "e", "f", "g", "h", "i", "j"})
    overlap = frozenset({"a", "b", "c", "d", "e", "f", "g", "h", "i", "k"})

    merged = merge_candidate_clusters(
        [subset, base, overlap],
        overlap_threshold=0.70,
    )

    assert subset not in merged
    assert merged == [base | overlap]


def test_find_and_merge_dupes_merges_concept_only_candidates(monkeypatch):
    events: list[dict] = []
    merge_calls: list[tuple[str, list[str]]] = []
    skills = [
        {
            "name": "Model SQL joins",
            "description": "Learn SQL joins.",
            "chapter_title": "Chapter 1",
            "concepts": [" SQL ", "JOINS"],
            "name_embedding": None,
        },
        {
            "name": "Explain SQL joins",
            "description": "Explain how joins work.",
            "chapter_title": "Chapter 2",
            "concepts": ["sql", "joins"],
            "name_embedding": None,
        },
        {
            "name": "Use pandas",
            "description": "Use pandas dataframes.",
            "chapter_title": "Chapter 3",
            "concepts": ["dataframe"],
            "name_embedding": [1.0, 0.0],
        },
    ]

    monkeypatch.setattr(nodes, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(nodes, "create_neo4j_driver", lambda: FakeDriver())
    monkeypatch.setattr(
        nodes, "load_all_skills_for_course", lambda _driver, _course_id: skills
    )
    monkeypatch.setattr(
        nodes,
        "merge_skill_into_canonical",
        lambda _driver, canonical, dupes: merge_calls.append(
            (canonical, sorted(dupes))
        ),
    )
    monkeypatch.setattr(
        nodes,
        "_build_llm",
        lambda: FakeStructuredLLM(
            [
                DupeGroupVerdict(
                    are_duplicates=True,
                    canonical_name="Model SQL joins",
                    skill_names_to_merge=["Explain SQL joins"],
                    reasoning="Same skill with different phrasing.",
                )
            ]
        ),
    )

    result = nodes.find_and_merge_dupes(_base_state())

    assert result["merged_skill_names"] == ["Explain SQL joins"]
    assert merge_calls == [("Model SQL joins", ["Explain SQL joins"])]
    assert events[-1] == {
        "type": "prerequisite_progress",
        "phase": "dedup",
        "merged": 1,
    }


def test_find_and_merge_dupes_unions_name_and_concept_candidates_transitively(
    monkeypatch,
):
    merge_calls: list[tuple[str, list[str]]] = []
    skills = [
        {
            "name": "SQL joins basics",
            "description": "Join fundamentals.",
            "chapter_title": "Chapter 1",
            "concepts": ["joins", "filters"],
            "name_embedding": [1.0, 0.0],
        },
        {
            "name": "Intro to SQL joins",
            "description": "Intro joins.",
            "chapter_title": "Chapter 2",
            "concepts": ["sql", "joins"],
            "name_embedding": [0.8, 0.6],
        },
        {
            "name": "Explain SQL joins",
            "description": "Explain joins.",
            "chapter_title": "Chapter 3",
            "concepts": [" SQL ", "JOINS"],
            "name_embedding": [0.0, 1.0],
        },
    ]

    monkeypatch.setattr(nodes, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(nodes, "create_neo4j_driver", lambda: FakeDriver())
    monkeypatch.setattr(
        nodes, "load_all_skills_for_course", lambda _driver, _course_id: skills
    )
    monkeypatch.setattr(
        nodes,
        "merge_skill_into_canonical",
        lambda _driver, canonical, dupes: merge_calls.append(
            (canonical, sorted(dupes))
        ),
    )
    monkeypatch.setattr(
        nodes,
        "_build_llm",
        lambda: FakeStructuredLLM(
            [
                DupeGroupVerdict(
                    are_duplicates=True,
                    canonical_name="SQL joins basics",
                    skill_names_to_merge=[
                        "Intro to SQL joins",
                        "Explain SQL joins",
                    ],
                    reasoning="Transitive duplicate group.",
                )
            ]
        ),
    )

    result = nodes.find_and_merge_dupes(_base_state())

    assert result["merged_skill_names"] == [
        "Explain SQL joins",
        "Intro to SQL joins",
    ]
    assert merge_calls == [
        (
            "SQL joins basics",
            ["Explain SQL joins", "Intro to SQL joins"],
        )
    ]


def test_find_and_merge_dupes_skips_negative_llm_verdict(monkeypatch):
    merge_calls: list[tuple[str, list[str]]] = []
    skills = [
        {
            "name": "Use SQL joins",
            "description": "Use joins.",
            "chapter_title": "Chapter 1",
            "concepts": ["sql", "joins"],
            "name_embedding": [1.0, 0.0],
        },
        {
            "name": "Use relational joins",
            "description": "Use relational joins.",
            "chapter_title": "Chapter 2",
            "concepts": ["joins", "relational"],
            "name_embedding": [0.8, 0.6],
        },
    ]

    monkeypatch.setattr(nodes, "get_stream_writer", lambda: lambda _event: None)
    monkeypatch.setattr(nodes, "create_neo4j_driver", lambda: FakeDriver())
    monkeypatch.setattr(
        nodes, "load_all_skills_for_course", lambda _driver, _course_id: skills
    )
    monkeypatch.setattr(
        nodes,
        "merge_skill_into_canonical",
        lambda _driver, canonical, dupes: merge_calls.append(
            (canonical, sorted(dupes))
        ),
    )
    monkeypatch.setattr(
        nodes,
        "_build_llm",
        lambda: FakeStructuredLLM(
            [
                DupeGroupVerdict(
                    are_duplicates=False,
                    canonical_name=None,
                    skill_names_to_merge=[],
                    reasoning="Related but not duplicates.",
                )
            ]
        ),
    )

    result = nodes.find_and_merge_dupes(_base_state())

    assert result["merged_skill_names"] == []
    assert merge_calls == []


def test_build_cluster_fanout_uses_in_memory_name_cosine_neighbors():
    skills = [
        {
            "name": "A",
            "description": "A",
            "chapter_title": "1",
            "chapter_index": 1,
            "concepts": [],
            "name_embedding": [1.0, 0.0, 0.0],
        },
        {
            "name": "B",
            "description": "B",
            "chapter_title": "2",
            "chapter_index": 2,
            "concepts": [],
            "name_embedding": [0.8, 0.6, 0.0],
        },
        {
            "name": "C",
            "description": "C",
            "chapter_title": "3",
            "chapter_index": 3,
            "concepts": [],
            "name_embedding": [0.8, 0.0, 0.6],
        },
    ]

    sends = nodes.build_cluster_fanout(
        {
            **_base_state(),
            "_clusterable_skills": skills,
        }
    )

    assert len(sends) == 1
    assert sends[0].node == "judge_cluster"
    assert {skill["name"] for skill in sends[0].arg["cluster"]} == {"A", "B", "C"}


def test_neighbor_helpers_build_expected_cluster_shape():
    skills = [
        {"name": "A", "name_embedding": [1.0, 0.0, 0.0]},
        {"name": "B", "name_embedding": [0.8, 0.6, 0.0]},
        {"name": "C", "name_embedding": [0.8, 0.0, 0.6]},
    ]

    names, sim_matrix = build_name_similarity_index(skills)
    neighbors = build_neighbor_adjacency(
        names,
        sim_matrix,
        threshold_low=0.72,
        threshold_high=0.90,
        top_k=10,
    )
    raw_clusters = build_raw_clusters(neighbors)

    assert neighbors == {
        "A": {"B", "C"},
        "B": {"A"},
        "C": {"A"},
    }
    assert raw_clusters == [
        frozenset({"A", "B", "C"}),
        frozenset({"A", "B"}),
        frozenset({"A", "C"}),
    ]


def test_cluster_prompt_includes_blocking_dependency_guardrails():
    assert "learner would be blocked without A" in CLUSTER_PREREQ_PROMPT
    assert "Do NOT emit edges for paraphrases" in CLUSTER_PREREQ_PROMPT
    assert "compare-vs-compare" in CLUSTER_PREREQ_PROMPT
    assert "broad tool-list vs specific-tool variants" in CLUSTER_PREREQ_PROMPT
    assert "taxonomy/classification and operational skills" in CLUSTER_PREREQ_PROMPT
