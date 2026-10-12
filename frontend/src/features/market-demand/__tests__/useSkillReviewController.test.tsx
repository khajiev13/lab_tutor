import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { reconciliationA, reconciliationFixture, reviewFixture } from "@/features/market-demand/__tests__/review-fixtures";
import type { SkillReview } from "@/features/market-demand/types";

vi.mock("@/features/market-demand/api", async () => ({
  ...await vi.importActual("@/features/market-demand/api"),
  saveSkillReviewDraft: vi.fn(), confirmSkillReviewSelection: vi.fn(), continueWithAvailableEvidence: vi.fn(),
}));
import { saveSkillReviewDraft, confirmSkillReviewSelection, continueWithAvailableEvidence } from "@/features/market-demand/api";

beforeEach(() => vi.resetAllMocks());

function setup(review = reviewFixture(), courseId = 1) {
  const onReviewChange = vi.fn();
  return {...renderHook(props => useSkillReviewController(props), {initialProps: {courseId, review, onReviewChange}}), onReviewChange};
}

it("selects all current category members despite search and leaves empty categories unchanged", () => {
  const {result} = setup();
  act(() => result.current.updateView({filters: {category_ids: [], search: "Python", scope: "all"}}));
  act(() => result.current.setCategory("tools", true));
  expect(result.current.draft.selected_candidate_ids).toEqual(["python", "sql", "reference"]);
  act(() => result.current.setCategory("empty", false));
  expect(result.current.draft.selected_candidate_ids).toEqual(["python", "sql", "reference"]);
  act(() => result.current.undo());
  expect(result.current.draft.selected_candidate_ids).toEqual([]);
});

it("keeps explicit exclusions protected through a local proposal, with one undo", () => {
  const review = {...reviewFixture(), recommendations: [{id: "proposal", candidate_revision: 1, base_selection_revision: 2, changes: [
    {candidate_id: "python", action: "add" as const, reason: "Relevant"},
    {candidate_id: "sql", action: "add" as const, reason: "Relevant"},
  ]}]};
  const {result} = setup(review);
  act(() => result.current.setCandidate("sql", false));
  act(() => result.current.applyProposal("proposal"));
  expect(result.current.draft.selected_candidate_ids).toEqual(["python"]);
  expect(result.current.draft.excluded_candidate_ids).toEqual(["sql"]);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  act(() => result.current.undo());
  expect(result.current.draft.selected_candidate_ids).toEqual([]);
  expect(result.current.draft.excluded_candidate_ids).toEqual(["sql"]);
  act(() => result.current.setCandidate("sql", true));
  expect(result.current.draft.excluded_candidate_ids).toEqual([]);
});

it("ignores stale proposals", () => {
  const {result} = setup({...reviewFixture(), recommendations: [{id: "old", candidate_revision: 0, base_selection_revision: 2, changes: [{candidate_id: "python", action: "add", reason: "Old"}]}]});
  act(() => result.current.applyProposal("old"));
  expect(result.current.draft.selected_candidate_ids).toEqual([]);
  expect(result.current.dirty).toBe(false);
});

it("preserves valid dirty choices on same-run refresh and requires changed revision acknowledgement", async () => {
  const review = reviewFixture();
  const {result, rerender, onReviewChange} = setup(review);
  act(() => result.current.setCandidate("python", true));
  act(() => result.current.setCandidate("sql", false));
  const refreshed = {...review, candidate_revision: 2, selection_revision: 3, selected_candidate_ids: ["reference"], candidates: [...review.candidates, {...review.candidates[0], candidate_id: "new"}]};
  rerender({courseId: 1, review: refreshed, onReviewChange});
  expect(result.current.draft.selected_candidate_ids).toEqual(["python"]);
  expect(result.current.draft.excluded_candidate_ids).toEqual(["sql"]);
  expect(result.current.reviewRequired).toBe(true);
  await act(async () => {await expect(result.current.save()).rejects.toThrow(/review/i);});
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  act(() => result.current.acknowledgeIncomingReview());
  vi.mocked(saveSkillReviewDraft).mockResolvedValue({...refreshed, selected_candidate_ids: ["python"], excluded_candidate_ids: ["sql"], selection_revision: 4});
  await act(async () => {await result.current.save();});
  expect(saveSkillReviewDraft).toHaveBeenCalledWith(1, expect.objectContaining({expected_candidate_revision: 2, expected_selection_revision: 3}));
});

it("reports lost candidate names and never transfers selections to merged/new candidates", () => {
  const review = {...reviewFixture(), selected_candidate_ids: ["python"], excluded_candidate_ids: ["sql"]};
  const {result, rerender, onReviewChange} = setup(review);
  const next = {...review, candidate_revision: 2, candidates: [review.candidates[1], {...review.candidates[0], candidate_id: "merged", display_name: "Merged Python"}], selected_candidate_ids: ["merged"]};
  rerender({courseId: 1, review: next, onReviewChange});
  expect(result.current.draft.selected_candidate_ids).toEqual([]);
  expect(result.current.draft.excluded_candidate_ids).toEqual(["sql"]);
  expect(result.current.reconciliation).toMatch(/Python/);
  expect(result.current.reviewRequired).toBe(true);
});

it.each(["course", "run", "revision"])("rejects an old save across a changed %s", async change => {
  const review = reviewFixture();
  const {result, rerender, onReviewChange} = setup(review);
  let finish!: (review: SkillReview) => void;
  vi.mocked(saveSkillReviewDraft).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  act(() => result.current.setCandidate("python", true));
  let pending!: Promise<SkillReview>;
  act(() => {pending = result.current.save();});
  const rejection = expect(pending).rejects.toThrow(/changed|stale/i);
  rerender({courseId: change === "course" ? 2 : 1, review: {...review, run_id: change === "run" ? "run-2" : "run-1", selection_revision: change === "revision" ? 4 : 2}, onReviewChange});
  await act(async () => {finish({...review, selection_revision: 3, selected_candidate_ids: ["python"]}); await rejection;});
  expect(onReviewChange).not.toHaveBeenCalled();
  expect(result.current.busy).toBe(false);
  if (change !== "revision") expect(result.current.draft.selected_candidate_ids).toEqual([]);
});

