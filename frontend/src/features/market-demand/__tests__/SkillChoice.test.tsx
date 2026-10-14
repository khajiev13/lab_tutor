import { useLayoutEffect } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SkillChoice } from "@/features/market-demand/components/SkillChoice";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { largeReviewFixture, reviewFixture } from "@/features/market-demand/__tests__/review-fixtures";
import { categorySelectionState } from "@/features/market-demand/selection";
import type { SkillReview } from "@/features/market-demand/types";

vi.mock("@/features/market-demand/api", async () => ({
  ...await vi.importActual("@/features/market-demand/api"), saveSkillReviewDraft: vi.fn(),
}));
import { saveSkillReviewDraft } from "@/features/market-demand/api";

beforeEach(() => vi.resetAllMocks());

function setup(review: SkillReview = largeReviewFixture()) {
  let controller!: SkillReviewController;
  const inspect = vi.fn();
  function Harness({review}: {review: SkillReview}) {
    const current = useSkillReviewController({courseId: 1, review, onReviewChange: () => {}});
    useLayoutEffect(() => {controller = current;});
    return <SkillChoice controller={current} onInspect={inspect}/>;
  }
  const rendered = render(<Harness review={review}/>);
  return {...rendered, rerenderReview: (review: SkillReview) => rendered.rerender(<Harness review={review}/>), getController: () => controller, inspect};
}

it("keeps zero selections explicit and browses only 58 job-backed candidates ten at a time", async () => {
  const user = userEvent.setup();
  const {getController} = setup();
  expect(screen.getByText("No skills chosen yet")).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Browse skills"}));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getAllByRole("checkbox", {name: /^Select Job skill/})).toHaveLength(10);
  expect(within(dialog).queryByText("Reference skill 1")).not.toBeInTheDocument();
  expect(getController().draft.selected_candidate_ids).toEqual([]);
});

it("uses every category member through search, later pages, close and reopen with mixed state", async () => {
  const user = userEvent.setup();
  const {getController} = setup();
  await user.click(screen.getByRole("button", {name: "Browse skills"}));
  await user.type(screen.getByRole("textbox", {name: "Search skills"}), "Job skill 01");
  const category = screen.getByRole("checkbox", {name: "Select category Tools (12 current members)"});
  category.focus();
  await user.keyboard(" ");
  expect(getController().draft.selected_candidate_ids).toHaveLength(12);
  await user.clear(screen.getByRole("textbox", {name: "Search skills"}));
  await user.click(screen.getByRole("button", {name: "Next page"}));
  await user.click(screen.getByRole("checkbox", {name: "Select Job skill 12"}));
  expect(getController().draft.selected_candidate_ids).toHaveLength(11);
  expect(getController().draft.excluded_candidate_ids).toContain("job-12");
  expect(getController().draft.excluded_candidate_ids).toContain("reference-1");
  expect(categorySelectionState(Array.from({length: 12}, (_, i) => `job-${String(i + 1).padStart(2, "0")}`), getController().draft.selected_candidate_ids)).toBe("indeterminate");
  expect(screen.getByRole("checkbox", {name: "Select category Tools (12 current members)"})).toHaveAttribute("aria-checked", "mixed");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name: "Review all 11"})).toHaveFocus();
  await user.click(screen.getByRole("button", {name: "Review all 11"}));
  expect(screen.getByRole("checkbox", {name: "Select Job skill 12"})).not.toBeChecked();
});

it("shows only five main rows for all 58 saved skills and offers complete review", async () => {
  const review = largeReviewFixture();
  review.selected_candidate_ids = Array.from({length: 58}, (_, i) => `job-${String(i + 1).padStart(2, "0")}`);
  const user = userEvent.setup();
  const {getController} = setup(review);
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
  expect(screen.getByRole("button", {name: "Review all 58"})).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Review all 58"}));
  await user.click(screen.getByRole("button", {name: "Next page"}));
  expect(screen.getByRole("checkbox", {name: "Select Job skill 12"})).toBeChecked();
  expect(getController().draft.selected_candidate_ids).toHaveLength(58);
});

