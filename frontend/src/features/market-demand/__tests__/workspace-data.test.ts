import {describe, expect, it} from "vitest";
import corpus from "@/features/market-demand/__tests__/teacher-workspace-patterns.json";
import {reviewFixture, workspaceEvidenceFixture, workspaceOtherSoc, workspaceReviewFixture, workspaceSoc, workspaceViewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import {buildWorkspaceData, derivePatternObservations, resolveOnetRating} from "@/features/market-demand/workspace-data";
import type {SkillReview, WorkspaceFilters, WorkspaceViewState} from "@/features/market-demand/types";

const draft = {selected_candidate_ids: [] as string[], excluded_candidate_ids: [] as string[]};

describe("exact workspace datasets", () => {
  it("keeps full scope while limiting demand and paginating heatmap/table", () => {
    const review = workspaceReviewFixture();
    review.candidates = Array.from({length: 40}, (_, i) => ({...review.candidates[0], candidate_id: String(i), display_name: `Skill ${String(i).padStart(2, "0")}`}));
    const data = buildWorkspaceData(review, draft, workspaceViewFixture());
    expect(data.scope.candidates).toHaveLength(40);
    expect(data.demandRows).toHaveLength(12);
    expect(data.heatmapPage.rows).toHaveLength(12);
    expect(data.tablePage.rows).toHaveLength(25);
    expect(data.tablePage.total).toBe(40);
    expect(data.observations.length).toBeLessThanOrEqual(2);
  });
  it("intersects NFKC search, category and local draft without changing denominators and clamps pages", () => {
    const review = reviewFixture();
    review.candidates[0].display_name = "  ＰＹＴＨＯＮ  ";
    const view = {...workspaceViewFixture(), page: 99, filters: {category_ids: ["tools"], search: " python ", scope: "selected" as const}};
    const data = buildWorkspaceData(review, {...draft, selected_candidate_ids: ["python"]}, view);
    expect(data.tablePage.page).toBe(1);
    expect(data.tablePage.rows.map(row => row.candidateId)).toEqual(["python"]);
    expect(data.tablePage.rows[0].candidate.job_metrics.assessed_posting_count).toBe(4);
    expect(buildWorkspaceData(review, draft, {...view, filters: {...view.filters, search: "py  thon"}}).scope.candidates).toEqual([]);
  });
  it.each(["asc", "desc"] as const)("keeps missing demand and ratings last for %s sorting", direction => {
    const review = workspaceReviewFixture();
    review.candidates = [{...review.candidates[0], candidate_id: "missing", job_metrics: {percentage: 100, assessed_posting_count: 0}},
      {...review.candidates[0], candidate_id: "zero", job_metrics: {percentage: 0, assessed_posting_count: 10}},
      {...review.candidates[0], candidate_id: "high", job_metrics: {percentage: 80, assessed_posting_count: 10}}];
    const view = {...workspaceViewFixture(), sort: {field: "frequency", direction}};
    expect(buildWorkspaceData(review, draft, view).tablePage.rows.map(row => row.candidateId)).toEqual(direction === "asc" ? ["zero", "high", "missing"] : ["high", "zero", "missing"]);
    review.candidates[1].onet_associations = [workspaceEvidenceFixture()];
    expect(buildWorkspaceData(review, draft, {...view, sort: {field: "rating", direction}}).tablePage.rows[0].candidateId).toBe("zero");
  });
  it("keeps an all-zero assessed sample distinct from an entirely unassessed sample", () => {
    const review = workspaceReviewFixture();
    review.candidates[0].job_metrics = {supporting_posting_count: 0, assessed_posting_count: 10, percentage: 0};
    const assessed = buildWorkspaceData(review, draft, workspaceViewFixture());
    expect(assessed.demandRows[0].demand).toBe(0);
    expect(assessed.observations).toEqual([]);
    review.candidates[0].job_metrics = {supporting_posting_count: 0, assessed_posting_count: 0, percentage: null};
    const unassessed = buildWorkspaceData(review, draft, workspaceViewFixture());
    expect(unassessed.demandRows[0].demand).toBeNull();
    expect(unassessed.observations).toEqual([]);
  });
  it("sorts ties by normalized Unicode code points then ID without collapsing whitespace", () => {
    const review = workspaceReviewFixture();
    review.candidates = ["😀", "\uE000", "Я", " A  B ", "ａ b", "a b"].map((label, i) => ({...review.candidates[0], candidate_id: String(i), display_name: label}));
    expect(buildWorkspaceData(review, draft, workspaceViewFixture()).tablePage.rows.map(row => row.candidateId)).toEqual(["3", "4", "5", "2", "1", "0"]);
  });
  it("uses only the chosen confirmed role for scatter and current metric for heatmap", () => {
    const review = workspaceReviewFixture();
    review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: "other", soc_code: workspaceOtherSoc})];
    const view = workspaceViewFixture();
    expect(buildWorkspaceData(review, draft, view).scatterPoints[0].importance).toBe(4);
    expect(buildWorkspaceData(review, draft, {...view, activeOccupationCode: null}).scatterPoints).toEqual([]);
    expect(buildWorkspaceData(review, draft, {...view, metric: "LV"}).heatmapPage.rows[0].ratings[workspaceSoc]).toMatchObject({status: "reported", value: 0});
    expect(buildWorkspaceData(review, draft, {...view, activeOccupationCode: "99-9999.00"}).scatterPoints).toEqual([]);
    expect(buildWorkspaceData({...review, analysis_metadata: null}, draft, view).heatmapPage.rows).toEqual([]);
  });
});

