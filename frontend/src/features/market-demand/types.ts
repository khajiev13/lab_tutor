// SSE event types from the backend
export type AgentName =
  | "workspace_review"
  | "supervisor"
  | "skill_finder"
  | "curriculum_mapper"
  | "skill_cleaner"
  | "concept_linker";

export type StreamEvent =
  | { type: "agent_start"; agent: AgentName; messageId: string; displayName: string; emoji: string }
  | { type: "text_delta"; delta: string; messageId: string }
  | { type: "text_done"; messageId: string }
  | { type: "tool_start"; toolName: string; toolCallId: string; args: Record<string, unknown>; agent: AgentName }
  | { type: "tool_args_update"; toolCallId: string; args: Record<string, unknown> }
  | { type: "tool_end"; toolCallId: string; toolName: string; result: unknown; status: "finished" | "error" }
  | { type: "state_update"; stateKey: string; value: unknown }
  | { type: "skill_review_changed"; run_id: string; candidate_revision: number; selection_revision: number; publication_revision: number }
  | { type: "context_resolved"; messageId: string; workspace_context: ResolvedContextMetadata }
  | ({ type: "error" } & StreamFailure)
  | { type: "stream_end"; outcome?: "completed" | "failed" };

// Chat message model
export type ToolCallStatus = "loading" | "finished" | "unknown" | "success" | "error";

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: ToolCallStatus;
  result?: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  agent?: AgentName;
  agentDisplayName?: string;
  agentEmoji?: string;
  content: string;
  toolCalls: ToolCall[];
  isStreaming: boolean;
  workspace_context?: ResolvedContextMetadata;
}

// Pipeline stages
export type PipelineStageId =
  | "fetch"
  | "select"
  | "extract"
  | "map"
  | "approve"
  | "link"
  | "insert";

export type StageStatus = "complete" | "active" | "pending";

// Agent state from tool_store
export interface AgentState {
  sources?: JobSource[];
  evidence_sources?: EvidenceSource[];
  onet_release?: string | null;
  selected_onet_occupations?: string[];
  onet_selection_confirmed?: boolean;
  run_id?: string | null;
  candidate_revision?: number;
  source_outcomes?: Record<string, SourceOutcome>;
  course_id: number | null;
  course_title: string | null;
  course_description: string | null;
  job_search_country: string | null;
  job_search_country_confirmed: boolean | null;
  job_search_location: string | null;
  fetched_jobs: Record<string, unknown>[] | null;
  job_groups: Record<string, number[]> | null;
  selected_jobs: Record<string, unknown>[] | null;
  extracted_skills: SkillEntry[] | null;
  total_jobs_for_extraction: number | null;
  existing_graph_skills: Record<string, unknown>[] | null;
  existing_concepts: string[] | null;
  curriculum_mapping: MappingEntry[] | null;
  selected_for_insertion: Record<string, unknown>[] | null;
  skill_concepts: Record<string, unknown> | null;
  insertion_results: InsertionResults | null;
  skill_job_urls: Record<string, string[]> | null;
}

export interface SkillEntry {
  name: string;
  category: string;
  frequency: number;
  pct: number;
}

export interface MappingEntry {
  name: string;
  category: string;
  status: "covered" | "gap" | "new_topic_needed";
  target_chapter?: string;
  related_concepts?: string[];
  priority?: "high" | "medium" | "low";
  reasoning?: string;
}

export interface InsertionResults {
  skills: number;
  job_postings: number;
  chapter_links: number;
  sourced_from: number;
  existing_concept_links: number;
  new_concepts: number;
}

export type JobSource = "indeed" | "linkedin" | "headhunter";
export type EvidenceSource = "jobs" | "onet";
export interface SourceConfiguration {
  sources: JobSource[];
  evidence_sources: EvidenceSource[];
  onet_release: string | null;
  onet_occupation_codes: string[];
}
export interface JobSourceAvailability {
  id: JobSource;
  label: string;
  availability: "available" | "unsupported_country" | "not_configured";
  reason: string | null;
}
export interface SourceOutcome {
  status: "idle" | "loading" | "success" | "empty" | "partial" | "error";
  received_count: number;
  usable_count: number;
  warnings: string[];
}
export interface OnetRelease { version: string; active: boolean; attribution: string }
export interface OnetOccupation { soc_code: string; title: string; description: string }
export interface SkillCategory { category_id: string; label: string }
export interface SkillCandidate {
  candidate_id: string;
  display_name: string;
  category_id: string;
  original_labels: string[];
  aliases: string[];
  evidence_references: VacancyEvidenceReference[];
  job_metrics: JobMetrics;
  onet_associations: OnetAssociation[];
  recommendation_reasons: string[];
  posting_support: "supported" | "missing";
  qualifying_posting_links: string[];
}
export interface RecommendationProposal {
  id: string;
  candidate_revision: number;
  base_selection_revision: number;
  changes: { candidate_id: string; action: "add" | "remove"; reason: string }[];
}
export interface CandidateReconciliation {
  reconciliation_id: string;
  candidate_id?: string | null;
  previous_candidate_ids: string[];
  reason: string;
  previous_candidates: { candidate_id: string; display_name: string }[];
  previous_selected_candidate_ids: string[];
  previous_excluded_candidate_ids: string[];
  resolved: boolean;
}
export interface SkillReview {
  analysis_metadata?: AnalysisMetadata | null;
  run_id: string | null;
  candidate_revision: number;
  selection_revision: number;
  categories: SkillCategory[];
  candidates: SkillCandidate[];
  selected_candidate_ids: string[];
  excluded_candidate_ids: string[];
  recommendations: RecommendationProposal[];
  reconciliations?: CandidateReconciliation[];
  source_outcomes: Record<string, SourceOutcome>;
  extraction_coverage: ExtractionCoverage;
  integration_review: IntegrationReviewPayload | null;
  publication_revision: number;
  approved_references: ApprovedSkillReference[];
}
export interface SkillReviewDraft {
  run_id: string;
  expected_candidate_revision: number;
  expected_selection_revision: number;
  selected_candidate_ids: string[];
  excluded_candidate_ids: string[];
  resolved_reconciliation_ids?: string[];
}