it("retains busy and dirty draft through a same-revision refresh during save", async () => {
  const review = reviewFixture();
  const {result, rerender, onReviewChange} = setup(review);
  let finish!: (review: SkillReview) => void;
  vi.mocked(saveSkillReviewDraft).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  act(() => result.current.setCandidate("python", true));
  let pending!: Promise<SkillReview>;
  act(() => {pending = result.current.save();});
  rerender({courseId: 1, review: {...review}, onReviewChange});
  expect(result.current.busy).toBe(true);
  expect(result.current.draft.selected_candidate_ids).toEqual(["python"]);
  await act(async () => {finish({...review, selection_revision: 3, selected_candidate_ids: ["python"]}); await pending;});
  expect(result.current.dirty).toBe(false);
  expect(onReviewChange).toHaveBeenCalledTimes(1);
});

it("saves before reviewMappings and confirms returned revisions", async () => {
  const review = reviewFixture();
  const acknowledged = {...review, candidate_revision: 1, selection_revision: 5, selected_candidate_ids: ["python"]};
  vi.mocked(saveSkillReviewDraft).mockResolvedValue(acknowledged);
  vi.mocked(confirmSkillReviewSelection).mockResolvedValue({...acknowledged, integration_review: {review_digest: "digest", candidate_revision: 1, selection_revision: 5, items: [], omissions: [], omissions_acknowledged: true}});
  const {result} = setup(review);
  act(() => result.current.setCandidate("python", true));
  let returned!: SkillReview;
  await act(async () => {returned = await result.current.reviewMappings();});
  expect(confirmSkillReviewSelection).toHaveBeenCalledWith(1, {run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 5});
  expect(returned.integration_review?.review_digest).toBe("digest");
  expect(result.current.dirty).toBe(false);
});

it("rejects failed saves and never confirms or clears the draft", async () => {
  vi.mocked(saveSkillReviewDraft).mockRejectedValue(new Error("Connection lost"));
  const {result} = setup();
  act(() => result.current.setCandidate("python", true));
  await act(async () => {await expect(result.current.reviewMappings()).rejects.toThrow("Connection lost");});
  expect(confirmSkillReviewSelection).not.toHaveBeenCalled();
  expect(result.current.draft.selected_candidate_ids).toEqual(["python"]);
  expect(result.current.error).toBe("Connection lost");
});

it("saves only explicit reconciliations, then confirms after server resolution", async () => {
  const review = reconciliationFixture();
  const {result} = setup(review);
  act(() => result.current.acknowledgeReconciliation(reconciliationA, true));
  expect(result.current.pendingReconciliationIds).toEqual([reconciliationA]);
  vi.mocked(saveSkillReviewDraft).mockResolvedValue({...review, selection_revision: 3, reconciliations: review.reconciliations.map(record => ({...record, resolved: true}))});
  vi.mocked(confirmSkillReviewSelection).mockResolvedValue({...review, selection_revision: 3});
  await act(async () => {await result.current.reviewMappings();});
  expect(saveSkillReviewDraft).toHaveBeenCalledWith(1, expect.objectContaining({resolved_reconciliation_ids: [reconciliationA]}));
  expect(confirmSkillReviewSelection).toHaveBeenCalledWith(1, expect.objectContaining({expected_selection_revision: 3}));
});

it("returns evidence acknowledgement and rejects acknowledgement failures", async () => {
  const review = {...reviewFixture(), extraction_coverage: {status: "partial" as const, acknowledged: false}};
  const acknowledged = {...review, extraction_coverage: {...review.extraction_coverage, acknowledged: true}};
  const {result} = setup(review);
  vi.mocked(continueWithAvailableEvidence).mockRejectedValueOnce(new Error("Unavailable"));
  await act(async () => {await expect(result.current.acknowledgeAvailableEvidence()).rejects.toThrow("Unavailable");});
  expect(result.current.needsEvidenceAcknowledgement).toBe(true);
  vi.mocked(continueWithAvailableEvidence).mockResolvedValue(acknowledged);
  await act(async () => {expect(await result.current.acknowledgeAvailableEvidence()).toEqual(acknowledged);});
  expect(result.current.needsEvidenceAcknowledgement).toBe(false);
});

it("rejects a retained old save action after a course/run generation changes", async () => {
  const review = reviewFixture();
  const {result, rerender, onReviewChange} = setup(review);
  act(() => result.current.setCandidate("python", true));
  const oldSave = result.current.save;
  rerender({courseId: 2, review: {...review, run_id: "run-2"}, onReviewChange});
  await act(async () => {await expect(oldSave()).rejects.toThrow(/changed|stale/i);});
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
});

it("locks local selection actions immediately when a save begins", async () => {
  const review = reviewFixture();
  const {result} = setup(review);
  act(() => result.current.setCandidate("python", true));
  let finish!: (review: SkillReview) => void;
  vi.mocked(saveSkillReviewDraft).mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  let pending!: Promise<SkillReview>;
  act(() => {
    pending = result.current.save();
    result.current.setCandidate("sql", true);
  });
  expect(result.current.draft.selected_candidate_ids).toEqual(["python"]);
  await act(async () => {finish({...review, selected_candidate_ids: ["python"], selection_revision: 3}); await pending;});
});
