import { useCallback, useEffect, useRef, useState } from "react";
import { deleteConversation, fetchAgentState, fetchConversationHistory, streamMarketDemandChat, fetchSkillReview } from "@/features/market-demand/api";
import { DEFAULT_MARKET_DEMAND_COUNTRY } from "@/features/market-demand/countries";
import type {
  AgentName,
  AgentState,
  ChatMessage,
  PipelineStageId,
  StageStatus,
  StreamEvent,
  ToolCall,
  SourceConfiguration,
  SkillReview,
} from "@/features/market-demand/types";

const EMPTY_STATE: AgentState = {
  course_id: null,
  course_title: null,
  course_description: null,
  job_search_country: DEFAULT_MARKET_DEMAND_COUNTRY,
  job_search_country_confirmed: false,
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

import { derivePipelineStages } from "@/features/market-demand/pipeline";

export interface UseAgentStreamReturn {
  isRestored: boolean;
  retryRestoration: () => void;
  skillReview: SkillReview | null;
  refreshSkillReview: () => Promise<void>;
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
  countryOverride: string | null = null,
  configurationOverride: SourceConfiguration | null = null
): UseAgentStreamReturn {
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [isRestored, setIsRestored] = useState(false);
  const reviewAbortRef = useRef<AbortController | null>(null);
  const [skillReview, setSkillReview] = useState<SkillReview | null>(null);
  const courseRef = useRef(courseId);
  const generationRef = useRef(0);
  const restoredRef = useRef(false);
  const reviewRequestRef = useRef(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentAgent, setCurrentAgent] = useState<AgentName | null>(null);
  const [agentState, setAgentState] = useState<AgentState>(EMPTY_STATE);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  // Refs for mutable state during streaming
  const messagesRef = useRef<ChatMessage[]>([]);
  const agentStateRef = useRef<AgentState>(EMPTY_STATE);

  const refreshSkillReview = useCallback(async () => {
    reviewAbortRef.current?.abort();
    const abort = new AbortController();
    reviewAbortRef.current = abort;
    const request = ++reviewRequestRef.current;
    const activeCourse = courseId;
    try {
      const snapshot = await fetchSkillReview(courseId, abort.signal);
      if (
        !abort.signal.aborted &&
        courseRef.current === activeCourse &&
        request === reviewRequestRef.current
      ) {
        setSkillReview(snapshot);
      }
    } catch (cause) {
      if (
        !abort.signal.aborted &&
        courseRef.current === activeCourse &&
        request === reviewRequestRef.current
      ) {
        setError(cause instanceof Error ? cause.message : "Failed to refresh skill review");
      }
      throw cause;
    }
  }, [courseId]);

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

      case "skill_review_changed": {
        void refreshSkillReview().catch(() => {});
        break;
      }

      case "stream_end": {
        setIsStreaming(false);
        setCurrentAgent(null);
        break;
      }
    }
  }, [refreshSkillReview]);

  // Load course-scoped conversation history whenever the course changes.
  useEffect(() => {
    let cancelled = false;
    const restoreAbort = new AbortController();
    courseRef.current = courseId;
    restoredRef.current = false;
    setIsRestored(false);
    reviewAbortRef.current?.abort();
    generationRef.current += 1;
    reviewRequestRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setSkillReview(null);
    setIsLoadingHistory(true);
    messagesRef.current = [];
    setMessages([]);
    agentStateRef.current = EMPTY_STATE;
    setAgentState(EMPTY_STATE);
    setThreadId(null);
    setCurrentAgent(null);
    setError(null);

    Promise.all([
      fetchConversationHistory(courseId),
      fetchAgentState(courseId),
      fetchSkillReview(courseId, restoreAbort.signal),
    ])
      .then(([historyData, stateData, reviewData]) => {
        if (cancelled) return;
        if (historyData.messages.length > 0) {
          messagesRef.current = historyData.messages;
          setMessages(historyData.messages);
        }
        if (historyData.threadId) {
          setThreadId(historyData.threadId);
        }
        // Restore agent state (pipeline progress, jobs, skills, etc.)
        setSkillReview(reviewData);
        restoredRef.current = true;
        setIsRestored(true);
        agentStateRef.current = stateData;
        setAgentState(stateData);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to restore conversation");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });

    return () => {
      cancelled = true;
      restoreAbort.abort();
      reviewAbortRef.current?.abort();
      restoredRef.current = false;
      generationRef.current += 1;
      reviewRequestRef.current += 1;
      abortRef.current?.abort();
    };
  }, [courseId, restoreAttempt]);

  const retryRestoration = useCallback(() => {
    setRestoreAttempt((attempt) => attempt + 1);
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (!restoredRef.current || courseRef.current !== courseId) return;
      abortRef.current?.abort();
      reviewAbortRef.current?.abort();
      reviewRequestRef.current += 1;
      const generation = ++generationRef.current;
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
          (agentStateRef.current.job_search_country_confirmed
            ? agentStateRef.current.job_search_country
            : null);
        const configuration: SourceConfiguration = configurationOverride ?? {
          sources: agentStateRef.current.sources ?? ["indeed", "linkedin"],
          evidence_sources: agentStateRef.current.evidence_sources ?? ["jobs"],
          onet_release: agentStateRef.current.onet_release ?? null,
          onet_occupation_codes: agentStateRef.current.selected_onet_occupations ?? [],
        };
        const isCurrent = () => !abort.signal.aborted && generation === generationRef.current && courseRef.current === courseId;
        await streamMarketDemandChat({
          ...configuration,
          courseId,
          message: text,
          country,
          signal: abort.signal,
          onThreadId: (id) => {if (isCurrent()) setThreadId(id);},
          onEvent: (event) => {if (isCurrent()) handleEvent(event);},
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
        if (!isAbort && generation === generationRef.current && courseRef.current === courseId) {
          const msg = e instanceof Error ? e.message : "Stream failed";
          setError(msg);
          console.error("Stream error:", e);
        }
      } finally {
        if (generation === generationRef.current && courseRef.current === courseId) {
          setIsStreaming(false);
          setCurrentAgent(null);
          abortRef.current = null;
        }
      }
    },
    [courseId, countryOverride, configurationOverride, handleEvent]
  );

  const stop = useCallback(() => {
    generationRef.current += 1;
    reviewRequestRef.current += 1;
    reviewAbortRef.current?.abort();
    abortRef.current?.abort();
    setIsStreaming(false);
    setCurrentAgent(null);
  }, []);

  const clearConversation = useCallback(async () => {
    stop();
    const generation = generationRef.current;
    try {
      await deleteConversation(courseId);
      if (generation !== generationRef.current || courseRef.current !== courseId) return;
      setSkillReview(null);
      messagesRef.current = [];
      setMessages([]);
      agentStateRef.current = EMPTY_STATE;
      setAgentState(EMPTY_STATE);
      setThreadId(null);
      setError(null);
    } catch (e) {
      if (generation !== generationRef.current || courseRef.current !== courseId) return;
      const msg = e instanceof Error ? e.message : "Failed to clear conversation";
      setError(msg);
      console.error("Clear conversation error:", e);
    }
  }, [courseId, stop]);

  const pipelineStages = derivePipelineStages(agentState);

  return {
    isRestored,
    retryRestoration,
    skillReview,
    refreshSkillReview,
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
