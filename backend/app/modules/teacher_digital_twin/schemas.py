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
    prereq_count: int = 0
    downstream_count: int = 0
    pco_risk_ratio: float = 0.0


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
    group_name: str = ""
    performance_tier: str = "developing"
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


class AutomaticWhatIfPreferences(BaseModel):
    """Teacher-provided hints for automatic LLM planning."""

    intervention_intensity: float = 0.6
    focus: Literal[
        "balanced",
        "broad_support",
        "prerequisite_bottlenecks",
        "high_risk_recovery",
    ] = "balanced"
    max_skills: int = 5


class AutomaticWhatIfCriteria(BaseModel):
    """Resolved automatic criteria after the LLM planner makes the final choice."""

    intervention_intensity: float
    focus: Literal[
        "balanced",
        "broad_support",
        "prerequisite_bottlenecks",
        "high_risk_recovery",
    ]
    max_skills: int
    llm_decision_summary: str


class WhatIfRequest(BaseModel):
    mode: Literal["manual", "automatic"] = "automatic"
    skills: list[WhatIfSkill] | None = None  # manual mode
    preferences: AutomaticWhatIfPreferences = AutomaticWhatIfPreferences()
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
    automatic_criteria: AutomaticWhatIfCriteria | None = None


# ── Feature 6: Skill Simulation (single-skill — kept for backward compat) ──


class SkillSimulationRequest(BaseModel):
    skill_name: str
    simulated_mastery: float = 0.5


class SkillSimulationResponse(BaseModel):
    skill_name: str
    simulated_mastery: float
    perceived_difficulty: float
    avg_class_mastery: float
    student_count: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str


# ── Feature 6b: Multi-Skill Simulation with Coherence Analysis ─────────────


class SkillTarget(BaseModel):
    """One skill to simulate, with an optional per-skill mastery override."""

    skill_name: str
    simulated_mastery: float | None = None  # None → use class average


class SkillSimResult(BaseModel):
    """Per-skill simulation result: difficulty stats + one adaptive exercise."""

    skill_name: str
    simulated_mastery: float
    avg_class_mastery: float
    perceived_difficulty: float
    student_count: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str


class SkillCoherencePair(BaseModel):
    """Pairwise co-selection similarity between two skills."""

    skill_a: str
    skill_b: str
    jaccard_score: float  # 0 = no shared students, 1 = identical student set


class SkillCoherenceResult(BaseModel):
    """Coherence summary for the full set of selected skills."""

    overall_score: float  # mean Jaccard across all pairs
    label: str  # "High" / "Medium" / "Low"
    pairs: list[SkillCoherencePair]
    teaching_order: list[str]  # sorted by avg mastery ascending (foundations first)
    clusters: list[list[str]]  # connected components with Jaccard ≥ 0.40
    common_students: int  # students who selected ≥ 2 of the chosen skills


class MultiSkillSimulationRequest(BaseModel):
    mode: Literal["manual", "automatic"] = "manual"
    skills: list[
        SkillTarget
    ] = []  # manual mode: explicit skills; automatic mode: auto-selected
    top_k: int = 5  # automatic mode: number of hardest skills to simulate
    default_mastery: float = 0.5


class MultiSkillSimulationResponse(BaseModel):
    mode: str
    course_id: int
    auto_selected_skills: list[str] = []
    skill_results: list[SkillSimResult]
    coherence: SkillCoherenceResult
    llm_insights: str | None = None
