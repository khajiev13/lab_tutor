/**
 * Teacher Digital Twin API — wraps all /teacher-twin/{course_id}/* endpoints.
 */

import api from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────

export interface SkillDifficultyItem {
  skill_name: string;
  student_count: number;
  avg_mastery: number;
  perceived_difficulty: number;
}

export interface SkillDifficultyResponse {
  course_id: number;
  skills: SkillDifficultyItem[];
  computed_at: string;
}

export interface SkillPopularityItem {
  skill_name: string;
  student_count: number;
  popularity_ratio: number;
}

export interface SkillPopularityResponse {
  course_id: number;
  total_students: number;
  most_popular: SkillPopularityItem[];
  least_popular: SkillPopularityItem[];
  computed_at: string;
}

export interface StudentMasterySummary {
  user_id: number;
  username: string;
  skill_count: number;
  avg_mastery: number;
  mastered_count: number;
  below_threshold_count: number;
  mastery_tier: 'high' | 'medium' | 'low';
}

export interface ClassMasteryResponse {
  course_id: number;
  total_students: number;
  class_avg_mastery: number;
  mastery_std_dev: number;
  students: StudentMasterySummary[];
  computed_at: string;
}

export interface StudentGroupSummary {
  group_id: string;
  skill_set: string[];
  student_count: number;
  student_names: string[];
  avg_group_mastery: number;
  suggested_next_skills: string[];
  group_readiness: number;
}

export interface StudentGroupsResponse {
  course_id: number;
  total_groups: number;
  groups: StudentGroupSummary[];
  computed_at: string;
}

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
  mode: 'manual' | 'automatic';
  skill_impacts: WhatIfSkillResult[];
  simulated_path: string[];
  pco_analysis: string[];
  recommendations: string[];
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
