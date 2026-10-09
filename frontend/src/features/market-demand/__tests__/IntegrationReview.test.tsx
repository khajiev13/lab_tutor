import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SkillReviewPanel } from "@/features/market-demand/components/SkillReviewPanel";
import { EvidenceLink } from "@/features/market-demand/components/SkillEvidencePanel";
import type { SkillReview } from "@/features/market-demand/types";
import { IntegrationReview } from "@/features/market-demand/components/IntegrationReview";
import { integrationFixture } from "@/features/market-demand/__tests__/review-fixtures";
vi.mock("@/features/market-demand/api",async()=>({...await vi.importActual("@/features/market-demand/api"),approveSkillIntegration:vi.fn()}));
import { approveSkillIntegration } from "@/features/market-demand/api";
beforeEach(()=>vi.resetAllMocks());

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
