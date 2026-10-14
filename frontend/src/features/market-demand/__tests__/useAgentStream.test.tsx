import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentState, SendResult, WorkspaceContext, StreamEvent, ResolvedContextMetadata, SkillReview } from "@/features/market-demand/types";
import { reviewFixture } from "@/features/market-demand/__tests__/review-fixtures";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
import {
  getMarketExecutionStatus,
  MarketDemandApiError,
  deleteConversation,
  fetchSkillReview,
  fetchAgentState,
  fetchConversationHistory,
  streamMarketDemandChat,
} from "@/features/market-demand/api";

vi.mock("@/features/market-demand/api", async () => ({
  ...await vi.importActual("@/features/market-demand/api"),
  getMarketExecutionStatus: vi.fn(),
  deleteConversation: vi.fn(),
  fetchSkillReview: vi.fn(),
  fetchAgentState: vi.fn(),
  fetchConversationHistory: vi.fn(),
  streamMarketDemandChat: vi.fn(async () => undefined),
}));

const EMPTY_STATE: AgentState = {
  course_id: null,
  course_title: null,
  course_description: null,
  job_search_country: "USA",
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

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "idle", state_updated_at: null});
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "thread-1"});
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  vi.mocked(fetchSkillReview).mockResolvedValue({
    run_id: null,
    candidate_revision: 0,
    selection_revision: 0,
    categories: [],
    candidates: [],
    selected_candidate_ids: [],
    excluded_candidate_ids: [],
    recommendations: [],
    source_outcomes: {},
    extraction_coverage: {},
    integration_review: null,
    publication_revision: 0,
    approved_references: [],
  });
  vi.mocked(streamMarketDemandChat).mockResolvedValue(undefined);
});

describe("useAgentStream country selection", () => {
  it("does not send the default country before the teacher confirms a country", async () => {
    const { result } = renderHook(() => useAgentStream(1));

    await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
    await act(async () => {
      await result.current.send({mode: "workflow", text: "Analyze the job market"});
    });

    expect(streamMarketDemandChat).toHaveBeenCalledWith(
      expect.objectContaining({
        country: null,
      })
    );
  });

  it("sends the country override when the teacher selects one", async () => {
    const { result } = renderHook(() => useAgentStream(1, "China"));

    await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
    await act(async () => {
      await result.current.send({mode: "workflow", text: "Analyze the job market"});
    });

    expect(streamMarketDemandChat).toHaveBeenCalledWith(
      expect.objectContaining({
        country: "China",
      })
    );
  });
});

it("restores provider choices and ignores cancelled stream callbacks", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId:"t"});
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, sources:["headhunter"], evidence_sources:["jobs", "onet"], onet_release:"31.0", selected_onet_occupations:["15-2051.00"]});
  let finish!: () => void;
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(() => new Promise<void>(r => {finish=r;}));
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  let pending!: Promise<SendResult>;
  act(() => {pending=result.current.send({mode: "workflow", text: "Analyze"});});
  expect(streamMarketDemandChat).toHaveBeenLastCalledWith(expect.objectContaining({sources:["headhunter"], evidence_sources:["jobs","onet"], onet_release:"31.0", onet_occupation_codes:["15-2051.00"]}));
  const old = vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  act(() => {result.current.stop(); old.onEvent({type:"state_update",stateKey:"fetched_jobs",value:[{title:"stale"}]});});
  expect(result.current.agentState.fetched_jobs).toBeNull();
  await act(async () => {finish(); await pending;});
});

it("aborts a previous course stream and prevents its finally clearing a newer stream", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages:[], threadId:"t"});
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  const finishes: (() => void)[]=[];
  vi.mocked(streamMarketDemandChat).mockImplementation(() => new Promise<void>(r => finishes.push(r)));
  const {result,rerender}=renderHook(({id})=>useAgentStream(id),{initialProps:{id:1}});
  await waitFor(()=>expect(result.current.isLoadingHistory).toBe(false));
  let first!:Promise<SendResult>; act(()=>{first=result.current.send({mode: "workflow", text: "First"});});
  const args=vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  rerender({id:2});
  await waitFor(()=>expect(result.current.isLoadingHistory).toBe(false));
  expect(args.signal?.aborted).toBe(true);
  let second!:Promise<SendResult>; act(()=>{second=result.current.send({mode: "workflow", text: "Second"});});
  await act(async()=>{finishes[0](); await first;});
  expect(result.current.isStreaming).toBe(true);
  await act(async()=>{finishes[1](); await second;});
});

it("refuses sends until restoration succeeds", async () => {
 vi.mocked(streamMarketDemandChat).mockResolvedValue(undefined);
 let restore!: (value:AgentState)=>void;
 vi.mocked(fetchConversationHistory).mockResolvedValue({messages:[],threadId:"t"});
 vi.mocked(fetchAgentState).mockImplementationOnce(()=>new Promise(r=>{restore=r;}));
 const {result}=renderHook(()=>useAgentStream(1));
 const before=vi.mocked(streamMarketDemandChat).mock.calls.length;
 await act(async()=>{await result.current.send({mode: "workflow", text: "Too early"});});
 expect(vi.mocked(streamMarketDemandChat).mock.calls.length).toBe(before);
 await act(async()=>{restore(EMPTY_STATE);});
});


it("restores the coherent review and refetches the latest SSE revision", async () => {
 const emptyReview = {run_id:"run-1",candidate_revision:1,selection_revision:0,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]};
 vi.mocked(fetchSkillReview).mockResolvedValueOnce(emptyReview).mockResolvedValueOnce({...emptyReview,candidate_revision:2});
 vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-1"});
 vi.mocked(fetchConversationHistory).mockResolvedValue({messages:[],threadId:"t"});
 let finish!:()=>void;
 vi.mocked(streamMarketDemandChat).mockImplementationOnce(()=>new Promise(r=>{finish=r;}));
 const {result}=renderHook(()=>useAgentStream(1));
 await waitFor(()=>expect(result.current.skillReview?.candidate_revision).toBe(1));
 let pending!:Promise<SendResult>; act(()=>{pending=result.current.send({mode: "workflow", text: "Analyze"});});
 const args=vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
 act(()=>args.onEvent({type:"skill_review_changed",run_id:"run-1",candidate_revision:2,selection_revision:0,publication_revision:0}));
 await waitFor(()=>expect(result.current.skillReview?.candidate_revision).toBe(2));
 await act(async()=>{finish();await pending;});
});

it("keeps restoration unavailable after state loading fails", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "t"});
  vi.mocked(fetchAgentState).mockRejectedValueOnce(new Error("State unavailable"));
  vi.mocked(fetchSkillReview).mockResolvedValue(null as never);
  vi.mocked(streamMarketDemandChat).mockResolvedValue(undefined);
  const before = vi.mocked(streamMarketDemandChat).mock.calls.length;
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.error).toBe("State unavailable"));
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(vi.mocked(streamMarketDemandChat).mock.calls.length).toBe(before);
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  await act(async () => {result.current.retryRestoration();});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
});

