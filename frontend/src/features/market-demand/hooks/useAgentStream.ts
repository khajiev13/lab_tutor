import { useCallback, useEffect, useRef, useState } from "react";
import { deleteConversation, fetchAgentState, fetchConversationHistory, streamMarketDemandChat, fetchSkillReview, getMarketExecutionStatus, MarketDemandApiError } from "@/features/market-demand/api";
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
  SendCommand,
  SendResult,
  StreamFailure,
  ExecutionObservation,
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

function withCurrentPriorityStatus(state: AgentState, review: SkillReview | null): AgentState {
  const progress = state.skill_priority_status;
  if (!progress || progress.status !== "running") return state;
  const assessment = review?.priority_assessment;
  if (assessment?.assessment_id === progress.assessment_id && assessment.status !== "running") {
    return {...state, skill_priority_status: {...progress, status: assessment.status, message: ""}};
  }
  const deadline = Date.parse(progress.deadline_at);
  if (!Number.isFinite(deadline) || deadline <= Date.now()) {
    return {...state, skill_priority_status: {...progress, status: "unavailable", message: ""}};
  }
  return state;
}

export interface UseAgentStreamReturn {
  isRestored: boolean;
  resetRecovery: "none" | "required";
  retryRestoration: () => void;
  skillReview: SkillReview | null;
  refreshSkillReview: () => Promise<void>;
  applySkillReview: (review: SkillReview) => void;
  messages: ChatMessage[];
  isStreaming: boolean;
  isLoadingHistory: boolean;
  currentAgent: AgentName | null;
  agentState: AgentState;
  pipelineStages: Record<PipelineStageId, StageStatus>;
  threadId: string | null;
  send: (command: SendCommand) => Promise<SendResult>;
  closeLiveResponse: () => void;
  reconcile: () => Promise<void>;
  execution: ExecutionObservation;
  streamError: StreamFailure | null;
  recoverableCommand: SendCommand | null;
  stop: () => void;
  clearConversation: () => Promise<void>;
  error: string | null;
}

