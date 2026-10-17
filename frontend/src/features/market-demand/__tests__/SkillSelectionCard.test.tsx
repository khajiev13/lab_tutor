import {useLayoutEffect} from "react";
import {act, render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, it, vi} from "vitest";
import {SkillSelectionCard} from "@/features/market-demand/components/SkillSelectionCard";
import {useSkillReviewController} from "@/features/market-demand/hooks/useSkillReviewController";
import {reviewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import type {PriorityAssessment, SkillReview} from "@/features/market-demand/types";

function priorityReview(): SkillReview {
  const base = reviewFixture();
  const assessment: PriorityAssessment = {assessment_id: "assessment-1", run_id: "run-1", candidate_revision: 1,
    input_fingerprint: "fingerprint", schema_version: 1, policy_version: "1", prompt_version: "1", model_id: "model",
    release: "30.0", started_at: "2026-10-15", updated_at: "2026-10-15", deadline_at: "2026-10-16", completed_at: "2026-10-15",
    status: "partial", contexts: [], results: [], summaries: {candidates: {}, categories: {}}, expected_pair_count: 24,
    completed_pair_count: 23, posting_hashes: {}, error_reasons: []};
  return {...base, priority_assessment: assessment, selected_candidate_ids: ["skill-0"], excluded_candidate_ids: ["skill-23", "reference"],
    categories: [{category_id: "tools", label: "Tools", priority: {value: 4, basis: "ai_estimate", complete: false, eligible_count: 24,
      scored_count: 23, onet_count: 1, estimated_count: 22, partial_count: 0, unavailable_count: 1, display_order: 0}}],
    candidates: [...Array.from({length: 24}, (_, index) => ({...base.candidates[0], candidate_id: `skill-${index}`,
      display_name: `Skill ${String(index).padStart(2, "0")}`, priority: {value: index === 22 ? null : index === 21 ? 4.2 : 4,
        basis: index === 22 ? "unavailable" as const : index === 21 ? "onet" as const : "ai_estimate" as const,
        complete: index !== 22, expected_contexts: 1, scored_contexts: index === 22 ? 0 : 1, display_order: 23 - index}})), base.candidates[2]]};
}
function setupPriorityReview(initial = priorityReview(), browse = true) {
  let current!: ReturnType<typeof useSkillReviewController>;
  function Harness({review}: {review: SkillReview}) {
    const controller = useSkillReviewController({courseId: 1, review, onReviewChange: vi.fn()});
    useLayoutEffect(() => {current = controller;}, [controller]);
    return <SkillSelectionCard browse={browse} controller={controller} onConfirm={vi.fn()} onInspect={vi.fn()}/>;
  }
  const view = render(<Harness review={initial}/>);
  return {...view, user: userEvent.setup(), controller: () => current,
    refresh: (review: SkillReview) => view.rerender(<Harness review={review}/>),
    initial,
    visibleCandidateIds: () => screen.queryAllByRole("checkbox", {name: /^Select Skill /}).map(row => row.getAttribute("aria-label")),
  };
}
it("shows compact importance labels while keeping exactly the existing teacher controls", async () => {
  const view = setupPriorityReview();
  expect(screen.getByText("4/5 · Estimated · Partial")).toBeInTheDocument();
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  expect(view.visibleCandidateIds().slice(0, 3)).toEqual(["Select Skill 23", "Select Skill 22", "Select Skill 21"]);
  expect(screen.getByText("4.2/5 · O*NET")).toBeInTheDocument();
  expect(screen.queryByText("Not assessed")).not.toBeInTheDocument();
  expect(screen.getByText(/Importance assessed for 23 of 24/)).toBeInTheDocument();
  expect(screen.getAllByText("4/5 · AI estimate")).toHaveLength(8);
  const controls = screen.getAllByRole("button").map(button => button.getAttribute("aria-label") ?? button.textContent);
  expect(screen.queryByRole("button", {name: /Confirm Selection/})).not.toBeInTheDocument();
  view.unmount();
  const legacy = setupPriorityReview({...view.initial, priority_assessment: null,
    categories: view.initial.categories.map(item => ({...item, priority: null})),
    candidates: view.initial.candidates.map(item => ({...item, priority: null}))});
  await legacy.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  expect(screen.getAllByRole("button").map(button => (button.getAttribute("aria-label") ?? button.textContent)?.replace(/Skill \d+/g, "Skill")))
    .toEqual(controls.map(value => value?.replace(/Skill \d+/g, "Skill")));
});
it("preserves dirty choices and row order when guidance refreshes", async () => {
  const view = setupPriorityReview();
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 21"}));
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 21"}));
  const before = view.visibleCandidateIds();
  const refreshed = {...view.initial, priority_assessment: {...view.initial.priority_assessment!, assessment_id: "assessment-2"},
    candidates: view.initial.candidates.map((item, index) => item.priority ? {...item, priority: {...item.priority, display_order: index, value: 3}} : item)};
  view.refresh(refreshed);
  expect(screen.getByText("3/5 · O*NET")).toBeInTheDocument();
  expect(view.visibleCandidateIds()).toEqual(before);
  expect(view.controller().draft.excluded_candidate_ids).toEqual(["skill-23", "reference", "skill-21"]);
  expect(view.controller().dirty).toBe(true);
  expect(view.controller().reviewRequired).toBe(false);
  expect(screen.queryByRole("button", {name: /Confirm Selection/})).not.toBeInTheDocument();
  view.refresh({...refreshed, candidate_revision: 2, priority_assessment: {...refreshed.priority_assessment, candidate_revision: 2}});
  expect(view.visibleCandidateIds()[0]).toBe("Select Skill 00");
});
it("selects off-page category members and retains an exclusion on reopen and reload", async () => {
  const view = setupPriorityReview();
  await view.user.click(screen.getByRole("checkbox", {name: /Select category Tools/}));
  expect(view.controller().draft.selected_candidate_ids).toHaveLength(24);
  expect(view.controller().draft.excluded_candidate_ids).toEqual(["reference"]);
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  await view.user.click(screen.getByRole("button", {name: "Next Tools page"}));
  await view.user.click(screen.getByRole("button", {name: "Next Tools page"}));
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 00"}));
  await view.user.click(screen.getByRole("button", {name: "Collapse Tools"}));
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  expect(screen.getByRole("checkbox", {name: "Select Skill 00"})).not.toBeChecked();
  const saved = {...view.initial, ...view.controller().draft};
  view.unmount();
  const reloaded = setupPriorityReview(saved);
  await reloaded.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  await reloaded.user.click(screen.getByRole("button", {name: "Next Tools page"}));
  await reloaded.user.click(screen.getByRole("button", {name: "Next Tools page"}));
  expect(screen.getByRole("checkbox", {name: "Select Skill 00"})).not.toBeChecked();
  expect(reloaded.controller().draft.excluded_candidate_ids).toEqual(["reference", "skill-0"]);
  expect(screen.queryByRole("checkbox", {name: "Select Reference skill"})).not.toBeInTheDocument();
});
it.each(["disabled", "stale", "wrong revision"])("keeps legacy order when %s guidance exists at entry", async mode => {
  const review = priorityReview();
  review.priority_assessment = mode === "disabled" ? null : {...review.priority_assessment!,
    status: mode === "stale" ? "stale" : "ready", candidate_revision: mode === "wrong revision" ? 0 : 1};
  const view = setupPriorityReview(review);
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  expect(view.visibleCandidateIds()[0]).toBe("Select Skill 00");
  expect(screen.queryByText("4.2/5 · O*NET")).not.toBeInTheDocument();
  act(() => view.controller().setCandidate("skill-2", true));
  expect(view.visibleCandidateIds()[0]).toBe("Select Skill 00");
});

it("shows decimal half-up ties in saved server order without reordering choices", async () => {
  const review = priorityReview();
  review.candidates = [4.04, 4.05, 4.06, 4.35].map((value, index) => ({...review.candidates[index],
    priority: {...review.candidates[index].priority!, value, basis: "onet_aggregate", display_order: [3, 2, 1, 0][index]}}));
  review.categories[0].priority = {...review.categories[0].priority!, value: 4.05, basis: "derived"};
  const view = setupPriorityReview(review);
  expect(screen.getByText("4.1/5 · O*NET average · Partial")).toBeInTheDocument();
  await view.user.click(screen.getByRole("button", {name: "Expand Tools"}));
  expect(view.visibleCandidateIds()).toEqual(["Select Skill 03", "Select Skill 02", "Select Skill 01", "Select Skill 00"]);
  for (const [name, label] of [["Skill 03", "4.4/5 · O*NET average"], ["Skill 02", "4.1/5 · O*NET average"], ["Skill 01", "4.1/5 · O*NET average"], ["Skill 00", "4/5 · O*NET average"]]) {
    expect(within(screen.getByRole("checkbox", {name: `Select ${name}`}).closest("label")!).getByText(label)).toBeInTheDocument();
  }
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 01"}));
  expect(view.visibleCandidateIds()).toEqual(["Select Skill 03", "Select Skill 02", "Select Skill 01", "Select Skill 00"]);
});

it("shows only five current saved choices initially while retaining the full selection and exclusions", () => {
  const review = priorityReview();
  review.selected_candidate_ids = ["skill-0", "skill-1", "skill-2", "skill-3", "skill-4", "skill-5"];
  const view = setupPriorityReview(review, false);
  expect(view.visibleCandidateIds()).toHaveLength(5);
  expect(screen.getByText(/1 more selected.*Skills & chart/)).toBeInTheDocument();
  expect(screen.queryByRole("checkbox", {name: /Select category/})).not.toBeInTheDocument();
  expect(view.controller().draft.selected_candidate_ids).toEqual(review.selected_candidate_ids);
  expect(view.controller().draft.excluded_candidate_ids).toEqual(["skill-23", "reference"]);
  expect(screen.getByRole("button", {name: "Confirm Selection (6)"})).toBeEnabled();
});
it("leaves zero choices empty with the full first-selection chooser inline", () => {
  const view = setupPriorityReview({...priorityReview(), selected_candidate_ids: []}, false);
  expect(screen.getByRole("checkbox", {name: "Select category Tools (24 current members)"})).not.toBeChecked();
  expect(view.controller().draft.selected_candidate_ids).toEqual([]);
  expect(screen.getByRole("button", {name: "Confirm Selection"})).toBeDisabled();
});

function sixtySkillReview(): SkillReview {
  const base = priorityReview();
  return {...base, categories: Array.from({length: 35}, (_, i) => ({category_id: `category-${i}`, label: `Category ${i}`})),
    selected_candidate_ids: ["skill-0", "skill-26", "skill-27", "skill-28", "skill-29"], excluded_candidate_ids: ["skill-1", "skill-59"],
    candidates: Array.from({length: 60}, (_, i) => ({...base.candidates[0], candidate_id: `skill-${i}`, display_name: `Skill ${String(i).padStart(2, "0")}`,
      category_id: `category-${i < 26 ? 0 : i - 25}`, priority: {value: i === 0 || i === 26 ? 4 : null,
        basis: i === 0 ? "onet" : i === 26 ? "ai_estimate" : "unavailable", complete: i === 0 || i === 26,
        expected_contexts: 1, scored_contexts: i === 0 || i === 26 ? 1 : 0, display_order: i}}))};
}
it("shows five saved choices and one honest coverage message for 60 skills across 35 categories", () => {
  const view = setupPriorityReview(sixtySkillReview(), false);
  expect(view.visibleCandidateIds()).toEqual(["Select Skill 00", "Select Skill 26", "Select Skill 27", "Select Skill 28", "Select Skill 29"]);
  expect(screen.getByText(/Importance assessed for 2 of 60 skills/)).toBeInTheDocument();
  expect(screen.getByText("4/5 · O*NET")).toBeInTheDocument();
  expect(screen.getByText("4/5 · AI estimate")).toBeInTheDocument();
  expect(screen.queryByText("Not assessed")).not.toBeInTheDocument();
  expect(view.controller().draft.excluded_candidate_ids).toEqual(["skill-1", "skill-59"]);
});
it("retains all 60 choices and category-wide selection beyond the five-skill preview", async () => {
  const view = setupPriorityReview(sixtySkillReview());
  expect(screen.getAllByRole("checkbox", {name: /^Select category/})).toHaveLength(35);
  await view.user.click(screen.getByRole("checkbox", {name: "Select category Category 0 (26 current members)"}));
  expect(view.controller().draft.selected_candidate_ids).toHaveLength(30);
  await view.user.click(screen.getByRole("button", {name: "Expand Category 0"}));
  await view.user.click(screen.getByRole("button", {name: "Next Category 0 page"}));
  await view.user.click(screen.getByRole("button", {name: "Next Category 0 page"}));
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 25"}));
  expect(view.controller().draft.selected_candidate_ids).toHaveLength(29);
  expect(view.controller().draft.excluded_candidate_ids).toEqual(["skill-59", "skill-25"]);
  const saved = {...view.initial, ...view.controller().draft};
  view.unmount();
  const reloaded = setupPriorityReview(saved, false);
  expect(reloaded.controller().draft.selected_candidate_ids).toHaveLength(29);
  expect(reloaded.controller().draft.excluded_candidate_ids).toEqual(["skill-59", "skill-25"]);
  expect(screen.getByRole("button", {name: "Confirm Selection (29)"})).toBeEnabled();
});

it("marks local changes as unsaved until the existing confirmation is used", async () => {
  const view = setupPriorityReview(sixtySkillReview(), false);
  expect(screen.queryByText("Changes are not saved until you confirm.")).not.toBeInTheDocument();
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 00"}));
  expect(screen.getByText("Changes are not saved until you confirm.")).toBeInTheDocument();
  expect(view.controller().dirty).toBe(true);
  expect(screen.getByRole("button", {name: "Confirm Selection (4)"})).toBeEnabled();
});

it("lets the first selection start inline and keeps its category list stable through draft edits", async () => {
  const view = setupPriorityReview({...sixtySkillReview(), selected_candidate_ids: []}, false);
  expect(screen.getAllByRole("checkbox", {name: /^Select category/})).toHaveLength(35);
  await view.user.click(screen.getByRole("button", {name: "Expand Category 0"}));
  await view.user.click(screen.getByRole("checkbox", {name: "Select Skill 00"}));
  expect(screen.getAllByRole("checkbox", {name: /^Select category/})).toHaveLength(35);
  expect(screen.getByRole("checkbox", {name: "Select Skill 00"})).toBeChecked();
  expect(screen.getByRole("button", {name: "Confirm Selection (1)"})).toBeEnabled();
  expect(view.controller().draft.selected_candidate_ids).toEqual(["skill-0"]);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
