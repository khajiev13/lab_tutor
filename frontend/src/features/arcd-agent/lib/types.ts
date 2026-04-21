export interface ConceptInfo {
  id: number | string;
  numeric_id?: number;
  name_zh: string;
  name_en: string;
}

export interface SkillInfo {
  id: number;
  /** Chapter this skill belongs to. Previously called domain_id. */
  chapter_id: number;
  /** Backward-compat alias for chapter_id. */
  domain_id: number;
  /** Numeric chapter ordering for chronological rendering (Chapter 1,2,3...). */
  chapter_order?: number;
  /** Human-readable name of the BOOK_CHAPTER / CHAPTER this skill belongs to. */
  chapter_name: string;
  name: string;
  /** CONCEPT nodes attached to this skill via REQUIRES_CONCEPT in the KG. */
  concepts: ConceptInfo[];
  n_concepts: number;
}

/** A chapter with all its skills grouped together. */
export interface ChapterGroup {
  chapter_id: number;
  chapter_name: string;
  chapter_order?: number;
  skills: SkillInfo[];
}

export interface TimelineEntry {
  step: number;
  timestamp: string;
  question_id: number;
  concept_id: number;
  skill_id: number;
  response: number;
  predicted_prob: number;
  mastery: number[];
  time_gap_hours: number;
}

export interface StudentSummary {
  total_interactions: number;
  accuracy: number;
  first_timestamp: string;
  last_timestamp: string;
  active_days: number;
  avg_mastery: number;
  strongest_skill: number;
  weakest_skill: number;
  skills_touched: number;
}

export interface ExercisePreview {
  type: string;
  count: number;
  difficulty_band: string;
  estimated_time_seconds?: number;
}

export interface ActionPlan {
  session_type: string;
  estimated_minutes: number;
  exercises: ExercisePreview[];
  question_ids: number[];
  sub_skills_to_focus: string[];
  success_criteria: string;
  next_review_date: string;
}

export interface LearningPathStep {
  rank: number;
  skill_id: number;
  skill_name: string;
  score: number;
  zpd_score: number;
  prereq_score: number;
  decay_score: number;
  momentum_score: number;
  transfer_score?: number;
  predicted_mastery_gain: number;
  current_mastery: number;
  projected_mastery: number;
  rationale: string;
  action_plan?: ActionPlan;
}

export interface LearningScheduleDay {
  date: string;
  sessions: LearningPathStep[];
  total_minutes: number;
  is_review_day?: boolean;
  student_events?: StudentEvent[];
}

export interface StudentEvent {
  id: string;
  user_id: number;
  date: string;
  title: string;
  event_type: "exam" | "assignment" | "busy" | "study" | "other";
  duration_minutes?: number | null;
  notes?: string;
  created_at?: string;
}

export interface LearningSchedule {
  schedule: LearningScheduleDay[];
  review_calendar: string[];
  study_guide: string;
  study_minutes_per_day: number;
  student_events?: StudentEvent[];
}

export interface ReplanTriggers {
  mastery_deviation_threshold: number;
  max_steps_before_recheck: number;
  pco_detected: boolean;
  session_outcomes_required: boolean;
}

export interface LearningPath {
  generated_at: string;
  path_length: number;
  total_predicted_gain: number;
  steps: LearningPathStep[];
  zpd_range: [number, number];
  strategy: string;
  replan_triggers?: ReplanTriggers;
  learning_schedule?: LearningSchedule;
}

export interface ReviewItem {
  skill_id: number;
  skill_name: string;
  question: string;
  hint: string;
  correct_answer: string;
  difficulty: string;
  urgency: number;
  mode: string;
}

export interface DialogueStep {
  step_num: number;
  prompt: string;
  expected_insight: string;
  scaffolding_hint: string;
}

export interface SlowThinkingPlan {
  skill_id: number;
  skill_name: string;
  /** Concept names related to this slow-thinking plan. */
  concepts: string[];
  identified_weakness: string;
  dialogue_steps: DialogueStep[];
  difficulty_level: string;
  estimated_duration_minutes: number;
  comprehension_score: number;
}

