import {useEffect, useEffectEvent} from "react";
import {render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, expect, it, vi} from "vitest";
import {WorkspaceOverview} from "@/features/market-demand/components/WorkspaceOverview";
import WorkspaceCompare from "@/features/market-demand/components/WorkspaceCompare";
import {WorkspaceDataTable} from "@/features/market-demand/components/WorkspaceDataTable";
import {SkillEvidencePanel} from "@/features/market-demand/components/SkillEvidencePanel";
import {useSkillReviewController} from "@/features/market-demand/hooks/useSkillReviewController";
import {buildWorkspaceData} from "@/features/market-demand/workspace-data";
import {reviewFixture, workspaceCandidateId, workspaceEvidenceFixture, workspaceOtherSoc, workspaceReviewFixture, workspaceSoc, workspaceViewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import type {SkillReview, WorkspaceQuestion, WorkspaceViewState} from "@/features/market-demand/types";

// ECharts is an external renderer; real browser lifecycle evidence is Task 12.
vi.mock("@/features/market-demand/components/EvidenceChart", () => ({EvidenceChart: ({label, option, onFocus}: {label: string; option: {series: {data: {focus: unknown}[]}[]}; onFocus: (focus: unknown) => void}) =>
  <div role="img" aria-label={label}><output data-testid="chart-options">{JSON.stringify(option)}</output>{option.series[0].data.map((item, i) => <button key={i} onClick={() => onFocus(item.focus)}>Plot {i + 1}</button>)}</div>}));
vi.mock("@/features/market-demand/api", async () => ({...await vi.importActual("@/features/market-demand/api"), saveSkillReviewDraft: vi.fn(), streamMarketDemandChat: vi.fn(), fetchPostingEvidence: vi.fn()}));
import {saveSkillReviewDraft, streamMarketDemandChat, fetchPostingEvidence} from "@/features/market-demand/api";
beforeEach(() => vi.clearAllMocks());

const defaultReview = workspaceReviewFixture();
const defaultView = workspaceViewFixture();

function Harness({review = defaultReview, view = defaultView, kind = "overview", onAsk = vi.fn()}: {review?: SkillReview; view?: WorkspaceViewState; kind?: "overview" | "compare" | "data"; onAsk?: (request: WorkspaceQuestion) => void}) {
  const controller = useSkillReviewController({courseId: 1, review, onReviewChange: vi.fn()});
  const initializeView = useEffectEvent((next: WorkspaceViewState) => controller.updateView(next));
  useEffect(() => initializeView(view), [view]);
  const data = buildWorkspaceData(review, controller.draft, controller.view);
  const props = {data, controller, onAsk};
  return <><output data-testid="state">{JSON.stringify({view: controller.view, draft: controller.draft})}</output>{kind === "overview" ? <WorkspaceOverview {...props}/> : kind === "compare" ? <WorkspaceCompare {...props}/> : <WorkspaceDataTable {...props}/>}</>;
}
function state() {return JSON.parse(screen.getByTestId("state").textContent!);}

it("bar and pattern inspection focus, Ask stages an editable question, and View all preserves filters", async () => {
  const review = workspaceReviewFixture();
  review.candidates[0].job_metrics = {supporting_posting_count: 6, assessed_posting_count: 10, percentage: 60, coverage_status: "partial"};
  const onAsk = vi.fn();
  const view = {...workspaceViewFixture(), filters: {category_ids: ["tools"], search: "Python", scope: "all" as const}};
  render(<Harness review={review} view={view} onAsk={onAsk}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "Plot 1"}));
  expect(state().view.focusedCandidateId).toBe(workspaceCandidateId);
  expect(state().draft.selected_candidate_ids).toEqual([]);
  await user.click(screen.getByRole("button", {name: "Inspect evidence"}));
  await user.click(screen.getByRole("button", {name: "Ask agent"}));
  expect(onAsk).toHaveBeenCalledWith({text: expect.any(String), candidateIds: [workspaceCandidateId], occupationCodes: [], insightKind: "common_sample"});
  expect(onAsk.mock.calls[0][0]).not.toHaveProperty("values");
  expect(screen.getAllByText(/6 \/ 10/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Partial collected sample/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "View all"}));
  expect(state().view).toMatchObject({view: "data", page: 1, filters: view.filters});
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("renders top 12 with full filtered count and fixed demand axis", () => {
  const review = workspaceReviewFixture();
  review.candidates = Array.from({length: 30}, (_, i) => ({...review.candidates[0], candidate_id: String(i), display_name: `Skill ${i}`}));
  render(<Harness review={review}/>);
  expect(screen.getByText(/Showing 12 of 30 matching skills/)).toBeInTheDocument();
  const option = JSON.parse(screen.getByTestId("chart-options").textContent!);
  expect(option.xAxis).toMatchObject({min: 0, max: 100});
  expect(option.series[0].data).toHaveLength(12);
});

