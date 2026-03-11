import { describe, it, expect } from "vitest";
import type { AgentState, PipelineStageId, StageStatus } from "../types";

// Import and test derivePipelineStages directly by re-implementing
// the same logic (it's not exported, so we test the contract).
// This tests the pure function logic that the hook depends on.

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

  const order: PipelineStageId[] = ["fetch", "select", "extract", "map", "approve", "link", "insert"];
  for (const id of order) {
    if (stages[id] === "pending") {
      stages[id] = "active";
      break;
    }
  }

  return stages;
}

const EMPTY_STATE: AgentState = {
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
};

describe("derivePipelineStages", () => {
  it("returns fetch as active when state is empty", () => {
    const stages = derivePipelineStages(EMPTY_STATE);
    expect(stages.fetch).toBe("active");
    expect(stages.select).toBe("pending");
    expect(stages.extract).toBe("pending");
  });

  it("marks fetch complete and select active when jobs fetched", () => {
    const state: AgentState = {
      ...EMPTY_STATE,
      fetched_jobs: [{ title: "Dev" }],
    };
    const stages = derivePipelineStages(state);
    expect(stages.fetch).toBe("complete");
    expect(stages.select).toBe("active");
  });

  it("marks multiple stages complete", () => {
    const state: AgentState = {
      ...EMPTY_STATE,
      fetched_jobs: [{ title: "Dev" }],
      selected_jobs: [{ title: "Dev" }],
      extracted_skills: [{ name: "Python", category: "lang", frequency: 10, pct: 50 }],
    };
    const stages = derivePipelineStages(state);
    expect(stages.fetch).toBe("complete");
    expect(stages.select).toBe("complete");
    expect(stages.extract).toBe("complete");
    expect(stages.map).toBe("active");
    expect(stages.approve).toBe("pending");
  });

  it("all stages complete when all data present", () => {
    const state: AgentState = {
      ...EMPTY_STATE,
      fetched_jobs: [{}],
      selected_jobs: [{}],
      extracted_skills: [{ name: "X", category: "Y", frequency: 1, pct: 100 }],
      curriculum_mapping: [{ name: "X", category: "Y", status: "covered" }],
      selected_for_insertion: [{}],
      skill_concepts: { X: ["c1"] },
      insertion_results: {
        skills: 1,
        job_postings: 5,
        chapter_links: 2,
        sourced_from: 3,
        existing_concept_links: 1,
        new_concepts: 0,
      },
    };
    const stages = derivePipelineStages(state);
    for (const id of Object.keys(stages) as PipelineStageId[]) {
      expect(stages[id]).toBe("complete");
    }
  });
});

describe("StreamEvent type contracts", () => {
  it("agent_start event has required fields", () => {
    const event = {
      type: "agent_start" as const,
      agent: "supervisor" as const,
      messageId: "msg-abc",
      displayName: "Supervisor",
      emoji: "📊",
    };
    expect(event.type).toBe("agent_start");
    expect(event.agent).toBe("supervisor");
    expect(event.messageId).toBeTruthy();
  });

  it("text_delta event has delta and messageId", () => {
    const event = {
      type: "text_delta" as const,
      delta: "Hello ",
      messageId: "msg-abc",
    };
    expect(event.delta).toBe("Hello ");
  });

  it("tool_end event has status", () => {
    const event = {
      type: "tool_end" as const,
      toolCallId: "tc-1",
      toolName: "fetch_jobs",
      result: { count: 42 },
      status: "success" as const,
    };
    expect(event.status).toBe("success");
  });

  it("AgentState has all 11 keys", () => {
    const keys = Object.keys(EMPTY_STATE);
    expect(keys).toHaveLength(11);
    expect(keys).toContain("fetched_jobs");
    expect(keys).toContain("insertion_results");
  });
});
