// ── Enums / Unions ─────────────────────────────────────────────

export type SessionStatus =
  | 'configuring'
  | 'discovering'
  | 'scoring'
  | 'awaiting_review'
  | 'downloading'
  | 'completed'
  | 'failed';

export type DownloadStatus =
  | 'pending'
  | 'downloading'
  | 'success'
  | 'failed'
  | 'manual_upload';

export type BookStatus = 'downloaded' | 'uploaded' | 'failed';

export type CourseLevel = 'bachelor' | 'master' | 'phd';

export type StreamEventType =
  | 'phase_update'
  | 'discovery_progress'
  | 'scoring_progress'
  | 'books_ready'
  | 'download_progress'
  | 'download_complete'
  | 'error';

// ── Request DTOs ───────────────────────────────────────────────

export interface WeightsConfig {
  C_topic: number;
  C_struc: number;
  C_scope: number;
  C_pub: number;
  C_auth: number;
  C_time: number;
  W_prac: number;
}

export const DEFAULT_WEIGHTS: WeightsConfig = {
  C_topic: 0.3,
  C_struc: 0.2,
  C_scope: 0.15,
  C_pub: 0.15,
  C_auth: 0.1,
  C_time: 0.1,
  W_prac: 0.0,
};

export interface StartSessionRequest {
  course_level: CourseLevel;
  weights: WeightsConfig;
}

export interface SelectBooksRequest {
  book_ids: number[];
}

// ── Response DTOs ──────────────────────────────────────────────

export interface BookSelectionSession {
  id: number;
  course_id: number;
  thread_id: string;
  status: SessionStatus;
  course_level: string;
  weights_json: string | null;
  progress_scored: number;
  progress_total: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookCandidate {
  id: number;
  session_id: number;
  course_id: number;
  title: string;
  authors: string | null;
  publisher: string | null;
  year: string | null;
  s_final: number | null;
  scores_json: string | null;
  selected_by_teacher: boolean;
  download_status: DownloadStatus;
  download_error: string | null;
  blob_path: string | null;
  source_url: string | null;
  created_at: string;
}

export interface ManualUploadResponse {
  book_id: number;
  blob_path: string;
}

export interface CourseSelectedBook {
  id: number;
  course_id: number;
  source_book_id: number | null;
  title: string;
  authors: string | null;
  publisher: string | null;
  year: string | null;
  status: BookStatus;
  blob_path: string | null;
  blob_url: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface SelectedBookManualUploadResponse {
  id: number;
  blob_path: string;
  blob_url: string | null;
  status: BookStatus;
}

// ── SSE Stream Event ───────────────────────────────────────────

export interface StreamEvent {
  type: StreamEventType;
  phase: string;
  message: string;
  progress?: number | null;
  total?: number | null;
  data?: Record<string, unknown> | null;
}

// ── Parsed Scores ──────────────────────────────────────────────

export interface BookScores {
  C_topic: number;
  C_topic_rationale: string;
  C_struc: number;
  C_struc_rationale: string;
  C_scope: number;
  C_scope_rationale: string;
  C_pub: number;
  C_pub_rationale: string;
  C_auth: number;
  C_auth_rationale: string;
  C_time: number;
  C_time_rationale: string;
  C_prac: number;
  C_prac_rationale: string;
  S_final: number;
  S_final_with_prac: number;
  book_title?: string;
  book_authors?: string;
}

/** Criteria metadata for display */
export interface ScoreCriterion {
  key: keyof BookScores;
  rationaleKey: keyof BookScores;
  label: string;
  weightKey: keyof WeightsConfig;
  description: string;
}

export const SCORE_CRITERIA: ScoreCriterion[] = [
  { key: 'C_topic', rationaleKey: 'C_topic_rationale', label: 'Topic Coverage', weightKey: 'C_topic', description: 'How well the book covers the course topics and keywords' },
  { key: 'C_struc', rationaleKey: 'C_struc_rationale', label: 'Structure Alignment', weightKey: 'C_struc', description: 'How closely the book structure matches the syllabus sequence' },
  { key: 'C_scope', rationaleKey: 'C_scope_rationale', label: 'Scope & Level', weightKey: 'C_scope', description: 'Whether the book matches the course academic level' },
  { key: 'C_pub', rationaleKey: 'C_pub_rationale', label: 'Publisher Quality', weightKey: 'C_pub', description: 'Reputation and quality of the publisher' },
  { key: 'C_auth', rationaleKey: 'C_auth_rationale', label: 'Author Credibility', weightKey: 'C_auth', description: 'Expertise and reputation of the author(s)' },
  { key: 'C_time', rationaleKey: 'C_time_rationale', label: 'Timeliness', weightKey: 'C_time', description: 'How current and up-to-date the book content is' },
  { key: 'C_prac', rationaleKey: 'C_prac_rationale', label: 'Practicality', weightKey: 'W_prac', description: 'Practical exercises, examples, and real-world applications' },
];

export function parseScores(scoresJson: string | null): BookScores | null {
  if (!scoresJson) return null;
  try {
    const data = JSON.parse(scoresJson);
    // Ensure required fields exist
    if (typeof data.C_topic !== 'number') return null;
    return data as BookScores;
  } catch {
    return null;
  }
}

// ── Analysis Types ─────────────────────────────────────────────

export type ExtractionRunStatus =
  | 'pending'
  | 'extracting'
  | 'embedding'
  | 'scoring'
  | 'completed'
  | 'failed'
  | 'book_picked';

export type AnalysisStrategy = 'chunking' | 'agentic';

export interface BookExtractionRun {
  id: number;
  course_id: number;
  status: ExtractionRunStatus;
  error_message: string | null;
  progress_detail: string | null;
  embedding_model: string | null;
  embedding_dims: number | null;
  created_at: string;
  updated_at: string;
}

export interface ConceptCoverageItem {
  concept_name: string;
  doc_topic: string;
  sim_max: number;
  best_match: string;
}

export interface BookUniqueConceptItem {
  name: string;
  chapter_title: string | null;
  section_title: string | null;
  sim_max: number;
  best_course_match: string;
}

export interface SimBucket {
  bucket_start: number;
  bucket_end: number;
  count: number;
}

export interface DocumentSummaryItem {
  document_id: string;
  topic: string | null;
  summary_text: string | null;
  sim_score: number;
}

export interface BookAnalysisSummary {
  id: number;
  run_id: number;
  selected_book_id: number;
  strategy: AnalysisStrategy;
  book_title: string;
  s_final_name: number;
  s_final_evidence: number;
  total_book_concepts: number;
  chapter_count: number;
  novel_count_default: number;
  overlap_count_default: number;
  covered_count_default: number;
  book_unique_concepts: BookUniqueConceptItem[];
  course_coverage: ConceptCoverageItem[];
  topic_scores: Record<string, number>;
  sim_distribution: SimBucket[];
  document_summaries: DocumentSummaryItem[];
  created_at: string;
}

// ── Reclassify helper ──────────────────────────────────────────

export type ConceptTier = 'novel' | 'overlap' | 'covered';

export function reclassify<T extends { sim_max: number }>(
  items: T[],
  novelThr: number,
  coveredThr: number,
): (T & { tier: ConceptTier })[] {
  return items.map((c) => ({
    ...c,
    tier:
      c.sim_max < novelThr
        ? 'novel'
        : c.sim_max < coveredThr
          ? 'overlap'
          : 'covered',
  }));
}

export const DEFAULT_NOVEL_THRESHOLD = 0.35;
export const DEFAULT_COVERED_THRESHOLD = 0.55;
