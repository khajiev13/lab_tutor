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