it.each(["history", "state", "review", "status"] as const)("ends restoration when the %s read never settles, even if it ignores abort", async (read) => {
  const reads = {history: fetchConversationHistory, state: fetchAgentState, review: fetchSkillReview, status: getMarketExecutionStatus};
  vi.mocked(reads[read]).mockImplementationOnce(() => new Promise<never>(() => {}));
  vi.useFakeTimers();
  const {result, unmount} = renderHook(() => useAgentStream(1));
  try {
    await act(async () => {await vi.advanceTimersByTimeAsync(29999);});
    expect(result.current.isLoadingHistory).toBe(true);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.isRestored).toBe(false);
    expect(result.current.error).toMatch(/restor.*timed out/i);
    expect(result.current.execution.outcome).toBe("unknown");
    for (const fetchRead of Object.values(reads)) {
      expect(vi.mocked(fetchRead).mock.calls[0][1]?.aborted).toBe(true);
    }
    await act(async () => {
      expect(await result.current.send({mode: "workflow", text: "Wait for restoration"})).toEqual({outcome: "detached"});
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(streamMarketDemandChat).not.toHaveBeenCalled();
    expect(deleteConversation).not.toHaveBeenCalled();
    for (const fetchRead of Object.values(reads)) expect(fetchRead).toHaveBeenCalledTimes(1);
  } finally {unmount(); vi.useRealTimers();}
});

it("does not treat an aborted status read as successful restoration at the deadline", async () => {
  vi.mocked(getMarketExecutionStatus).mockImplementationOnce((_courseId, signal) => new Promise((_resolve, reject) => {
    signal?.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), {once: true});
  }));
  vi.useFakeTimers();
  const {result, unmount} = renderHook(() => useAgentStream(1));
  try {
    await act(async () => {await vi.advanceTimersByTimeAsync(30000);});
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.isRestored).toBe(false);
    expect(result.current.error).toMatch(/restor.*timed out/i);
  } finally {unmount(); vi.useRealTimers();}
});

it.each(["response", "error"] as const)("allows manual retry after timeout and ignores the old read's late %s", async (completion) => {
  let resolveOld!: (history: Awaited<ReturnType<typeof fetchConversationHistory>>) => void;
  let rejectOld!: (cause: Error) => void;
  vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise((resolve, reject) => {
    resolveOld = resolve;
    rejectOld = reject;
  }));
  vi.useFakeTimers();
  const {result, unmount} = renderHook(() => useAgentStream(1));
  try {
    await act(async () => {await vi.advanceTimersByTimeAsync(30000);});
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.error).toMatch(/restor.*timed out/i);

    const restoredReview = reviewFixture();
    vi.mocked(fetchSkillReview).mockResolvedValue(restoredReview);
    vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: restoredReview.run_id, sources: ["headhunter"]});
    vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "restored-thread", messages: [{
      id: "restored-message", role: "agent", content: "Restored evidence", toolCalls: [], isStreaming: false,
    }]});
    await act(async () => {result.current.retryRestoration();});
    expect(result.current.isRestored).toBe(true);
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.error).toBeNull();

    await act(async () => {
      if (completion === "response") resolveOld({threadId: "obsolete-thread", messages: []});
      else rejectOld(new Error("Obsolete restoration failed"));
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(result.current.isRestored).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.threadId).toBe("restored-thread");
    expect(result.current.messages.map(message => message.content)).toEqual(["Restored evidence"]);
    expect(result.current.agentState.sources).toEqual(["headhunter"]);
    expect(result.current.skillReview).toEqual(restoredReview);
    expect(result.current.execution.outcome).toBe("unknown");
  } finally {unmount(); vi.useRealTimers();}
});

it("shares one restoration deadline across consistency reads without replacing acknowledged data", async () => {
  const initial = reviewFixture();
  const acknowledged = {...initial, selection_revision: initial.selection_revision + 1};
  vi.mocked(fetchSkillReview).mockResolvedValue(initial);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id, sources: ["headhunter"]});
  const {result, unmount} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  act(() => result.current.applySkillReview(acknowledged));
  let resolveFirst!: (review: SkillReview) => void;
  vi.mocked(fetchSkillReview)
    .mockImplementationOnce(() => new Promise(resolve => {resolveFirst = resolve;}))
    .mockImplementationOnce(() => new Promise<never>(() => {}));
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id, sources: ["linkedin"]});
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "obsolete-thread", messages: []});
  vi.useFakeTimers();
  try {
    act(() => result.current.retryRestoration());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20000);
      resolveFirst(initial);
    });
    expect(fetchSkillReview).toHaveBeenCalledTimes(3);
    await act(async () => {await vi.advanceTimersByTimeAsync(9999);});
    expect(result.current.isLoadingHistory).toBe(true);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.isRestored).toBe(false);
    expect(result.current.error).toMatch(/restor.*timed out/i);
    expect(result.current.skillReview).toEqual(acknowledged);
    expect(result.current.agentState.sources).toEqual(["headhunter"]);
    expect(result.current.threadId).toBe("thread-1");
    expect(result.current.messages).toEqual([]);
    expect(vi.mocked(fetchSkillReview).mock.calls.at(-1)![1]?.aborted).toBe(true);
  } finally {unmount(); vi.useRealTimers();}
});

it("keeps a new course restoration pending past the previous course's deadline", async () => {
  let resolveOld!: (history: Awaited<ReturnType<typeof fetchConversationHistory>>) => void;
  let resolveCurrent!: (history: Awaited<ReturnType<typeof fetchConversationHistory>>) => void;
  vi.mocked(fetchConversationHistory)
    .mockImplementationOnce(() => new Promise(resolve => {resolveOld = resolve;}))
    .mockImplementationOnce(() => new Promise(resolve => {resolveCurrent = resolve;}));
  vi.mocked(fetchAgentState).mockImplementation(async id => ({...EMPTY_STATE, course_id: id}));
  vi.useFakeTimers();
  const {result, rerender, unmount} = renderHook(({id}) => useAgentStream(id), {initialProps: {id: 1}});
  try {
    await act(async () => {await vi.advanceTimersByTimeAsync(20000);});
    rerender({id: 2});
    expect(vi.mocked(fetchConversationHistory).mock.calls[0][1]?.aborted).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
      resolveOld({threadId: "obsolete-thread", messages: []});
    });
    expect(result.current.isLoadingHistory).toBe(true);
    expect(result.current.isRestored).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.threadId).toBeNull();
    await act(async () => {resolveCurrent({threadId: "current-thread", messages: []});});
    expect(result.current.isRestored).toBe(true);
    expect(result.current.agentState.course_id).toBe(2);
    expect(result.current.threadId).toBe("current-thread");
    await act(async () => {await vi.advanceTimersByTimeAsync(30000);});
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.isRestored).toBe(true);
    expect(result.current.error).toBeNull();
  } finally {unmount(); vi.useRealTimers();}
});