it("shows unavailable sample values rather than plotting zeros and handles no matching candidates", () => {
  const review = workspaceReviewFixture();
  review.candidates[0].job_metrics = {assessed_posting_count: 0, percentage: null};
  const {rerender} = render(<Harness review={review}/>);
  expect(screen.getByText("Unavailable: No assessed postings")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  rerender(<Harness review={review} view={{...workspaceViewFixture(), filters: {category_ids: [], search: "missing", scope: "all"}}}/>);
  expect(screen.getByText(/No matching skills/)).toBeInTheDocument();
});

it("scatter focus carries role/evidence; controls only change occupational view state", async () => {
  const review = workspaceReviewFixture();
  review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: "tester-evidence", soc_code: workspaceOtherSoc})];
  render(<Harness review={review} kind="compare" view={{...workspaceViewFixture(), view: "demand_importance"}}/>);
  const user = userEvent.setup();
  const option = JSON.parse(screen.getByTestId("chart-options").textContent!);
  expect(option.xAxis).toMatchObject({min: 0, max: 100});
  expect(option.yAxis).toMatchObject({min: 1, max: 5});
  await user.click(screen.getByRole("button", {name: "Plot 1"}));
  expect(state().view).toMatchObject({focusedCandidateId: workspaceCandidateId, activeOccupationCode: workspaceSoc});
  await user.selectOptions(screen.getByRole("combobox", {name: "Compare occupation"}), workspaceOtherSoc);
  expect(state().view.activeOccupationCode).toBe(workspaceOtherSoc);
  expect(state().draft.selected_candidate_ids).toEqual([]);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("heatmap supports zero/one role, hides and re-enables confirmed roles, switches fixed scales and pages 12 rows", async () => {
  const review = workspaceReviewFixture();
  review.candidates = Array.from({length: 13}, (_, i) => ({...review.candidates[0], candidate_id: String(i), display_name: `Skill ${i}`, onet_associations: [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: "tester", soc_code: workspaceOtherSoc})]}));
  render(<Harness review={review} kind="compare" view={{...workspaceViewFixture(), view: "occupations"}}/>);
  const user = userEvent.setup();
  expect(screen.getByText("Rows 1–12 of 13")).toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Next rows"}));
  expect(screen.getByText("Rows 13–13 of 13")).toBeInTheDocument();
  await user.selectOptions(screen.getByRole("combobox", {name: "Compare metric"}), "LV");
  expect(JSON.parse(screen.getByTestId("chart-options").textContent!).visualMap).toMatchObject({min: 0, max: 7});
  await user.click(screen.getByRole("checkbox", {name: "Display Tester"}));
  expect(screen.getByText(/Single-role reference view/)).toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", {name: "Display Developer"}));
  expect(screen.getByText(/No occupations displayed/)).toBeInTheDocument();
  await user.click(screen.getByRole("checkbox", {name: "Display Tester"}));
  expect(screen.getByText(/Single-role reference view/)).toBeInTheDocument();
  expect(state().view.occupationCodes).toEqual([workspaceOtherSoc]);
  expect(state().draft.selected_candidate_ids).toEqual([]);
});

