import { useState } from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { SkillReviewPanel } from "@/features/market-demand/components/SkillReviewPanel";
import { integrationFixture, reviewFixture } from "@/features/market-demand/__tests__/review-fixtures";
import type { SkillReview, OnetEvidence, OnetMetric, OnetAssociation } from "@/features/market-demand/types";

vi.mock("@/features/market-demand/api", async () => ({...await vi.importActual("@/features/market-demand/api"),saveSkillReviewDraft:vi.fn(),confirmSkillReviewSelection:vi.fn(),continueWithAvailableEvidence:vi.fn(),fetchPostingEvidence:vi.fn(),approveSkillIntegration:vi.fn()}));
import { saveSkillReviewDraft, confirmSkillReviewSelection, fetchPostingEvidence, continueWithAvailableEvidence, approveSkillIntegration } from "@/features/market-demand/api";
beforeEach(() => vi.resetAllMocks());

it("selects hidden category members, preserves individual exclusions through filtering/sorting and reload", async () => {
  const review = reviewFixture();
  const onReviewChange = vi.fn();
  vi.mocked(saveSkillReviewDraft).mockImplementation(async (_, body) => ({...review,...body,selection_revision:3}));
  const {unmount} = render(<SkillReviewPanel courseId={1} review={review} onReviewChange={onReviewChange}/>);
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox",{name:"Filter skills"}),"Python");
  await user.click(screen.getByRole("checkbox",{name:/Select category Tools/}));
  expect(screen.getByText("3 selected · 1 needs supporting job posting")).toBeInTheDocument();
  await user.clear(screen.getByRole("textbox",{name:"Filter skills"}));
  await user.click(screen.getByRole("checkbox",{name:"Select SQL"}));
  expect(screen.getByRole("checkbox",{name:/Select category Tools/})).toHaveAttribute("aria-checked","mixed");
  await user.selectOptions(screen.getByRole("combobox",{name:"Sort skills"}),"name");
  await user.click(screen.getByRole("button",{name:"Save draft"}));
  await waitFor(() => expect(screen.getByText("Draft saved")).toBeInTheDocument());
  expect(saveSkillReviewDraft).toHaveBeenCalledWith(1,{run_id:"run-1",expected_candidate_revision:1,expected_selection_revision:2,selected_candidate_ids:["python","reference"],excluded_candidate_ids:["sql"]});
  unmount();
  render(<SkillReviewPanel courseId={1} review={onReviewChange.mock.calls[0][0]} onReviewChange={onReviewChange}/>);
  expect(screen.getByRole("checkbox",{name:"Select SQL"})).not.toBeChecked();
  expect(screen.getByRole("checkbox",{name:"Select Python"})).toBeChecked();
});

it("applies selected suggestions locally, protects excluded IDs and undoes the batch", async () => {
  const review = {...reviewFixture(),excluded_candidate_ids:["sql"],recommendations:[{id:"p",candidate_revision:1,base_selection_revision:2,changes:[{candidate_id:"python",action:"add" as const,reason:"Relevant"},{candidate_id:"sql",action:"add" as const,reason:"Relevant"}]}]};
  render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox",{name:"Apply suggestion for Python"}));
  await user.click(screen.getByRole("button",{name:"Apply selected suggestions"}));
  expect(screen.getByRole("checkbox",{name:"Select Python"})).toBeChecked();
  expect(screen.getByRole("checkbox",{name:"Select SQL"})).not.toBeChecked();
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button",{name:"Undo local change"}));
  expect(screen.getByRole("checkbox",{name:"Select Python"})).not.toBeChecked();
});

it.each(["Connection lost","Stale revision"])("retains unsaved choices on %s without success or publication", async message => {
  const review = reviewFixture();
  vi.mocked(saveSkillReviewDraft).mockRejectedValueOnce(new Error(message));
  render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox",{name:"Select Python"}));
  await user.click(screen.getByRole("button",{name:"Save draft"}));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("checkbox",{name:"Select Python"})).toBeChecked();
  expect(screen.queryByText("Draft saved")).not.toBeInTheDocument();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"Confirm selection for mapping"})).toBeDisabled();
});

