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
      courseId: 1,
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
      courseId: 1,
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
    await streamMarketDemandChat({courseId: 1, message, country: "Uzbekistan", sources: ["headhunter"], evidence_sources: ["jobs", "onet"], onet_release: "31.0", onEvent: vi.fn()});
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