it.each(["response", "error"] as const)("rejects obsolete review %s after same-course stream replacement", async (completion) => {
  const review = {run_id: "run-1", candidate_revision: 1, selection_revision: 0, categories: [], candidates: [], selected_candidate_ids: [], excluded_candidate_ids: [], recommendations: [], source_outcomes: {}, extraction_coverage: {}, integration_review: null, publication_revision: 0, approved_references: []};
  let resolveReview!: (value: typeof review) => void;
  let rejectReview!: (reason: Error) => void;
  vi.mocked(fetchSkillReview).mockResolvedValueOnce(review).mockImplementationOnce(() => new Promise((resolve, reject) => {
    resolveReview = resolve;
    rejectReview = reject;
  }));
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-1"});
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "t"});
  const finishes: (() => void)[] = [];
  vi.mocked(streamMarketDemandChat).mockImplementation(() => new Promise(resolve => finishes.push(resolve)));
  const {result} = renderHook(() => useAgentStream(1));
  await act(async () => {});
  await waitFor(() => expect(result.current.skillReview?.candidate_revision).toBe(1));
  let first!: Promise<SendResult>;
  act(() => {first = result.current.send({mode: "workflow", text: "First"});});
  const firstArgs = vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  act(() => firstArgs.onEvent({type: "skill_review_changed", run_id: "run-1", candidate_revision: 99, selection_revision: 0, publication_revision: 0}));
  let second!: Promise<SendResult>;
  act(() => {second = result.current.send({mode: "workflow", text: "Second"});});
  await act(async () => {
    if (completion === "response") resolveReview({...review, candidate_revision: 99});
    else rejectReview(new Error("Obsolete review failed"));
  });
  expect(result.current.skillReview?.candidate_revision).toBe(1);
  expect(result.current.error).toBeNull();
  await act(async () => {finishes.forEach(finish => finish()); await Promise.all([first, second]);});
});

it("ignores an old clear rejection after switching courses", async () => {
  let rejectClear!: (reason: Error) => void;
  vi.mocked(deleteConversation).mockImplementationOnce(() => new Promise((_, reject) => {
    rejectClear = reject;
  }));
  const { result, rerender } = renderHook(({ courseId }) => useAgentStream(courseId), {
    initialProps: { courseId: 1 },
  });
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let clearing!: Promise<void>;
  act(() => { clearing = result.current.clearConversation(); });
  rerender({ courseId: 2 });
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {
    rejectClear(new Error("Old course clear failed"));
    await expect(clearing).rejects.toThrow("Old course clear failed");
  });
  expect(result.current.error).toBeNull();
});

it("accepts acknowledged review mutations but rejects older revisions and previous-course acknowledgements", async () => {
  const review = {run_id:"run-1",candidate_revision:1,selection_revision:2,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]};
  vi.mocked(fetchSkillReview).mockResolvedValue(review);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-1"});
  const {result,rerender} = renderHook(({courseId})=>useAgentStream(courseId),{initialProps:{courseId:1}});
  await waitFor(()=>expect(result.current.isRestored).toBe(true));
  const oldApply = result.current.applySkillReview;
  act(()=>result.current.applySkillReview({...review,selection_revision:3,selected_candidate_ids:["python"]}));
  expect(result.current.skillReview?.selected_candidate_ids).toEqual(["python"]);
  act(()=>result.current.applySkillReview(review));
  expect(result.current.skillReview?.selection_revision).toBe(3);
  rerender({courseId:2});
  await waitFor(()=>expect(result.current.isRestored).toBe(true));
  act(()=>oldApply({...review,selection_revision:99}));
  expect(result.current.skillReview?.selection_revision).toBe(2);
});

const contextual: WorkspaceContext = {kind: "occupation_reference", version: 1, intent: "explain", release: "31.0", occupation_codes: ["15-2051.00"], element_ids: [], metric: "IM"};

it("sends unfocused contextual questions without workflow config", async () => {
  const {result} = renderHook(() => useAgentStream(1, "China"));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {await result.current.send({mode: "contextual", text: "Explain", context: contextual});});
  const args = vi.mocked(streamMarketDemandChat).mock.calls[0][0];
  expect(args).toMatchObject({mode: "contextual", workspace_context: contextual});
  expect(args).not.toHaveProperty("country");
  expect(args).not.toHaveProperty("sources");
});

it.each(["completed", "failed", "eof", "error_without_end"] as const)("requires terminal proof for %s", async (kind) => {
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
    if (kind === "failed" || kind === "error_without_end") onEvent({type: "error", code: "persistence_failed", message: "Save failed", recovery: "Refresh first"} as StreamEvent);
    if (kind === "completed" || kind === "failed") onEvent({type: "stream_end", outcome: kind} as StreamEvent);
  });
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let sent!: SendResult;
  await act(async () => {sent = await result.current.send({mode: "contextual", text: "Explain", context: contextual});});
  expect(sent.outcome).toBe(kind === "completed" || kind === "failed" ? kind : "detached");
  expect(result.current.execution.outcome).toBe(kind === "completed" || kind === "failed" ? kind : "unknown");
  if (kind !== "completed") expect(result.current.recoverableCommand?.text).toBe("Explain");
  if (kind === "failed") expect(result.current.streamError).toMatchObject({code: "persistence_failed", recovery: "Refresh first"});
});

it("closeLiveResponse retains partial transcript and leaves execution unknown", async () => {
  let finish!: () => void;
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(({onEvent}) => {
    onEvent({type: "agent_start", agent: "workspace_review", messageId: "a", displayName: "Evidence assistant", emoji: "🤖"} as StreamEvent);
    onEvent({type: "text_delta", messageId: "a", delta: "Partial"});
    return new Promise(resolve => {finish = resolve;});
  });
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let pending!: Promise<SendResult>;
  act(() => {pending = result.current.send({mode: "workflow", text: "Analyze"});});
  act(() => result.current.closeLiveResponse());
  expect(result.current.messages.some(m => m.content === "Partial")).toBe(true);
  expect(result.current.messages.every(m => !m.isStreaming)).toBe(true);
  expect(result.current.execution.outcome).toBe("unknown");
  await act(async () => {finish(); expect((await pending).outcome).toBe("detached");});
});

it("keeps rejected reset data and rejects its promise", async () => {
  vi.mocked(deleteConversation).mockRejectedValueOnce(new MarketDemandApiError(409, "execution_busy", "Running", "Refresh"));
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  const before = result.current.skillReview;
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow("Running");});
  expect(result.current.skillReview).toBe(before);
  expect(result.current.threadId).toBe("thread-1");
  expect(result.current.isRestored).toBe(true);
});

