import { useCallback, useEffect, useRef, useState } from "react";
import { deleteConversation, fetchAgentState, fetchConversationHistory, streamMarketDemandChat } from "../api";
import { DEFAULT_MARKET_DEMAND_COUNTRY } from "../countries";
import type {
  AgentName,
  AgentState,
  ChatMessage,
  PipelineStageId,
  StageStatus,
  StreamEvent,
  ToolCall,
} from "../types";

const EMPTY_STATE: AgentState = {
  course_id: null,
  course_title: null,
  course_description: null,
  job_search_country: DEFAULT_MARKET_DEMAND_COUNTRY,
  job_search_location: "United States",
  fetched_jobs: null,
  job_groups: null,
  selected_jobs: null,
  extracted_skills: null,
  total_jobs_for_extraction: null,
  existing_graph_skills: null,
  existing_concepts: null,
  curriculum_mapping: null,
  selected_for_insertion: null,
  skill_concepts: null,
  insertion_results: null,
  skill_job_urls: null,
};

function derivePipelineStages(state: AgentState): Record<PipelineStageId, StageStatus> {
  const stages: Record<PipelineStageId, StageStatus> = {
    fetch: "pending",
    select: "pending",
    extract: "pending",
    map: "pending",
    approve: "pending",
    link: "pending",
    insert: "pending",
  };

  if (state.fetched_jobs) stages.fetch = "complete";
  if (state.selected_jobs) stages.select = "complete";
  if (state.extracted_skills) stages.extract = "complete";
  if (state.curriculum_mapping) stages.map = "complete";
  if (state.selected_for_insertion) stages.approve = "complete";
  if (state.skill_concepts) stages.link = "complete";
  if (state.insertion_results) stages.insert = "complete";

  // Find first pending to mark active
  const order: PipelineStageId[] = ["fetch", "select", "extract", "map", "approve", "link", "insert"];
  for (const id of order) {
    if (stages[id] === "pending") {
      stages[id] = "active";
      break;
    }
  }

  return stages;
}

export interface UseAgentStreamReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  isLoadingHistory: boolean;
  currentAgent: AgentName | null;
  agentState: AgentState;
  pipelineStages: Record<PipelineStageId, StageStatus>;
  threadId: string | null;
  send: (text: string) => Promise<void>;
  stop: () => void;
  clearConversation: () => Promise<void>;
  error: string | null;
}