it("unconfirmed occupation comparison stays empty", () => {
  render(<Harness review={{...workspaceReviewFixture(), analysis_metadata: null}} kind="compare"/>);
  expect(screen.getByText(/No confirmed occupations/)).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("requires explicit ambiguous descriptor choice and retains suppressed/unmatched cells as inspectable reasons", async () => {
  const review = workspaceReviewFixture();
  const first = workspaceEvidenceFixture();
  const second = workspaceEvidenceFixture({id: "second", element_id: "other", label: "Other descriptor"});
  const suppressed = workspaceEvidenceFixture({id: "suppressed", soc_code: workspaceOtherSoc});
  suppressed.evidence.ratings.IM!.status = "suppressed";
  review.candidates[0].onet_associations = [first, second, suppressed];
  render(<Harness review={review} kind="compare" view={{...workspaceViewFixture(), view: "occupations"}}/>);
  expect(screen.getByText(/Multiple matched descriptors/)).toBeInTheDocument();
  expect(screen.getByText(/Unavailable: suppressed/)).toBeInTheDocument();
  const user = userEvent.setup();
  await user.selectOptions(screen.getByRole("combobox", {name: "Descriptor for Python · Developer"}), first.evidence.id);
  expect(state().view.descriptorChoices).toEqual([{candidate_id: workspaceCandidateId, evidence_id: first.evidence.id}]);
  expect(state().draft.selected_candidate_ids).toEqual([]);
});

it("Data pages 25 rows, supports keyboard inspect and explicit local selection, missing values remain last on sort", async () => {
  const review = workspaceReviewFixture();
  review.candidates = Array.from({length: 26}, (_, i) => ({...review.candidates[0], candidate_id: String(i), display_name: `Skill ${String(i).padStart(2, "0")}`, job_metrics: i === 0 ? {} : {assessed_posting_count: 10, supporting_posting_count: i % 10, percentage: i % 10 * 10}}));
  render(<Harness review={review} kind="data"/>);
  expect(screen.getByText("Rows 1–25 of 26")).toBeInTheDocument();
  const user = userEvent.setup();
  screen.getByRole("button", {name: "Inspect Skill 00"}).focus();
  await user.keyboard("{Enter}");
  expect(state().view.focusedCandidateId).toBe("0");
  expect(state().draft.selected_candidate_ids).toEqual([]);
  await user.click(screen.getByRole("checkbox", {name: "Select Skill 00"}));
  expect(state().draft.selected_candidate_ids).toEqual(["0"]);
  await user.click(screen.getByRole("button", {name: "Sort by frequency"}));
  expect(screen.queryByRole("checkbox", {name: "Select Skill 00"})).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Next rows"}));
  expect(screen.getByText("Rows 26–26 of 26")).toBeInTheDocument();
  expect(screen.getByRole("checkbox", {name: "Select Skill 00"})).toBeChecked();
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
});

it("inspector exposes source/mapping/rating provenance and unavailable statuses without suppressed numbers", async () => {
  const candidate = reviewFixture().candidates[0];
  const evidence = workspaceEvidenceFixture();
  evidence.evidence.ratings.IM!.status = "suppressed";
  evidence.evidence.ratings.IM!.date = "2025-01";
  evidence.evidence.ratings.IM!.quality = {suppressed: true};
  candidate.onet_associations = [evidence];
  render(<SkillEvidencePanel courseId={1} candidate={candidate}/>);
  await userEvent.setup().click(screen.getByText("Evidence for Python"));
  expect(screen.getByText(/30.0.*essential.*2.B.3.m/)).toBeInTheDocument();
  expect(screen.getByText(/reviewed.*Equivalent/)).toBeInTheDocument();
  expect(screen.getByText(/IM: unavailable \(suppressed\)/)).toBeInTheDocument();
  expect(screen.queryByText(/IM: 4/)).not.toBeInTheDocument();
  expect(screen.getByText(/2025-01/)).toBeInTheDocument();
  expect(screen.getByText(/"suppressed": true/)).toBeInTheDocument();
  expect(within(screen.getByText("Evidence for Python").closest("details")!).getByRole("link", {name: /O\*NET reference/})).toHaveAttribute("href", "https://onetonline.org");
  expect(fetchPostingEvidence).not.toHaveBeenCalled();
});

it("Data retains missing/suppressed/not relevant/no association/ambiguity reasons and no unavailable numbers", async () => {
  const review = workspaceReviewFixture();
  const template = review.candidates[0];
  review.candidates = ["missing", "suppressed", "not_relevant", "no_association", "ambiguous"].map((status, index) => {
    const association = workspaceEvidenceFixture({id: `rating-${index}`});
    if (status === "missing" || status === "suppressed" || status === "not_relevant") association.evidence.ratings.IM!.status = status;
    return {...template, candidate_id: status, display_name: status, posting_support: "missing" as const, job_metrics: {},
      onet_associations: status === "no_association" ? [] : status === "ambiguous" ? [association, workspaceEvidenceFixture({id: "different", element_id: "different"})] : [association]};
  });
  render(<Harness review={review} kind="data"/>);
  for (const reason of ["Unavailable: missing", "Unavailable: suppressed", "Unavailable: not relevant", "Unavailable: no equivalent association in this release"])
    expect(screen.getByText(reason)).toBeInTheDocument();
  expect(screen.getByText(/Multiple matched descriptors/)).toBeInTheDocument();
  expect(screen.queryByText("4 / 5")).not.toBeInTheDocument();
  expect(screen.getAllByText("Needs job evidence")).toHaveLength(5);
  await userEvent.setup().click(screen.getByRole("button", {name: "Inspect suppressed"}));
  expect(state().view.focusedCandidateId).toBe("suppressed");
  expect(state().draft.selected_candidate_ids).toEqual([]);
});

it("keeps the comparison pinned to confirmed roles and allows at most five displayed", async () => {
  const review = workspaceReviewFixture();
  review.analysis_metadata!.occupations = Array.from({length: 6}, (_, i) => ({soc_code: `role-${i}`, title: `Role ${i}`}));
  const view = {...workspaceViewFixture(), view: "occupations" as const, occupationCodes: ["role-0", "role-1", "role-2", "role-3", "role-4"], activeOccupationCode: "role-0"};
  render(<Harness review={review} kind="compare" view={view}/>);
  expect(screen.getByRole("checkbox", {name: "Display Role 5"})).toBeDisabled();
  const user = userEvent.setup();
  await user.click(screen.getByRole("checkbox", {name: "Display Role 0"}));
  expect(screen.getByRole("checkbox", {name: "Display Role 5"})).toBeEnabled();
  await user.click(screen.getByRole("checkbox", {name: "Display Role 5"}));
  expect(state().view.occupationCodes).toEqual(["role-1", "role-2", "role-3", "role-4", "role-5"]);
  expect(state().view.activeOccupationCode).toBeNull();
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("cell inspection stages the exact evidence without selection, and scatter keeps IM when preceded by LV", async () => {
  const review = workspaceReviewFixture();
  review.candidates[0].onet_associations = [workspaceEvidenceFixture(), workspaceEvidenceFixture({id: "tester-evidence", soc_code: workspaceOtherSoc})];
  const {rerender} = render(<Harness review={review} kind="compare" view={{...workspaceViewFixture(), view: "occupations"}}/>);
  await userEvent.setup().click(screen.getByRole("button", {name: "Inspect Python · Tester"}));
  expect(state().view).toMatchObject({focusedCandidateId: workspaceCandidateId, activeOccupationCode: workspaceOtherSoc, descriptorChoices: [{candidate_id: workspaceCandidateId, evidence_id: "tester-evidence"}]});
  expect(state().draft.selected_candidate_ids).toEqual([]);
  rerender(<Harness review={review} kind="compare" view={{...workspaceViewFixture(), view: "demand_importance", metric: "LV"}}/>);
  expect(screen.getByText("4 / 5")).toBeInTheDocument();
  expect(screen.queryByText("0 / 7")).not.toBeInTheDocument();
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it("purged posting retrieval retains provenance and resets content when the owning course changes", async () => {
  const posting = {snapshot_id: "snapshot-1", provider: "headhunter" as const, native_id: "123", original_url: "https://hh.uz/vacancy/123", title: "Developer", company: "Acme", description_text: "Private course 1 posting", original_description: "text", raw_payload: {}, retrieved_at: "2026-10-09", status: "active", purged_at: null};
  vi.mocked(fetchPostingEvidence).mockResolvedValueOnce(posting).mockResolvedValueOnce({...posting, purged_at: "2026-10-12"});
  const candidate = reviewFixture().candidates[0];
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={candidate}/>);
  const user = userEvent.setup();
  await user.click(screen.getByText("Evidence for Python"));
  await user.click(screen.getByRole("button", {name: "Load full posting evidence"}));
  expect(await screen.findByText("Private course 1 posting")).toBeInTheDocument();
  rerender(<SkillEvidencePanel courseId={2} candidate={candidate}/>);
  expect(screen.queryByText("Private course 1 posting")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", {name: "Load full posting evidence"}));
  expect(await screen.findByText(/Posting content unavailable: purged 2026-10-12/)).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Original job posting"})).toHaveAttribute("href", "https://hh.uz/vacancy/123");
  expect(fetchPostingEvidence).toHaveBeenLastCalledWith(2, "snapshot-1", expect.any(AbortSignal));
});

it("Overview retains failed/partial collection reasons without inventing replacement data", () => {
  const review = workspaceReviewFixture();
  review.candidates = [];
  review.source_outcomes = {headhunter: {status: "error", received_count: 0, usable_count: 0, warnings: ["Provider timed out <img src=x>"]}};
  review.extraction_coverage = {status: "failed", assessed_postings: 0, warnings: ["No postings assessed"]};
  const {container} = render(<Harness review={review}/>);
  expect(screen.getByText(/Provider timed out <img src=x>/)).toBeInTheDocument();
  expect(screen.getByText("No postings assessed")).toBeInTheDocument();
  expect(screen.getByText(/No matching skills/)).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
});

it("software evidence stays categorical even if a payload includes a numeric metric", async () => {
  const candidate = workspaceReviewFixture().candidates[0];
  candidate.onet_associations = [workspaceEvidenceFixture({family: "software", flags: {hot_technology: true}})];
  render(<SkillEvidencePanel courseId={1} candidate={candidate}/>);
  await userEvent.setup().click(screen.getByText("Evidence for Python"));
  expect(screen.getByText(/Software-reference flags are categorical/)).toBeInTheDocument();
  expect(screen.queryByText(/IM: 4/)).not.toBeInTheDocument();
  expect(screen.getByText(/"hot_technology": true/)).toBeInTheDocument();
});

it("inspector keeps nonqualifying posting provenance while marking missing job evidence and stages descriptor choice", async () => {
  const candidate = workspaceReviewFixture().candidates[0];
  candidate.posting_support = "missing";
  candidate.qualifying_posting_links = [];
  const first = workspaceEvidenceFixture();
  const other = workspaceEvidenceFixture({id: "other", element_id: "other", label: "Other descriptor"});
  candidate.onet_associations = [first, other];
  const choose = vi.fn();
  render(<SkillEvidencePanel courseId={1} candidate={candidate} focusedEvidenceId={first.evidence.id} ratings={{[workspaceSoc]: {status: "ambiguous", evidence: [first.evidence, other.evidence]}}} onChooseDescriptor={choose}/>);
  const user = userEvent.setup();
  await user.click(screen.getByText("Evidence for Python"));
  expect(screen.getByText(/Needs job evidence/)).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Original job posting"})).toBeInTheDocument();
  expect(screen.getByText("Focused chart evidence")).toBeInTheDocument();
  await user.selectOptions(screen.getByRole("combobox", {name: `Inspector descriptor for Python · ${workspaceSoc}`}), "other");
  expect(choose).toHaveBeenCalledWith("other", workspaceSoc);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  expect(fetchPostingEvidence).not.toHaveBeenCalled();
});

it.each(["data", "compare"] as const)("%s distinguishes unchosen occupation from genuine missing association", async kind => {
  const review = workspaceReviewFixture();
  review.candidates[0].onet_associations = [workspaceEvidenceFixture()];
  render(<Harness review={review} kind={kind} view={{...workspaceViewFixture(), view: "demand_importance", activeOccupationCode: null}}/>);
  expect(screen.getByText("Choose an occupation to see its reported rating")).toBeInTheDocument();
  expect(screen.queryByText("Unavailable: no equivalent association in this release")).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.selectOptions(screen.getByRole("combobox", {name: "Compare occupation"}), workspaceSoc);
  expect(screen.getByText("4 / 5")).toBeInTheDocument();
  expect(screen.queryByText("Choose an occupation to see its reported rating")).not.toBeInTheDocument();
  await user.selectOptions(screen.getByRole("combobox", {name: "Compare occupation"}), workspaceOtherSoc);
  expect(screen.getByText("Unavailable: no equivalent association in this release")).toBeInTheDocument();
  expect(state().draft.selected_candidate_ids).toEqual([]);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

it.each(["data", "compare"] as const)("%s retains eligible descriptor chooser after reported/missing/suppressed choices and supports clearing", async kind => {
  const review = workspaceReviewFixture();
  const reported = workspaceEvidenceFixture();
  const missing = workspaceEvidenceFixture({id: "missing-descriptor", element_id: "missing-element", label: "Missing descriptor"});
  missing.evidence.ratings.IM!.status = "missing";
  const suppressed = workspaceEvidenceFixture({id: "suppressed-descriptor", element_id: "suppressed-element", label: "Suppressed descriptor"});
  suppressed.evidence.ratings.IM!.status = "suppressed";
  review.candidates[0].onet_associations = [reported, missing, suppressed, workspaceEvidenceFixture({id: "wrong-release", release: "29.0", element_id: "wrong", label: "Wrong release"}), {...workspaceEvidenceFixture({id: "related", element_id: "related", label: "Related descriptor"}), relation: "related"}, workspaceEvidenceFixture({id: "software", family: "software", element_id: "software", label: "Software descriptor"})];
  const view = {...workspaceViewFixture(), view: "occupations" as const, occupationCodes: [workspaceSoc]};
  render(<Harness review={review} kind={kind} view={view}/>);
  const chooser = () => screen.getByRole("combobox", {name: "Descriptor for Python · Developer"});
  expect(within(chooser()).getAllByRole("option")).toHaveLength(4);
  expect(within(chooser()).queryByRole("option", {name: /Wrong release|Related descriptor|Software descriptor/})).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.selectOptions(chooser(), reported.evidence.id);
  expect(screen.getByText("4 / 5")).toBeInTheDocument();
  expect(chooser()).toHaveValue(reported.evidence.id);
  await user.selectOptions(chooser(), "missing-descriptor");
  expect(screen.getByText("Unavailable: missing")).toBeInTheDocument();
  expect(chooser()).toHaveValue("missing-descriptor");
  await user.selectOptions(chooser(), "suppressed-descriptor");
  expect(screen.getByText("Unavailable: suppressed")).toBeInTheDocument();
  expect(chooser()).toHaveValue("suppressed-descriptor");
  expect(screen.queryByText("4 / 5")).not.toBeInTheDocument();
  await user.selectOptions(chooser(), "");
  expect(screen.getByText(/Multiple matched descriptors/)).toBeInTheDocument();
  expect(chooser()).toHaveValue("");
  expect(state().view.descriptorChoices).toEqual([]);
  expect(state().draft.selected_candidate_ids).toEqual([]);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});

function InspectorHarness({review}: {review: SkillReview}) {
  const controller = useSkillReviewController({courseId: 1, review, onReviewChange: vi.fn()});
  const initializeView = useEffectEvent(() => controller.updateView({...workspaceViewFixture(), occupationCodes: [workspaceSoc]}));
  useEffect(() => initializeView(), []);
  const data = buildWorkspaceData(review, controller.draft, controller.view);
  const row = data.rows[0];
  return <><output data-testid="state">{JSON.stringify({view: controller.view, draft: controller.draft})}</output>
    <SkillEvidencePanel courseId={1} candidate={row.candidate} ratings={row.ratings} onChooseDescriptor={(id, code) => controller.updateView({descriptorChoices: [
      ...controller.view.descriptorChoices.filter(choice => choice.candidate_id !== row.candidateId || !row.candidate.onet_associations.some(item => item.evidence.id === choice.evidence_id && item.evidence.soc_code === code)),
      ...(id ? [{candidate_id: row.candidateId, evidence_id: id}] : []),
    ]})}/></>;
}

it("inspector retains descriptor identity and lets shared view state change or clear resolved choices", async () => {
  const review = workspaceReviewFixture();
  const first = workspaceEvidenceFixture();
  const suppressed = workspaceEvidenceFixture({id: "suppressed-descriptor", element_id: "suppressed", label: "Suppressed descriptor"});
  suppressed.evidence.ratings.IM!.status = "suppressed";
  review.candidates[0].onet_associations = [first, suppressed];
  render(<InspectorHarness review={review}/>);
  const user = userEvent.setup();
  await user.click(screen.getByText("Evidence for Python"));
  const chooser = () => screen.getByRole("combobox", {name: `Inspector descriptor for Python · ${workspaceSoc}`});
  await user.selectOptions(chooser(), first.evidence.id);
  expect(screen.getByText(`${workspaceSoc}: 4 / 5`)).toBeInTheDocument();
  expect(chooser()).toHaveValue(first.evidence.id);
  await user.selectOptions(chooser(), "suppressed-descriptor");
  expect(screen.getByText(`${workspaceSoc}: Unavailable: suppressed`)).toBeInTheDocument();
  expect(chooser()).toHaveValue("suppressed-descriptor");
  await user.selectOptions(chooser(), "");
  expect(screen.getByText(`${workspaceSoc}: Multiple matched descriptors`)).toBeInTheDocument();
  expect(state().view.descriptorChoices).toEqual([]);
  expect(state().draft.selected_candidate_ids).toEqual([]);
  expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
  expect(fetchPostingEvidence).not.toHaveBeenCalled();
});
