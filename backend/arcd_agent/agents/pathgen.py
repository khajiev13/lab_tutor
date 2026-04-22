"""
PathGen — Learning Path Generator.

Classes:
    PathGenConfig        — configuration for the path generator
    PrerequisiteFilter   — filter skills whose prerequisites are not met
    ZPDFilter            — keep only skills within the Zone of Proximal Development
    ScoringEngine        — multi-component skill scoring
    PathGenerator        — end-to-end greedy path construction pipeline
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np


@dataclass
class PathGenConfig:
    """Configuration for PathGenerator.

    Attributes:
        zpd_lo: lower mastery bound for ZPD (default 0.40).
        zpd_hi: upper mastery bound for ZPD (default 0.90).
        prereq_threshold: minimum mastery for a prerequisite to be considered satisfied.
        w_zpd: weight for zpd_proximity component.
        w_prereq: weight for prereq_strength component.
        w_decay: weight for decay_urgency component.
        w_momentum: weight for momentum component.
        path_length: maximum number of steps in the generated path.
        zpd_relax_band: how much to relax ZPD bounds if no skills are in-band.
    """

    zpd_lo: float = 0.40
    zpd_hi: float = 0.90
    prereq_threshold: float = 0.60
    w_zpd: float = 0.35
    w_prereq: float = 0.25
    w_decay: float = 0.25
    w_momentum: float = 0.15
    path_length: int = 8
    zpd_relax_band: float = 0.10


class PrerequisiteFilter:
    """Filter skills based on whether their prerequisites are sufficiently mastered.

    A skill is eligible if all skills that must precede it (according to the
    prerequisite adjacency) have mastery >= prereq_threshold.

    Args:
        A_pre: prerequisite adjacency matrix (n_skills × n_skills).
               A_pre[i, j] > 0 means skill i is a prerequisite of skill j.
        prereq_threshold: minimum mastery for a prerequisite to be satisfied.
    """

    def __init__(
        self,
        A_pre: np.ndarray | None = None,
        prereq_threshold: float = 0.60,
    ):
        self.A_pre = A_pre
        self.prereq_threshold = prereq_threshold

    def eligible(self, mastery: list[float]) -> list[int]:
        """Return skill IDs whose prerequisites are all satisfied."""
        n = len(mastery)
        if self.A_pre is None:
            return list(range(n))

        A = self.A_pre[:n, :n] if self.A_pre.shape[0] >= n else self.A_pre
        eligible = []
        for s in range(n):
            prereqs = np.where(A[:n, s] > 0)[0]
            if len(prereqs) == 0:
                eligible.append(s)
                continue
            satisfied = all(
                mastery[p] >= self.prereq_threshold for p in prereqs if p < len(mastery)
            )
            if satisfied:
                eligible.append(s)
        return eligible


class ZPDFilter:
    """Keep only skills within the Zone of Proximal Development.

    Skills with mastery in [zpd_lo, zpd_hi] are in ZPD. If no skills
    fall in the strict ZPD, the band is relaxed by zpd_relax_band.

    Args:
        zpd_lo: lower mastery bound.
        zpd_hi: upper mastery bound.
        zpd_relax_band: expansion applied when the strict band is empty.
    """

    def __init__(
        self,
        zpd_lo: float = 0.40,
        zpd_hi: float = 0.90,
        zpd_relax_band: float = 0.10,
    ):
        self.zpd_lo = zpd_lo
        self.zpd_hi = zpd_hi
        self.zpd_relax_band = zpd_relax_band

    def filter(self, candidates: list[int], mastery: list[float]) -> list[int]:
        """Filter candidates to those in ZPD; relax bounds if band is empty."""
        in_zpd = [s for s in candidates if self.zpd_lo <= mastery[s] <= self.zpd_hi]
        if in_zpd:
            return in_zpd
        # Relax and retry
        lo = max(0.0, self.zpd_lo - self.zpd_relax_band)
        hi = min(1.0, self.zpd_hi + self.zpd_relax_band)
        relaxed = [s for s in candidates if lo <= mastery[s] <= hi]
        return relaxed if relaxed else candidates


class ScoringEngine:
    """Multi-component skill scoring for path construction.

    Score(s) = w_zpd * zpd_proximity(s)
             + w_prereq * prereq_strength(s)
             + w_decay * decay_urgency(s)
             + w_momentum * momentum(s)

    Components:
        zpd_proximity:  how close mastery is to the optimal ZPD midpoint.
        prereq_strength: fraction of prerequisites that are satisfied.
        decay_urgency:  urgency derived from hours since last practice.
        momentum:       recency of practice (inverse of hours_since, capped).

    Args:
        w_zpd, w_prereq, w_decay, w_momentum: component weights.
        zpd_target: target mastery within ZPD for zpd_proximity.
        A_pre: prerequisite adjacency for prereq_strength.
        prereq_threshold: mastery threshold to count a prereq as satisfied.
    """

    def __init__(
        self,
        w_zpd: float = 0.35,
        w_prereq: float = 0.25,
        w_decay: float = 0.25,
        w_momentum: float = 0.15,
        zpd_target: float = 0.65,
        A_pre: np.ndarray | None = None,
        prereq_threshold: float = 0.60,
    ):
        self.w_zpd = w_zpd
        self.w_prereq = w_prereq
        self.w_decay = w_decay
        self.w_momentum = w_momentum
        self.zpd_target = zpd_target
        self.A_pre = A_pre
        self.prereq_threshold = prereq_threshold

    def score(
        self,
        skill_id: int,
        mastery: list[float],
        hours_since: dict[int, float],
        decay_vector: list[float] | None = None,
    ) -> dict[str, float]:
        """Compute the multi-component score for a single skill."""
        m = mastery[skill_id] if skill_id < len(mastery) else 0.0
        h = hours_since.get(skill_id, 0.0)

        # ZPD proximity: 1.0 when mastery == zpd_target, 0.0 when far from it
        zpd_prox = max(0.0, 1.0 - abs(m - self.zpd_target) / 0.5)

        # Prerequisite strength
        prereq_str = self._prereq_strength(skill_id, mastery)

        # Decay urgency
        d_val = (
            decay_vector[skill_id]
            if (decay_vector and skill_id < len(decay_vector))
            else None
        )
        if d_val is not None:
            decay_urg = 1.0 - float(d_val)
        else:
            decay_urg = 1.0 - math.exp(-0.01 * max(h, 0.0))

        # Momentum: scales up with recency (inverse hours, capped at 168h = 1 week)
        momentum = max(0.0, 1.0 - h / 168.0) if h < 168.0 else 0.0

        total = (
            self.w_zpd * zpd_prox
            + self.w_prereq * prereq_str
            + self.w_decay * decay_urg
            + self.w_momentum * momentum
        )

        return {
            "total": round(total, 4),
            "zpd_proximity": round(zpd_prox, 4),
            "prereq_strength": round(prereq_str, 4),
            "decay_urgency": round(decay_urg, 4),
            "momentum": round(momentum, 4),
        }

    def _prereq_strength(self, skill_id: int, mastery: list[float]) -> float:
        if self.A_pre is None:
            return 1.0
        n = len(mastery)
        A = self.A_pre[:n, :n] if self.A_pre.shape[0] >= n else self.A_pre
        prereqs = np.where(A[:n, skill_id] > 0)[0]
        if len(prereqs) == 0:
            return 1.0
        satisfied = sum(
            1
            for p in prereqs
            if p < len(mastery) and mastery[p] >= self.prereq_threshold
        )
        return satisfied / len(prereqs)


class PathGenerator:
    """End-to-end greedy learning path construction.

    Pipeline:
        1. PrerequisiteFilter → eligible candidates
        2. ZPDFilter         → in-ZPD subset
        3. ScoringEngine     → rank candidates
        4. Greedy selection  → pick top skill, update state, repeat

    Args:
        config: PathGenConfig instance.
        skill_names: dict mapping skill_id → human-readable name.
        A_pre: prerequisite adjacency matrix.
        decay_vector: optional per-skill current decay values.
    """

    def __init__(
        self,
        config: PathGenConfig | None = None,
        skill_names: dict[int, str] | None = None,
        A_pre: np.ndarray | None = None,
        decay_vector: list[float] | None = None,
    ):
        self.config = config or PathGenConfig()
        self.skill_names = skill_names or {}
        self.decay_vector = decay_vector

        self._prereq_filter = PrerequisiteFilter(
            A_pre=A_pre, prereq_threshold=self.config.prereq_threshold
        )
        self._zpd_filter = ZPDFilter(
            zpd_lo=self.config.zpd_lo,
            zpd_hi=self.config.zpd_hi,
            zpd_relax_band=self.config.zpd_relax_band,
        )
        self._scoring = ScoringEngine(
            w_zpd=self.config.w_zpd,
            w_prereq=self.config.w_prereq,
            w_decay=self.config.w_decay,
            w_momentum=self.config.w_momentum,
            A_pre=A_pre,
            prereq_threshold=self.config.prereq_threshold,
        )

    def generate(
        self,
        mastery: list[float],
        hours_since: dict[int, float] | None = None,
        exclude_skills: set[int] | None = None,
    ) -> dict:
        """Generate a personalized learning path.

        Args:
            mastery: per-skill mastery values.
            hours_since: dict of skill_id → hours since last practice.
            exclude_skills: skill IDs to exclude from the path.

        Returns:
            dict with keys: generated_at, path_length, total_predicted_gain,
            steps, zpd_range, strategy.
        """
        _n = len(mastery)
        hours: dict[int, float] = hours_since or {}
        excluded: set[int] = exclude_skills or set()
        mastery_copy = list(mastery)

        eligible = [
            s for s in self._prereq_filter.eligible(mastery_copy) if s not in excluded
        ]
        eligible = self._zpd_filter.filter(eligible, mastery_copy)

        steps = []
        selected: set[int] = set()

        for rank in range(self.config.path_length):
            candidates = [s for s in eligible if s not in selected]
            if not candidates:
                break

            scored = []
            for s in candidates:
                sc = self._scoring.score(s, mastery_copy, hours, self.decay_vector)
                scored.append((s, sc))

            scored.sort(key=lambda x: x[1]["total"], reverse=True)
            best_sid, best_sc = scored[0]

            cur = mastery_copy[best_sid]
            gain = round(float((1.0 - cur) * 0.15), 4)
            projected = round(min(1.0, cur + gain), 4)
            name = self.skill_names.get(best_sid, f"Skill {best_sid}")

            steps.append(
                {
                    "rank": rank + 1,
                    "skill_id": best_sid,
                    "skill_name": name,
                    "score": best_sc["total"],
                    "zpd_score": best_sc["zpd_proximity"],
                    "prereq_score": best_sc["prereq_strength"],
                    "decay_score": best_sc["decay_urgency"],
                    "momentum_score": best_sc["momentum"],
                    "current_mastery": round(cur, 4),
                    "predicted_mastery_gain": gain,
                    "projected_mastery": projected,
                    "rationale": (
                        f"Mastery {cur:.0%} → targeting improvement. "
                        f"ZPD={best_sc['zpd_proximity']:.2f}, "
                        f"prereq={best_sc['prereq_strength']:.2f}, "
                        f"decay={best_sc['decay_urgency']:.2f}."
                    ),
                }
            )

            selected.add(best_sid)
            mastery_copy[best_sid] = projected

        return {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "path_length": len(steps),
            "total_predicted_gain": round(
                sum(s["predicted_mastery_gain"] for s in steps), 4
            ),
            "steps": steps,
            "zpd_range": [self.config.zpd_lo, self.config.zpd_hi],
            "strategy": "zpd_prereq_decay_momentum",
        }
