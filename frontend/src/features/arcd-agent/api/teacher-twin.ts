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

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types matching backend Pydantic schemas ────────────────────────────────

export interface SkillDifficultyItem {
  skill_name: string;
  student_count: number;
  avg_mastery: number;
  perceived_difficulty: number;
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

export interface WhatIfRequest {
  mode?: "manual" | "automatic";
  skills?: WhatIfSkill[];
  delta?: number;
  top_k?: number;
  target_gain?: number;
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

export function simulateSkills(
  courseId: number,
  body: MultiSkillSimulationRequest,
): Promise<MultiSkillSimulationResponse> {
  return apiFetch(`/teacher-twin/${courseId}/simulate-skills`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchStudentPortfolio(courseId: number, studentId: number): Promise<unknown> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/portfolio`);
}

export function fetchStudentTwin(courseId: number, studentId: number): Promise<unknown> {
  return apiFetch(`/teacher-twin/${courseId}/student/${studentId}/twin`);
}
