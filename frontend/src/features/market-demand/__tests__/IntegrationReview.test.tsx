import { useState } from "react";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { SkillReviewPanel as ControlledSkillReviewPanel } from "@/features/market-demand/components/SkillReviewPanel";
import { EvidenceLink } from "@/features/market-demand/components/SkillEvidencePanel";
import type { IntegrationApprovalResponse, SkillReview } from "@/features/market-demand/types";
import { IntegrationReview } from "@/features/market-demand/components/IntegrationReview";
import { integrationFixture, reconciliationFixture, withdrawalFixture } from "@/features/market-demand/__tests__/review-fixtures";
function SkillReviewPanel({courseId, review, onReviewChange, disabled}: {courseId: number; review: SkillReview; onReviewChange: (review: SkillReview) => void; disabled?: boolean}) {
  const controller = useSkillReviewController({courseId, review, onReviewChange, disabled});
  return <ControlledSkillReviewPanel courseId={courseId} controller={controller}/>;
}

vi.mock("@/features/market-demand/api",async()=>({...await vi.importActual("@/features/market-demand/api"),approveSkillIntegration:vi.fn(),prepareSkillWithdrawal:vi.fn()}));
import { approveSkillIntegration, prepareSkillWithdrawal } from "@/features/market-demand/api";
beforeEach(()=>vi.resetAllMocks());

it("reviewed concepts displays normalized server names and nullable descriptions as safe text before approval", () => {
  const review = integrationFixture();
  const item = {...review.integration_review!.items[0], concepts: [
    {name: "Normalized Python functions", description: "Call functions with <script>alert('description')</script> arguments"},
    {name: "<img src=x onerror=alert('name')>", description: null},
  ]};
  review.integration_review!.items[0] = item;
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  const target = screen.getByText("Python programming").closest("div")!;
  expect(within(target).getByText("Chapters: Programming")).toBeInTheDocument();
  expect(within(target).getByText("Normalized Python functions")).toBeInTheDocument();
  expect(within(target).getByText("Call functions with <script>alert('description')</script> arguments")).toBeInTheDocument();
  expect(within(target).getByText("<img src=x onerror=alert('name')>")).toBeInTheDocument();
  expect(target.querySelector("script, img")).toBeNull();
  expect(within(target).queryByText("null")).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeEnabled();
  expect(approveSkillIntegration).not.toHaveBeenCalled();
});

it("reviewed concepts keeps an absent concepts field compatible with target/chapter review and approval", () => {
  render(<IntegrationReview courseId={1} review={integrationFixture()} onReviewChange={vi.fn()}/>);
  expect(screen.getByText("Python programming")).toBeInTheDocument();
  expect(screen.getByText("Chapters: Programming")).toBeInTheDocument();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeEnabled();
  expect(approveSkillIntegration).not.toHaveBeenCalled();
});

it("shows reviewed targets/chapters and blocks final approval without every proposed posting", () => {
  const review = integrationFixture();
  review.candidates[0].posting_support="missing";
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByText("Python programming")).toBeInTheDocument();
  expect(screen.getByText(/Programming/)).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Approve integration"})).toBeDisabled();
  expect(screen.getByText(/Needs supporting job posting/)).toBeInTheDocument();
});

