import { cn } from "@/lib/utils";
import {
  AgentResponse,
  type ToolCall as AgentToolCall,
} from "@/components/ui/agent-response";
import { Loader } from "@/components/ui/loader";
import { AGENT_IDENTITIES } from "../agent-config";
import type { ChatMessage, ToolCall } from "../types";

const TOOL_LABELS: Record<string, string> = {
  fetch_jobs: "Fetch Jobs",
  select_jobs_by_group: "Select Job Groups",
  start_extraction: "Extract Skills",
  list_chapters: "Load Curriculum Chapters",
  get_chapter_details: "Review Chapter Details",
  get_section_concepts: "Load Section Concepts",
  check_skills_coverage: "Check Skill Coverage",
  get_extracted_skills: "Review Extracted Skills",
  save_curriculum_mapping: "Save Curriculum Mapping",
  approve_skill_selection: "Approve Skill Selection",
  load_mapped_skills: "Load Mapped Skills",
  load_existing_skills_for_chapters: "Load Existing Chapter Skills",
  compare_and_clean: "Clean Redundant Skills",
  finalize_cleaned_skills: "Finalize Skill Set",
  extract_concepts_for_skills: "Link Skills to Concepts",
  insert_market_skills_to_neo4j: "Update Knowledge Map",
  delete_market_skills: "Remove Market Skills",
  show_current_state: "Review Pipeline State",
  save_skills_for_insertion: "Save Skills for Insertion",
};

function mapToolCalls(toolCalls: ToolCall[]): AgentToolCall[] {
  return toolCalls.map((tc) => ({
    id: tc.id,
    name: TOOL_LABELS[tc.name] ?? tc.name,
    input: tc.args,
    output: tc.result,
    status:
      tc.status === "loading"
        ? "running"
        : tc.status === "success"
          ? "completed"
          : "failed",
  }));
}

interface AgentMessageProps {
  message: ChatMessage;
}

export function AgentMessage({ message }: AgentMessageProps) {
  const identity = message.agent ? AGENT_IDENTITIES[message.agent] : null;

  const Icon = identity?.icon;

  const agentAvatar = (
    <div
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2",
        identity?.bgColor ?? "bg-muted",
        identity?.borderColor ?? "border-muted"
      )}
    >
      {Icon ? (
        <Icon className={cn("size-4", identity?.accentColor)} />
      ) : (
        <span className="text-sm">🤖</span>
      )}
    </div>
  );

  // Loading state: no content yet, no tool calls
  if (!message.content && message.toolCalls.length === 0 && message.isStreaming) {
    return (
      <div className="flex items-center gap-3 px-4 py-2">
        {agentAvatar}
        <Loader variant="typing" size="sm" />
      </div>
    );
  }

  return (
    <AgentResponse
      message={message.content}
      toolCalls={mapToolCalls(message.toolCalls)}
      isStreaming={message.isStreaming}
      avatar={agentAvatar}
      agentName={identity?.displayName || message.agentDisplayName || "Agent"}
    />
  );
}
