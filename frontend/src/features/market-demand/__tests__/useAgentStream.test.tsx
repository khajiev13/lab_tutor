import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentState } from "@/features/market-demand/types";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
import {
  deleteConversation,
  fetchSkillReview,
  fetchAgentState,
  fetchConversationHistory,
  streamMarketDemandChat,
} from "@/features/market-demand/api";

vi.mock("@/features/market-demand/api", () => ({
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
      await result.current.send("Analyze the job market");
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
      await result.current.send("Analyze the job market");
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
  let pending!: Promise<void>;
  act(() => {pending=result.current.send("Analyze");});
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
  let first!:Promise<void>; act(()=>{first=result.current.send("First");});
  const args=vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  rerender({id:2});
  await waitFor(()=>expect(result.current.isLoadingHistory).toBe(false));
  expect(args.signal?.aborted).toBe(true);
  let second!:Promise<void>; act(()=>{second=result.current.send("Second");});
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
 await act(async()=>{await result.current.send("Too early");});
 expect(vi.mocked(streamMarketDemandChat).mock.calls.length).toBe(before);
 await act(async()=>{restore(EMPTY_STATE);});
});


it("restores the coherent review and refetches the latest SSE revision", async () => {
 const emptyReview = {run_id:"run-1",candidate_revision:1,selection_revision:0,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]};
 vi.mocked(fetchSkillReview).mockResolvedValueOnce(emptyReview).mockResolvedValueOnce({...emptyReview,candidate_revision:2});
 vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
 vi.mocked(fetchConversationHistory).mockResolvedValue({messages:[],threadId:"t"});
 let finish!:()=>void;
 vi.mocked(streamMarketDemandChat).mockImplementationOnce(()=>new Promise(r=>{finish=r;}));
 const {result}=renderHook(()=>useAgentStream(1));
 await waitFor(()=>expect(result.current.skillReview?.candidate_revision).toBe(1));
 let pending!:Promise<void>; act(()=>{pending=result.current.send("Analyze");});
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
  await act(async () => {await result.current.send("Analyze");});
  expect(vi.mocked(streamMarketDemandChat).mock.calls.length).toBe(before);
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  await act(async () => {result.current.retryRestoration();});
  await waitFor(() => expect(result.current.isRestored).toBe(true));
});

it.each(["response", "error"] as const)("rejects obsolete review %s after same-course stream replacement", async (completion) => {
  const review = {run_id: "run-1", candidate_revision: 1, selection_revision: 0, categories: [], candidates: [], selected_candidate_ids: [], excluded_candidate_ids: [], recommendations: [], source_outcomes: {}, extraction_coverage: {}, integration_review: null, publication_revision: 0, approved_references: []};
  let resolveReview!: (value: typeof review) => void;
  let rejectReview!: (reason: Error) => void;
  vi.mocked(fetchSkillReview).mockResolvedValueOnce(review).mockImplementationOnce(() => new Promise((resolve, reject) => {
    resolveReview = resolve;
    rejectReview = reject;
  }));
  vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "t"});
  const finishes: (() => void)[] = [];
  vi.mocked(streamMarketDemandChat).mockImplementation(() => new Promise(resolve => finishes.push(resolve)));
  const {result} = renderHook(() => useAgentStream(1));
  await act(async () => {});
  await waitFor(() => expect(result.current.skillReview?.candidate_revision).toBe(1));
  let first!: Promise<void>;
  act(() => {first = result.current.send("First");});
  const firstArgs = vi.mocked(streamMarketDemandChat).mock.calls.at(-1)![0];
  act(() => firstArgs.onEvent({type: "skill_review_changed", run_id: "run-1", candidate_revision: 99, selection_revision: 0, publication_revision: 0}));
  let second!: Promise<void>;
  act(() => {second = result.current.send("Second");});
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
    await clearing;
  });
  expect(result.current.error).toBeNull();
});

it("accepts acknowledged review mutations but rejects older revisions and previous-course acknowledgements", async () => {
  const review = {run_id:"run-1",candidate_revision:1,selection_revision:2,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]};
  vi.mocked(fetchSkillReview).mockResolvedValue(review);
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
