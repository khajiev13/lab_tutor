import api from '@/services/api';

const BASE = '/student-learning-path';

export interface StudentSkillBankSkill {
  name: string;
  description?: string | null;
  category?: string | null;
  is_selected?: boolean;
  source?: string | null;
  peer_count?: number;
}

export interface StudentSkillBankChapter {
  chapter_id: string;
  title: string;
  chapter_index: number;
  skills: StudentSkillBankSkill[];
}

export interface StudentSkillBankBook {
  book_id: string;
  title: string;
  authors?: string | null;
  chapters: StudentSkillBankChapter[];
}

export interface StudentSkillBankJobPosting {
  url: string;
  title: string;
  company: string | null;
  site?: string | null;
  search_term?: string | null;
  is_interested: boolean;
  skills: StudentSkillBankSkill[];
}

export interface SkillSelectionRange {
  min_skills: number;
  max_skills: number;
  is_default: boolean;
}

export interface PrerequisiteEdge {
  prerequisite_name: string;
  dependent_name: string;
  confidence: 'high' | 'medium' | 'low';
  reasoning: string;
}

export interface SkillBanksResponse {
  book_skill_banks: StudentSkillBankBook[];
  market_skill_bank: StudentSkillBankJobPosting[];
  selected_skill_names: string[];
  interested_posting_urls: string[];
  peer_selection_counts: Record<string, number>;
  selection_range: SkillSelectionRange;
  prerequisite_edges: PrerequisiteEdge[];
}

export interface LearningPathSkill {
  name: string;
  source: string;
  description: string | null;
  skill_type: string;
  concepts: { name: string; description: string }[];
  readings: {
    title: string;
    url: string;
    domain: string;
    snippet: string;
    search_content: string;
    search_result_url: string;
    search_result_domain: string;
    source_engine: string;
    source_engines: string[];
    search_metadata_json: string;
    resource_type: string;
    final_score: number;
    concepts_covered: string[];
  }[];
  videos: {
    title: string;
    url: string;
    domain: string;
    snippet: string;
    search_content: string;
    video_id: string;
    search_result_url: string;
    search_result_domain: string;
    source_engine: string;
    source_engines: string[];
    search_metadata_json: string;
    resource_type: string;
    final_score: number;
    concepts_covered: string[];
  }[];
  questions: {
    id: string;
    text: string;
    difficulty: 'easy' | 'medium' | 'hard';
    options: string[];
  }[];
  is_known: boolean;
  resource_status: 'loaded' | 'pending';
}

export interface LearningPathChapter {
  title: string;
  chapter_index: number;
  description: string | null;
  selected_skills: LearningPathSkill[];
  quiz_status: 'locked' | 'quiz_required' | 'learning' | 'completed';
  easy_question_count: number;
  answered_count: number;
}

export interface LearningPathResponse {
  course_id: number;
  course_title: string;
  chapters: LearningPathChapter[];
  total_selected_skills: number;
  skills_with_resources: number;
}

export interface BuildProgressEvent {
  type: string;
  skill_name: string;
  phase: string;
  detail: string;
  skills_completed: number;
  total_skills: number;
}

export interface BuildSelectedSkillInput {
  name: string;
  source: 'book' | 'market';
}

export interface QuizQuestion {
  id: string;
  skill_name: string;
  text: string;
  options: string[];
}

export interface PreviousAnswer {
  selected_option: 'A' | 'B' | 'C' | 'D';
  answered_right: boolean;
  answered_at: string;
}

export interface ChapterQuizResponse {
  course_id: number;
  chapter_index: number;
  chapter_title: string;
  questions: QuizQuestion[];
  previous_answers: Record<string, PreviousAnswer>;
}

export interface QuizAnswerSubmission {
  question_id: string;
  selected_option: 'A' | 'B' | 'C' | 'D';
}

export interface QuizSubmitRequest {
  answers: QuizAnswerSubmission[];
}