export interface MasteryUpdateEntry {
  skill_id: number;
  old_mastery: number;
  new_mastery: number;
  outcome: number;
  source: string;
  timestamp: string;
}

export interface ReviewRewards {
  total_points: number;
  session_points: number;
  events_count: number;
  current_streak: number;
}

export interface MasteryDeviation {
  skill_id: number;
  original: number;
  current: number;
  delta: number;
  direction: string;
}

export interface ReviewSession {
  student_uid: string;
  dataset_id: string;
  started_at: string;
  completed_at: string;
  pco_skills_detected: number[];
  /** Number of PCO skills (convenience; may equal pco_skills_detected.length). */
  pco_count?: number;
  /** Net change in mastery over the session. */
  mastery_delta?: number;
  /** Number of exercise-generation requests (or array of requests) from review. */
  exegen_requests?: number | unknown[];
  fast_reviews: ReviewItem[];
  slow_thinking_plans: SlowThinkingPlan[];
  mastery_updates: MasteryUpdateEntry[];
  rewards: ReviewRewards;
  needs_replan: boolean;
  deviations: MasteryDeviation[];
}

/** Optional session data from the AdaEx (adaptive exercise) agent. */
export interface AdaExSession {
  [key: string]: unknown;
}

/** Optional log entries from the orchestrator agent. */
export type OrchestratorLogEntry = Record<string, unknown>;

/** Per-student modality coverage fractions (0–1). Null when dataset is quiz-only. */
export interface ModalityCoverage {
  quiz_pct: number;
  video_pct: number;
  reading_pct: number;
}

/** Weighted final grade breakdown for a chapter using the 60/20/20 rubric. */
export interface ModalityBreakdown {
  quiz_grade: number;
  video_coverage: number;
  reading_coverage: number;
  weighted_final: number;
}

export interface StudentPortfolio {
  uid: string;
  summary: StudentSummary;
  final_mastery: number[];
  /** Peak mastery per skill (highest value ever observed in the timeline). */
  base_mastery?: number[];
  /** Per-student coverage across modalities; absent for quiz-only datasets. */
  modality_coverage?: ModalityCoverage | null;
  timeline: TimelineEntry[];
  learning_path?: LearningPath;
  review_session?: ReviewSession;
  /** Session data from the AdaEx agent, if run. */
  adaex_session?: AdaExSession;
  /** Log entries from the orchestrator, if run. */
  orchestrator_log?: OrchestratorLogEntry[];
}

export interface ModelInfo {
  total_params: number;
  best_val_auc: number;
  n_skills: number;
  n_questions: number;
  n_students: number;
  d: number;
}

export interface DatasetPortfolio {
  id: string;
  name: string;
  model_info: ModelInfo;
  skills: SkillInfo[];
  students: StudentPortfolio[];
}

export interface PortfolioData {
  generated_at: string;
  datasets: DatasetPortfolio[];
}

export interface InsightResponse {
  greeting_summary: string;
  knowledge_tracing_insight: string;
  recommended_next_step: string;
}

/** Map from skill index to skill name. */
export function buildSkillNameMap(skills: SkillInfo[]): Record<number, string> {
  const map: Record<number, string> = {};
  for (const skill of skills) {
    map[skill.id] = skill.name;
  }
  return map;
}

// Backward-compat alias used by older imports.
export const buildSubSkillNameMap = buildSkillNameMap;

export function getAllSkillIds(skills: SkillInfo[]): number[] {
  return skills.map((s) => s.id).sort((a, b) => a - b);
}

// Backward-compat alias.
export const getAllSubSkillIds = getAllSkillIds;

/** Find the skill that contains a given concept id. */
export function getSkillForConcept(skills: SkillInfo[], conceptId: number | string): SkillInfo | undefined {
  for (const skill of skills) {
    if (skill.concepts.some((c) => c.id === conceptId)) return skill;
  }
  return undefined;
}