it("keeps the full proposal and prior publication visible on server evidence rejection", async () => {
  vi.mocked(approveSkillIntegration).mockRejectedValue(new Error("missing_job_evidence: python"));
  render(<IntegrationReview courseId={1} review={integrationFixture()} onReviewChange={vi.fn()}/>);
  await userEvent.setup().click(screen.getByRole("button",{name:"Approve integration"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("missing_job_evidence: python");
  expect(screen.getByText("Python programming")).toBeInTheDocument();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
  expect(screen.queryByText(/Approval saved/)).not.toBeInTheDocument();
});

it("submits digest and exact IDs and distinguishes SQL approval from pending projection", async () => {
  const review = integrationFixture();
  vi.mocked(approveSkillIntegration).mockResolvedValue({review:{...review,publication_revision:4},projection_status:"pending"});
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  await userEvent.setup().click(screen.getByRole("button",{name:"Approve integration"}));
  expect(await screen.findByText("Approval saved; publication waiting for projection")).toBeInTheDocument();
  expect(approveSkillIntegration).toHaveBeenCalledWith(1,{run_id:"run-1",expected_candidate_revision:1,expected_selection_revision:2,review_digest:"digest-1",approved_candidate_ids:["python"]});
});

it.each(["candidate_revision", "selection_revision"] as const)("blocks stale %s independently of acknowledged omissions", revision => {
  const review = integrationFixture();
  review.integration_review = {...review.integration_review!, [revision]: 0};
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.getByText(/Review revisions changed/)).toBeInTheDocument();
  expect(screen.queryByText(/Acknowledge the current evidence omissions/)).not.toBeInTheDocument();
});

it("blocks unacknowledged omissions independently of current revisions", () => {
  const review = integrationFixture();
  review.integration_review = {...review.integration_review!, omissions: ["HeadHunter incomplete"], omissions_acknowledged: false};
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.getByText("HeadHunter incomplete")).toBeInTheDocument();
  expect(screen.queryByText(/Review revisions changed/)).not.toBeInTheDocument();
});

function ReviewParent({initialReview}: {initialReview: SkillReview}) {
  const [review, setReview] = useState(initialReview);
  return <SkillReviewPanel courseId={1} review={review} onReviewChange={setReview}/>;
}

it.each([
  {projection: "pending" as const, acknowledgement: "Approval saved; publication waiting for projection"},
  {projection: "error" as const, acknowledgement: "Approval saved; projection failed"},
])("retains $projection projection acknowledgement through the real panel parent when approval clears the proposal", async ({projection, acknowledgement}) => {
  const review = integrationFixture();
  vi.mocked(approveSkillIntegration).mockResolvedValue({
    review: {...review, integration_review: null, publication_revision: 4},
    projection_status: projection,
  });
  render(<ReviewParent initialReview={review}/>);
  await userEvent.setup().click(screen.getByRole("button", {name: "Approve integration"}));
  expect(await screen.findByRole("status")).toHaveTextContent(acknowledgement);
  expect(screen.queryByText("Python programming")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Approve integration"})).not.toBeInTheDocument();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
});

const unusableLinks = [
  {label: "empty list", urls: []},
  {label: "empty string", urls: [""]},
  {label: "relative path", urls: ["/vacancy/123"]},
  {label: "protocol-relative path", urls: ["//hh.uz/vacancy/123"]},
  {label: "script scheme", urls: ["javascript:alert(1)"]},
  {label: "FTP scheme", urls: ["ftp://employer.example/job/123"]},
  {label: "malformed absolute URL", urls: ["https://"]},
  {label: "scheme without absolute authority", urls: ["https:hh.uz/vacancy/123"]},
];

it.each(unusableLinks)("blocks approval when supported candidate links contain only $label", ({urls}) => {
  const review = integrationFixture();
  review.candidates[0].qualifying_posting_links = urls;
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
});

it.each(unusableLinks)("blocks approval and renders no posting link when reviewed target links contain only $label", ({urls}) => {
  const review = integrationFixture();
  review.integration_review!.items[0].qualifying_posting_links = urls;
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.queryByRole("link", {name: "Original job posting"})).not.toBeInTheDocument();
});

it.each(unusableLinks.filter(item => item.urls.length > 0))("omits an evidence link for $label", ({urls}) => {
  render(<EvidenceLink url={urls[0]} label="Original job posting"/>);
  expect(screen.queryByRole("link", {name: "Original job posting"})).not.toBeInTheDocument();
});

it.each(["http://employer.example/job/123", "https://employer.example/job/123"])("allows supported approval and renders an available absolute link %s", url => {
  const review = integrationFixture();
  review.candidates[0].qualifying_posting_links = ["", url];
  review.integration_review!.items[0].qualifying_posting_links = ["/relative", url];
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeEnabled();
  expect(screen.getByRole("link", {name: "Original job posting"})).toHaveAttribute("href", url);
});

it.each([
  {projection: "projected" as const, acknowledgement: "Withdrawal saved; removal projected"},
  {projection: "pending" as const, acknowledgement: "Withdrawal saved; removal waiting for projection"},
  {projection: "error" as const, acknowledgement: "Withdrawal saved; projection failed"},
])("explicit withdrawal uses two steps and preserves unsaved choices despite missing evidence/history ($projection)", async ({projection, acknowledgement}) => {
  const initial = reconciliationFixture();
  initial.candidates[0].posting_support = "missing";
  initial.candidates[0].qualifying_posting_links = [];
  initial.extraction_coverage = {status: "partial", acknowledged: false, warnings: ["Posting unavailable"]};
  const prepared = {...withdrawalFixture(), candidates: initial.candidates, extraction_coverage: initial.extraction_coverage};
  let finish!: (response: SkillReview) => void;
  vi.mocked(prepareSkillWithdrawal).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  vi.mocked(approveSkillIntegration).mockResolvedValueOnce({
    review: {...prepared, integration_review: null, publication_revision: 4, approved_references: []},
    projection_status: projection,
  });
  render(<ReviewParent initialReview={initial}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox", {name: "Select SQL"}));
  await user.click(screen.getByRole("checkbox", {name: "Acknowledge reconciliation for Prior Python"}));
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeDisabled();
  const prepareButton = screen.getByRole("button", {name: "Prepare withdrawal"});
  expect(prepareButton).toBeEnabled();
  expect(screen.getByText(/saved learning paths and resources.*preserved/i)).toBeInTheDocument();
  expect(screen.getByText(/other approvals.*keep.*available/i)).toBeInTheDocument();
  await user.click(prepareButton);
  expect(prepareSkillWithdrawal).toHaveBeenCalledWith(1, {run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 2});
  expect(screen.getByText("Published Python")).toBeInTheDocument();
  expect(approveSkillIntegration).not.toHaveBeenCalled();
  expect(screen.queryByText(/Withdrawal saved/)).not.toBeInTheDocument();
  expect(prepareButton).toBeDisabled();
  await act(async () => finish(prepared));
  expect(screen.getByRole("checkbox", {name: "Select SQL"})).toBeChecked();
  expect(screen.getByRole("checkbox", {name: "Acknowledge reconciliation for Prior Python"})).toBeChecked();
  expect(screen.getByRole("button", {name: "Withdraw approval"})).toBeEnabled();
  await user.click(screen.getByRole("button", {name: "Withdraw approval"}));
  expect(await screen.findByRole("status")).toHaveTextContent(acknowledgement);
  expect(approveSkillIntegration).toHaveBeenCalledWith(1, {
    run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 2,
    review_digest: "withdrawal-digest-1", approved_candidate_ids: [],
  });
  expect(screen.queryByText("Published Python")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Prepare withdrawal"})).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", {name: "Select SQL"})).toBeChecked();
  expect(screen.getByRole("checkbox", {name: "Acknowledge reconciliation for Prior Python"})).toBeChecked();
}, 15000);

it.each(["pending", "error"] as const)("explicit withdrawal remains preparable for an active offering with %s projection", projection => {
  const review = reconciliationFixture();
  review.approved_references[0] = {...review.approved_references[0], projection_status: projection, available_for_new_selection: false};
  render(<ReviewParent initialReview={review}/>);
  expect(screen.getByRole("button", {name: "Prepare withdrawal"})).toBeEnabled();
});

it.each(["candidate", "selection", "missing digest", "nonempty items"] as const)("explicit withdrawal blocks a %s review", invalid => {
  const review = withdrawalFixture();
  if (invalid === "candidate") review.integration_review.candidate_revision = 0;
  if (invalid === "selection") review.integration_review.selection_revision = 0;
  if (invalid === "missing digest") review.integration_review.review_digest = "";
  if (invalid === "nonempty items") review.integration_review.items = integrationFixture().integration_review!.items;
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("button", {name: "Withdraw approval"})).toBeDisabled();
  expect(approveSkillIntegration).not.toHaveBeenCalled();
});