describe("O*NET rating resolution", () => {
  it("deduplicates IDs and same-descriptor rows but preserves descriptor ambiguity until chosen", () => {
    const candidate = workspaceReviewFixture().candidates[0];
    const first = workspaceEvidenceFixture();
    candidate.onet_associations = [first, first, workspaceEvidenceFixture({id: "second"})];
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0")).toMatchObject({status: "reported", value: 4});
    candidate.onet_associations.push(workspaceEvidenceFixture({id: "distinct", element_id: "other"}));
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0").status).toBe("ambiguous");
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0", "distinct")).toMatchObject({status: "reported", descriptorKey: ["30.0", "essential", "other"]});
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0", "unknown").status).toBe("no_association");
  });
  it.each(["missing", "suppressed", "not_relevant"] as const)("retains %s and never plots its numeric value", status => {
    const candidate = workspaceReviewFixture().candidates[0];
    const association = workspaceEvidenceFixture();
    association.evidence.ratings.IM!.status = status;
    candidate.onet_associations = [association];
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0")).toMatchObject({status});
    expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0")).not.toHaveProperty("value");
  });
  it("rejects wrong release, broader/software, absent bounds, wrong scale, non-finite and out-of-range values", () => {
    const candidate = workspaceReviewFixture().candidates[0];
    for (const association of [workspaceEvidenceFixture({release: "29.0"}), {...workspaceEvidenceFixture(), relation: "broader" as const}, workspaceEvidenceFixture({family: "software"})]) {
      candidate.onet_associations = [association];
      expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0").status).toBe("no_association");
    }
    for (const patch of [{minimum: undefined}, {maximum: 6}, {scale_id: "LV"}, {value: NaN}, {value: Infinity}, {value: 0}, {value: 6}]) {
      const association = workspaceEvidenceFixture();
      Object.assign(association.evidence.ratings.IM!, patch);
      candidate.onet_associations = [association];
      expect(resolveOnetRating(candidate, workspaceSoc, "IM", "30.0").status).toBe("missing");
    }
  });
});

describe("reviewed cross-language observations", () => {
  it.each(corpus.cases)("$name", ({review: raw, context, expected}) => {
    const review = {...reviewFixture(), ...raw, candidates: raw.candidates.map(candidate => ({...reviewFixture().candidates[0], original_labels: [], aliases: [], ...candidate}))} as SkillReview;
    const view: WorkspaceViewState = {...workspaceViewFixture(), filters: context.filters as WorkspaceFilters, occupationCodes: context.occupation_codes, descriptorChoices: context.descriptor_choices};
    const before = JSON.stringify(review);
    const data = buildWorkspaceData(review, {selected_candidate_ids: review.selected_candidate_ids, excluded_candidate_ids: []}, view);
    expect(derivePatternObservations(data.scope)).toEqual(expected);
    expect(data.observations).toEqual(expected);
    expect(JSON.stringify(review)).toBe(before);
  });
  it("refuses role comparisons when explicit choices refer to different descriptors", () => {
    const review = workspaceReviewFixture();
    review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: "role2", soc_code: workspaceOtherSoc, element_id: "other"})];
    const view = {...workspaceViewFixture(), descriptorChoices: [{candidate_id: review.candidates[0].candidate_id, evidence_id: "role2"}]};
    expect(buildWorkspaceData(review, draft, view).observations).toEqual([]);
    expect(buildWorkspaceData(review, draft, view).heatmapPage.rows[0].ratings[workspaceSoc].status).toBe("ambiguous");
    expect(buildWorkspaceData(review, draft, view).heatmapPage.rows[0].ratings[workspaceOtherSoc].status).toBe("ambiguous");
  });
});