it("reconciles ambiguous resets before another mutation and never replays", async () => {
  vi.mocked(deleteConversation).mockRejectedValueOnce(new Error("Reset connection lost"));
  let history!: (value: {messages: []; threadId: string}) => void;
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise(resolve => {history = resolve;}));
  let clearing!: Promise<void>;
  act(() => {clearing = result.current.clearConversation();});
  await act(async () => {});
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await result.current.send({mode: "workflow", text: "Retry"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow("unavailable");});
  expect(deleteConversation).toHaveBeenCalledTimes(1);
  await act(async () => {history({messages: [], threadId: ""}); await expect(clearing).rejects.toThrow("Reset connection lost");});
  expect(result.current.isRestored).toBe(true);
  expect(result.current.threadId).toBeNull();
});

it("does not enable mutations from mixed active run snapshots", async () => {
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-new"});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("polls visible busy execution at two seconds then ten, stops hidden and idle, refreshes on return", async () => {
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "busy", state_updated_at: "now"});
  const {result, unmount} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.useFakeTimers();
  // Reinstall the busy timer in fake time through a visibility refresh.
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  await act(async () => {});
  vi.mocked(getMarketExecutionStatus).mockClear();
  try {
    await act(async () => {await vi.advanceTimersByTimeAsync(2000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(1);
    await act(async () => {await vi.advanceTimersByTimeAsync(28000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(15);
    await act(async () => {await vi.advanceTimersByTimeAsync(9999);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(15);
    await act(async () => {await vi.advanceTimersByTimeAsync(1);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(16);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await act(async () => {await vi.advanceTimersByTimeAsync(20000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(16);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "idle", state_updated_at: "later"});
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    expect(result.current.execution).toMatchObject({status: "idle", outcome: "unknown"});
    const calls = vi.mocked(getMarketExecutionStatus).mock.calls.length;
    await act(async () => {await vi.advanceTimersByTimeAsync(20000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(calls);
    expect(streamMarketDemandChat).not.toHaveBeenCalled();
    expect(deleteConversation).not.toHaveBeenCalled();
    unmount();
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    await act(async () => {await vi.advanceTimersByTimeAsync(20000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(calls);
  } finally {vi.restoreAllMocks(); vi.useRealTimers();}
});

it("restores unmatched tools as unknown and keeps source outcomes independent of returned text", async () => {
  // This fixture represents persisted pre-run state, not orphaned checkpoints after reset.
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "idle", state_updated_at: "2026-10-13T12:00:00Z"});
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "t", outcome: "unknown", messages: [{id: "restored", role: "agent", agent: "workspace_review", content: "Old partial", isStreaming: true, toolCalls: [{id: "old", name: "collect", args: {}, status: "loading"}]}]});
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
    onEvent({type: "agent_start", agent: "skill_finder", messageId: "new", displayName: "Finder", emoji: ""});
    onEvent({type: "tool_start", agent: "skill_finder", toolCallId: "tool", toolName: "collect", args: {}});
    onEvent({type: "tool_end", toolCallId: "tool", toolName: "collect", status: "finished", result: "Provider denied request"});
    onEvent({type: "state_update", stateKey: "source_outcomes", value: {jobs: {status: "error", received_count: 0, usable_count: 0, warnings: ["Denied"]}}});
    // Keep recovery snapshot aligned with the live source outcome.
    vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, source_outcomes: {jobs: {status: "error", received_count: 0, usable_count: 0, warnings: ["Denied"]}}});
  });
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  expect(result.current.messages[0].toolCalls[0].status).toBe("unknown");
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(result.current.messages.at(-1)?.toolCalls[0].status).toBe("finished");
  expect(result.current.agentState.source_outcomes?.jobs.status).toBe("error");
  expect(result.current.execution.outcome).toBe("unknown");
});

it("reconciliation replaces partial transcript with the completed authoritative history without claiming success", async () => {
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "idle", state_updated_at: "2026-10-13T12:00:00Z"});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
    onEvent({type: "agent_start", agent: "workspace_review", messageId: "a", displayName: "Evidence assistant", emoji: "🤖"});
    onEvent({type: "text_delta", messageId: "a", delta: "Partial"});
    vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "thread-1", outcome: "unknown", messages: [{id: "a", role: "agent", content: "Complete server response", toolCalls: [], isStreaming: false}]});
  });
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(result.current.messages.at(-1)?.content).toBe("Complete server response");
  expect(result.current.execution.outcome).toBe("unknown");
});

it("ignores delayed status and snapshot responses after course change", async () => {
  const {result, rerender} = renderHook(({id}) => useAgentStream(id), {initialProps: {id: 1}});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let resolve!: (status: {status: "busy"; state_updated_at: string}) => void;
  vi.mocked(getMarketExecutionStatus).mockImplementationOnce(() => new Promise(r => {resolve = r;}));
  let refreshing!: Promise<void>;
  act(() => {refreshing = result.current.reconcile();});
  rerender({id: 2});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {resolve({status: "busy", state_updated_at: "old"}); await refreshing;});
  expect(result.current.execution).toMatchObject({status: "idle", state_updated_at: null, outcome: "unknown"});
});

it.each([true, false])("retains live terminal proof for the first run with run-id event %s", async (hasRunEvent) => {
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
    if (hasRunEvent) onEvent({type: "state_update", stateKey: "run_id", value: "run-new"});
    onEvent({type: "stream_end", outcome: "completed"});
    vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-new"});
    vi.mocked(fetchSkillReview).mockResolvedValue({...result.current.skillReview!, run_id: "run-new"});
  });
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(result.current.execution.outcome).toBe("completed");
});