export interface QuizAnswerResult {
  question_id: string;
  skill_name: string;
  selected_option: 'A' | 'B' | 'C' | 'D';
  answered_right: boolean;
  correct_option: 'A' | 'B' | 'C' | 'D';
}

export interface QuizSubmitResponse {
  chapter_index: number;
  results: QuizAnswerResult[];
  skills_known: string[];
}

export async function getSkillBanks(courseId: number): Promise<SkillBanksResponse> {
  const { data } = await api.get(`${BASE}/${courseId}/skill-banks`);
  return data;
}

export async function selectSkills(
  courseId: number,
  skillNames: string[],
  source: 'book' | 'market',
): Promise<{ selected: number }> {
  const { data } = await api.post(`${BASE}/${courseId}/select-skills`, {
    skill_names: skillNames,
    source,
  });
  return data;
}

export async function deselectSkills(
  courseId: number,
  skillNames: string[],
): Promise<{ deselected: number }> {
  const { data } = await api.delete(`${BASE}/${courseId}/deselect-skills`, {
    data: { skill_names: skillNames },
  });
  return data;
}

export async function selectJobPostings(
  courseId: number,
  postingUrls: string[],
): Promise<{ postings_linked: number }> {
  const { data } = await api.post(`${BASE}/${courseId}/select-job-postings`, {
    posting_urls: postingUrls,
  });
  return data;
}

export async function deselectJobPosting(
  courseId: number,
  postingUrl: string,
): Promise<{ orphans_deleted: number }> {
  const { data } = await api.delete(`${BASE}/${courseId}/deselect-job-posting`, {
    data: { posting_url: postingUrl },
  });
  return data;
}

export async function buildLearningPath(
  courseId: number,
  selectedSkills: BuildSelectedSkillInput[] = [],
): Promise<{ run_id: string; status: string }> {
  const payload = selectedSkills.length > 0 ? { selected_skills: selectedSkills } : undefined;
  const { data } = await api.post(`${BASE}/${courseId}/build`, payload);
  return data;
}

export async function getLearningPath(
  courseId: number,
): Promise<LearningPathResponse> {
  const { data } = await api.get(`${BASE}/${courseId}/path`);
  return data;
}

export async function getChapterQuiz(
  courseId: number,
  chapterIndex: number,
): Promise<ChapterQuizResponse> {
  const { data } = await api.get(`${BASE}/${courseId}/chapters/${chapterIndex}/quiz`);
  return data;
}

export async function submitChapterQuiz(
  courseId: number,
  chapterIndex: number,
  answers: QuizAnswerSubmission[],
): Promise<QuizSubmitResponse> {
  const payload: QuizSubmitRequest = { answers };
  const { data } = await api.post(`${BASE}/${courseId}/chapters/${chapterIndex}/quiz/submit`, payload);
  return data;
}

export async function trackResourceOpen(
  courseId: number,
  payload: { resource_type: 'reading' | 'video'; url: string },
): Promise<void> {
  await api.post(`${BASE}/${courseId}/resources/open`, payload).catch(() => {});
}

export function streamBuildProgress(
  courseId: number,
  runId: string,
  onEvent: (event: BuildProgressEvent) => void,
  onComplete: () => void,
  onError: (err: Error) => void,
): () => void {
  const baseUrl = api.defaults.baseURL || '';
  const token = localStorage.getItem('access_token');
  const url = `${baseUrl}${BASE}/${courseId}/build/stream/${runId}`;

  const eventSource = new EventSource(`${url}?token=${token}`);

  eventSource.addEventListener('skill_progress', (e) => {
    try {
      const data = JSON.parse(e.data) as BuildProgressEvent;
      onEvent(data);
    } catch {
      // Ignore parse errors
    }
  });

  eventSource.addEventListener('stream_end', () => {
    eventSource.close();
    onComplete();
  });

  eventSource.addEventListener('error', () => {
    eventSource.close();
    onError(new Error('SSE connection error'));
  });

  eventSource.onerror = () => {
    eventSource.close();
    onError(new Error('SSE connection error'));
  };

  return () => eventSource.close();
}