export type CoverageStatus = "full" | "partial" | "failed" | "pending";
export interface JobMetrics {
  supporting_posting_count?: number;
  assessed_posting_count?: number;
  selected_posting_count?: number;
  percentage?: number | null;
  coverage_status?: CoverageStatus;
}
export interface VacancyEvidenceReference {
  snapshot_id: string;
  provider: JobSource;
  original_url: string;
  original_phrase: string;
  evidence_kind: "provider_tag" | "extracted_text";
  excerpt: string | null;
  excerpt_start: number | null;
  excerpt_end: number | null;
  retrieved_at: string;
  status: string;
}
export interface OnetMetric {
  scale_id: string;
  value: number | null;
  minimum: number;
  maximum: number;
  status: "reported" | "missing" | "suppressed" | "not_relevant";
  date: string | null;
  quality: Record<string, unknown>;
}
export interface OnetEvidence {
  id: string;
  release: string;
  soc_code: string;
  occupation_title: string;
  family: "essential" | "transferable" | "software";
  element_id: string;
  label: string;
  definition: string;
  workplace_example: string | null;
  ratings: Partial<Record<"IM" | "LV", OnetMetric>>;
  flags: Record<string, boolean | null>;
  source_url: string;
  attribution: string;
}
export interface OccupationSkills {
  release: string;
  soc_code: string;
  items: OnetEvidence[];
}
export interface OnetAssociation {
  evidence: OnetEvidence;
  relation: "equivalent" | "broader" | "related" | "unmatched";
  mapping_method: string;
  rationale: string;
}
export interface ExtractionCoverage {
  status?: CoverageStatus;
  selected_postings?: number;
  assessed_postings?: number;
  failed_postings?: number;
  total_chunks?: number;
  assessed_chunks?: number;
  warnings?: string[];
  acknowledged?: boolean;
}
export interface IntegrationReviewPayload {
  withdrawal?: boolean;
  review_digest: string;
  candidate_revision: number;
  selection_revision: number;
  items: {
    candidate_id: string;
    target: {identity: string; label: string; source: "book" | "market"; origin: string};
    chapters: {chapter_id: string; title: string}[];
    concepts?: {name: string; description: string | null}[];
    disposition: "new" | "covered" | "merged";
    qualifying_posting_links: string[];
    evidence_snapshot_ids: string[];
  }[];
  omissions: string[];
  omissions_acknowledged: boolean;
}
export interface ApprovedSkillReference {
  reference_id: string;
  label: string;
  category: string;
  source: "book" | "market";
  origin: string;
  qualifying_posting_links: string[];
  projection_status: "pending" | "projected" | "error";
  available_for_new_selection: boolean;
}
export interface SkillReviewRevision {
  run_id: string;
  expected_candidate_revision: number;
  expected_selection_revision: number;
}
export interface IntegrationApproval extends SkillReviewRevision {
  review_digest: string;
  approved_candidate_ids: string[];
}
export interface IntegrationApprovalResponse {
  review: SkillReview;
  projection_status: "pending" | "projected" | "error";
}
export interface PostingEvidence {
  snapshot_id: string;
  provider: JobSource;
  native_id: string | null;
  original_url: string;
  title: string | null;
  company: string | null;
  description_text: string | null;
  original_description: string | null;
  raw_payload: Record<string, unknown> | null;
  retrieved_at: string;
  status: string;
  purged_at: string | null;
}

