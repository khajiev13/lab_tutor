"""K-Means clustering with Elbow + Silhouette optimal-K selection."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


@dataclass
class ClusteringResult:
    k_optimal: int
    labels: np.ndarray
    centroids: np.ndarray
    silhouette: float
    k_range: list[int]
    wcss_values: list[float]
    sil_values: list[float]
    k_elbow: int


def find_optimal_k(
    embeddings: np.ndarray,
    k_min: int | None = None,
    k_max: int | None = None,
    random_state: int = 42,
) -> ClusteringResult:
    """Run K-Means over a range and pick K* via Elbow + Silhouette."""
    n = embeddings.shape[0]
    if k_min is None:
        k_min = max(2, math.floor(math.sqrt(n / 2)))
    if k_max is None:
        k_max = min(n - 1, math.ceil(2 * math.sqrt(n)))
    k_range = list(range(k_min, k_max + 1))

    wcss_values: list[float] = []
    sil_values: list[float] = []
    all_labels = {}
    all_centroids = {}

    for k in k_range:
        km = KMeans(n_clusters=k, random_state=random_state, n_init="auto")
        km.fit(embeddings)
        wcss_values.append(float(km.inertia_))
        all_labels[k] = km.labels_
        all_centroids[k] = km.cluster_centers_
        sil = silhouette_score(embeddings, km.labels_)
        sil_values.append(float(sil))

    # Elbow via second derivative
    if len(wcss_values) > 2:
        deltas = [
            wcss_values[i] - wcss_values[i + 1] for i in range(len(wcss_values) - 1)
        ]
        delta2 = [deltas[i] - deltas[i + 1] for i in range(len(deltas) - 1)]
        k_elbow = k_range[int(np.argmax(delta2)) + 1]
    else:
        k_elbow = k_range[0]

    # Silhouette refinement in neighbourhood
    window = [k for k in range(max(k_min, k_elbow - 2), min(k_max, k_elbow + 2) + 1)]
    best_k, best_sil = k_elbow, -1.0
    for k in window:
        idx = k_range.index(k)
        if sil_values[idx] > best_sil:
            best_sil = sil_values[idx]
            best_k = k

    return ClusteringResult(
        k_optimal=best_k,
        labels=all_labels[best_k],
        centroids=all_centroids[best_k],
        silhouette=best_sil,
        k_range=k_range,
        wcss_values=wcss_values,
        sil_values=sil_values,
        k_elbow=k_elbow,
    )
