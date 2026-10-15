import type { AgentState, PipelineStageId, StageStatus } from "@/features/market-demand/types";

function hasItems(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return value != null && (typeof value !== "object" || Object.keys(value).length > 0);
}

export function derivePipelineStages(state: AgentState): Record<PipelineStageId, StageStatus> {
  const outcomes = Object.values(state.source_outcomes ?? {});
  const collected = outcomes.length > 0
    ? outcomes.every((outcome) => outcome.status === "success" || outcome.status === "empty" || outcome.status === "skipped")
    : hasItems(state.fetched_jobs);
  const stages: Record<PipelineStageId, StageStatus> = {
    fetch: collected ? "complete" : "pending",
    select: hasItems(state.selected_jobs) ? "complete" : "pending",
    extract: hasItems(state.extracted_skills) ? "complete" : "pending",
    map: hasItems(state.curriculum_mapping) ? "complete" : "pending",
    approve: hasItems(state.selected_for_insertion) ? "complete" : "pending",
    link: hasItems(state.skill_concepts) ? "complete" : "pending",
    insert: hasItems(state.insertion_results) ? "complete" : "pending",
  };
  const order: PipelineStageId[] = ["fetch", "select", "extract", "map", "approve", "link", "insert"];
  const active = order.find((id) => stages[id] === "pending");
  if (active) stages[active] = "active";
  return stages;
}
