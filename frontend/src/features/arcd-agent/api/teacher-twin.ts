/**
 * Teacher Digital Twin — frontend API wrapper.
 *
 * All endpoints require a TEACHER JWT token.
 * Mirrors backend /teacher-twin/{course_id}/... routes.
 */

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("access_token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface ApiFetchOptions extends RequestInit {
  /** Abort the request after this many milliseconds. Surfaces as a clear
   *  error message instead of an indefinite spinner. Default: no timeout. */
  timeoutMs?: number;
}

async function apiFetch<T>(url: string, init?: ApiFetchOptions): Promise<T> {
  const { timeoutMs, signal: callerSignal, ...rest } = init ?? {};

  // Compose caller's AbortSignal (if any) with our own timeout signal so
  // either source can cancel the request.
  const controller = new AbortController();
  const onCallerAbort = () => controller.abort(callerSignal?.reason);
  if (callerSignal) {
    if (callerSignal.aborted) controller.abort(callerSignal.reason);
    else callerSignal.addEventListener("abort", onCallerAbort, { once: true });
  }
  const timer =
    typeof timeoutMs === "number" && timeoutMs > 0
      ? setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs)
      : null;

  try {
    const res = await fetch(`${API_BASE}${url}`, {
      ...rest,
      headers: { ...authHeaders(), ...(rest.headers ?? {}) },
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error(
        `Request timed out after ${(timeoutMs ?? 0) / 1000}s. The server is taking longer than expected — try again or reduce the simulation size.`,
      );
    }
    throw err;
  } finally {
    if (timer !== null) clearTimeout(timer);
    if (callerSignal) callerSignal.removeEventListener("abort", onCallerAbort);
  }
}

// ── Types matching backend Pydantic schemas ────────────────────────────────

export interface SkillDifficultyItem {
  skill_name: string;
  /** All students who selected or attempted the skill (SELECTED_SKILL ∪ MASTERED). */
  student_count: number;
  /** Subset who actually have a `MASTERED` edge — i.e. real practice signal. */
  attempted_count: number;
  avg_mastery: number;
  /** 1 − avg mastery, computed only over `attempted_count`. 0 when no attempts. */
  perceived_difficulty: number;
  prereq_count: number;
  downstream_count: number;
  pco_risk_ratio: number;
}

export interface SkillDifficultyResponse {
  course_id: number;
  skills: SkillDifficultyItem[];
  total_skills: number;
}

export interface SkillPopularityItem {
  skill_name: string;
  selection_count: number;
  rank: number;
}

export interface SkillPopularityResponse {
  course_id: number;
  all_skills: SkillPopularityItem[];
  most_popular: SkillPopularityItem[];
  least_popular: SkillPopularityItem[];
  total_students: number;
}

export interface StudentMasterySummary {
  user_id: number;
  full_name: string;
  email: string;
  selected_skill_count: number;
  avg_mastery: number;
  mastered_count: number;
  struggling_count: number;
  pco_count: number;
  at_risk: boolean;
}

export interface ClassMasteryResponse {
  course_id: number;
  students: StudentMasterySummary[];
  class_avg_mastery: number;
  at_risk_count: number;
  total_students: number;
}

export interface StudentGroupMember {
  user_id: number;
  full_name: string;
  avg_mastery: number;
}

export interface StudentGroup {
  group_id: string;
  group_name: string;
  performance_tier: string;
  skill_set: string[];
  member_count: number;
  members: StudentGroupMember[];
  group_avg_mastery: number;
  suggested_path: string[];
}

export interface StudentGroupsResponse {
  course_id: number;
  groups: StudentGroup[];
  ungrouped_students: StudentGroupMember[];
  total_groups: number;
}

export interface WhatIfSkill {
  skill_name: string;
  hypothetical_mastery: number;
}

export type AutomaticWhatIfFocus =
  | "balanced"
  | "broad_support"
  | "prerequisite_bottlenecks"
  | "high_risk_recovery";

export interface AutomaticWhatIfPreferences {
  intervention_intensity?: number;
  focus?: AutomaticWhatIfFocus;
  max_skills?: number;
}

export type WhatIfPlanningSource = "llm" | "rule_based" | "mixed";

export interface AutomaticWhatIfCriteria {
  intervention_intensity: number;
  focus: AutomaticWhatIfFocus;
  max_skills: number;
  llm_decision_summary: string;
  /**
   * Where the per-skill targets actually came from. The frontend uses this to
   * avoid claiming "LLM decided" when the rule-based fallback ran (e.g. when
   * the LLM provider is unreachable or returned invalid JSON).
   */
  planning_source: WhatIfPlanningSource;
}

