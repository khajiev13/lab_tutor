from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DupeGroupVerdict(BaseModel):
    are_duplicates: bool
    canonical_name: str | None = None
    skill_names_to_merge: list[str] = Field(default_factory=list)
    reasoning: str


class PrerequisiteEdge(BaseModel):
    prerequisite_skill: str
    dependent_skill: str
    confidence: Literal["high", "medium", "low"]
    reasoning: str


class ClusterPrerequisiteResult(BaseModel):
    edges: list[PrerequisiteEdge]
