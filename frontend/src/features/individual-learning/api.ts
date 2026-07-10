import api from '@/services/api';

const BASE = '/individual-learning';

export interface IndividualProfile {
  user_id: number;
  onboarding_status:
    | 'needs_cv'
    | 'extracting'
    | 'needs_profile_review'
    | 'needs_jobs'
    | 'needs_skill_selection'
    | 'ready'
    | 'error';
  target_titles: string[];
  preferred_country?: string | null;
  preferred_location?: string | null;
  reviewed_at?: string | null;
  cv_document_id: number | null;
  extraction_run_id: number | null;
  active_thread_id: string | null;
  next_step: IndividualNextStep;
  extracted_profile: IndividualCvProfileExtraction | null;
  pending_interrupt: IndividualGraphReviewInterrupt | IndividualGraphJobsInterrupt | null;
}

export interface IndividualCvDocument {
  id: number;
  user_id: number;
  original_filename: string;
  content_type?: string | null;
  status: string;
}

export type IndividualNextStep =
  | 'upload_cv'
  | 'wait_for_extraction'
  | 'review_profile'
  | 'search_jobs'
  | 'select_jobs_and_skills'
  | 'learning_path'
  | 'retry_cv';

export interface IndividualCvSkillExtraction {
  name: string;
  category?: string | null;
  evidence?: string | null;
  confidence?: number | null;
}

export interface IndividualCvExperienceExtraction {
  title?: string | null;
  organization?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  summary?: string | null;
}

export interface IndividualCvProfileExtraction {
  summary?: string | null;
  skills?: IndividualCvSkillExtraction[];
  experience?: IndividualCvExperienceExtraction[];
  projects?: string[];
  education?: string[];
  certifications?: string[];
  tools?: string[];
  languages?: string[];
  industries?: string[];
  seniority_signals?: string[];
  target_title_suggestions?: string[];
  confidence_summary?: Record<string, number>;
}

export interface IndividualSkillBankSkill {
  name: string;
  description?: string | null;
  category?: string | null;
  is_selected?: boolean;
  coverage?: 'covered' | 'gap' | 'partial' | 'unknown';
}

export interface IndividualGraphJobPosting {
  url: string;
  title: string;
  company?: string | null;
  site?: string | null;
  search_term?: string | null;
  country?: string | null;
  location?: string | null;
  description?: string | null;
  match_score?: number | null;
  skill_extraction_status?: 'completed' | 'failed';
  skill_extraction_error?: string | null;
  skills?: Array<{
    name: string;
    category?: string | null;
    description?: string | null;
    coverage?: 'covered' | 'gap' | 'partial' | 'unknown';
  }>;
}

export interface IndividualSkillBankJobPosting {
  url: string;
  title: string;
  company: string;
  site?: string | null;
  search_term?: string | null;
  is_interested: boolean;
  match_score?: number | null;
  skill_extraction_status?: 'completed' | 'failed';
  skill_extraction_error?: string | null;
  skills: IndividualSkillBankSkill[];
}

export interface IndividualSkillBanksResponse {
  market_skill_bank: IndividualSkillBankJobPosting[];
  selected_skill_names: string[];
  interested_posting_urls: string[];
}

export interface IndividualGraphReviewInterrupt {
  kind: 'review_profile_and_roles';
  profile: IndividualCvProfileExtraction;
  target_title_suggestions: string[];
}

export interface IndividualGraphJobsInterrupt {
  kind: 'choose_jobs_and_skills';
  candidate_jobs: IndividualGraphJobPosting[];
  skill_bank: Array<{
    name: string;
    category?: string | null;
    description?: string | null;
  }>;
}

export type IndividualGraphInterrupt =
  | IndividualGraphReviewInterrupt
  | IndividualGraphJobsInterrupt
  | {
      kind: string;
      [key: string]: unknown;
    };