it("keeps polling after replacing a stream within the same course", async () => {
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.useFakeTimers();
  const finishes: (() => void)[] = [];
  vi.mocked(streamMarketDemandChat).mockImplementation(() => new Promise(r => finishes.push(r)));
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "busy", state_updated_at: null});
  let first!: Promise<SendResult>;
  let second!: Promise<SendResult>;
  try {
    act(() => {first = result.current.send({mode: "workflow", text: "First"});});
    await act(async () => {await vi.advanceTimersByTimeAsync(2000);});
    act(() => {second = result.current.send({mode: "workflow", text: "Second"});});
    vi.mocked(getMarketExecutionStatus).mockClear();
    await act(async () => {await vi.advanceTimersByTimeAsync(2000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(1);
  } finally {
    await act(async () => {finishes.forEach(f => f()); await Promise.all([first, second]);});
    vi.useRealTimers();
  }
});

it("refuses a reset during an attached reply without detaching or clearing it", async () => {
  let finish!: () => void;
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(({onEvent}) => {
    onEvent({type: "agent_start", agent: "workspace_review", messageId: "a", displayName: "Evidence assistant", emoji: "🤖"});
    onEvent({type: "text_delta", messageId: "a", delta: "Still responding"});
    return new Promise(r => {finish = r;});
  });
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let sending!: Promise<SendResult>;
  act(() => {sending = result.current.send({mode: "workflow", text: "Analyze"});});
  const before = result.current.messages;
  const review = result.current.skillReview;
  const signal = vi.mocked(streamMarketDemandChat).mock.calls[0][0].signal;
  await act(async () => {await expect(result.current.clearConversation()).rejects.toMatchObject({status: 409});});
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(signal?.aborted).toBe(false);
  expect(result.current.messages).toBe(before);
  expect(result.current.skillReview).toBe(review);
  expect(result.current.isStreaming).toBe(true);
  await act(async () => {finish(); await sending;});
});

it("does not publish an old reset failure after its recovery awaited a course change", async () => {
  const {result, rerender} = renderHook(({id}) => useAgentStream(id), {initialProps: {id: 1}});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let resolve!: (value: {messages: []; threadId: string}) => void;
  vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise(r => {resolve = r;}));
  vi.mocked(deleteConversation).mockRejectedValueOnce(new Error("Old reset lost connection"));
  let clearing!: Promise<void>;
  act(() => {clearing = result.current.clearConversation();});
  await act(async () => {});
  rerender({id: 2});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {resolve({messages: [], threadId: "old"}); await expect(clearing).rejects.toThrow("Old reset lost connection");});
  expect(result.current.error).toBeNull();
  expect(result.current.threadId).toBe("thread-1");
});

it.each([409, 422])("retains recoverable question and structured HTTP %s rejection across restoration retry", async (status) => {
  vi.mocked(streamMarketDemandChat).mockRejectedValueOnce(new MarketDemandApiError(status, "context_stale", "Context changed", "Refresh first"));
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let sent!: SendResult;
  await act(async () => {sent = await result.current.send({mode: "contextual", text: "Explain this", context: contextual});});
  expect(sent).toMatchObject({outcome: "failed", error: {status, code: "context_stale", recovery: "Refresh first"}});
  expect(result.current.execution.outcome).toBe("unknown");
  act(() => result.current.retryRestoration());
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  expect(result.current.recoverableCommand?.text).toBe("Explain this");
  expect(streamMarketDemandChat).toHaveBeenCalledTimes(1);
});

it("clears local surfaces only after acknowledged reset success", async () => {
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let finish!: () => void;
  vi.mocked(deleteConversation).mockImplementationOnce(() => new Promise(r => {finish = r;}));
  const before = result.current.skillReview;
  let pending!: Promise<void>;
  act(() => {pending = result.current.clearConversation();});
  expect(result.current.skillReview).toBe(before);
  expect(result.current.threadId).toBe("thread-1");
  expect(result.current.isRestored).toBe(false);
  await act(async () => {finish(); await pending;});
  expect(result.current.skillReview).toBeNull();
  expect(result.current.threadId).toBeNull();
  expect(result.current.messages).toEqual([]);
  expect(result.current.execution).toMatchObject({status: "idle", outcome: "unknown"});
});


it("keeps distinct stable human IDs and context metadata for repeated questions live and restored", async () => {
  const metadata: ResolvedContextMetadata = {
    kind: "occupation_reference", version: 1, intent: "explain", run_id: null,
    candidate_revision: null, selection_revision: null, release: "31.0", view: null,
    metric: "IM", occupation_codes: ["15-2051.00"], occupations: [{soc_code: "15-2051.00", title: "Data Scientists"}],
    candidate_ids: [], candidate_labels: {}, filters: null, descriptor_choices: [], insight_kind: null,
    matching_count: 0, included_count: 0, omitted_count: 0, evidence_included_count: 0, evidence_omitted_count: 0,
    facts: [], coverage: {}, notices: ["Reference context"],
  };
  let turn = 0;
  vi.mocked(streamMarketDemandChat).mockImplementation(async ({onEvent}) => {
    onEvent({type: "context_resolved", messageId: `human-${++turn}`, workspace_context: metadata});
    onEvent({type: "stream_end", outcome: "completed"});
  });
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  for (let i = 0; i < 2; i++) await act(async () => {await result.current.send({mode: "contextual", text: "Explain", context: contextual});});
  expect(result.current.messages.map(m => ({id: m.id, content: m.content, context: m.workspace_context}))).toEqual([
    {id: "human-1", content: "Explain", context: metadata}, {id: "human-2", content: "Explain", context: metadata},
  ]);
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "thread-1", outcome: "unknown", messages: result.current.messages});
  await act(async () => {await result.current.reconcile();});
  expect(result.current.messages.map(m => m.id)).toEqual(["human-1", "human-2"]);
  expect(result.current.messages[1].workspace_context?.notices).toEqual(["Reference context"]);
});

it.each(["retryRestoration", "refreshSkillReview"] as const)("ignores a retained old-course %s callback", async (name) => {
  const {result, rerender} = renderHook(({id}) => useAgentStream(id), {initialProps: {id: 1}});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  const oldCallback = result.current[name];
  rerender({id: 2});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  const requests = vi.mocked(fetchSkillReview).mock.calls.length;
  await act(async () => {await oldCallback();});
  expect(fetchSkillReview).toHaveBeenCalledTimes(requests);
  expect(result.current.isLoadingHistory).toBe(false);
  expect(result.current.isRestored).toBe(true);
});


it("retries an old reconciliation before publishing surfaces after newer same-run SSE review", async () => {
  const initial = reviewFixture();
  const newer = {...initial, candidate_revision: initial.candidate_revision + 1};
  vi.mocked(fetchSkillReview).mockResolvedValue(initial);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id, candidate_revision: initial.candidate_revision});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let finish!: () => void;
  vi.mocked(streamMarketDemandChat).mockImplementationOnce(() => new Promise(r => {finish = r;}));
  let sending!: Promise<SendResult>;
  act(() => {sending = result.current.send({mode: "workflow", text: "Analyze"});});
  const args = vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  let oldReview!: (review: SkillReview) => void;
  let retryState!: (state: AgentState) => void;
  vi.mocked(fetchSkillReview).mockImplementationOnce(() => new Promise(r => {oldReview = r;})).mockResolvedValue(newer);
  vi.mocked(fetchAgentState).mockResolvedValueOnce({...EMPTY_STATE, run_id: initial.run_id, fetched_jobs: [{title: "Obsolete job"}]}).mockImplementationOnce(() => new Promise(r => {retryState = r;}));
  vi.mocked(fetchConversationHistory).mockResolvedValueOnce({threadId: "obsolete-thread", messages: [], outcome: "unknown"});
  let refreshing!: Promise<void>;
  act(() => {refreshing = result.current.reconcile();});
  act(() => args.onEvent({type: "skill_review_changed", run_id: initial.run_id!, candidate_revision: newer.candidate_revision, selection_revision: newer.selection_revision, publication_revision: newer.publication_revision}));
  await waitFor(() => expect(result.current.skillReview?.candidate_revision).toBe(newer.candidate_revision));
  await act(async () => {oldReview(initial);});
  expect(result.current.skillReview).toEqual(newer);
  expect(result.current.threadId).not.toBe("obsolete-thread");
  expect(result.current.agentState.fetched_jobs).toBeNull();
  expect(result.current.isRestored).toBe(false);
  await act(async () => {retryState({...EMPTY_STATE, run_id: initial.run_id, candidate_revision: newer.candidate_revision}); await refreshing;});
  expect(result.current.isRestored).toBe(true);
  expect(result.current.skillReview).toEqual(newer);
  expect(result.current.agentState.candidate_revision).toBe(newer.candidate_revision);
  await act(async () => {finish(); await sending;});
});