// Backward-compat aliases.
export const getChapterForSubSkill = (skills: SkillInfo[], skillId: number) =>
  skills.find((s) => s.id === skillId);
export const getDomainForSubSkill = getChapterForSubSkill;

// ── Digital Twin types ─────────────────────────────────────────────────────

export interface TwinSkillAlert {
  skill_id: number;
  skill_name: string;
  current_mastery: number;
  predicted_decay: number;
  downstream_at_risk: number;
  priority: "HIGH" | "MEDIUM" | "LOW";
}

export interface TwinRiskForecast {
  horizon_days: number;
  threshold: number;
  total_at_risk: number;
  computed_at?: string;
  at_risk_skills: TwinSkillAlert[];
}

export interface TwinScenarioPath {
  name: string;
  skills: number[];
  skill_names: string[];
  avg_mastery_gain: number;
  final_avg_mastery: number;
  trajectory: { step: number; avgMastery: number }[];
  coherence_score: number;
  justification: string[];
}

export interface TwinReviewDemo {
  skill_id: number;
  skill_name: string;
  mastery_now: number;
  mastery_review_3d: number;
  mastery_review_7d: number;
  recommendation: string;
}

export interface TwinScenarioComparison {
  horizon_days: number;
  path_a: TwinScenarioPath;
  path_b: TwinScenarioPath;
  path_c: TwinScenarioPath;
  best_path: "path_a" | "path_b" | "path_c";
  review_schedule_demo?: TwinReviewDemo;
}

export interface TwinConfidence {
  rmse: number;
  mae: number;
  quality: string;
  description?: string;
  per_skill_rmse: number[];
}

export interface TwinCurrentState {
  mastery: number[];
  snapshot_type: string;
  timestamp: number;
  hu_fresh: boolean;
  skill_names: Record<string, string>;
  summary: {
    avg_mastery: number;
    above_60pct: number;
    below_40pct: number;
    n_skills: number;
  };
}

export interface TwinSnapshotEntry {
  index: number;
  step: number;
  timestamp: number;
  snapshot_type: string;
  avg_mastery: number;
  mastery: number[];
}

export interface TwinViewerData {
  student_id: string;
  generated_at: string;
  dataset: string;
  current_twin: TwinCurrentState;
  snapshot_history: TwinSnapshotEntry[];
  risk_forecast: TwinRiskForecast;
  scenario_comparison: TwinScenarioComparison;
  twin_confidence: TwinConfidence;
  recommended_schedule_summary?: {
    next_days: LearningScheduleDay[];
    student_events: StudentEvent[];
    review_calendar?: string[];
  };
}

/**
 * Group a flat skills array into chapters.
 * Skills with no chapter_name are placed in an "Uncategorized" group.
 * Order of chapters follows first appearance in the skills array.
 */
export function groupByChapter(skills: SkillInfo[]): ChapterGroup[] {
  const order: number[] = [];
  const map = new Map<number, ChapterGroup>();
  for (const skill of skills) {
    const cid = skill.chapter_id;
    if (!map.has(cid)) {
      order.push(cid);
      map.set(cid, {
        chapter_id: cid,
        chapter_name: skill.chapter_name || "Uncategorized",
        chapter_order: skill.chapter_order ?? 9999,
        skills: [],
      });
    }
    const group = map.get(cid)!;
    if ((skill.chapter_order ?? 9999) < (group.chapter_order ?? 9999)) {
      group.chapter_order = skill.chapter_order ?? 9999;
    }
    group.skills.push(skill);
  }
  return order
    .map((cid) => map.get(cid)!)
    .sort((a, b) => {
      const ao = a.chapter_order ?? 9999;
      const bo = b.chapter_order ?? 9999;
      if (ao !== bo) return ao - bo;
      return a.chapter_name.localeCompare(b.chapter_name);
    });
}
