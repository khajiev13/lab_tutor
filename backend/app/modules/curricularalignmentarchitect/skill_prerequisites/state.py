from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class SkillPrerequisiteState(TypedDict):
    course_id: int
    merged_skill_names: list[str]
    prereq_edges: Annotated[
        list[dict], operator.add
    ]  # fan-in accumulator from judge_cluster
    final_edges: list[dict]  # after dedup + DAG enforcement
    _clusterable_skills: list[dict]  # temp storage for build_cluster_fanout


class ClusterInput(TypedDict):
    cluster: list[dict]
    prereq_edges: Annotated[list[dict], operator.add]
