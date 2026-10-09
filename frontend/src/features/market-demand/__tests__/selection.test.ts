import { describe, expect, it } from "vitest";
import { applyCategorySelection, applyIndividualSelection, applyRecommendationChanges, categorySelectionState, reconcileDraft } from "@/features/market-demand/selection";

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