it.each(["candidate_revision", "selection_revision", "publication_revision"] as const)("reconciliation preserves an acknowledged %s floor", async (field) => {
  const initial = reviewFixture();
  const acknowledged = {...initial, [field]: initial[field] + 1};
  vi.mocked(fetchSkillReview).mockResolvedValue(initial);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  act(() => result.current.applySkillReview(acknowledged));
  vi.mocked(fetchSkillReview).mockResolvedValueOnce(initial).mockResolvedValue(acknowledged);
  await act(async () => {await result.current.reconcile();});
  expect(result.current.skillReview?.[field]).toBe(acknowledged[field]);
  expect(result.current.isRestored).toBe(true);
});

it("ignores hidden obsolete idle poll A while replacement busy poll B remains attached", async () => {
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "busy", state_updated_at: "initial"});
  const {result, unmount} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  vi.useFakeTimers();
  let resolveA!: (status: {status: "idle"; state_updated_at: string}) => void;
  let resolveB!: (status: {status: "busy"; state_updated_at: string}) => void;
  vi.mocked(getMarketExecutionStatus).mockImplementationOnce(() => new Promise(r => {resolveA = r;})).mockImplementationOnce(() => new Promise(r => {resolveB = r;}));
  const historyReads = vi.mocked(fetchConversationHistory).mock.calls.length;
  try {
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    const signalA = vi.mocked(getMarketExecutionStatus).mock.calls.at(-1)![1];
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    expect(signalA?.aborted).toBe(true);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    const signalB = vi.mocked(getMarketExecutionStatus).mock.calls.at(-1)![1];
    await act(async () => {resolveA({status: "idle", state_updated_at: "obsolete"});});
    expect(signalB?.aborted).toBe(false);
    expect(result.current.execution).toMatchObject({status: "busy", state_updated_at: "initial"});
    expect(fetchConversationHistory).toHaveBeenCalledTimes(historyReads);
    await act(async () => {resolveB({status: "busy", state_updated_at: "newer"});});
    expect(result.current.execution).toMatchObject({status: "busy", state_updated_at: "newer"});
    const reads = vi.mocked(getMarketExecutionStatus).mock.calls.length;
    await act(async () => {await vi.advanceTimersByTimeAsync(2000);});
    expect(getMarketExecutionStatus).toHaveBeenCalledTimes(reads + 1);
  } finally {unmount(); vi.restoreAllMocks(); vi.useRealTimers();}
});

it("rejects two regressing coherent reads without publishing stale surfaces or enabling mutations", async () => {
  const initial = reviewFixture();
  const acknowledged = {...initial, selection_revision: initial.selection_revision + 1};
  vi.mocked(fetchSkillReview).mockResolvedValue(initial);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  act(() => result.current.applySkillReview(acknowledged));
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "obsolete-thread", messages: [], outcome: "unknown"});
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id, fetched_jobs: [{title: "Obsolete job"}]});
  const reads = vi.mocked(fetchSkillReview).mock.calls.length;
  await act(async () => {await expect(result.current.reconcile()).rejects.toThrow("Review changed during refresh");});
  expect(fetchSkillReview).toHaveBeenCalledTimes(reads + 2);
  expect(result.current.skillReview).toEqual(acknowledged);
  expect(result.current.agentState.fetched_jobs).toBeNull();
  expect(result.current.threadId).toBe("thread-1");
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await result.current.send({mode: "workflow", text: "Analyze"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  vi.mocked(fetchSkillReview).mockResolvedValue(acknowledged);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: initial.run_id});
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "thread-1", messages: [], outcome: "unknown"});
  await act(async () => {await result.current.reconcile();});
  expect(result.current.isRestored).toBe(true);
  expect(result.current.skillReview).toEqual(acknowledged);
});

const retainedResetHistory = (runId = "run-old") => ({threadId: "thread-1", messages: [{
  id: "old-question", role: "user" as const, content: "Explain retained evidence", toolCalls: [], isStreaming: false,
  workspace_context: {kind: "run_review", version: 1, intent: "explain", run_id: runId,
    candidate_revision: 1, selection_revision: 2, release: null, view: "overview", metric: "frequency",
    occupation_codes: [], occupations: [], candidate_ids: [], candidate_labels: {}, filters: null,
    descriptor_choices: [], insight_kind: null, matching_count: 0, included_count: 0, omitted_count: 0,
    evidence_included_count: 0, evidence_omitted_count: 0, facts: [], coverage: {}, notices: [],
  } satisfies ResolvedContextMetadata,
}]});

it("recognizes partial reset on reload without restoring edits or automatically deleting", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.resetRecovery).toBe("required");
  expect(result.current.isRestored).toBe(false);
  expect(result.current.execution).toMatchObject({status: "idle", outcome: "unknown"});
  await act(async () => {await result.current.send({mode: "workflow", text: "Start"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(fetchConversationHistory).toHaveBeenCalledTimes(2);
});

it("retains old review and recoverable question after partial reset until explicit retry acknowledgement", async () => {
  const review = reviewFixture();
  const emptyReview = await vi.mocked(fetchSkillReview)(1);
  vi.mocked(fetchSkillReview).mockResolvedValue(review);
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: review.run_id});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {await result.current.send({mode: "contextual", text: "Keep my question", context: contextual});});
  const oldMessages = result.current.messages;
  vi.mocked(deleteConversation).mockRejectedValueOnce(new Error("Reset connection lost"));
  vi.mocked(fetchSkillReview).mockResolvedValue(emptyReview);
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory(review.run_id!));
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow("Reset connection lost");});
  expect(result.current.resetRecovery).toBe("required");
  expect(result.current.isRestored).toBe(false);
  expect(result.current.skillReview).toBe(review);
  expect(result.current.messages).toBe(oldMessages);
  expect(result.current.recoverableCommand?.text).toBe("Keep my question");
  act(() => result.current.applySkillReview({...review, selection_revision: 99}));
  expect(result.current.skillReview).toBe(review);
  let acknowledge!: () => void;
  vi.mocked(deleteConversation).mockImplementationOnce(() => new Promise(resolve => {acknowledge = resolve;}));
  let retry!: Promise<void>;
  act(() => {retry = result.current.clearConversation();});
  await waitFor(() => expect(deleteConversation).toHaveBeenCalledTimes(2));
  expect(result.current.skillReview).toBe(review);
  expect(result.current.recoverableCommand?.text).toBe("Keep my question");
  await act(async () => {acknowledge(); await retry;});
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.isRestored).toBe(true);
  expect(result.current.skillReview).toBeNull();
  expect(result.current.messages).toEqual([]);
  expect(result.current.recoverableCommand).toBeNull();
  expect(result.current.execution.outcome).toBe("unknown");
  expect(streamMarketDemandChat).toHaveBeenCalledTimes(1);
});