it("labels proposals, never silently accepts advice, and protects excluded or unsupported additions", async () => {
  const user = userEvent.setup();
  const review = {...reviewFixture(), excluded_candidate_ids: ["sql"], recommendations: [{id: "proposal", candidate_revision: 1, base_selection_revision: 2, changes: [
    {candidate_id: "python", action: "add" as const, reason: "Useful"},
    {candidate_id: "sql", action: "add" as const, reason: "Useful"},
    {candidate_id: "reference", action: "add" as const, reason: "Context"},
  ]}]};
  const {getController, inspect} = setup(review);
  expect(getController().draft.selected_candidate_ids).toEqual([]);
  expect(screen.queryByRole("button", {name: "Apply proposal for Python"})).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Inspect Python"}));
  expect(inspect).toHaveBeenCalledWith("python");
  await user.click(screen.getByRole("button", {name: "Browse skills"}));
  expect(screen.getByRole("button", {name: "Apply proposal for SQL"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "Apply proposal for Reference skill"})).toBeDisabled();
  expect(screen.getByText(/Needs supporting job posting/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Apply proposal for Python"}));
  expect(getController().draft.selected_candidate_ids).toEqual(["python"]);
  expect(getController().draft.excluded_candidate_ids).toEqual(["sql"]);
});

it("retains the draft on a failed save and reconciles the server response on retry", async () => {
  const user = userEvent.setup();
  const review = reviewFixture();
  const {getController} = setup(review);
  await user.click(screen.getByRole("button", {name: "Browse skills"}));
  await user.click(screen.getByRole("checkbox", {name: "Select Python"}));
  await user.keyboard("{Escape}");
  vi.mocked(saveSkillReviewDraft).mockRejectedValueOnce(new Error("Connection lost"));
  await user.click(screen.getByRole("button", {name: "Save draft"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  expect(getController().draft.selected_candidate_ids).toEqual(["python"]);
  expect(getController().dirty).toBe(true);
  vi.mocked(saveSkillReviewDraft).mockResolvedValueOnce({...review, selected_candidate_ids: ["python"], selection_revision: 3});
  await user.click(screen.getByRole("button", {name: "Save draft"}));
  expect(await screen.findByRole("status")).toHaveTextContent("Draft saved");
  expect(getController().review?.selection_revision).toBe(3);
  expect(getController().dirty).toBe(false);
});

it("surfaces lost posting evidence as a required review while preserving the saved choice", async () => {
  const user = userEvent.setup();
  const review = {...reviewFixture(), selected_candidate_ids: ["python"]};
  const {rerenderReview, getController} = setup(review);
  const unsupported = {...review, candidate_revision: 2, candidates: review.candidates.map(item => item.candidate_id === "python" ? {...item, qualifying_posting_links: []} : item)};
  rerenderReview(unsupported);
  expect(getController().draft.selected_candidate_ids).toEqual(["python"]);
  expect(screen.getByRole("alert")).toHaveTextContent(/Review required.*Python/);
  expect(screen.getByRole("button", {name: "Save draft"})).toBeDisabled();
  await user.click(screen.getByRole("button", {name: "Remove Python"}));
  expect(getController().draft.selected_candidate_ids).toEqual([]);
  expect(getController().draft.excluded_candidate_ids).toContain("python");
});

it("closes Browse before opening job evidence and retains its draft", async () => {
 const {inspect, getController} = setup();
 await userEvent.click(screen.getByRole("button", {name:"Browse skills"}));
 await userEvent.click(screen.getByRole("checkbox", {name:"Select Job skill 01"}));
 await userEvent.click(screen.getByRole("button", {name:"Inspect Job skill 01"}));
 expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
 expect(inspect).toHaveBeenCalledWith("job-01");
 expect(getController().draft.selected_candidate_ids).toEqual(["job-01"]);
});
