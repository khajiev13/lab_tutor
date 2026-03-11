import { cn } from "@/lib/utils";
import {
  AgentResponse,
  type ToolCall as AgentToolCall,
} from "@/components/ui/agent-response";
import { Loader } from "@/components/ui/loader";
import { AGENT_IDENTITIES } from "../agent-config";
import type { ChatMessage, ToolCall } from "../types";

function mapToolCalls(toolCalls: ToolCall[]): AgentToolCall[] {
  return toolCalls.map((tc) => ({
    id: tc.id,
    name: tc.name,
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