it.each(["busy", "unknown"] as const)("guards confirmed partial-reset retry with fresh %s status", async (status) => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  vi.mocked(getMarketExecutionStatus).mockImplementation(async () => {
    if (status === "unknown") throw new Error("Status unavailable");
    return {status, state_updated_at: null};
  });
  await act(async () => {
    if (status === "busy") await expect(result.current.clearConversation()).rejects.toMatchObject({status: 409});
    else await result.current.clearConversation();
  });
  expect(deleteConversation).toHaveBeenCalledTimes(status === "busy" ? 0 : 1);
  expect(result.current.execution.outcome).toBe("unknown");
  expect(result.current.isRestored).toBe(status !== "busy");
  if (status === "busy") expect(result.current.resetRecovery).toBe("required");
});

it("retains actionable partial-reset retry after another failure or server busy rejection", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  for (const failure of [new Error("Offline"), new MarketDemandApiError(409, "execution_busy", "Running", "Refresh")]) {
    vi.mocked(deleteConversation).mockRejectedValueOnce(failure);
    await act(async () => {await expect(result.current.clearConversation()).rejects.toBe(failure);});
    expect(result.current.resetRecovery).toBe("required");
    expect(result.current.isRestored).toBe(false);
  }
  expect(deleteConversation).toHaveBeenCalledTimes(2);
});

it.each(["mixed-history", "active-state", "transient-read", "changing-history"])("does not enable reset recovery for %s", async (kind) => {
  const history = retainedResetHistory();
  vi.mocked(fetchConversationHistory).mockResolvedValue(history);
  if (kind === "mixed-history") vi.mocked(fetchConversationHistory).mockResolvedValue({...history, messages: [...history.messages, ...retainedResetHistory("other-run").messages]});
  if (kind === "active-state") vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-new"});
  if (kind === "transient-read") vi.mocked(fetchSkillReview).mockRejectedValue(new Error("Read unavailable"));
  if (kind === "changing-history") vi.mocked(fetchConversationHistory).mockResolvedValueOnce(history).mockResolvedValue(retainedResetHistory("other-run"));
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow("unavailable");});
  expect(deleteConversation).not.toHaveBeenCalled();
});

it.each(["read", "delete"])("ignores partial-reset retry %s and retained callback after course change", async (phase) => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory());
  const {result, rerender} = renderHook(({id}) => useAgentStream(id), {initialProps: {id: 1}});
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.resetRecovery).toBe("required");
  const oldClear = result.current.clearConversation;
  let finish!: () => void;
  if (phase === "read") vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise(resolve => {finish = () => resolve(retainedResetHistory());}));
  else vi.mocked(deleteConversation).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  let retry!: Promise<void>;
  act(() => {retry = oldClear();});
  if (phase === "delete") await waitFor(() => expect(deleteConversation).toHaveBeenCalledOnce());
  else await act(async () => {});
  vi.mocked(fetchConversationHistory).mockResolvedValue({threadId: "course-2", messages: []});
  rerender({id: 2});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {finish(); await retry;});
  expect(result.current.threadId).toBe("course-2");
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.error).toBeNull();
  await act(async () => {await expect(oldClear()).rejects.toThrow("unavailable");});
  expect(deleteConversation).toHaveBeenCalledTimes(phase === "delete" ? 1 : 0);
});

it("does not delete after a newer same-course read supersedes partial-reset retry validation", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedResetHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.resetRecovery).toBe("required"));
  let finish!: (value: ReturnType<typeof retainedResetHistory>) => void;
  vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  let retry!: Promise<void>;
  act(() => {retry = result.current.clearConversation();});
  await act(async () => {});
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "run-new"});
  await act(async () => {await expect(result.current.reconcile()).rejects.toThrow("changed");});
  await act(async () => {finish(retainedResetHistory()); await expect(retry).rejects.toThrow("changed");});
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(result.current.isRestored).toBe(false);
  expect(result.current.resetRecovery).toBe("none");
});

