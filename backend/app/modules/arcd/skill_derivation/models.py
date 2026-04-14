"""Data models for the dynamic skill derivation pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(eq=False)
class SkillCluster:
    skill_id: str
    skill_name: str
    description: str
    concept_ids: list[str]
    centroid: np.ndarray  # shape [D]
    coherent: bool = True

    @property
    def size(self) -> int:
        return len(self.concept_ids)


@dataclass
class SkillPrerequisite:
    from_skill: str
    to_skill: str
    strength: float


@dataclass
class CourseSkillMap:
    course_id: str | None
    skills: list[SkillCluster] = field(default_factory=list)
    prerequisites: list[SkillPrerequisite] = field(default_factory=list)
    K: int = 0
    silhouette_score: float = 0.0

    @property
    def centroid_matrix(self) -> np.ndarray:
        """Return [K x D] matrix of skill centroids."""
        if not self.skills:
            return np.empty((0, 0))
        return np.stack([s.centroid for s in self.skills])

    def concept_to_skill(self, concept_id: str) -> int | None:
        """Return skill index for a concept, or None."""
        for idx, sk in enumerate(self.skills):
            if concept_id in sk.concept_ids:
                return idx
        return None

    def skill_id_to_idx(self, skill_id: str) -> int | None:
        for idx, sk in enumerate(self.skills):
            if sk.skill_id == skill_id:
                return idx
        return None
