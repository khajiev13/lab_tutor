/**
 * Cognitive Diagnosis API — wraps all /diagnosis/* endpoints.
 */

import api from '@/services/api';

// ── Types ────────────────────────────────────────────────────────────────

export interface SkillMastery {
  skill_name: string;
  mastery: number;
  decay: number;
  status: 'not_started' | 'below' | 'at' | 'above';
  attempt_count: number;
  correct_count: number;
  last_practice_ts: number | null;
  model_version: string;
}

export interface MasteryResponse {
  user_id: number;
  course_id: number | null;
  skills: SkillMastery[];
  total_skills: number;
  computed_at: string;
}

export interface PathStep {
  rank: number;
  skill_name: string;
  current_mastery: number;
  predicted_mastery_gain: number;
  projected_mastery: number;
  score: number;
  rationale: string;
  resources?: Record<string, unknown>;
}

export interface LearningPathDiagnosisResponse {
  user_id: number;
  course_id: number;
  generated_at: string;
  path_length: number;
  total_predicted_gain: number;
  steps: PathStep[];
  zpd_range: [number, number];
  strategy: string;
}

export interface PCOSkill {
  skill_name: string;
  failure_streak: number;
  mastery: number;
  decay_risk: number;
  why: string;
}

export interface ReviewResponse {
  user_id: number;
  pco_skills: PCOSkill[];
  review_queue: { skill_name: string; urgency: number }[];
  emotional_state: string;
  teaching_strategy: Record<string, unknown>;
}

export interface ExerciseResponse {
  exercise_id: string;
  skill_name: string;
  problem: string;
  format: 'multiple_choice' | 'open_ended' | 'fill_blank';
  options: string[];
  correct_answer: string;
  hints: string[];
  concepts_tested: string[];
  estimated_time_seconds: number;
  difficulty_target: number;
  difficulty_band: string;
  why: string;
  quality_warning: boolean;
}

export interface PortfolioResponse {
  user_id: number;
  course_id: number | null;
  mastery: SkillMastery[];
  learning_path: LearningPathDiagnosisResponse | null;
  pco_skills: PCOSkill[];
  stats: {
    total_skills: number;
    mastered_skills: number;
    in_progress_skills: number;
    not_started_skills: number;
    average_mastery: number;
    pco_count: number;
  };
  generated_at: string;
}

// ── API calls ────────────────────────────────────────────────────────────

export const diagnosisApi = {
  /** POST /diagnosis/mastery/{course_id} — compute + store mastery */
  computeMastery: (courseId: number) =>
    api.post<MasteryResponse>(`/diagnosis/mastery/${courseId}`),

  /** GET /diagnosis/mastery/{course_id} — read cached mastery */
  getMastery: (courseId: number) =>
    api.get<MasteryResponse>(`/diagnosis/mastery/${courseId}`),

  /** GET /diagnosis/path/{course_id} — PathGen learning path */
  getPath: (courseId: number, pathLength = 8) =>
    api.get<LearningPathDiagnosisResponse>(`/diagnosis/path/${courseId}`, {
      params: { path_length: pathLength },
    }),

  /** POST /diagnosis/review/{course_id} — RevFell review session */
  getReview: (courseId: number, topK = 5) =>
    api.post<ReviewResponse>(`/diagnosis/review/${courseId}`, { top_k: topK }),

  /** POST /diagnosis/exercise — AdaEx adaptive exercise */
  getExercise: (skillName: string, context = '') =>
    api.post<ExerciseResponse>('/diagnosis/exercise', {
      skill_name: skillName,
      context,
    }),

  /** GET /diagnosis/portfolio/{course_id} — full portfolio */
  getPortfolio: (courseId: number) =>
    api.get<PortfolioResponse>(`/diagnosis/portfolio/${courseId}`),

  /** POST /diagnosis/interactions — log ATTEMPTED */
  logInteraction: (data: {
    question_id: string;
    answered_right: boolean;
    selected_option?: string;
    answered_at?: string;
    course_id?: number;
  }) => {
    const { course_id, ...body } = data;
    return api.post('/diagnosis/interactions', body, {
      params: course_id ? { course_id } : undefined,
    });
  },

  /** POST /diagnosis/engagements — log ENGAGES_WITH */
  logEngagement: (data: {
    resource_id: string;
    resource_type: 'reading' | 'video';
    opened_at?: string;
  }) => api.post('/diagnosis/engagements', data),
};
