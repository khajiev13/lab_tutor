import { cn } from "@/lib/utils";
import { AgentResponse } from "@/components/ui/agent-response";
import { Loader } from "@/components/ui/loader";
import { AGENT_IDENTITIES } from "@/features/market-demand/agent-config";
import type { ChatMessage, ToolCall } from "@/features/market-demand/types";

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

const TOOL_STATUS: Record<ToolCall["status"], string> = {
  loading: "Running", finished: "Finished", success: "Finished", error: "Failed", unknown: "Outcome unknown",
};

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
        <div><p className="text-sm font-medium">{identity?.displayName || message.agentDisplayName || "Agent"} · Preparing response</p><Loader variant="typing" size="sm" /></div>
      </div>
    );
  }

  return (
    <div>
    <AgentResponse
      message={message.content}
      toolCalls={[]}
      isStreaming={message.isStreaming}
      avatar={agentAvatar}
      agentName={identity?.displayName || message.agentDisplayName || "Agent"}
    />
    {message.toolCalls.length > 0 && <div className="space-y-2 px-4 pb-3">
      {message.toolCalls.map(tool => <details key={tool.id} className="rounded-md border p-2 text-sm">
        <summary className="cursor-pointer">{TOOL_LABELS[tool.name] ?? tool.name} · {TOOL_STATUS[tool.status]}</summary>
        <p className="mt-2 font-medium">Input</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(tool.args, null, 2)}</pre>
        {tool.result !== undefined && <><p className="mt-2 font-medium">Returned details</p><pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all text-xs">{typeof tool.result === "string" ? tool.result : JSON.stringify(tool.result, null, 2)}</pre></>}
      </details>)}
    </div>}
    </div>
  );
}