it("shows reconciliation and keeps late/merged candidates unselected", () => {
  const review = {...reviewFixture(),selected_candidate_ids:["python"],excluded_candidate_ids:["sql"]};
  const {rerender} = render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  const merged = {...review,candidate_revision:2,candidates:[review.candidates[1],review.candidates[2],{...review.candidates[0],candidate_id:"merged",display_name:"Merged Python"}],selected_candidate_ids:[]};
  rerender(<SkillReviewPanel courseId={1} review={merged} onReviewChange={vi.fn()}/>);
  expect(screen.getByRole("alert")).toHaveTextContent(/removed or merged.*Python/i);
  expect(screen.getByRole("checkbox",{name:"Select Merged Python"})).not.toBeChecked();
  expect(screen.getByRole("checkbox",{name:"Select SQL"})).not.toBeChecked();
});

it("requires server acknowledgement for mapping and ignores a stale save response", async () => {
  const review = reviewFixture();
  let finish!: (review: SkillReview) => void;
  vi.mocked(saveSkillReviewDraft).mockImplementationOnce(() => new Promise(resolve => {finish=resolve;}));
  const changed = vi.fn();
  const {rerender} = render(<SkillReviewPanel courseId={1} review={review} onReviewChange={changed}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox",{name:"Select Python"}));
  await user.click(screen.getByRole("button",{name:"Save draft"}));
  expect(screen.queryByText("Draft saved")).not.toBeInTheDocument();
  rerender(<SkillReviewPanel courseId={1} review={{...review,selection_revision:4,selected_candidate_ids:["sql"]}} onReviewChange={changed}/>);
  await act(async () => finish({...review,selection_revision:3,selected_candidate_ids:["python"]}));
  expect(changed).not.toHaveBeenCalled();
  expect(screen.queryByText("Draft saved")).not.toBeInTheDocument();
});

it("confirms the saved snapshot using revisions, independently of unrated skills", async () => {
  const review = {...reviewFixture(),selected_candidate_ids:["python"]};
  vi.mocked(confirmSkillReviewSelection).mockResolvedValue(review);
  render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  await userEvent.setup().click(screen.getByRole("button",{name:"Confirm selection for mapping"}));
  expect(await screen.findByText("Selection confirmed for mapping")).toBeInTheDocument();
  expect(confirmSkillReviewSelection).toHaveBeenCalledWith(1,{run_id:"run-1",expected_candidate_revision:1,expected_selection_revision:2});
});

it("renders full evidence as safe text/JSON with genuine posting links", async () => {
  vi.mocked(fetchPostingEvidence).mockResolvedValue({snapshot_id:"snapshot-1",provider:"headhunter",native_id:"123",original_url:"https://hh.uz/vacancy/123",title:"Developer",company:"Acme",description_text:"Use Python",original_description:"<script>alert('x')</script>",raw_payload:{description:"<img src=x onerror=alert(1)>"},retrieved_at:"2026-10-09",status:"active",purged_at:null});
  const {container} = render(<SkillReviewPanel courseId={1} review={reviewFixture()} onReviewChange={vi.fn()}/>);
  const user = userEvent.setup();
  const pythonEvidence = screen.getByText("Evidence for Python").closest("details")!;
  await user.click(within(pythonEvidence).getByText("Evidence for Python"));
  expect(within(pythonEvidence).getByRole("link",{name:"Original job posting"})).toHaveAttribute("href","https://hh.uz/vacancy/123");
  await user.click(screen.getByRole("button",{name:"Load full posting evidence"}));
  expect(await screen.findByText("<script>alert('x')</script>")).toBeInTheDocument();
  expect(container.querySelector("script,img")).toBeNull();
  expect(screen.getByText(/"description": "<img/)).toBeInTheDocument();
});

it("separates occupation-specific equivalent ratings from broader context and unavailable scores", async () => {
  const review = reviewFixture();
  const metric: OnetMetric = {scale_id:"IM",value:4,minimum:1,maximum:5,status:"reported",date:null,quality:{}};
  const evidence: OnetEvidence = {id:"onet-1",release:"31.0",soc_code:"15-2051.00",occupation_title:"Data Scientists",family:"transferable",element_id:"x",label:"Programming",definition:"Write programs",workplace_example:null,ratings:{IM:metric},flags:{},source_url:"https://www.onetonline.org/link/summary/15-2051.00",attribution:"O*NET"};
  review.candidates[0].onet_associations = [{evidence,relation:"broader",mapping_method:"agent",rationale:"General descriptor"},{evidence:{...evidence,id:"onet-2",soc_code:"15-1252.00",occupation_title:"Software Developers",ratings:{IM:{...metric,value:3},LV:{...metric,scale_id:"LV",value:5,status:"suppressed"}}},relation:"equivalent",mapping_method:"review",rationale:"Exact match"}];
  render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  expect(screen.getByText(/Data Scientists.*broader context/)).toBeInTheDocument();
  expect(screen.getByText(/Software Developers.*equivalent/)).toBeInTheDocument();
  expect(screen.getByText(/LV: unavailable \(suppressed\)/)).toBeInTheDocument();
  expect(screen.getByRole("option",{name:"O*NET importance"})).toBeDisabled();
  await userEvent.setup().selectOptions(screen.getByRole("combobox",{name:"Active occupation"}),"15-1252.00");
  expect(screen.getByRole("option",{name:"O*NET importance"})).not.toBeDisabled();
});

it("orders actual skill rows by the selected occupation and excludes broader, suppressed and unavailable ratings", async () => {
  const review = reviewFixture();
  const association = (id: string, soc: string, value: number | null, status: OnetMetric["status"], relation: OnetAssociation["relation"]): OnetAssociation => ({
    evidence: {
      id, release: "31.0", soc_code: soc,
      occupation_title: soc === "15-2051.00" ? "Data Scientists" : "Software Developers",
      family: "transferable", element_id: id, label: "Programming", definition: "Write programs",
      workplace_example: null,
      ratings: {IM: {scale_id: "IM", value, minimum: 1, maximum: 5, status, date: null, quality: {}}},
      flags: {}, source_url: `https://www.onetonline.org/link/summary/${soc}`, attribution: "O*NET",
    },
    relation, mapping_method: "review", rationale: "Reviewed descriptor relationship",
  });
  const template = {...review.candidates[0], evidence_references: []};
  review.candidates = [
    {...template, candidate_id: "alpha", display_name: "Alpha", onet_associations: [association("alpha-science", "15-2051.00", 5, "reported", "broader"), association("alpha-software", "15-1252.00", 1, "reported", "equivalent")]},
    {...template, candidate_id: "bravo", display_name: "Bravo", onet_associations: [association("bravo-science", "15-2051.00", 2, "reported", "equivalent"), association("bravo-software", "15-1252.00", 4, "reported", "equivalent")]},
    {...template, candidate_id: "charlie", display_name: "Charlie", onet_associations: [association("charlie-science", "15-2051.00", 4, "reported", "equivalent"), association("charlie-software", "15-1252.00", 2, "reported", "equivalent")]},
    {...template, candidate_id: "delta", display_name: "Delta", onet_associations: [association("delta-science", "15-2051.00", 5, "suppressed", "equivalent"), association("delta-software", "15-1252.00", 5, "suppressed", "equivalent")]},
    {...template, candidate_id: "echo", display_name: "Echo", onet_associations: [association("echo-science", "15-2051.00", null, "missing", "equivalent"), association("echo-software", "15-1252.00", null, "reported", "equivalent")]},
  ];
  render(<SkillReviewPanel courseId={1} review={review} onReviewChange={vi.fn()}/>);
  const user = userEvent.setup();
  await user.selectOptions(screen.getByRole("combobox", {name: "Active occupation"}), "15-2051.00");
  await user.selectOptions(screen.getByRole("combobox", {name: "Sort skills"}), "importance");
  expect(screen.getAllByRole("checkbox", {name: /^Select (Alpha|Bravo|Charlie|Delta|Echo)$/}).map(element => element.getAttribute("aria-label"))).toEqual([
    "Select Charlie", "Select Bravo", "Select Alpha", "Select Delta", "Select Echo",
  ]);
  await user.selectOptions(screen.getByRole("combobox", {name: "Active occupation"}), "15-1252.00");
  expect(screen.getAllByRole("checkbox", {name: /^Select (Alpha|Bravo|Charlie|Delta|Echo)$/}).map(element => element.getAttribute("aria-label"))).toEqual([
    "Select Bravo", "Select Charlie", "Select Alpha", "Select Delta", "Select Echo",
  ]);
});

function continuationFixture(): SkillReview {
  const review = integrationFixture();
  return {
    ...review,
    selected_candidate_ids: ["reference"],
    source_outcomes: {headhunter: {status: "partial", received_count: 5, usable_count: 4, warnings: ["One posting unavailable"]}},
    extraction_coverage: {status: "partial", selected_postings: 5, assessed_postings: 4, failed_postings: 1, total_chunks: 5, assessed_chunks: 4, warnings: ["One posting unassessed"], acknowledged: false},
    integration_review: {
      ...review.integration_review!,
      items: [{...review.integration_review!.items[0], candidate_id: "reference", target: {identity: "reference-target", label: "Reference target", source: "market", origin: "onet"}, qualifying_posting_links: [], evidence_snapshot_ids: []}],
      omissions: ["One posting unavailable"], omissions_acknowledged: false,
    },
  };
}

function acknowledgedContinuation(review: SkillReview): SkillReview {
  return {...review, extraction_coverage: {...review.extraction_coverage, acknowledged: true}, integration_review: {...review.integration_review!, omissions_acknowledged: true}};
}

function ReviewParent({initialReview}: {initialReview: SkillReview}) {
  const [review, setReview] = useState(initialReview);
  return <SkillReviewPanel courseId={1} review={review} onReviewChange={setReview}/>;
}

it("keeps mapping blocked until delayed continuation acknowledgement and keeps unsupported publication blocked afterward", async () => {
  const review = continuationFixture();
  let finish!: (response: SkillReview) => void;
  vi.mocked(continueWithAvailableEvidence).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  render(<ReviewParent initialReview={review}/>);
  const user = userEvent.setup();
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeDisabled();
  await user.click(screen.getByRole("button", {name: "Continue with available evidence"}));
  expect(continueWithAvailableEvidence).toHaveBeenCalledWith(1, {run_id: "run-1", expected_candidate_revision: 1, expected_selection_revision: 2});
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  await act(async () => {finish(acknowledgedContinuation(review));});
  expect(await screen.findByRole("status")).toHaveTextContent("Evidence omissions acknowledged; supporting postings are still required");
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeEnabled();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.getByRole("checkbox", {name: "Select Reference skill"})).toBeChecked();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
});

it("retains partial-evidence gates and prior publication when continuation fails", async () => {
  vi.mocked(continueWithAvailableEvidence).mockRejectedValueOnce(new Error("Acknowledgement unavailable"));
  render(<ReviewParent initialReview={continuationFixture()}/>);
  await userEvent.setup().click(screen.getByRole("button", {name: "Continue with available evidence"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Acknowledgement unavailable");
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  expect(screen.getByRole("button", {name: "Continue with available evidence"})).toBeEnabled();
  expect(screen.getByRole("checkbox", {name: "Select Reference skill"})).toBeChecked();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
});

it("allows mapping after successful continuation without publishing an O*NET-only candidate", async () => {
  const review = continuationFixture();
  vi.mocked(continueWithAvailableEvidence).mockResolvedValueOnce(acknowledgedContinuation(review));
  render(<ReviewParent initialReview={review}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "Continue with available evidence"}));
  expect(await screen.findByRole("status")).toHaveTextContent("Evidence omissions acknowledged; supporting postings are still required");
  expect(screen.getByRole("button", {name: "Confirm selection for mapping"})).toBeEnabled();
  expect(screen.getByRole("button", {name: "Approve integration"})).toBeDisabled();
  await user.click(screen.getByRole("button", {name: "Approve integration"}));
  expect(approveSkillIntegration).not.toHaveBeenCalled();
  expect(screen.getByText("Published Python")).toBeInTheDocument();
});