export function useAgentStream(
  courseId: number,
  countryOverride: string | null = null
): UseAgentStreamReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<AgentName | null>(null);
  const [agentState, setAgentState] = useState<AgentState>(EMPTY_STATE);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Refs for mutable state during streaming
  const messagesRef = useRef<ChatMessage[]>([]);
  const agentStateRef = useRef<AgentState>(EMPTY_STATE);

  const handleEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case "agent_start": {
        setCurrentAgent(event.agent);
        // Resolve any pending tool calls and stop streaming on the previous agent message.
        // Handoff tools (transfer_to_*) never emit tool_end, so we close them out here.
        messagesRef.current = messagesRef.current.map((m, idx) => {
          if (idx === messagesRef.current.length - 1 && m.role === "agent" && m.isStreaming) {
            return {
              ...m,
              isStreaming: false,
              toolCalls: m.toolCalls.map((tc) =>
                tc.status === "loading" ? { ...tc, status: "success" as const } : tc
              ),
            };
          }
          return m;
        });
        const newMsg: ChatMessage = {
          id: event.messageId,
          role: "agent",
          agent: event.agent,
          agentDisplayName: event.displayName,
          agentEmoji: event.emoji,
          content: "",
          toolCalls: [],
          isStreaming: true,
        };
        messagesRef.current = [...messagesRef.current, newMsg];
        setMessages(messagesRef.current);
        break;
      }

      case "text_delta": {
        messagesRef.current = messagesRef.current.map((m) =>
          m.id === event.messageId
            ? { ...m, content: m.content + event.delta }
            : m
        );
        setMessages([...messagesRef.current]);
        break;
      }

      case "text_done": {
        messagesRef.current = messagesRef.current.map((m) =>
          m.id === event.messageId ? { ...m, isStreaming: false } : m
        );
        setMessages([...messagesRef.current]);
        break;
      }

      case "tool_start": {
        const toolCall: ToolCall = {
          id: event.toolCallId,
          name: event.toolName,
          args: event.args,
          status: "loading",
        };
        // Attach tool call to the last agent message
        messagesRef.current = messagesRef.current.map((m, idx) =>
          idx === messagesRef.current.length - 1 && m.role === "agent"
            ? { ...m, toolCalls: [...m.toolCalls, toolCall] }
            : m
        );
        // If no agent message exists yet, create one
        if (
          messagesRef.current.length === 0 ||
          messagesRef.current[messagesRef.current.length - 1].role !== "agent"
        ) {
          const newMsg: ChatMessage = {
            id: `tc-${event.toolCallId}`,
            role: "agent",
            agent: event.agent,
            content: "",
            toolCalls: [toolCall],
            isStreaming: true,
          };
          messagesRef.current = [...messagesRef.current, newMsg];
        }
        setMessages([...messagesRef.current]);
        break;
      }

      case "tool_end": {
        messagesRef.current = messagesRef.current.map((m) => ({
          ...m,
          toolCalls: m.toolCalls.map((tc) =>
            tc.id === event.toolCallId
              ? { ...tc, status: event.status, result: event.result }
              : tc
          ),
        }));
        setMessages([...messagesRef.current]);
        break;
      }

      case "tool_args_update": {
        // Update tool call args with the full accumulated args from backend
        messagesRef.current = messagesRef.current.map((m) => ({
          ...m,
          toolCalls: m.toolCalls.map((tc) =>
            tc.id === event.toolCallId
              ? { ...tc, args: event.args }
              : tc
          ),
        }));
        setMessages([...messagesRef.current]);
        break;
      }

      case "state_update": {
        agentStateRef.current = {
          ...agentStateRef.current,
          [event.stateKey]: event.value,
        };
        setAgentState({ ...agentStateRef.current });
        break;
      }

      case "stream_end": {
        setIsStreaming(false);
        setCurrentAgent(null);
        break;
      }
    }
  }, []);

  // Load course-scoped conversation history whenever the course changes.
  useEffect(() => {
    let cancelled = false;
    setIsLoadingHistory(true);
    messagesRef.current = [];
    setMessages([]);
    agentStateRef.current = EMPTY_STATE;
    setAgentState(EMPTY_STATE);
    setThreadId(null);
    setCurrentAgent(null);
    setError(null);

    Promise.all([fetchConversationHistory(courseId), fetchAgentState(courseId)])
      .then(([historyData, stateData]) => {
        if (cancelled) return;
        if (historyData.messages.length > 0) {
          messagesRef.current = historyData.messages;
          setMessages(historyData.messages);
        }
        if (historyData.threadId) {
          setThreadId(historyData.threadId);
        }
        // Restore agent state (pipeline progress, jobs, skills, etc.)
        agentStateRef.current = stateData;
        setAgentState(stateData);
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Failed to load history:", err);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [courseId]);

  const send = useCallback(
    async (text: string) => {
      setError(null);

      // Add user message (skip for initial empty greeting)
      if (text) {
        const userMsg: ChatMessage = {
          id: `user-${Date.now()}`,
          role: "user",
          content: text,
          toolCalls: [],
          isStreaming: false,
        };
        messagesRef.current = [...messagesRef.current, userMsg];
        setMessages(messagesRef.current);
      }

      setIsStreaming(true);
      const abort = new AbortController();
      abortRef.current = abort;

      try {
        const country =
          countryOverride ??
          agentStateRef.current.job_search_country ??
          DEFAULT_MARKET_DEMAND_COUNTRY;
        await streamMarketDemandChat({
          courseId,
          message: text,
          country,
          signal: abort.signal,
          onThreadId: (id) => setThreadId(id),
          onEvent: handleEvent,
          onError: (err) => {
            console.error("Stream event error:", err);
          },
        });
      } catch (e) {
        const isAbort =
          typeof e === "object" &&
          e !== null &&
          "name" in e &&
          (e as { name: string }).name === "AbortError";
        if (!isAbort) {
          const msg = e instanceof Error ? e.message : "Stream failed";
          setError(msg);
          console.error("Stream error:", e);
        }
      } finally {
        setIsStreaming(false);
        setCurrentAgent(null);
      }
    },
    [courseId, countryOverride, handleEvent]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setCurrentAgent(null);
  }, []);

  const clearConversation = useCallback(async () => {
    try {
      await deleteConversation(courseId);
      messagesRef.current = [];
      setMessages([]);
      agentStateRef.current = EMPTY_STATE;
      setAgentState(EMPTY_STATE);
      setThreadId(null);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to clear conversation";
      setError(msg);
      console.error("Clear conversation error:", e);
    }
  }, [courseId]);

  const pipelineStages = derivePipelineStages(agentState);

  return {
    messages,
    isStreaming,
    isLoadingHistory,
    currentAgent,
    agentState,
    pipelineStages,
    threadId,
    send,
    stop,
    clearConversation,
    error,
  };
}
