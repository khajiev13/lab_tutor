"""
src/evaluation/pathgen_eval.py — PathGen algorithm variants and evaluation metrics.

Extracted from scripts/eval_pathgen.py so that the algorithms are importable
as a library rather than only runnable as a script.

Contains:
    topological_order           — Kahn's algorithm for curriculum ordering
    pathgen                     — PathGen v1: original greedy algorithm (Algorithm 2)
    pathgen_v2                  — PathGen v2: beam search + adaptive weights + unlock potential
    pathgen_v2_with_explanations — v2 + per-step natural language rationale
    random_path                 — Baseline: uniform random selection
    sequential_path             — Baseline: topological curriculum order
    lowest_first_path           — Baseline: greedy lowest-mastery selection
    evaluate_path               — Multi-metric path evaluation (5 metrics)
"""

from __future__ import annotations

from collections import deque

import numpy as np

# ── Graph utilities ───────────────────────────────────────────────────


def topological_order(A: np.ndarray) -> list[int]:
    """Kahn's algorithm: return skills in topological (curriculum) order.

    Args:
        A: Prerequisite adjacency matrix (n × n). A[i,j] > 0 means i is a
           prerequisite of j.

    Returns:
        List of skill indices in topological order (prerequisites first).
    """
    n = A.shape[0]
    indeg = (A > 0).sum(axis=0).astype(int)
    q: deque[int] = deque(i for i in range(n) if indeg[i] == 0)
    order: list[int] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in range(n):
            if A[u, v] > 0:
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    if len(order) < n:
        order.extend(i for i in range(n) if i not in order)
    return order


def _children_of(A: np.ndarray) -> dict[int, set[int]]:
    """Return dict mapping each skill to its direct downstream children."""
    S = A.shape[0]
    return {s: set(np.where(A[s, :] > 0)[0]) for s in range(S)}


def _parents_of(A: np.ndarray) -> dict[int, set[int]]:
    """Return dict mapping each skill to its prerequisite parents."""
    S = A.shape[0]
    return {s: set(np.where(A[:, s] > 0)[0]) for s in range(S)}


def _score_skill(s: int, m: np.ndarray, decay: np.ndarray,
                  parents: dict[int, set[int]],
                  w_zpd: float = 0.4, w_pre: float = 0.2,
                  w_dec: float = 0.3, w_base: float = 0.1) -> float:
    """Multi-component scoring for a single candidate skill."""
    z_s = 1.0 - abs(m[s] - 0.65) / 0.25
    p_s = np.mean([m[p] for p in parents[s]]) if parents[s] else 1.0
    d_s = 1.0 - decay[s]
    return w_zpd * z_s + w_pre * p_s + w_dec * d_s + w_base * 0.5


# ── PathGen v1 ────────────────────────────────────────────────────────


def pathgen(mastery: np.ndarray, decay: np.ndarray, A: np.ndarray,
             K: int = 8, zpd_lo: float = 0.40, zpd_hi: float = 0.90,
             tau_pre: float = 0.50) -> list[int]:
    """Algorithm 2 from the ARCD paper: ZPD-based learning path generation.

    Args:
        mastery:  Per-skill mastery vector in [0, 1].
        decay:    Per-skill retention decay in [0, 1] (1 = full retention).
        A:        Prerequisite adjacency matrix.
        K:        Maximum path length.
        zpd_lo:   Lower ZPD mastery bound.
        zpd_hi:   Upper ZPD mastery bound.
        tau_pre:  Minimum prerequisite mastery threshold.

    Returns:
        Ordered list of skill indices.
    """
    S = len(mastery)
    parents = _parents_of(A)
    m = mastery.copy()
    path: list[int] = []

    for _ in range(K):
        candidates = [s for s in range(S) if s not in path
                       and all(m[p] >= tau_pre for p in parents[s])]
        if not candidates:
            break

        zpd_cands = [s for s in candidates if zpd_lo <= m[s] <= zpd_hi]
        if not zpd_cands:
            zpd_cands = [s for s in candidates if 0.25 <= m[s] <= 0.95]
        if not zpd_cands:
            break

        best_s, best_score = -1, -1e9
        for s in zpd_cands:
            score = _score_skill(s, m, decay, parents)
            if score > best_score:
                best_score = score
                best_s = s
        if best_s < 0:
            break

        path.append(best_s)
        m[best_s] = min(1.0, m[best_s] + 0.10)

    return path


# ── PathGen v2 ────────────────────────────────────────────────────────