export interface WhatIfRequest {
  mode?: "manual" | "automatic";
  skills?: WhatIfSkill[];
  preferences?: AutomaticWhatIfPreferences;
  enable_llm?: boolean;
}

export interface SkillInterventionImpact {
  skill_name: string;
  current_avg_mastery: number;
  simulated_avg_mastery: number;
  class_gain: number;
  students_helped: number;
  recommendation_score: number;
}

export interface WhatIfResponse {
  mode: string;
  course_id: number;
  simulated_path: string[];
  pco_analysis: string[];
  recommendations: string[];
  skill_impacts: SkillInterventionImpact[];
  summary: string;
  llm_recommendation: string | null;
  automatic_criteria?: AutomaticWhatIfCriteria | null;
}

export interface SkillSimulationRequest {
  skill_name: string;
  simulated_mastery?: number;
}

export interface SkillSimulationResponse {
  skill_name: string;
  simulated_mastery: number;
  perceived_difficulty: number;
  avg_class_mastery: number;
  student_count: number;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

// ── Multi-skill simulation types ───────────────────────────────────────────

export interface SkillTarget {
  skill_name: string;
  simulated_mastery?: number | null;
}

export interface MultiSkillSimulationRequest {
  mode?: "manual" | "automatic";
  skills?: SkillTarget[];
  top_k?: number;
  default_mastery?: number;
}

export interface SkillSimResult {
  skill_name: string;
  simulated_mastery: number;
  avg_class_mastery: number;
  perceived_difficulty: number;
  student_count: number;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface SkillCoherencePair {
  skill_a: string;
  skill_b: string;
  jaccard_score: number;
}

export interface SkillCoherenceResult {
  overall_score: number;
  label: "High" | "Medium" | "Low";
  pairs: SkillCoherencePair[];
  teaching_order: string[];
  clusters: string[][];
  common_students: number;
}

export interface MultiSkillSimulationResponse {
  mode: string;
  course_id: number;
  auto_selected_skills: string[];
  skill_results: SkillSimResult[];
  coherence: SkillCoherenceResult;
  llm_insights: string | null;
}

// ── API functions ──────────────────────────────────────────────────────────

export function fetchSkillDifficulty(courseId: number): Promise<SkillDifficultyResponse> {
  return apiFetch(`/teacher-twin/${courseId}/skill-difficulty`);
}

export function fetchSkillPopularity(courseId: number): Promise<SkillPopularityResponse> {
  return apiFetch(`/teacher-twin/${courseId}/skill-popularity`);
}

export function fetchClassMastery(courseId: number): Promise<ClassMasteryResponse> {
  return apiFetch(`/teacher-twin/${courseId}/class-mastery`);
}

export function fetchStudentGroups(courseId: number): Promise<StudentGroupsResponse> {
  return apiFetch(`/teacher-twin/${courseId}/student-groups`);
}

export function runWhatIf(courseId: number, body: WhatIfRequest): Promise<WhatIfResponse> {
  return apiFetch(`/teacher-twin/${courseId}/what-if`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fetchStudentPortfolioForTeacher(courseId: number, studentId: number): Promise<any> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/portfolio`);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function fetchStudentTwinForTeacher(courseId: number, studentId: number): Promise<any> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/twin`);
}

export function simulateSkill(
  courseId: number,
  body: SkillSimulationRequest,
): Promise<SkillSimulationResponse> {
  return apiFetch(`/teacher-twin/${courseId}/simulate-skill`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Multi-skill simulation. Backend fans out per-skill exercise generation in
 *  parallel (~5 concurrent), so wall-clock is bounded by the slowest skill
 *  (~10-15s) plus an LLM-insights call (≤20s). 120s timeout gives generous
 *  headroom while still preventing the spinner from hanging forever if the
 *  LLM provider is unreachable. */
export function simulateSkills(
  courseId: number,
  body: MultiSkillSimulationRequest,
): Promise<MultiSkillSimulationResponse> {
  return apiFetch(`/teacher-twin/${courseId}/simulate-skills`, {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 120_000,
  });
}

export function fetchStudentPortfolio(courseId: number, studentId: number): Promise<unknown> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/portfolio`);
}

export function fetchStudentTwin(courseId: number, studentId: number): Promise<unknown> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/twin`);
}
