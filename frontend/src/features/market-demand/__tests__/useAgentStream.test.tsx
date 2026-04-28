import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentState } from "../types";
import { useAgentStream } from "../hooks/useAgentStream";
import {
  fetchAgentState,
  fetchConversationHistory,
  streamMarketDemandChat,
} from "../api";

vi.mock("../api", () => ({
  deleteConversation: vi.fn(),
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

describe("useAgentStream country selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchConversationHistory).mockResolvedValue({
      messages: [],
      threadId: "thread-1",
    });
    vi.mocked(fetchAgentState).mockResolvedValue(EMPTY_STATE);
  });

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