export interface IndividualGraphResponse {
  thread_id: string;
  status: 'interrupted' | 'completed';
  interrupt: IndividualGraphInterrupt | null;
  target_titles: string[];
  selected_posting_urls: string[];
  selected_skill_names: string[];
}

export interface IndividualLearningPathResource {
  id: string;
  title: string;
  url: string;
  domain?: string | null;
  video_id?: string | null;
}

export interface IndividualLearningPathQuestion {
  id: string;
  text: string;
  difficulty: 'easy' | 'medium' | 'hard';
  options: string[];
}

export interface IndividualLearningPathSkill {
  name: string;
  description?: string | null;
  source?: string | null;
  selected_at?: string | null;
  readings: IndividualLearningPathResource[];
  videos: IndividualLearningPathResource[];
  questions: IndividualLearningPathQuestion[];
}

export interface IndividualLearningPathResponse {
  user_id: number;
  build_status: 'completed' | 'partial' | 'failed' | null;
  build_run_id: string | null;
  build_error: string | null;
  selected_skills: IndividualLearningPathSkill[];
  total_selected_skills: number;
  skills_with_resources: number;
}

export async function getIndividualProfile(): Promise<IndividualProfile> {
  const { data } = await api.get(`${BASE}/profile`);
  return data;
}

export async function uploadCv(file: File): Promise<IndividualCvDocument> {
  const formData = new FormData();
  formData.append('file', file);

  const { data } = await api.post(`${BASE}/cv`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function retryCvExtraction(
  cvDocumentId: number,
): Promise<IndividualCvDocument> {
  const { data } = await api.post(`${BASE}/cv/${cvDocumentId}/retry`);
  return data;
}

export async function startIndividualGraph(cvDocumentId: number): Promise<IndividualGraphResponse> {
  const { data } = await api.post(`${BASE}/graph/start`, {
    cv_document_id: cvDocumentId,
  });
  return data;
}

export async function resumeIndividualGraph(
  threadId: string,
  payload: Record<string, unknown>,
): Promise<IndividualGraphResponse> {
  const { data } = await api.post(`${BASE}/graph/resume`, {
    thread_id: threadId,
    payload,
  });
  return data;
}

export async function getIndividualSkillBanks(): Promise<IndividualSkillBanksResponse> {
  const { data } = await api.get(`${BASE}/skill-banks`);
  return data;
}

export async function selectInterestedJobs(
  postingUrls: string[],
): Promise<{ postings_linked: number }> {
  const { data } = await api.post(`${BASE}/interested-jobs`, {
    posting_urls: postingUrls,
  });
  return data;
}

export async function selectIndividualSkills(
  skillNames: string[],
): Promise<{ selected: number }> {
  const { data } = await api.post(`${BASE}/select-skills`, {
    skill_names: skillNames,
  });
  return data;
}

export async function deselectIndividualSkills(
  skillNames: string[],
): Promise<{ deselected: number }> {
  const { data } = await api.delete(`${BASE}/select-skills`, {
    data: { skill_names: skillNames },
  });
  return data;
}

export async function buildIndividualLearningPath(
  skillNames: string[],
): Promise<{
  status: 'completed' | 'partial' | 'failed';
  run_id: string;
  error?: string | null;
}> {
  const { data } = await api.post(`${BASE}/build`, {
    skill_names: skillNames,
  });
  return data;
}

export async function getIndividualLearningPath(): Promise<IndividualLearningPathResponse> {
  const { data } = await api.get(`${BASE}/path`);
  return data;
}

export const individualLearningApi = {
  getProfile: getIndividualProfile,
  uploadCv,
  retryCvExtraction,
  startGraph: startIndividualGraph,
  resumeGraph: resumeIndividualGraph,
  getSkillBanks: getIndividualSkillBanks,
  selectInterestedJobs,
  selectSkills: selectIndividualSkills,
  deselectSkills: deselectIndividualSkills,
  build: buildIndividualLearningPath,
  getPath: getIndividualLearningPath,
};