def _adaptive_weights(mastery: np.ndarray,
                       decay: np.ndarray) -> tuple[float, float, float, float]:
    """Compute per-student scoring weights from their mastery profile.

    Students with severe forgetting get higher decay weight;
    students with many low-mastery skills get higher prerequisite weight.
    """
    avg_decay = np.mean(decay)
    low_mastery_frac = np.mean(mastery < 0.40)

    w_zpd = 0.35
    w_dec = 0.25 + 0.15 * (1.0 - avg_decay)
    w_pre = 0.15 + 0.10 * low_mastery_frac
    w_base = max(0.05, 1.0 - w_zpd - w_dec - w_pre)
    return w_zpd, w_pre, w_dec, w_base


def _unlock_potential(s: int, m: np.ndarray, A: np.ndarray,
                       children: dict[int, set[int]],
                       tau_pre: float = 0.50, gain: float = 0.10) -> int:
    """Count downstream skills that become prerequisite-ready if s is mastered."""
    parents = _parents_of(A)
    simulated = m.copy()
    simulated[s] = min(1.0, simulated[s] + gain)
    unlocked = 0
    for c in children.get(s, set()):
        was_blocked = any(m[p] < tau_pre for p in parents[c])
        now_ready = all(simulated[p] >= tau_pre for p in parents[c])
        if was_blocked and now_ready:
            unlocked += 1
    return unlocked


def pathgen_v2(mastery: np.ndarray, decay: np.ndarray, A: np.ndarray,
               K: int = 8, zpd_lo: float = 0.40, zpd_hi: float = 0.90,
               tau_pre: float = 0.50, beam_width: int = 3,
               time_per_skill: np.ndarray | None = None,
               time_budget: float | None = None) -> list[int]:
    """Enhanced PathGen with beam search, adaptive weights, time budget, and unlock scoring.

    Args:
        beam_width:     Number of candidate paths to maintain at each step.
        time_per_skill: Optional per-skill estimated learning time array.
        time_budget:    Optional maximum total time for the path.

    Returns:
        Ordered list of skill indices (best beam path).
    """
    S = len(mastery)
    parents = _parents_of(A)
    children = _children_of(A)
    w_zpd, w_pre, w_dec, w_base = _adaptive_weights(mastery, decay)

    beams: list[tuple[list[int], np.ndarray, float, float]] = [
        ([], mastery.copy(), 0.0, 0.0)
    ]

    for _ in range(K):
        all_expansions = []

        for path, m, total_time, cum_score in beams:
            candidates = [s for s in range(S) if s not in path
                           and all(m[p] >= tau_pre for p in parents[s])]
            if not candidates:
                all_expansions.append((path, m, total_time, cum_score))
                continue

            zpd_cands = [s for s in candidates if zpd_lo <= m[s] <= zpd_hi]
            if not zpd_cands:
                zpd_cands = [s for s in candidates if 0.25 <= m[s] <= 0.95]
            if not zpd_cands:
                all_expansions.append((path, m, total_time, cum_score))
                continue

            for s in zpd_cands:
                skill_time = float(time_per_skill[s]) if time_per_skill is not None else 0.0
                if time_budget is not None and (total_time + skill_time) > time_budget:
                    continue

                base_score = _score_skill(s, m, decay, parents, w_zpd, w_pre, w_dec, w_base)
                unlock_bonus = 0.1 * _unlock_potential(s, m, A, children, tau_pre)
                step_score = base_score + unlock_bonus

                new_m = m.copy()
                new_m[s] = min(1.0, new_m[s] + 0.10)
                all_expansions.append(
                    (path + [s], new_m, total_time + skill_time, cum_score + step_score)
                )

        if not all_expansions:
            break

        all_expansions.sort(key=lambda x: x[3], reverse=True)
        beams = all_expansions[:beam_width]

    return max(beams, key=lambda x: x[3])[0] if beams else []


