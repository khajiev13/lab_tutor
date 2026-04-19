"""Cognitive Diagnosis — Pydantic request/response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Shared ────────────────────────────────────────────────────────────────


class SkillMastery(BaseModel):
    """Per-skill mastery + decay snapshot."""

    model_config = ConfigDict(from_attributes=True)

    skill_name: str
    mastery: float = Field(ge=0.0, le=1.0)
    decay: float = Field(ge=0.0, le=1.0, description="1.0 = fully retained, 0.0 = forgotten")
    status: Literal["not_started", "below", "at", "above"] = "not_started"
    attempt_count: int = 0
    correct_count: int = 0
    last_practice_ts: int | None = None
    model_version: str = "arcd_v2"


# ── Request schemas ────────────────────────────────────────────────────────


class LogInteractionRequest(BaseModel):
    """Log a student answering a question."""

    question_id: str
    is_correct: bool
    timestamp_sec: int | None = None
    time_spent_sec: int | None = None
    attempt_number: int = 1


class LogEngagementRequest(BaseModel):
    """Log a student engaging with a reading or video resource."""

    resource_id: str
    resource_type: Literal["reading", "video"]
    progress: float = Field(ge=0.0, le=1.0, default=0.0)
    duration_sec: int | None = None
    timestamp_sec: int | None = None


class ReviewRequest(BaseModel):
    """Trigger a Learning Fellow review session."""

    top_k: int = Field(default=5, ge=1, le=20)


class ExerciseRequest(BaseModel):
    """Request an adaptive exercise for a specific skill."""

    skill_name: str
    context: str = ""


class StudentEventCreate(BaseModel):
    """Create/update a student-planned calendar event."""

    date: str
    title: str
    event_type: Literal["exam", "assignment", "busy", "study", "other"]
    duration_minutes: int | None = Field(default=None, ge=0, le=1440)
    notes: str = ""


class StudentEventsQuery(BaseModel):
    """Filter events by optional date range (YYYY-MM-DD)."""

    from_date: str | None = None
    to_date: str | None = None


# ── Response schemas ───────────────────────────────────────────────────────


class MasteryResponse(BaseModel):
    """Full mastery vector for a student."""

    user_id: int
    course_id: int | None = None
    skills: list[SkillMastery] = []
    total_skills: int = 0
    computed_at: str = ""


class PathStep(BaseModel):
    rank: int
    skill_name: str
    current_mastery: float
    predicted_mastery_gain: float
    projected_mastery: float
    score: float
    rationale: str = ""
    resources: dict = Field(default_factory=dict)


class LearningPathDiagnosisResponse(BaseModel):
    user_id: int
    course_id: int
    generated_at: str = ""
    path_length: int = 0
    total_predicted_gain: float = 0.0
    steps: list[PathStep] = []
    zpd_range: list[float] = [0.40, 0.90]
    strategy: str = "zpd_prereq_decay_momentum"
    learning_schedule: dict | None = None


class PCOSkill(BaseModel):
    skill_name: str
    failure_streak: int
    mastery: float
    decay_risk: float
    why: str


class ReviewResponse(BaseModel):
    user_id: int
    pco_skills: list[PCOSkill] = []
    review_queue: list[dict] = []
    emotional_state: str = "engaged"
    teaching_strategy: dict = Field(default_factory=dict)
    agenda_context: list[dict] = []


class StudentEventResponse(BaseModel):
    id: str
    user_id: int
    date: str
    title: str
    event_type: Literal["exam", "assignment", "busy", "study", "other"]
    duration_minutes: int | None = None
    notes: str = ""
    created_at: str = ""


class StudentEventsListResponse(BaseModel):
    events: list[StudentEventResponse] = []


class ExerciseOption(BaseModel):
    label: str
    text: str


class ExerciseResponse(BaseModel):
    exercise_id: str
    skill_name: str
    problem: str
    format: Literal["multiple_choice", "open_ended", "fill_blank"] = "open_ended"
    options: list[str] = []
    correct_answer: str = ""
    hints: list[str] = []
    concepts_tested: list[str] = []
    estimated_time_seconds: int = 120
    difficulty_target: float = 0.5
    difficulty_band: str = "medium"
    why: str = ""
    quality_warning: bool = False


class PortfolioResponse(BaseModel):
    user_id: int
    course_id: int | None = None
    mastery: list[SkillMastery] = []
    learning_path: LearningPathDiagnosisResponse | None = None
    pco_skills: list[PCOSkill] = []
    stats: dict = Field(default_factory=dict)
    generated_at: str = ""


# ── What-if strategy advisor (ARCD Twin) ───────────────────────────────────


class WhatIfPathOption(BaseModel):
    name: str
    total_gain: float
    final_avg: float
    target_skills: list[str] = []
    coherence_score: float = 0.0


class WhatIfAnalysisRequest(BaseModel):
    mastery_vector: list[float] = []
    strategy_options: list[WhatIfPathOption] = []
    recommended_strategy: str | None = None


class WhatIfAnalysisResponse(BaseModel):
    best_strategy: str
    rationale: str
    action_items: list[str] = []
    generated_at: str
    source: Literal["llm", "rule_based"] = "rule_based"


# ── ARCD Dashboard format (matches frontend PortfolioData TS interface) ────


class ArcdConceptInfo(BaseModel):
    id: int | str
    numeric_id: int | None = None
    name_zh: str = ""
    name_en: str = ""


class ArcdSkillInfo(BaseModel):
    id: int
    chapter_id: int = 0
    domain_id: int = 0  # backward-compat alias for chapter_id
    chapter_order: int = 9999  # numeric order (e.g., chapter_index) for chronological sorting
    chapter_name: str = ""  # human-readable name of the BOOK_CHAPTER this skill belongs to
    name: str
    concepts: list[ArcdConceptInfo] = []
    n_concepts: int = 0


class ArcdTimelineEntry(BaseModel):
    step: int
    timestamp: str = ""
    question_id: int = 0
    concept_id: int = 0
    skill_id: int
    response: int
    predicted_prob: float = 0.5
    mastery: list[float] = []
    time_gap_hours: float = 0.0


class ArcdStudentSummary(BaseModel):
    total_interactions: int = 0
    accuracy: float = 0.0
    first_timestamp: str = ""
    last_timestamp: str = ""
    active_days: int = 0
    avg_mastery: float = 0.0
    strongest_skill: int = 0
    weakest_skill: int = 0
    skills_touched: int = 0


class ArcdLearningPathStep(BaseModel):
    rank: int
    skill_id: int
    skill_name: str
    score: float = 0.0
    zpd_score: float = 0.0
    prereq_score: float = 0.0
    decay_score: float = 0.0
    momentum_score: float = 0.0
    transfer_score: float | None = None
    predicted_mastery_gain: float = 0.0
    current_mastery: float = 0.0
    projected_mastery: float = 0.0
    rationale: str = ""
    action_plan: dict | None = None


class ArcdLearningPath(BaseModel):
    generated_at: str = ""
    path_length: int = 0
    total_predicted_gain: float = 0.0
    steps: list[ArcdLearningPathStep] = []
    zpd_range: list[float] = [0.40, 0.90]
    strategy: str = "zpd_prereq_decay_momentum"
    learning_schedule: dict | None = None


class ArcdStudentPortfolio(BaseModel):
    uid: str
    summary: ArcdStudentSummary
    final_mastery: list[float] = []
    base_mastery: list[float] | None = None
    modality_coverage: dict | None = None
    timeline: list[ArcdTimelineEntry] = []
    learning_path: ArcdLearningPath | None = None
    review_session: dict | None = None


class ArcdModelInfo(BaseModel):
    total_params: int = 0
    best_val_auc: float = 0.0
    n_skills: int = 0
    n_questions: int = 0
    n_students: int = 1
    d: int = 64


class ArcdDatasetPortfolio(BaseModel):
    id: str
    name: str
    model_info: ArcdModelInfo
    skills: list[ArcdSkillInfo] = []
    students: list[ArcdStudentPortfolio] = []


class ArcdPortfolioData(BaseModel):
    """Matches the frontend PortfolioData TypeScript interface exactly."""

    generated_at: str = ""
    datasets: list[ArcdDatasetPortfolio] = []


# ── ARCD Twin format (matches frontend TwinViewerData TS interface) ────────


class ArcdTwinCurrentState(BaseModel):
    mastery: list[float] = []
    snapshot_type: str = "live"
    timestamp: int = 0
    hu_fresh: bool = True
    skill_names: dict[str, str] = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)


class ArcdTwinSnapshotEntry(BaseModel):
    index: int
    step: int
    timestamp: int = 0
    snapshot_type: str = "live"
    avg_mastery: float = 0.0
    mastery: list[float] = []


class ArcdTwinSkillAlert(BaseModel):
    skill_id: int
    skill_name: str
    current_mastery: float
    predicted_decay: float
    downstream_at_risk: int = 0
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class ArcdTwinRiskForecast(BaseModel):
    horizon_days: int = 30
    threshold: float = 0.5
    total_at_risk: int = 0
    computed_at: str | None = None
    at_risk_skills: list[ArcdTwinSkillAlert] = []


class ArcdTwinScenarioPath(BaseModel):
    name: str
    skills: list[int] = []
    skill_names: list[str] = []
    avg_mastery_gain: float = 0.0
    final_avg_mastery: float = 0.0


class ArcdTwinScenarioComparison(BaseModel):
    horizon_days: int = 30
    path_a: ArcdTwinScenarioPath = Field(
        default_factory=lambda: ArcdTwinScenarioPath(name="current")
    )
    path_b: ArcdTwinScenarioPath = Field(
        default_factory=lambda: ArcdTwinScenarioPath(name="recommended")
    )
    best_path: str = "path_a"


class ArcdTwinConfidence(BaseModel):
    rmse: float = 0.0
    mae: float = 0.0
    quality: str = "N/A"
    description: str | None = None
    per_skill_rmse: list[float] = []


class ArcdTwinViewerData(BaseModel):
    """Matches the frontend TwinViewerData TypeScript interface."""

    student_id: str
    generated_at: str = ""
    dataset: str = ""
    current_twin: ArcdTwinCurrentState
    snapshot_history: list[ArcdTwinSnapshotEntry] = []
    risk_forecast: ArcdTwinRiskForecast = Field(default_factory=ArcdTwinRiskForecast)
    scenario_comparison: ArcdTwinScenarioComparison = Field(
        default_factory=ArcdTwinScenarioComparison
    )
    twin_confidence: ArcdTwinConfidence = Field(default_factory=ArcdTwinConfidence)
    recommended_schedule_summary: dict | None = None