export function useAgentStream(
  courseId: number,
  countryOverride: string | null = null,
  configurationOverride: SourceConfiguration | null = null
): UseAgentStreamReturn {
  const [isRestored, setIsRestored] = useState(false);
  const [resetRecovery, setResetRecovery] = useState<"none" | "required">("none");
  const resetRecoveryStatusRef = useRef<ExecutionObservation["status"] | null>(null);
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
  const snapshotAbortRef = useRef<AbortController | null>(null);
  const snapshotRequestRef = useRef(0);
  const skillReviewRef = useRef<SkillReview | null>(null);
  const resetPendingRef = useRef(false);
  const terminalProofRef = useRef<{generation: number; runId: string | null; createdRun?: boolean; outcome: "completed" | "failed"} | null>(null);
  const busySinceRef = useRef<number | null>(null);
  const [streamGeneration, setStreamGeneration] = useState(0);
  const [execution, setExecution] = useState<ExecutionObservation>({status: "unknown", state_updated_at: null, outcome: "unknown"});
  const [streamError, setStreamError] = useState<StreamFailure | null>(null);
  const [recoverableCommand, setRecoverableCommand] = useState<SendCommand | null>(null);

  // Refs for mutable state during streaming
  const messagesRef = useRef<ChatMessage[]>([]);
  const agentStateRef = useRef<AgentState>(EMPTY_STATE);

  const reconcile = useCallback(async (retainTranscript = false) => {
    if (courseRef.current !== courseId) return;
    snapshotAbortRef.current?.abort();
    reviewAbortRef.current?.abort();
    reviewRequestRef.current += 1;
    const abort = new AbortController();
    snapshotAbortRef.current = abort;
    const request = ++snapshotRequestRef.current;
    const generation = generationRef.current;
    const ownsRequest = () => courseRef.current === courseId &&
      request === snapshotRequestRef.current && generation === generationRef.current;
    const isCurrent = () => !abort.signal.aborted && ownsRequest();
    restoredRef.current = false;
    setIsRestored(false);
    resetRecoveryStatusRef.current = null;
    setResetRecovery("none");
    let partialResetSignature: string | null = null;
    // One deadline covers both consistency reads, even if transport/auth ignores abort.
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timeout = setTimeout(() => {
        reject(new Error("Conversation restoration timed out. Retry restoration to try again."));
        abort.abort();
      }, 30000);
    });
    try {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const [history, state, review, status] = await Promise.race([Promise.all([
          fetchConversationHistory(courseId, abort.signal),
          fetchAgentState(courseId, abort.signal),
          fetchSkillReview(courseId, abort.signal),
          getMarketExecutionStatus(courseId, abort.signal).catch(() => ({status: "unknown" as const, state_updated_at: null})),
        ]), deadline]);
        if (!isCurrent()) return;
        const runId = state.run_id ?? null;
        const historicalRuns = [...new Set(history.messages.flatMap(message =>
          message.workspace_context?.run_id ? [message.workspace_context.run_id] : []))];
        // SQL reset can commit before checkpoint cleanup fails. This is reset-only recovery,
        // never permission to publish mismatched history/review or resume the former run.
        const emptyRunReview = runId === null && review?.run_id === null &&
          review.candidates.length === 0 && review.candidate_revision === 0 &&
          review.selection_revision === 0 && review.publication_revision === 0;
        const contextlessWorkflowHistory = emptyRunReview && history.messages.length > 0 &&
          history.messages.every(message => !message.workspace_context);
        const onlyCourseDefaults = state.job_search_country === EMPTY_STATE.job_search_country &&
          state.job_search_country_confirmed === false && state.job_search_location === EMPTY_STATE.job_search_location &&
          Object.entries(state).every(([key, value]) => ["course_id", "course_title", "course_description",
            "job_search_country", "job_search_country_confirmed", "job_search_location"].includes(key) || value == null);
        // Null run IDs also occur before a run exists. A successful SQL status read
        // distinguishes persisted pre-run state from absent state with retained checkpoints.
        if (contextlessWorkflowHistory && (status.status !== "idle" || status.state_updated_at === undefined)) {
          setExecution({...status, outcome: "unknown"});
          throw new Error("The analysis status could not be confirmed as idle. Refresh before changing this workspace.");
        }
        const absentWorkflowState = contextlessWorkflowHistory && status.state_updated_at === null;
        if (absentWorkflowState && (!onlyCourseDefaults || !history.threadId)) {
          throw new Error("Analysis changed during refresh. Refresh again before taking another action.");
        }
        const partialReset = emptyRunReview && !!history.threadId &&
          (historicalRuns.length === 1 || absentWorkflowState);
        if (partialReset) {
          const signature = JSON.stringify([history.threadId, historicalRuns[0], history.messages.map(message => message.id)]);
          if (attempt === 0) {partialResetSignature = signature; continue;}
          if (signature === partialResetSignature) {
            resetRecoveryStatusRef.current = status.status;
            setResetRecovery("required");
            setExecution({...status, outcome: "unknown"});
            throw new Error("The previous reset did not finish. Confirm a reset retry to start a new analysis. Your current workspace and question are retained until it succeeds.");
          }
          throw new Error("Conversation changed during refresh. Refresh again before taking another action.");
        }
        if ((review?.run_id ?? null) !== runId || history.messages.some(message =>
          message.workspace_context?.run_id && message.workspace_context.run_id !== runId)) {
          throw new Error("Conversation and review changed during refresh. Refresh again before taking another action.");
        }
        const sameRun = (skillReviewRef.current?.run_id ?? null) === runId;
        const current = skillReviewRef.current;
        if (sameRun && current && review && (
          review.candidate_revision < current.candidate_revision ||
          review.selection_revision < current.selection_revision ||
          review.publication_revision < current.publication_revision
        )) {
          // Discard every surface from this read; a newer SSE/acknowledgement set the floor.
          if (attempt === 0) continue;
          throw new Error("Review changed during refresh. Refresh again before taking another action.");
        }
        skillReviewRef.current = review;
        setSkillReview(review);
        agentStateRef.current = withCurrentPriorityStatus(state, review);
        setAgentState(agentStateRef.current);
        // An attached partial response is still useful while server history catches up.
        if (!retainTranscript || !sameRun || !messagesRef.current.length ||
          (status.status === "idle" && history.messages.some(message => message.id === messagesRef.current.at(-1)?.id))) {
          messagesRef.current = history.messages.map(message => ({...message, isStreaming: false,
            toolCalls: message.toolCalls.map(tool => ({...tool, status: tool.status === "loading" ? "unknown" : tool.status === "success" ? "finished" : tool.status}))}));
          setMessages(messagesRef.current);
        }
        setThreadId(history.threadId || null);
        const proof = terminalProofRef.current;
        const proven = proof?.generation === generation && (proof.runId === runId || (proof.createdRun && proof.runId === null));
        if (proven && proof) terminalProofRef.current = {...proof, runId, createdRun: false};
        setExecution({...status, outcome: proven && proof ? proof.outcome : "unknown"});
        if (!resetPendingRef.current) {
          restoredRef.current = true;
          setIsRestored(true);
        }
        break;
      }
    } catch (cause) {
      if (ownsRequest()) setError(cause instanceof Error ? cause.message : "Failed to restore conversation");
      throw cause;
    } finally {
      clearTimeout(timeout);
      if (ownsRequest()) setIsLoadingHistory(false);
    }
  }, [courseId]);

  const refreshSkillReview = useCallback(async () => {
    if (courseRef.current !== courseId) return;
    reviewAbortRef.current?.abort();
    const abort = new AbortController();
    reviewAbortRef.current = abort;
    const request = ++reviewRequestRef.current;
    const generation = generationRef.current;
    try {
      const snapshot = await fetchSkillReview(courseId, abort.signal);
      if (abort.signal.aborted || courseRef.current !== courseId || request !== reviewRequestRef.current || generation !== generationRef.current) return;
      if ((snapshot.run_id ?? null) !== (agentStateRef.current.run_id ?? null)) {
        await reconcile(true);
        return;
      }
      const current = skillReviewRef.current;
      if (current && (snapshot.candidate_revision < current.candidate_revision || snapshot.selection_revision < current.selection_revision || snapshot.publication_revision < current.publication_revision)) return;
      skillReviewRef.current = snapshot;
      setSkillReview(snapshot);
      agentStateRef.current = withCurrentPriorityStatus(agentStateRef.current, snapshot);
      setAgentState(agentStateRef.current);
    } catch (cause) {
      if (!abort.signal.aborted && courseRef.current === courseId && request === reviewRequestRef.current && generation === generationRef.current) {
        setError(cause instanceof Error ? cause.message : "Failed to refresh skill review");
      }
      throw cause;
    }
  }, [courseId, reconcile]);

  const applySkillReview = useCallback((snapshot: SkillReview) => {
    if (courseRef.current !== courseId || !restoredRef.current) return;
    reviewAbortRef.current?.abort();
    reviewRequestRef.current += 1;
    const current = skillReviewRef.current;
    if (!current || snapshot.run_id !== current.run_id ||
      snapshot.candidate_revision < current.candidate_revision ||
      snapshot.selection_revision < current.selection_revision ||
      snapshot.publication_revision < current.publication_revision) return;
    skillReviewRef.current = snapshot;
    setSkillReview(snapshot);
  }, [courseId]);

  const handleEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case "agent_start": {
        setCurrentAgent(event.agent);
        // Preserve uncertain tools across agent handoff; termination needs a matching result.
        messagesRef.current = messagesRef.current.map((m, idx) => {
          if (idx === messagesRef.current.length - 1 && m.role === "agent" && m.isStreaming) {
            return {
              ...m,
              isStreaming: false,
              toolCalls: m.toolCalls.map((tc) =>
                tc.status === "loading" ? { ...tc, status: "unknown" as const } : tc
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
        agentStateRef.current = withCurrentPriorityStatus({
          ...agentStateRef.current,
          [event.stateKey]: event.value,
        }, skillReviewRef.current);
        setAgentState({ ...agentStateRef.current });
        break;
      }

      case "skill_review_changed": {
        if (event.run_id === agentStateRef.current.run_id) void refreshSkillReview().catch(() => {});
        else void reconcile(true).catch(() => {});
        break;
      }
      case "context_resolved": {
        const index = messagesRef.current.map(message => message.role).lastIndexOf("user");
        if (index !== -1) {
          messagesRef.current = messagesRef.current.map((message, i) => i === index ? {...message, id: event.messageId, workspace_context: event.workspace_context} : message);
          setMessages(messagesRef.current);
        }
        break;
      }
      case "error": {
        setStreamError({code: event.code, message: event.message, recovery: event.recovery});
        setError(event.message);
        break;
      }
      case "stream_end": {
        if (event.outcome) {
          terminalProofRef.current = {generation: generationRef.current, runId: agentStateRef.current.run_id ?? null, outcome: event.outcome};
          setExecution(current => ({...current, outcome: event.outcome!}));
        }
        setIsStreaming(false);
        setCurrentAgent(null);
        break;
      }
    }
  }, [refreshSkillReview, reconcile]);

  // Restore all editable surfaces together; stale requests cannot update another course.
  useEffect(() => {
    courseRef.current = courseId;
    restoredRef.current = false;
    resetPendingRef.current = false;
    resetRecoveryStatusRef.current = null;
    setResetRecovery("none");
    terminalProofRef.current = null;
    busySinceRef.current = null;
    generationRef.current += 1;
    reviewRequestRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsRestored(false);
    setIsStreaming(false);
    skillReviewRef.current = null;
    setSkillReview(null);
    setIsLoadingHistory(true);
    messagesRef.current = [];
    setMessages([]);
    agentStateRef.current = EMPTY_STATE;
    setAgentState(EMPTY_STATE);
    setThreadId(null);
    setCurrentAgent(null);
    setError(null);
    setStreamError(null);
    setRecoverableCommand(null);
    setExecution({status: "unknown", state_updated_at: null, outcome: "unknown"});
    void reconcile().catch(() => {});
    return () => {
      snapshotAbortRef.current?.abort();
      reviewAbortRef.current?.abort();
      restoredRef.current = false;
      generationRef.current += 1;
      reviewRequestRef.current += 1;
      snapshotRequestRef.current += 1;
      abortRef.current?.abort();
    };
  }, [courseId, reconcile]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let requestAbort: AbortController | undefined;
    let requestSequence = 0;
    const generation = generationRef.current;
    if (execution.status === "busy" || isStreaming) busySinceRef.current ??= Date.now();
    else busySinceRef.current = null;
    const started = busySinceRef.current ?? Date.now();
    const isCurrent = () => !stopped && generation === generationRef.current && courseRef.current === courseId;
    const visible = () => document.visibilityState !== "hidden";
    const poll = async (refreshSnapshot = false) => {
      if (!isCurrent() || !visible()) return;
      const abort = new AbortController();
      requestAbort = abort;
      const request = ++requestSequence;
      const isCurrentPoll = () => isCurrent() && request === requestSequence && !abort.signal.aborted && visible();
      try {
        const status = await getMarketExecutionStatus(courseId, abort.signal);
        if (!isCurrentPoll()) return;
        setExecution(current => ({...current, ...status}));
        if (status.status === "idle") {
          if (!abortRef.current && (execution.status === "busy" || refreshSnapshot)) await reconcile(true);
          return;
        }
        timer = setTimeout(() => {void poll();}, Date.now() - started >= 30000 ? 10000 : 2000);
      } catch {
        if (isCurrentPoll()) setExecution(current => ({...current, status: "unknown", state_updated_at: null}));
      }
    };
    const onVisibility = () => {
      requestSequence += 1;
      clearTimeout(timer);
      requestAbort?.abort();
      if (visible()) void poll(true);
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (visible() && (execution.status === "busy" || isStreaming)) timer = setTimeout(() => {void poll();}, 2000);
    return () => {
      stopped = true;
      clearTimeout(timer);
      requestAbort?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [courseId, execution.status, isStreaming, streamGeneration, reconcile]);

  useEffect(() => {
    const progress = agentState.skill_priority_status;
    if (progress?.status !== "running") return;
    const remaining = Date.parse(progress.deadline_at) - Date.now();
    const timer = setTimeout(() => {
      agentStateRef.current = withCurrentPriorityStatus(agentStateRef.current, skillReviewRef.current);
      setAgentState(agentStateRef.current);
    }, Math.max(0, Math.min(remaining, 2_147_483_647)));
    return () => clearTimeout(timer);
  }, [agentState.skill_priority_status]);

  const retryRestoration = useCallback(() => {
    if (courseRef.current !== courseId) return;
    setIsLoadingHistory(true);
    setError(null);
    void reconcile(true).catch(() => {});
  }, [courseId, reconcile]);

  const finishMessages = useCallback(() => {
    messagesRef.current = messagesRef.current.map(message => ({...message, isStreaming: false,
      toolCalls: message.toolCalls.map(tool => tool.status === "loading" ? {...tool, status: "unknown"} : tool)}));
    setMessages(messagesRef.current);
  }, []);

  const send = useCallback(async (command: SendCommand): Promise<SendResult> => {
    if (!restoredRef.current || resetPendingRef.current || courseRef.current !== courseId) return {outcome: "detached"};
    abortRef.current?.abort();
    snapshotAbortRef.current?.abort();
    snapshotRequestRef.current += 1;
    reviewAbortRef.current?.abort();
    reviewRequestRef.current += 1;
    const generation = ++generationRef.current;
    const initialRunId = agentStateRef.current.run_id ?? null;
    setStreamGeneration(generation);
    terminalProofRef.current = null;
    setError(null);
    setStreamError(null);
    setRecoverableCommand(command);
    setExecution(current => ({...current, outcome: "unknown"}));
    if (command.text) {
      messagesRef.current = [...messagesRef.current, {id: `user-${generation}-${Date.now()}`, role: "user", content: command.text, toolCalls: [], isStreaming: false}];
      setMessages(messagesRef.current);
    }
    setIsStreaming(true);
    const abort = new AbortController();
    abortRef.current = abort;
    const isCurrent = () => !abort.signal.aborted && generation === generationRef.current && courseRef.current === courseId;
    const result: SendResult = {outcome: "detached"};
    let failure: StreamFailure | undefined;
    try {
      const callbacks = {
        courseId, message: command.text, signal: abort.signal,
        onThreadId: (id: string) => {if (isCurrent()) setThreadId(id);},
        onEvent: (event: StreamEvent) => {
          if (!isCurrent()) return;
          if (event.type === "stream_end" && event.outcome) result.outcome = event.outcome;
          if (event.type === "error") failure = {code: event.code, message: event.message, recovery: event.recovery};
          handleEvent(event);
          if (event.type === "stream_end" && event.outcome && terminalProofRef.current) {
            terminalProofRef.current.createdRun = command.mode === "workflow" && initialRunId === null;
          }
        },
      };
      if (command.mode === "contextual") {
        await streamMarketDemandChat({...callbacks, mode: "contextual", workspace_context: command.context});
      } else {
        const country = countryOverride ?? (agentStateRef.current.job_search_country_confirmed ? agentStateRef.current.job_search_country : null);
        const configuration = configurationOverride ?? {
          sources: agentStateRef.current.sources ?? ["indeed", "linkedin", "headhunter"],
          evidence_sources: agentStateRef.current.evidence_sources ?? ["jobs"],
          onet_release: agentStateRef.current.onet_release ?? null,
          onet_occupation_codes: agentStateRef.current.selected_onet_occupations ?? [],
        };
        await streamMarketDemandChat({...callbacks, ...configuration, mode: "workflow", country});
      }
    } catch (cause) {
      if (isCurrent()) {
        if (cause instanceof MarketDemandApiError && (cause.status === 409 || cause.status === 422)) result.outcome = "failed";
        failure = cause instanceof MarketDemandApiError ? {status: cause.status, code: cause.code, message: cause.message, recovery: cause.recovery} : {
          code: "connection_lost", message: cause instanceof Error ? cause.message : "Response disconnected", recovery: "Refresh conversation and review before retrying.",
        };
        setError(failure.message);
        setStreamError(failure);
      }
    } finally {
      if (isCurrent()) {
        setIsStreaming(false);
        setCurrentAgent(null);
        abortRef.current = null;
        finishMessages();
        if (result.outcome === "completed") setRecoverableCommand(null);
        else if (!failure) setError(result.outcome === "failed" ? "Response failed. Refresh before retrying." : "Response disconnected before completion. Refresh before retrying.");
        await reconcile(true).catch(() => {});
      }
    }
    if (abort.signal.aborted || generation !== generationRef.current || courseRef.current !== courseId) return {outcome: "detached"};
    return {...result, ...(failure ? {error: failure} : {})};
  }, [courseId, countryOverride, configurationOverride, handleEvent, finishMessages, reconcile]);

  const closeLiveResponse = useCallback(() => {
    if (courseRef.current !== courseId) return;
    generationRef.current += 1;
    setStreamGeneration(generationRef.current);
    terminalProofRef.current = null;
    reviewRequestRef.current += 1;
    reviewAbortRef.current?.abort();
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
    setCurrentAgent(null);
    finishMessages();
    setExecution(current => ({...current, outcome: "unknown"}));
    void reconcile(true).catch(() => {});
  }, [courseId, finishMessages, reconcile]);

  const clearConversation = useCallback(async () => {
    if (courseRef.current !== courseId || resetPendingRef.current || (!restoredRef.current && resetRecoveryStatusRef.current === null)) throw new Error("Workspace reset unavailable");
    if (abortRef.current || execution.status === "busy") throw new MarketDemandApiError(409, "execution_busy", "Analysis is still running", "Refresh execution status before starting a new analysis.");
    const generation = generationRef.current;
    const wasRestored = restoredRef.current;
    resetPendingRef.current = true;
    restoredRef.current = false;
    setIsRestored(false);
    try {
      if (!wasRestored) {
        // The teacher explicitly confirmed retry. Recheck ownership/partial shape/status,
        // keeping every ordinary mutation blocked throughout these bounded reads.
        const recovery = reconcile();
        const request = snapshotRequestRef.current;
        try {await recovery;} catch (cause) {
          if (generation !== generationRef.current || courseRef.current !== courseId) return;
          if (request !== snapshotRequestRef.current || resetRecoveryStatusRef.current === null) throw cause;
        }
        if (generation !== generationRef.current || courseRef.current !== courseId) return;
        if (request !== snapshotRequestRef.current) throw new Error("Workspace changed while checking reset. Refresh before retrying.");
        if (resetRecoveryStatusRef.current === "busy") throw new MarketDemandApiError(409, "execution_busy", "Analysis is still running", "Refresh execution status before starting a new analysis.");
        // Unknown status is not success; the DELETE lease guard remains authoritative.
      }
      await deleteConversation(courseId);
      if (generation !== generationRef.current || courseRef.current !== courseId) return;
      snapshotAbortRef.current?.abort();
      snapshotRequestRef.current += 1;
      reviewAbortRef.current?.abort();
      reviewRequestRef.current += 1;
      terminalProofRef.current = null;
      resetRecoveryStatusRef.current = null;
      setResetRecovery("none");
      skillReviewRef.current = null;
      setSkillReview(null);
      messagesRef.current = [];
      setMessages([]);
      agentStateRef.current = EMPTY_STATE;
      setAgentState(EMPTY_STATE);
      setThreadId(null);
      setError(null);
      setStreamError(null);
      setRecoverableCommand(null);
      setExecution({status: "idle", state_updated_at: null, outcome: "unknown"});
      restoredRef.current = true;
      setIsRestored(true);
    } catch (cause) {
      if (generation === generationRef.current && courseRef.current === courseId) {
        if (cause instanceof MarketDemandApiError && cause.status === 409) {
          restoredRef.current = wasRestored;
          setIsRestored(wasRestored);
        } else {
          try {
            const recovery = reconcile();
            const request = snapshotRequestRef.current;
            await recovery;
            if (generation === generationRef.current && courseRef.current === courseId && request === snapshotRequestRef.current) {
              restoredRef.current = true;
              setIsRestored(true);
            }
          } catch { /* Failed recovery keeps ordinary mutations blocked. */ }
        }
        if (generation === generationRef.current && courseRef.current === courseId) {
          setError(cause instanceof Error ? cause.message : "Failed to clear conversation");
        }
      }
      throw cause;
    } finally {
      if (generation === generationRef.current && courseRef.current === courseId) resetPendingRef.current = false;
    }
  }, [courseId, execution.status, reconcile]);

  const pipelineStages = derivePipelineStages(agentState);

  return {
    isRestored,
    resetRecovery,
    retryRestoration,
    skillReview,
    refreshSkillReview,
    applySkillReview,
    messages,
    isStreaming,
    isLoadingHistory,
    currentAgent,
    agentState,
    pipelineStages,
    threadId,
    send,
    stop: closeLiveResponse,
    closeLiveResponse,
    reconcile,
    execution,
    streamError,
    recoverableCommand,
    clearConversation,
    error,
  };
}
