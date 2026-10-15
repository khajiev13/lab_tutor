import { describe, expect, it } from "vitest";
import { applyCategorySelection, applyIndividualSelection, applyRecommendationChanges, categorySelectionState, reconcileDraft, jobBackedCandidates, isUsablePostingUrl } from "@/features/market-demand/selection";

import { largeReviewFixture, reviewFixture } from "@/features/market-demand/__tests__/review-fixtures";

describe("explicit snapshot selection", () => {
  it("selects all current members and clears their exclusions without selecting later IDs", () => {
    expect(applyCategorySelection({selected_candidate_ids:["other"],excluded_candidate_ids:["b"]}, ["a","b"], true)).toEqual({selected_candidate_ids:["other","a","b"],excluded_candidate_ids:[]});
    expect(categorySelectionState(["a","b","late"],["a","b"])).toBe("indeterminate");
  });
  it("marks an individual exclusion and reports category none/some/all by membership", () => {
    expect(applyIndividualSelection({selected_candidate_ids:["a","b"],excluded_candidate_ids:[]}, "b", false)).toEqual({selected_candidate_ids:["a"],excluded_candidate_ids:["b"]});
    expect(categorySelectionState(["a","b"],["unrelated"])).toBe(false);
    expect(categorySelectionState(["a","b"],["a"])).toBe("indeterminate");
    expect(categorySelectionState(["a","b"],["a","b","unrelated"])).toBe(true);
  });
  it("clearing a category explicitly excludes all its members", () => {
    expect(applyCategorySelection({selected_candidate_ids:["a","other"],excluded_candidate_ids:[]},["a","b"],false)).toEqual({selected_candidate_ids:["other"],excluded_candidate_ids:["a","b"]});
  });
  it("applies only chosen suggestion changes and protects explicit exclusions", () => {
    expect(applyRecommendationChanges({selected_candidate_ids:["a"],excluded_candidate_ids:["b"]},[{candidate_id:"b",action:"add",reason:"Suggested"},{candidate_id:"c",action:"add",reason:"Suggested"},{candidate_id:"a",action:"remove",reason:"Suggested"}],["b","c"])).toEqual({selected_candidate_ids:["a","c"],excluded_candidate_ids:["b"]});
  });
  it("reconciles removed IDs visibly without transferring a selection to a merged or late member", () => {
    expect(reconcileDraft({selected_candidate_ids:["a","removed"],excluded_candidate_ids:["b"]},["a","b","merged","late"])).toEqual({draft:{selected_candidate_ids:["a"],excluded_candidate_ids:["b"]},removed_ids:["removed"]});
  });
});


describe("job-backed choices", () => {
  it("excludes reference-only candidates and orders eligible skills by name then ID", () => {
    const review = largeReviewFixture();
    review.candidates.reverse();
    const choices = jobBackedCandidates(review);
    expect(choices).toHaveLength(58);
    expect(choices[0].candidate_id).toBe("job-01");
    expect(choices[57].candidate_id).toBe("job-58");
  });
  it.each(["https://user:pass@example.com/job", "http://user@example.com/job", "https:///", "https:///example.com/job", "https://\\example.com/job", "//example.com/job", "javascript:alert(1)"])("rejects unusable posting URL %s", url => {
    expect(isUsablePostingUrl(url)).toBe(false);
    const review = reviewFixture();
    review.candidates[0].qualifying_posting_links = [url];
    expect(jobBackedCandidates(review).map(item => item.candidate_id)).toEqual(["sql"]);
  });
  it("breaks equal-name ties by candidate ID", () => {
    const review = reviewFixture();
    review.candidates = [{...review.candidates[0], display_name: "Same", candidate_id: "z"}, {...review.candidates[0], display_name: "Same", candidate_id: "a"}];
    expect(jobBackedCandidates(review).map(item => item.candidate_id)).toEqual(["a", "z"]);
  });
  it("requires supported status even with a valid URL", () => {
    const review = reviewFixture();
    review.candidates[0].posting_support = "missing";
    expect(jobBackedCandidates(review).map(item => item.candidate_id)).toEqual(["sql"]);
  });
});

it("formats official, estimated, partial and unavailable guidance without inventing scores", async () => {
  const {priorityLabel} = await import("@/features/market-demand/selection");
  const candidate = {value: 4.2, basis: "onet" as const, complete: true, expected_contexts: 1, scored_contexts: 1, display_order: 0};
  expect(priorityLabel(candidate)).toBe("4.2/5 · O*NET");
  expect(priorityLabel({...candidate, basis: "onet_aggregate", value: 4})).toBe("4/5 · O*NET average");
  expect(priorityLabel({...candidate, basis: "ai_estimate", value: 4})).toBe("4/5 · AI estimate");
  expect(priorityLabel({...candidate, basis: "unavailable", value: null})).toBe("Not assessed");
  expect(priorityLabel(null)).toBeNull();
  const category = {value: 4, basis: "ai_estimate" as const, complete: true, eligible_count: 5, scored_count: 5,
    onet_count: 2, estimated_count: 3, partial_count: 0, unavailable_count: 0, display_order: 0};
  expect(priorityLabel(category)).toBe("4/5 · Estimated");
  expect(priorityLabel({...category, complete: false})).toBe("4/5 · Estimated · Partial");
  expect(priorityLabel({...category, basis: "derived", estimated_count: 0})).toBe("4/5 · O*NET average");
});
