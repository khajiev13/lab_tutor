import { beforeEach, describe, expect, it, vi } from "vitest";

import { streamMarketDemandChat } from "@/features/market-demand/api";
import * as marketDemandApi from "@/features/market-demand/api";
import api from "@/services/api";
import { withdrawalFixture } from "@/features/market-demand/__tests__/review-fixtures";

function emptySseResponse() {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.close();
      },
    }),
    { status: 200 }
  );
}

describe("streamMarketDemandChat", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("access_token", "token");
    vi.stubGlobal("fetch", vi.fn(async () => emptySseResponse()));
  });

  it("omits country from the request until the teacher explicitly selects one", async () => {
    await streamMarketDemandChat({
      mode: "workflow", courseId: 1,
      message: "Analyze the job market",
      country: null,
      onEvent: vi.fn(),
    });

    const fetchMock = vi.mocked(fetch);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toEqual({ message: "Analyze the job market" });
  });

  it("sends country after the teacher explicitly selects one", async () => {
    await streamMarketDemandChat({
      mode: "workflow", courseId: 1,
      message: "Analyze the job market",
      country: "China",
      onEvent: vi.fn(),
    });

    const fetchMock = vi.mocked(fetch);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body).toEqual({ message: "Analyze the job market", country: "China" });
  });
});

it("serializes only explicitly selected providers and O*NET on every reply", async () => {
  localStorage.setItem("access_token", "token");
  vi.stubGlobal("fetch", vi.fn(async () => emptySseResponse()));
  for (const message of ["Analyze", '"data analyst"', "1, 2"]) {
    await streamMarketDemandChat({mode: "workflow", courseId: 1, message, country: "Uzbekistan", sources: ["headhunter"], evidence_sources: ["jobs", "onet"], onet_release: "31.0", onEvent: vi.fn()});
    const body = JSON.parse(String(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.body));
    expect(body).toEqual({message, country: "Uzbekistan", sources: ["headhunter"], evidence_sources: ["jobs", "onet"], onet_release: "31.0"});
  }
});

it("explicit withdrawal prepares a server review with current run revisions on the agreed endpoint", async () => {
  const review = withdrawalFixture();
  const post = vi.spyOn(api, "post").mockResolvedValueOnce({data: review});
  try {
    expect(marketDemandApi).toHaveProperty("prepareSkillWithdrawal", expect.any(Function));
    const response = await marketDemandApi.prepareSkillWithdrawal(7, {
      run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 2,
    });
    expect(post).toHaveBeenCalledWith("/courses/7/market-demand/skill-review/withdrawal-review", {
      run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 2,
    });
    expect(response).toEqual(review);
  } finally {
    post.mockRestore();
  }
});

const context = {kind: "occupation_reference", version: 1, intent: "explain", release: "31.0", occupation_codes: ["15-2051.00"], element_ids: [], metric: "IM"} as const;

it("contextual transport never serializes workflow settings even from a contaminated object", async () => {
  localStorage.setItem("access_token", "token");
  vi.stubGlobal("fetch", vi.fn(async () => emptySseResponse()));
  const args = {mode: "contextual" as const, courseId: 1, message: "Explain", workspace_context: {...context, occupation_codes: [...context.occupation_codes], element_ids: []}, country: "USA", sources: ["indeed"], onEvent: vi.fn()};
  await streamMarketDemandChat(args as never);
  const body = JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body));
  expect(body.workspace_context.intent).toBe("explain");
  expect(Object.keys(body).sort()).toEqual(["message", "workspace_context"]);
});

it.each([409, 422])("retains structured HTTP %s recovery", async (status) => {
  localStorage.setItem("access_token", "token");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({detail: {code: "context_stale", message: "Refresh context", recovery: "Review first"}}), {status})));
  await expect(streamMarketDemandChat({mode: "workflow", courseId: 1, message: "Question", country: null, onEvent: vi.fn()})).rejects.toMatchObject({status, code: "context_stale", message: "Refresh context", recovery: "Review first"});
});

