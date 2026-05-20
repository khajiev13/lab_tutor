export interface CourseCreate {
  title: string;
  description?: string | null;
}

export type ExtractionStatus = 'not_started' | 'in_progress' | 'finished' | 'failed';

export type FileProcessingStatus = 'pending' | 'processing' | 'processed' | 'failed';

export type CourseLevel = 'bachelor' | 'master' | 'phd';

export type PublicationStatus = 'draft' | 'published';

export type MarketGateStatus = 'not_started' | 'completed' | 'waived';

export type AvailabilityStatus = 'draft' | 'published' | 'publishing_paused';

export type GateStatus = 'locked' | 'ready' | 'complete' | 'blocked';

export type ReadinessGateId = 'book' | 'market' | 'prerequisites' | 'publish';

export type NextActionId = ReadinessGateId | 'none';

export interface Course extends CourseCreate {
  id: number;
  description: string | null;
  teacher_id: number;
  created_at: string;
  extraction_status: ExtractionStatus;
  publication_status: PublicationStatus;
  market_gate_status: MarketGateStatus;
  level: CourseLevel;
}

export interface Enrollment {
  id: number;
  course_id: number;
  student_id: number;
  created_at: string;
}

export interface CourseFileRead {
  id: number;
  course_id: number;
  filename: string;
  blob_path: string;
  content_hash: string | null;
  uploaded_at: string;
  status: FileProcessingStatus;
  last_error: string | null;
  processed_at: string | null;
}

export type EmbeddingStatus = 'not_started' | 'in_progress' | 'completed' | 'failed';

export interface CourseFileEmbeddingStatus {
  id: number;
  filename: string;
  status: FileProcessingStatus;
  content_hash: string | null;
  processed_at: string | null;
  last_error: string | null;

  document_id: string | null;
  embedding_status: EmbeddingStatus;
  embedded_at: string | null;
  embedding_last_error: string | null;
}

export interface CourseEmbeddingStatusResponse {
  course_id: number;
  extraction_status: ExtractionStatus;
  embedding_status: EmbeddingStatus;
  embedding_started_at: string | null;
  embedding_finished_at: string | null;
  embedding_last_error: string | null;
  files: CourseFileEmbeddingStatus[];
}

export interface ReadinessNextAction {
  id: NextActionId;
  label: string;
  route: string | null;
}

export interface ReadinessGate {
  id: ReadinessGateId;
  label: string;
  status: GateStatus;
  route: string | null;
  detail: string;
}

export interface PrerequisiteReviewSummary {
  status: PrerequisiteReviewStatus;
  edge_count: number;
  isolated_skill_count: number;
  last_generated_at: string | null;
}

export type PrerequisiteReviewStatus = 'not_started' | 'needs_review' | 'approved' | 'stale';

export type PrerequisiteEdgeConfidence = 'high' | 'medium' | 'low';

export type PrerequisiteEdgeSource = 'ai' | 'teacher';

export interface PrerequisiteSkill {
  name: string;
  source: string;
  chapter_title: string | null;
}

export interface PrerequisiteDraftEdge {
  prerequisite_name: string;
  dependent_name: string;
  confidence: PrerequisiteEdgeConfidence;
  reasoning: string;
  source: PrerequisiteEdgeSource;
}

export interface PrerequisiteValidation {
  is_valid: boolean;
  errors: string[];
  cycle_path: string[];
}

export interface PrerequisiteReviewMetadata {
  edge_count: number;
  generated_edge_count: number;
  added_edge_count: number;
  removed_edge_count: number;
  isolated_skill_count: number;
  last_generated_at: string | null;
  last_invalidated_at: string | null;
  approved_at: string | null;
}

export interface PrerequisiteReview {
  course_id: number;
  status: PrerequisiteReviewStatus;
  is_rebuilding: boolean;
  skills: PrerequisiteSkill[];
  draft_edges: PrerequisiteDraftEdge[];
  isolated_skills: string[];
  validation: PrerequisiteValidation;
  metadata: PrerequisiteReviewMetadata;
}

export interface SavePrerequisiteReviewPayload {
  draft_edges: PrerequisiteDraftEdge[];
  isolated_skills_viewed: boolean;
}

export interface CourseReadiness {
  course_id: number;
  publication_status: PublicationStatus;
  availability_status: AvailabilityStatus;
  can_publish: boolean;
  blockers: string[];
  next_action: ReadinessNextAction;
  gates: ReadinessGate[];
  prerequisite_review: PrerequisiteReviewSummary;
}
