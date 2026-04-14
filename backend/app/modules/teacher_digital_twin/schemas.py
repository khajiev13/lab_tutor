"""Teacher Digital Twin — Pydantic v2 DTOs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# ── Feature 1: Skill Difficulty ────────────────────────────────────────────


class SkillDifficultyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill_name: str
    student_count: int
    avg_mastery: float
    perceived_difficulty: float  # 1 - avg_mastery


class SkillDifficultyResponse(BaseModel):
    course_id: int
    skills: list[SkillDifficultyItem]
    total_skills: int


# ── Feature 2: Skill Popularity ───────────────────────────────────────────


class SkillPopularityItem(BaseModel):
    skill_name: str
    selection_count: int
    rank: int


class SkillPopularityResponse(BaseModel):
    course_id: int
    all_skills: list[SkillPopularityItem]
    most_popular: list[SkillPopularityItem]
    least_popular: list[SkillPopularityItem]
    total_students: int


# ── Feature 3: Class Mastery ───────────────────────────────────────────────


class StudentMasterySummary(BaseModel):
    user_id: int
    full_name: str
    email: str
    selected_skill_count: int
    avg_mastery: float
    mastered_count: int
    struggling_count: int
    pco_count: int
    at_risk: bool


class ClassMasteryResponse(BaseModel):
    course_id: int
    students: list[StudentMasterySummary]
    class_avg_mastery: float
    at_risk_count: int
    total_students: int


# ── Feature 4: Student Groups ──────────────────────────────────────────────


class StudentGroupMember(BaseModel):
    user_id: int
    full_name: str
    avg_mastery: float


class StudentGroup(BaseModel):
    group_id: str
    skill_set: list[str]
    member_count: int
    members: list[StudentGroupMember]
    group_avg_mastery: float
    suggested_path: list[str]


class StudentGroupsResponse(BaseModel):
    course_id: int
    groups: list[StudentGroup]
    ungrouped_students: list[StudentGroupMember]
    total_groups: int


# ── Feature 5: What-If Simulation ─────────────────────────────────────────


class WhatIfSkill(BaseModel):
    skill_name: str
    hypothetical_mastery: float  # 0.0 to 1.0


class WhatIfRequest(BaseModel):
    mode: Literal["manual", "automatic"] = "automatic"
    skills: list[WhatIfSkill] | None = None  # manual mode
    delta: float = 0.20  # automatic mode: estimated lecture impact
    top_k: int = 5
    target_gain: float = 0.10
    enable_llm: bool = False


class SkillInterventionImpact(BaseModel):
    skill_name: str
    current_avg_mastery: float
    simulated_avg_mastery: float
    class_gain: float
    students_helped: int
    recommendation_score: float = 0.0


class WhatIfResponse(BaseModel):
    mode: str
    course_id: int
    simulated_path: list[str]
    pco_analysis: list[str]
    recommendations: list[str]
    skill_impacts: list[SkillInterventionImpact]
    summary: str
    llm_recommendation: str | None = None