it("explicit withdrawal never treats an unmarked initial empty publication as a withdrawal", () => {
  const review = integrationFixture();
  review.approved_references = [];
  review.selected_candidate_ids = [];
  review.integration_review!.items = [];
  render(<IntegrationReview courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.queryByRole("button", {name: "Withdraw approval"})).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Prepare withdrawal"})).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
});

it("explicit withdrawal uses active references rather than historical publication revision", () => {
  const review = {...reconciliationFixture(), approved_references: [], publication_revision: 9};
  render(<ReviewParent initialReview={review}/>);
  expect(screen.queryByRole("button", {name: "Prepare withdrawal"})).not.toBeInTheDocument();
});

it("explicit withdrawal honors the panel external lock even though publication-only gates can be bypassed", () => {
  render(<SkillReviewPanel courseId={1} review={withdrawalFixture()} onReviewChange={vi.fn()} disabled/>);
  expect(screen.getByRole("button", {name: "Prepare withdrawal"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "Withdraw approval"})).toBeDisabled();
});

it.each(["prepare", "withdraw"] as const)("explicit withdrawal retains offering and choices when %s fails", async action => {
  const review = action === "prepare" ? reconciliationFixture() : withdrawalFixture();
  if (action === "prepare") vi.mocked(prepareSkillWithdrawal).mockRejectedValueOnce(new Error("Withdrawal preparation rejected"));
  else vi.mocked(approveSkillIntegration).mockRejectedValueOnce(new Error("Withdrawal digest rejected"));
  render(<ReviewParent initialReview={review}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox", {name: "Select SQL"}));
  await user.click(screen.getByRole("button", {name: action === "prepare" ? "Prepare withdrawal" : "Withdraw approval"}));
  expect(await screen.findByRole("alert")).toHaveTextContent(action === "prepare" ? "Withdrawal preparation rejected" : "Withdrawal digest rejected");
  expect(screen.getByText("Published Python")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", {name: "Select SQL"})).toBeChecked();
  expect(screen.queryByText(/Withdrawal saved/)).not.toBeInTheDocument();
});

it.each(["prepare", "withdraw"] as const)("explicit withdrawal ignores late %s completion after a different review/run arrives", async action => {
  const review = action === "prepare" ? reconciliationFixture() : withdrawalFixture();
  let finishPrepare!: (response: SkillReview) => void;
  let finishApprove!: (response: IntegrationApprovalResponse) => void;
  if (action === "prepare") vi.mocked(prepareSkillWithdrawal).mockImplementationOnce(() => new Promise(resolve => {finishPrepare = resolve;}));
  else vi.mocked(approveSkillIntegration).mockImplementationOnce(() => new Promise(resolve => {finishApprove = resolve;}));
  const changed = vi.fn();
  const {rerender} = render(<IntegrationReview courseId={1} review={review} onReviewChange={changed}/>);
  await userEvent.setup().click(screen.getByRole("button", {name: action === "prepare" ? "Prepare withdrawal" : "Withdraw approval"}));
  const next = {...reconciliationFixture(), run_id: "run-2", candidate_revision: 2, selection_revision: 3, approved_references: []};
  rerender(<IntegrationReview courseId={1} review={next} onReviewChange={changed}/>);
  await act(async () => {
    if (action === "prepare") finishPrepare(withdrawalFixture());
    else finishApprove({review: {...review, integration_review: null, approved_references: []}, projection_status: "pending"});
  });
  expect(changed).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", {name: "Withdraw approval"})).not.toBeInTheDocument();
});
