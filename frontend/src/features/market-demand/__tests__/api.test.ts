import { beforeEach, describe, expect, it, vi } from "vitest";

import { streamMarketDemandChat } from "../api";

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