it("does not restore editing when failed-reset reconciliation is superseded by a mixed-run read", async () => {
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  let finish!: (value: {threadId: string; messages: []}) => void;
  vi.mocked(fetchConversationHistory).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  vi.mocked(deleteConversation).mockRejectedValueOnce(new Error("Reset offline"));
  let reset!: Promise<void>;
  act(() => {reset = result.current.clearConversation();});
  await act(async () => {});
  vi.mocked(fetchAgentState).mockResolvedValue({...EMPTY_STATE, run_id: "new-run"});
  await act(async () => {await expect(result.current.reconcile()).rejects.toThrow("changed");});
  await act(async () => {finish({threadId:"thread-1",messages:[]}); await expect(reset).rejects.toThrow("Reset offline");});
  expect(result.current.isRestored).toBe(false);
  await act(async () => {await result.current.send({mode:"workflow",text:"Start"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

// Real workflow HumanMessage/AIMessage history has no workspace_context metadata.
const retainedWorkflowHistory = () => ({threadId: "thread-1", outcome: "unknown" as const, messages: [
  {id: "user-workflow", role: "user" as const, content: "Analyze this course", toolCalls: [], isStreaming: false},
  {id: "agent-workflow", role: "agent" as const, agent: "skill_finder" as const, content: "Collected job evidence", toolCalls: [], isStreaming: false},
]});
// Mirror the absent-state wire response: course/default country only, all other keys null.
const absentWorkflowThreadState = {...EMPTY_STATE, course_id: 1, course_title: "Test Course", course_description: "",
  teacher_id: null, extraction_coverage: null, onet_evidence: null, sources: null, evidence_sources: null,
  onet_release: null, selected_onet_occupations: null, onet_selection_confirmed: null, run_id: null,
  candidate_revision: null, source_outcomes: null, selection_revision: null, publication_revision: null,
  selected_candidate_ids: null, excluded_candidate_ids: null, selection_confirmation: null,
  review_stage: null, skill_review_change_id: null, curated_skills: null, mapped_skills: null,
  final_skills: null, _cleaned_results: null, _raw_skill_urls: null,
} as unknown as AgentState;

it("recognizes workflow-only partial reset on fresh reload and requires confirmed retry", async () => {
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedWorkflowHistory());
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.isRestored).toBe(false);
  expect(result.current.resetRecovery).toBe("required");
  expect(result.current.skillReview).toBeNull();
  expect(deleteConversation).not.toHaveBeenCalled();
  await act(async () => {await result.current.send({mode:"workflow",text:"Start"});});
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  await act(async () => {await result.current.clearConversation();});
  expect(deleteConversation).toHaveBeenCalledOnce();
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.isRestored).toBe(true);
  expect(result.current.messages).toEqual([]);
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("retains workflow-only old review configuration and question through failed reset and retry until acknowledgement", async () => {
  const emptyReview = await vi.mocked(fetchSkillReview)(1);
  const review = reviewFixture();
  const configured: AgentState = {...EMPTY_STATE, run_id:review.run_id, sources:["headhunter"],
    evidence_sources:["jobs"], job_search_country:"Russia", job_search_country_confirmed:true, job_search_location:"Russia",
    fetched_jobs:[{title:"Developer"}], candidate_revision:review.candidate_revision};
  vi.mocked(fetchAgentState).mockResolvedValue(configured);
  vi.mocked(fetchSkillReview).mockResolvedValue(review);
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedWorkflowHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  await act(async () => {await result.current.send({mode:"workflow",text:"Keep this workflow question"});});
  const retained = result.current.messages;
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  vi.mocked(fetchSkillReview).mockResolvedValue(emptyReview);
  for (const message of ["Initial reset offline", "Retry offline"]) {
    vi.mocked(deleteConversation).mockRejectedValueOnce(new Error(message));
    await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow(message);});
    expect(result.current.isRestored).toBe(false);
    expect(result.current.resetRecovery).toBe("required");
    expect(result.current.skillReview).toBe(review);
    expect(result.current.agentState).toBe(configured);
    expect(result.current.messages).toBe(retained);
    expect(result.current.recoverableCommand?.text).toBe("Keep this workflow question");
  }
  await act(async () => {
    await result.current.send({mode:"workflow",text:"Start"});
    await result.current.send({mode:"contextual",text:"Explain",context:contextual});
  });
  act(() => result.current.applySkillReview({...review,selection_revision:99}));
  expect(result.current.skillReview).toBe(review);
  expect(streamMarketDemandChat).toHaveBeenCalledOnce();
  let acknowledge!: () => void;
  vi.mocked(deleteConversation).mockImplementationOnce(() => new Promise(resolve => {acknowledge = resolve;}));
  let retry!: Promise<void>;
  act(() => {retry = result.current.clearConversation();});
  await waitFor(() => expect(deleteConversation).toHaveBeenCalledTimes(3));
  expect(result.current.agentState).toBe(configured);
  expect(result.current.skillReview).toBe(review);
  expect(result.current.recoverableCommand?.text).toBe("Keep this workflow question");
  await act(async () => {acknowledge(); await retry;});
  expect(result.current.agentState.fetched_jobs).toBeNull();
  expect(result.current.skillReview).toBeNull();
  expect(result.current.recoverableCommand).toBeNull();
  expect(result.current.isRestored).toBe(true);
  expect(streamMarketDemandChat).toHaveBeenCalledOnce();
});

it.each(["status-failure", "known-busy", "nondefault-source", "nondefault-market"])("does not restore workflow-only retained history when absence is unproven: %s", async (kind) => {
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedWorkflowHistory());
  if (kind === "status-failure") vi.mocked(getMarketExecutionStatus).mockRejectedValue(new Error("Status unavailable"));
  else if (kind === "known-busy") vi.mocked(getMarketExecutionStatus).mockResolvedValue({status:"busy",state_updated_at:null});
  if (kind === "nondefault-source") vi.mocked(fetchAgentState).mockResolvedValue({...absentWorkflowThreadState,sources:["indeed"]});
  if (kind === "nondefault-market") vi.mocked(fetchAgentState).mockResolvedValue({...absentWorkflowThreadState,job_search_country:"China",job_search_country_confirmed:true,job_search_location:"China"});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isLoadingHistory).toBe(false));
  expect(result.current.isRestored).toBe(false);
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.skillReview).toBeNull();
  await act(async () => {await result.current.send({mode:"workflow",text:"Start"});});
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow();});
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("refuses confirmed workflow-only retry when a fresh status read cannot prove state absence", async () => {
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedWorkflowHistory());
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.resetRecovery).toBe("required"));
  vi.mocked(getMarketExecutionStatus).mockRejectedValue(new Error("Status unavailable"));
  await act(async () => {await expect(result.current.clearConversation()).rejects.toThrow();});
  expect(deleteConversation).not.toHaveBeenCalled();
  expect(result.current.isRestored).toBe(false);
});

it.each(["default-persisted", "configured-persisted"])("normally restores legitimate workflow-only pre-run history: %s", async (kind) => {
  const state = kind === "default-persisted" ? absentWorkflowThreadState : {...EMPTY_STATE, job_search_country:"China", job_search_country_confirmed:true, job_search_location:"China"};
  vi.mocked(fetchAgentState).mockResolvedValue(state);
  vi.mocked(fetchConversationHistory).mockResolvedValue(retainedWorkflowHistory());
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status:"idle",state_updated_at:"2026-10-13T12:00:00Z"});
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.messages[0].content).toBe("Analyze this course");
  expect(result.current.agentState).toBe(state);
  expect(deleteConversation).not.toHaveBeenCalled();
});

it("normally restores a truly empty workspace with absent authoritative state", async () => {
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  expect(result.current.resetRecovery).toBe("none");
  expect(result.current.messages).toEqual([]);
  expect(deleteConversation).not.toHaveBeenCalled();
});

it("does not classify a null-run occupation-reference conversation as contextless workflow recovery", async () => {
  const history = retainedResetHistory();
  vi.mocked(fetchConversationHistory).mockResolvedValue({...history, messages:[{...history.messages[0],
    workspace_context:{...history.messages[0].workspace_context,kind:"occupation_reference",run_id:null,release:"31.0"}}]});
  vi.mocked(fetchAgentState).mockResolvedValue(absentWorkflowThreadState);
  const {result} = renderHook(() => useAgentStream(1));
  await waitFor(() => expect(result.current.isRestored).toBe(true));
  expect(result.current.resetRecovery).toBe("none");
  expect(deleteConversation).not.toHaveBeenCalled();
});

it('searches all three job providers together for a new analysis without source setup', async () => {
 const {result}=renderHook(()=>useAgentStream(1));
 await waitFor(()=>expect(result.current.isRestored).toBe(true));
 await act(async()=>{await result.current.send({mode:'workflow',text:'Analyze the job market'});});
 expect(streamMarketDemandChat).toHaveBeenCalledWith(expect.objectContaining({sources:['indeed','linkedin','headhunter'],evidence_sources:['jobs']}));
});