def pathgen_v2_with_explanations(mastery: np.ndarray, decay: np.ndarray,
                                   A: np.ndarray, skill_names: list[str] | None = None,
                                   K: int = 8, zpd_lo: float = 0.40, zpd_hi: float = 0.90,
                                   tau_pre: float = 0.50, beam_width: int = 3,
                                   time_per_skill: np.ndarray | None = None,
                                   time_budget: float | None = None
                                   ) -> tuple[list[int], list[dict]]:
    """PathGen v2 that also returns per-step natural language explanations.

    Returns:
        Tuple of ``(path, explanations)`` where each explanation is a dict with
        ``skill_id``, ``skill_name``, ``mastery_before``, and ``why``.
    """
    parents = _parents_of(A)
    children = _children_of(A)

    path = pathgen_v2(mastery, decay, A, K, zpd_lo, zpd_hi, tau_pre,
                      beam_width, time_per_skill, time_budget)

    explanations: list[dict] = []
    m_sim = mastery.copy()
    for s in path:
        name = skill_names[s] if skill_names and s < len(skill_names) else f"Skill {s}"
        reasons = []

        prereqs = parents[s]
        if prereqs:
            avg_pre = np.mean([m_sim[p] for p in prereqs])
            reasons.append(f"prerequisites are ready (avg mastery {avg_pre:.0%})")
        else:
            reasons.append("no prerequisites needed")

        reasons.append(f"current mastery {m_sim[s]:.0%} is in your ZPD")

        if decay[s] < 0.70:
            reasons.append(f"retention has decayed to {decay[s]:.0%} — urgent review")

        n_unlock = _unlock_potential(s, m_sim, A, children, tau_pre)
        if n_unlock > 0:
            reasons.append(f"mastering this unlocks {n_unlock} downstream skill(s)")

        explanations.append({
            "skill_id": int(s),
            "skill_name": name,
            "mastery_before": round(float(m_sim[s]), 3),
            "why": f"Recommended because: {'; '.join(reasons)}.",
        })
        m_sim[s] = min(1.0, m_sim[s] + 0.10)

    return path, explanations


# ── Baselines ─────────────────────────────────────────────────────────


def random_path(mastery: np.ndarray, decay: np.ndarray, A: np.ndarray,
                K: int = 8, rng: np.random.Generator | None = None) -> list[int]:
    """Baseline 1: uniform random skill selection."""
    S = len(mastery)
    if rng is None:
        rng = np.random.default_rng()
    chosen = rng.choice(S, size=min(K, S), replace=False)
    return list(chosen)


def sequential_path(mastery: np.ndarray, decay: np.ndarray, A: np.ndarray,
                     K: int = 8) -> list[int]:
    """Baseline 2: curriculum order (topological sort)."""
    return topological_order(A)[:K]


def lowest_first_path(mastery: np.ndarray, decay: np.ndarray, A: np.ndarray,
                       K: int = 8) -> list[int]:
    """Baseline 3: greedily pick the lowest-mastery skills."""
    return list(np.argsort(mastery)[:K])


# ── Evaluation ────────────────────────────────────────────────────────


def evaluate_path(path: list[int], mastery: np.ndarray, decay: np.ndarray,
                   A: np.ndarray, zpd_lo: float = 0.40, zpd_hi: float = 0.90,
                   tau_pre: float = 0.50,
                   rng: np.random.Generator | None = None) -> dict:
    """Compute five evaluation metrics for a learning path.

    Metrics:
        zpd_align:  Fraction of steps within ZPD [zpd_lo, zpd_hi].
        prereq_sat: Fraction of steps where all prerequisites ≥ tau_pre.
        proj_gain:  Total projected mastery gain (stochastic).
        decay_cov:  Fraction of high-decay skills (decay < 0.70) covered.
        unlock_pot: Total downstream skills unlocked by the path.

    Args:
        path:   Ordered list of skill indices.
        mastery, decay, A: Student/graph state.
        rng:    Optional RNG for reproducible stochastic gain simulation.

    Returns:
        Dict with keys ``zpd_align``, ``prereq_sat``, ``proj_gain``,
        ``decay_cov``, ``unlock_pot``.
    """
    if len(path) == 0:
        return {"zpd_align": 0.0, "prereq_sat": 0.0, "proj_gain": 0.0,
                "decay_cov": 0.0, "unlock_pot": 0}

    if rng is None:
        rng = np.random.default_rng()

    parents = _parents_of(A)
    children = _children_of(A)

    zpd_count = sum(1 for s in path if zpd_lo <= mastery[s] <= zpd_hi)
    prereq_ok = sum(1 for s in path if all(mastery[p] >= tau_pre for p in parents[s]))

    proj_gain = 0.0
    m_sim = mastery.copy()
    total_unlocks = 0
    for s in path:
        zpd_center = 0.65
        zpd_factor = max(0.3, 1.0 - abs(m_sim[s] - zpd_center) / 0.40)
        noise = rng.normal(0, 0.02)
        step_gain = max(0.0, min(1.0 - m_sim[s], 0.10 * zpd_factor + noise))
        proj_gain += step_gain
        total_unlocks += _unlock_potential(s, m_sim, A, children, tau_pre)
        m_sim[s] = min(1.0, m_sim[s] + step_gain)

    high_decay = set(np.where(decay < 0.70)[0])
    decay_cov = (len(set(path) & high_decay) / max(len(high_decay), 1)
                 if high_decay else 1.0)

    return {
        "zpd_align":  zpd_count / len(path),
        "prereq_sat": prereq_ok / len(path),
        "proj_gain":  proj_gain,
        "decay_cov":  decay_cov,
        "unlock_pot": total_unlocks,
    }