it("parses fragmented CRLF frames", async () => {
  localStorage.setItem("access_token", "token");
  const onEvent = vi.fn();
  const encoder = new TextEncoder();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({start(c) {
    for (const part of ['event: stream_end\r', '\ndata: {"outcome":"com', 'pleted"}\r\n\r', '\n']) c.enqueue(encoder.encode(part));
    c.close();
  }}))));
  await streamMarketDemandChat({mode: "workflow", courseId: 1, message: "", country: null, onEvent});
  expect(onEvent).toHaveBeenCalledWith({type: "stream_end", outcome: "completed"});
});

it.each(["truncated", "network", "malformed"])("rejects %s streams without silently succeeding", async (kind) => {
  localStorage.setItem("access_token", "token");
  let reads = 0;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(new ReadableStream({pull(c) {
    if (reads++ === 0) c.enqueue(new TextEncoder().encode(kind === "malformed" ? 'data: broken\n\n' : 'data: {"type":"text_delta"'));
    else if (kind === "network") c.error(new Error("Connection lost"));
    else c.close();
  }}))));
  await expect(streamMarketDemandChat({mode: "workflow", courseId: 1, message: "", country: null, onEvent: vi.fn()})).rejects.toThrow();
});

it("reads execution without making a mutation and preserves reset conflicts", async () => {
  const get = vi.spyOn(api, "get").mockResolvedValueOnce({data: {status: "busy", state_updated_at: null}});
  const del = vi.spyOn(api, "delete").mockRejectedValueOnce({isAxiosError: true, response: {status: 409, data: {detail: {code: "execution_busy", message: "Still running", recovery: "Refresh"}}}});
  try {
    await expect(marketDemandApi.getMarketExecutionStatus(7)).resolves.toEqual({status: "busy", state_updated_at: null});
    expect(get).toHaveBeenCalledWith("/courses/7/market-demand/execution-status", {signal: undefined});
    await expect(marketDemandApi.deleteConversation(7)).rejects.toMatchObject({status: 409, code: "execution_busy", message: "Still running", recovery: "Refresh"});
  } finally {get.mockRestore(); del.mockRestore();}
});

it("does not mistake a heartbeat plus truncated data for a complete stream", async () => {
  localStorage.setItem("access_token", "token");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(': heartbeat\ndata: {"type":"stream_end"')));
  await expect(streamMarketDemandChat({mode: "workflow", courseId: 1, message: "", country: null, onEvent: vi.fn()})).rejects.toThrow("incomplete");
});

it("rejects missing contextual mode or payload instead of falling back to workflow", async () => {
  localStorage.setItem("access_token", "token");
  const fetchMock = vi.fn(async () => emptySseResponse());
  vi.stubGlobal("fetch", fetchMock);
  for (const args of [{mode: "contextual", workspace_context: undefined}, {workspace_context: context}]) {
    await expect(streamMarketDemandChat({...args, courseId: 1, message: "Explain", onEvent: vi.fn()} as never)).rejects.toThrow();
  }
  expect(fetchMock).not.toHaveBeenCalled();
});

it("loads occupation reference evidence with the exact GET DTO, release and abort signal", async () => {
  const response = {release: "31.0", soc_code: "15-2051.00", items: []};
  const get = vi.spyOn(api, "get").mockResolvedValueOnce({data: response});
  const signal = new AbortController().signal;
  try {
    expect(marketDemandApi).toHaveProperty("getOccupationSkills", expect.any(Function));
    await expect(marketDemandApi.getOccupationSkills(7, "31.0", "15-2051.00", signal)).resolves.toEqual(response);
    expect(get).toHaveBeenCalledWith("/courses/7/occupation-reference/occupations/15-2051.00/skills", {params: {release: "31.0"}, signal});
  } finally {get.mockRestore();}
});
