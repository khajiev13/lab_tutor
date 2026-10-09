// SSE event types from the backend
export type AgentName =
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
  | { type: "tool_end"; toolCallId: string; toolName: string; result: unknown; status: "success" | "error" }
  | { type: "state_update"; stateKey: string; value: unknown }
  | { type: "skill_review_changed"; run_id: string; candidate_revision: number; selection_revision: number; publication_revision: number }
  | { type: "stream_end" };

// Chat message model
export type ToolCallStatus = "loading" | "success" | "error";

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
  evidence_references: Record<string, unknown>[];
  job_metrics: Record<string, unknown>;
  onet_associations: Record<string, unknown>[];
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
export interface SkillReview {
  run_id: string | null;
  candidate_revision: number;
  selection_revision: number;
  categories: SkillCategory[];
  candidates: SkillCandidate[];
  selected_candidate_ids: string[];
  excluded_candidate_ids: string[];
  recommendations: RecommendationProposal[];
  source_outcomes: Record<string, SourceOutcome>;
  extraction_coverage: Record<string, unknown>;
  integration_review: Record<string, unknown> | null;
  publication_revision: number;
  approved_references: Record<string, unknown>[];
}
export interface SkillReviewDraft {
  run_id: string;
  expected_candidate_revision: number;
  expected_selection_revision: number;
  selected_candidate_ids: string[];
  excluded_candidate_ids: string[];
}
