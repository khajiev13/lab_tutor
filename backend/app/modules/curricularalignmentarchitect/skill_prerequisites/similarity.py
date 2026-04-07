from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

Pair = tuple[str, str]


def normalize_concepts(concepts: Iterable[str] | None) -> list[str]:
    if not concepts:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for concept in concepts:
        token = concept.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def build_name_similarity_index(
    skills: Sequence[dict[str, Any]],
) -> tuple[list[str], np.ndarray]:
    names: list[str] = []
    embeddings: list[np.ndarray] = []

    for skill in skills:
        embedding = skill.get("name_embedding")
        if embedding is None:
            continue
        names.append(skill["name"])
        embeddings.append(np.asarray(embedding, dtype=np.float32))

    if not embeddings:
        return [], np.empty((0, 0), dtype=np.float32)

    matrix = np.vstack(embeddings)
    return names, _cosine_similarity_matrix(matrix)


def build_concept_similarity_index(
    skills: Sequence[dict[str, Any]],
) -> tuple[list[str], np.ndarray]:
    concept_map = {
        skill["name"]: normalize_concepts(skill.get("concepts")) for skill in skills
    }
    concept_names = sorted(
        {concept for concepts in concept_map.values() for concept in concepts}
    )
    skill_names = [skill["name"] for skill in skills if concept_map[skill["name"]]]

    if not concept_names or not skill_names:
        return [], np.empty((0, 0), dtype=np.float32)

    concept_to_idx = {concept: index for index, concept in enumerate(concept_names)}
    matrix = np.zeros((len(skill_names), len(concept_names)), dtype=np.float32)

    for row_idx, skill_name in enumerate(skill_names):
        for concept in concept_map[skill_name]:
            matrix[row_idx, concept_to_idx[concept]] = 1.0

    return skill_names, _cosine_similarity_matrix(matrix)


def collect_similarity_pairs(
    names: Sequence[str],
    sim_matrix: np.ndarray,
    *,
    threshold_low: float,
    threshold_high: float,
    top_k: int | None = None,
) -> set[Pair]:
    pairs: set[Pair] = set()
    if sim_matrix.size == 0:
        return pairs

    for index, name in enumerate(names):
        for match_idx in _sorted_matches(
            sim_matrix[index],
            index,
            threshold_low=threshold_low,
            threshold_high=threshold_high,
            top_k=top_k,
        ):
            pairs.add(_stable_pair(name, names[match_idx]))

    return pairs


def build_neighbor_adjacency(
    names: Sequence[str],
    sim_matrix: np.ndarray,
    *,
    threshold_low: float,
    threshold_high: float,
    top_k: int | None = None,
) -> dict[str, set[str]]:
    neighbors = {name: set() for name in names}
    if sim_matrix.size == 0:
        return neighbors

    for index, name in enumerate(names):
        for match_idx in _sorted_matches(
            sim_matrix[index],
            index,
            threshold_low=threshold_low,
            threshold_high=threshold_high,
            top_k=top_k,
        ):
            other_name = names[match_idx]
            neighbors[name].add(other_name)
            neighbors[other_name].add(name)

    return neighbors


def build_raw_clusters(neighbors: dict[str, set[str]]) -> list[frozenset[str]]:
    return [
        frozenset({name} | matches) for name, matches in neighbors.items() if matches
    ]


def merge_candidate_clusters(
    raw_clusters: Sequence[frozenset[str]],
    *,
    overlap_threshold: float,
) -> list[frozenset[str]]:
    merged_clusters: list[frozenset[str]] = []

    for cluster in raw_clusters:
        absorbed = False
        new_merged: list[frozenset[str]] = []

        for existing in merged_clusters:
            if cluster <= existing:
                absorbed = True
                new_merged.append(existing)
            elif existing <= cluster:
                new_merged.append(cluster)
            elif _overlap(cluster, existing) > overlap_threshold:
                new_merged.append(cluster | existing)
                absorbed = True
            else:
                new_merged.append(existing)

        merged_clusters = new_merged
        if not absorbed:
            merged_clusters.append(cluster)

    deduped: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    for cluster in merged_clusters:
        if cluster in seen:
            continue
        seen.add(cluster)
        deduped.append(cluster)

    return deduped


def _cosine_similarity_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    normalized = matrix / norms
    return normalized @ normalized.T


def _sorted_matches(
    row: np.ndarray,
    self_index: int,
    *,
    threshold_low: float,
    threshold_high: float,
    top_k: int | None,
) -> list[int]:
    matches = [
        index
        for index in range(len(row))
        if index != self_index and threshold_low <= float(row[index]) < threshold_high
    ]
    matches.sort(key=lambda index: float(row[index]), reverse=True)
    return matches if top_k is None else matches[:top_k]


def _stable_pair(a: str, b: str) -> Pair:
    return (a, b) if a < b else (b, a)


def _overlap(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / max(len(a | b), 1)