export interface AnalysisOccupation {
  soc_code: string;
  title: string;
}
export interface AnalysisMetadata {
  country: string | null;
  job_sources: JobSource[];
  evidence_sources: EvidenceSource[];
  onet_release: string | null;
  occupations: AnalysisOccupation[];
  created_at: string;
  updated_at: string;
}
export interface ExecutionStatus {
  status: "busy" | "idle";
  state_updated_at: string | null;
}
export type WorkspaceView = "overview" | "demand_importance" | "occupations" | "data";
export type WorkspaceMetric = "frequency" | "IM" | "LV";
export type InsightKind = "common_sample" | "occupation_difference" | "shared_importance";
export interface WorkspaceFilters {
  category_ids: string[];
  search: string;
  scope: "all" | "selected";
}
export interface DescriptorChoice {
  candidate_id: string;
  evidence_id: string;
}
export interface RunReviewContext {
  kind: "run_review";
  version: 1;
  intent: "explain" | "propose_selection";
  run_id: string;
  expected_candidate_revision: number;
  expected_selection_revision: number;
  view: WorkspaceView;
  focused_candidate_id: string | null;
  candidate_ids: string[];
  filters: WorkspaceFilters;
  occupation_codes: string[];
  metric: WorkspaceMetric;
  descriptor_choices: DescriptorChoice[];
  insight_kind: InsightKind | null;
  has_unsaved_changes: boolean;
}
export interface OccupationReferenceContext {
  kind: "occupation_reference";
  version: 1;
  intent: "explain";
  release: string;
  occupation_codes: string[];
  element_ids: string[];
  metric: "IM" | "LV";
}
export type WorkspaceContext = RunReviewContext | OccupationReferenceContext;
export interface ResolvedContextMetadata {
  kind: "run_review" | "occupation_reference";
  version: 1;
  intent: "explain" | "propose_selection";
  run_id: string | null;
  candidate_revision: number | null;
  selection_revision: number | null;
  release: string | null;
  view: string | null;
  metric: WorkspaceMetric;
  occupation_codes: string[];
  occupations: AnalysisOccupation[];
  candidate_ids: string[];
  candidate_labels: Record<string, string>;
  filters: WorkspaceFilters | null;
  descriptor_choices: DescriptorChoice[];
  insight_kind: InsightKind | null;
  matching_count: number;
  included_count: number;
  omitted_count: number;
  evidence_included_count: number;
  evidence_omitted_count: number;
  facts: Record<string, unknown>[];
  coverage: Record<string, unknown>;
  notices: string[];
}
export interface WorkspaceViewState {
  view: WorkspaceView;
  filters: WorkspaceFilters;
  focusedCandidateId: string | null;
  occupationCodes: string[];
  activeOccupationCode: string | null;
  metric: WorkspaceMetric;
  descriptorChoices: DescriptorChoice[];
  sort: {field: string; direction: "asc" | "desc"};
  page: number;
}

export type DescriptorKey = [release: string, family: string, elementId: string];
export type RatingResolution =
  | {status: "reported"; value: number; metric: "IM" | "LV"; evidence: OnetEvidence; descriptorKey: DescriptorKey}
  | {status: "missing" | "suppressed" | "not_relevant"; evidence: OnetEvidence; descriptorKey: DescriptorKey}
  | {status: "no_association"}
  | {status: "ambiguous"; evidence: OnetEvidence[]};
export interface PatternValue {
  candidate_id: string;
  occupation_code: string | null;
  value: number;
  supporting_count: number | null;
  assessed_count: number | null;
}
export interface PatternObservation {
  kind: InsightKind;
  candidate_ids: string[];
  occupation_codes: string[];
  descriptor_keys: DescriptorKey[];
  values: PatternValue[];
  coverage: {extraction_coverage: ExtractionCoverage; source_outcomes: Record<string, SourceOutcome>};
}
export interface NormalizedWorkspaceScope {
  candidates: SkillCandidate[];
  release: string | null;
  occupationCodes: string[];
  confirmedOccupationCodes: string[];
  metric: WorkspaceMetric;
  descriptorChoices: DescriptorChoice[];
  coverage: PatternObservation["coverage"];
}
export interface WorkspaceRow {
  candidateId: string;
  label: string;
  candidate: SkillCandidate;
  selected: boolean;
  demand: number | null;
  rating: RatingResolution;
  ratings: Record<string, RatingResolution>;
}
export interface WorkspacePage {
  rows: WorkspaceRow[];
  page: number;
  pageSize: number;
  pageCount: number;
  total: number;
  start: number;
  end: number;
}
export interface WorkspaceData {
  scope: NormalizedWorkspaceScope;
  rows: WorkspaceRow[];
  demandRows: WorkspaceRow[];
  scatterPoints: (WorkspaceRow & {demand: number; importance: number; importanceRating: Extract<RatingResolution, {status: "reported"}>})[];
  heatmapPage: WorkspacePage;
  tablePage: WorkspacePage;
  observations: PatternObservation[];
}

export interface ChartFocus {
  candidateId: string;
  occupationCode?: string;
  evidenceId?: string;
}
export interface WorkspaceQuestion {
  text: string;
  candidateIds?: string[];
  occupationCodes?: string[];
  insightKind?: PatternObservation["kind"];
}

export interface StreamFailure {
  code: string;
  message: string;
  recovery: string;
  status?: number;
}
export type SendCommand =
  | {mode: "workflow"; text: string}
  | {mode: "contextual"; text: string; context: WorkspaceContext};
export type SendResult = {outcome: "completed" | "failed" | "detached"; error?: StreamFailure};
export interface ExecutionObservation {
  status: ExecutionStatus["status"] | "unknown";
  state_updated_at: string | null;
  outcome: "completed" | "failed" | "unknown";
}
