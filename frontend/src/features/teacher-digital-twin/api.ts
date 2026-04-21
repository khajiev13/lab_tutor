/**
 * Teacher Digital Twin API — wraps all /teacher-twin/{course_id}/* endpoints.
 * Types mirror backend Pydantic schemas exactly (backend/app/modules/teacher_digital_twin/schemas.py).
 */

import api from '@/services/api';

// ── Feature 1: Skill Difficulty ────────────────────────────────────────────

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

// ── Feature 2: Skill Popularity ───────────────────────────────────────────

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

// ── Feature 3: Class Mastery ───────────────────────────────────────────────

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

// ── Feature 4: Student Groups ──────────────────────────────────────────────

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

// ── Feature 5: What-If Simulation ─────────────────────────────────────────

export interface WhatIfSkillInput {
  skill_name: string;
  hypothetical_mastery?: number;
}

export interface WhatIfRequest {
  mode: 'manual' | 'automatic';
  skills?: WhatIfSkillInput[];
  target_gain?: number;
  top_k?: number;
  delta?: number;
  enable_llm?: boolean;
}

export interface WhatIfSkillResult {
  skill_name: string;
  current_avg_mastery: number;
  simulated_avg_mastery: number;
  class_gain: number;
  students_helped: number;
  recommendation_score: number;
}

export interface WhatIfResponse {
  course_id: number;
  mode: string;
  simulated_path: string[];
  pco_analysis: string[];
  recommendations: string[];
  skill_impacts: WhatIfSkillResult[];
  summary: string;
  llm_recommendation?: string | null;
}

// ── API calls ─────────────────────────────────────────────────────────────

export const teacherTwinApi = {
  /** GET /teacher-twin/{courseId}/skill-difficulty */
  getSkillDifficulty: (courseId: number) =>
    api.get<SkillDifficultyResponse>(`/teacher-twin/${courseId}/skill-difficulty`),

  /** GET /teacher-twin/{courseId}/skill-popularity */
  getSkillPopularity: (courseId: number) =>
    api.get<SkillPopularityResponse>(`/teacher-twin/${courseId}/skill-popularity`),

  /** GET /teacher-twin/{courseId}/class-mastery */
  getClassMastery: (courseId: number) =>
    api.get<ClassMasteryResponse>(`/teacher-twin/${courseId}/class-mastery`),

  /** GET /teacher-twin/{courseId}/student-groups */
  getStudentGroups: (courseId: number) =>
    api.get<StudentGroupsResponse>(`/teacher-twin/${courseId}/student-groups`),

  /** POST /teacher-twin/{courseId}/what-if */
  runWhatIf: (courseId: number, body: WhatIfRequest) =>
    api.post<WhatIfResponse>(`/teacher-twin/${courseId}/what-if`, body),
};
