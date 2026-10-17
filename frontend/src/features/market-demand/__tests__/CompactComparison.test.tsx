import {act, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axios from "axios";
import {beforeEach, expect, it, vi} from "vitest";
import {CompactComparison} from "@/features/market-demand/components/CompactComparison";
import {workspaceEvidenceFixture, workspaceReviewFixture, workspaceSoc} from "@/features/market-demand/__tests__/review-fixtures";

const runtime = vi.hoisted(() => ({init: vi.fn(), use: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), on: vi.fn(), off: vi.fn()}));
vi.mock("echarts/core", async importOriginal => {
  const original = await importOriginal<typeof import("echarts/core")>();
  return {...original, init: runtime.init, use: runtime.use};
});
vi.mock("echarts/charts", () => ({BarChart: {}, ScatterChart: {}, HeatmapChart: {}}));
vi.mock("echarts/components", () => ({GridComponent: {}, DatasetComponent: {}, TooltipComponent: {}, VisualMapComponent: {}, AriaComponent: {}}));
vi.mock("echarts/renderers", () => ({SVGRenderer: {}}));
beforeEach(() => {
  vi.clearAllMocks();
  runtime.init.mockReset().mockReturnValue(runtime);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(600);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(300);
  vi.stubGlobal("ResizeObserver", class {observe() {} disconnect() {}});
});
function fixture() {
  const review = workspaceReviewFixture();
  review.candidates = Array.from({length: 7}, (_, index) => ({...review.candidates[0], candidate_id: `skill-${index}`, display_name: `Skill ${index}`,
    job_metrics: {supporting_posting_count: 4, assessed_posting_count: 7, selected_posting_count: 8, percentage: 57.14, coverage_status: "partial" as const}}));
  return review;
}
it("creates no chart before opening and paginates five labelled entries without losing choices", async () => {
  const review = fixture();
  review.candidates[0].job_metrics = {supporting_posting_count: 3, assessed_posting_count: 7, selected_posting_count: 8, percentage: 42.86, coverage_status: "partial"};
  const ids = review.candidates.map(row => row.candidate_id);
  const props = {review, candidateIds: ids, open: false, onOpenChange: vi.fn(), onAsk: vi.fn()};
  const {rerender} = render(<CompactComparison {...props}/>);
  expect(runtime.init).not.toHaveBeenCalled();
  rerender(<CompactComparison {...props} open/>);
  const list = screen.getByRole("list", {name: "Comparison values"});
  expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  expect(screen.getByText(/5 of 7/)).toBeInTheDocument();
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  expect(runtime.setOption.mock.calls.at(-1)![0].series[0].data).toHaveLength(5);
  const user = userEvent.setup();
  screen.getByRole("button", {name: "Next comparison page"}).focus();
  await user.keyboard("{Enter}");
  expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByText(/Skill 6/, {selector: "strong"})).toBeInTheDocument();
  expect(ids).toHaveLength(7);
});
it("keeps read-only bar/measure/occupation interaction separate from exact Ask context", async () => {
  const review = fixture();
  review.candidates = review.candidates.slice(0, 2);
  const a = workspaceEvidenceFixture({id: "a", element_id: "a", label: "Programming"});
  a.relation = "related"; a.evidence.ratings.IM!.value = 3.38;
  const b = workspaceEvidenceFixture({id: "b", element_id: "b", label: "Design"});
  review.candidates[0].onet_associations = [a, b];
  const onAsk = vi.fn(); const before = JSON.stringify(review);
  const post = vi.spyOn(axios, "post");
  render(<CompactComparison review={review} candidateIds={["skill-0", "skill-1"]} open onOpenChange={vi.fn()} onAsk={onAsk}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "O*NET importance"}));
  expect(screen.getByRole("combobox", {name: "Descriptor for Skill 0"})).toBeInTheDocument();
  await user.selectOptions(screen.getByRole("combobox", {name: "Descriptor for Skill 0"}), "a");
  await waitFor(() => expect(runtime.setOption.mock.calls.at(-1)![0].xAxis).toMatchObject({min: 1, max: 5}));
  const click = runtime.on.mock.calls.find(([name]) => name === "click")![1];
  act(() => click({data: runtime.setOption.mock.calls.at(-1)![0].series[0].data[0]}));
  expect(onAsk).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", {name: "Ask about Programming — related to Skill 0"}));
  expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({candidateIds: ["skill-0"], occupationCodes: [workspaceSoc], text: expect.stringContaining("30.0")}), [{candidate_id: "skill-0", evidence_id: "a"}]);
  await user.selectOptions(screen.getByRole("combobox", {name: "Descriptor for Skill 0"}), "b");
  expect(screen.getByRole("button", {name: "Ask about Design — equivalent to Skill 0"})).toBeInTheDocument();
  await user.selectOptions(screen.getByRole("combobox", {name: "Descriptor for Skill 0"}), "");
  expect(screen.getByRole("combobox", {name: "Descriptor for Skill 0"})).toHaveValue("");
  await user.selectOptions(screen.getByRole("combobox", {name: "Confirmed occupation"}), "15-1253.00");
  expect(screen.getByText("No comparable reported values. Unavailable evidence is listed below.")).toBeInTheDocument();
  expect(onAsk).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(review)).toBe(before);
  expect(post).not.toHaveBeenCalled();
});
it("keeps accessible values and sources when the chart fails, then disposes on close", async () => {
  const review = fixture();
  runtime.init.mockImplementationOnce(() => {throw new Error("chunk unavailable");});
  const props = {review, candidateIds: ["skill-0"], open: true, onOpenChange: vi.fn(), onAsk: vi.fn()};
  const {rerender} = render(<CompactComparison {...props}/>);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Chart unavailable/);
  expect(screen.getByRole("list", {name: "Comparison values"})).toHaveTextContent("4 of 7 assessed postings");
  expect(screen.getByRole("link", {name: "Original source for Skill 0"})).toHaveAttribute("href", "https://hh.uz/vacancy/123");
  rerender(<CompactComparison {...props} open={false}/>);
  rerender(<CompactComparison {...props}/>);
  await waitFor(() => expect(runtime.setOption).toHaveBeenCalled());
  rerender(<CompactComparison {...props} open={false}/>);
  expect(runtime.dispose).toHaveBeenCalledTimes(1);
});

it("pages candidate skills before shared-descriptor deduplication so Ask retains bounded exact mappings", async () => {
  const review = fixture();
  const base = review.candidates[0];
  review.candidates = Array.from({length: 58}, (_, index) => ({...base, candidate_id: `skill-${index}`, display_name: `Skill ${index}`,
    onet_associations: [workspaceEvidenceFixture({id: `evidence-${index}`})]}));
  const onAsk = vi.fn();
  const onOpenChange = vi.fn();
  render(<CompactComparison review={review} candidateIds={review.candidates.map(row => row.candidate_id)} open onOpenChange={onOpenChange} onAsk={onAsk}/>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "O*NET importance"}));
  expect(screen.getByText(/5 of 58 skills/)).toBeInTheDocument();
  expect(within(screen.getByRole("list", {name: "Comparison values"})).getAllByRole("listitem")).toHaveLength(1);
  await user.click(screen.getByRole("button", {name: /^Ask about Programming/}));
  expect(onAsk.mock.calls[0][0].candidateIds).toEqual(["skill-0", "skill-1", "skill-2", "skill-3", "skill-4"]);
  expect(onAsk.mock.calls[0][1]).toEqual([0, 1, 2, 3, 4].map(index => ({candidate_id: `skill-${index}`, evidence_id: `evidence-${index}`})));
  await user.click(screen.getByRole("button", {name: "Next comparison page"}));
  await user.click(screen.getByRole("button", {name: /^Ask about Programming/}));
  expect(onAsk.mock.calls[1][0].candidateIds).toEqual(["skill-5", "skill-6", "skill-7", "skill-8", "skill-9"]);
  await user.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
it("requires a named occupation and stored release before asking about O*NET context", async () => {
  const review = fixture();
  review.analysis_metadata = null;
  const onAsk = vi.fn();
  render(<CompactComparison review={review} candidateIds={["skill-0"]} open onOpenChange={vi.fn()} onAsk={onAsk}/>);
  const user = userEvent.setup();
  expect(screen.getByRole("button", {name: "Ask about Skill 0"})).toBeEnabled();
  await user.click(screen.getByRole("button", {name: "O*NET importance"}));
  const ask = screen.getByRole("button", {name: "Ask about Skill 0"});
  expect(ask).toBeDisabled();
  await user.click(ask);
  expect(onAsk).not.toHaveBeenCalled();
});
it("describes conflicting shared descriptor values as unavailable without offering a phantom choice", async () => {
  const review = fixture();
  review.candidates = review.candidates.slice(0, 2);
  review.candidates.forEach((candidate, index) => {
    const association = workspaceEvidenceFixture({id: `shared-${index}`});
    association.evidence.ratings.IM!.value = index === 0 ? 3.38 : 4.2;
    candidate.onet_associations = [association];
  });
  render(<CompactComparison review={review} candidateIds={["skill-0", "skill-1"]} open onOpenChange={vi.fn()} onAsk={vi.fn()}/>);
  await userEvent.setup().click(screen.getByRole("button", {name: "O*NET importance"}));
  const list = screen.getByRole("list", {name: "Comparison values"});
  expect(list).toHaveTextContent("Unavailable · conflicting saved descriptor values");
  expect(list).not.toHaveTextContent("Choose a descriptor");
  expect(within(list).queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("img", {name: "O*NET importance for Developer"})).not.toBeInTheDocument();
});

it("retains complete Unicode source labels and exact candidate context while wrapping long text", async () => {
  const review = fixture();
  const label = "中文Русский " + "UnbrokenLabel".repeat(20);
  review.candidates[0].display_name = label;
  const onAsk = vi.fn();
  render(<CompactComparison review={review} candidateIds={["skill-0"]} open onOpenChange={vi.fn()} onAsk={onAsk}/>);
  expect(within(screen.getByRole("list", {name:"Comparison values"})).getByText(label, {selector:"strong"})).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", {name:`Ask about ${label}`}));
  expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({candidateIds:["skill-0"],text:expect.stringContaining(label)}), []);
});

it("summarizes identical counts without a redundant chart and retains each source and exact question", async () => {
  const review = fixture();
  const onAsk = vi.fn();
  render(<CompactComparison review={review} candidateIds={review.candidates.slice(0, 5).map(row => row.candidate_id)} open onOpenChange={vi.fn()} onAsk={onAsk}/>);
  expect(screen.getByText(/All 5 skills appear in 4 of 7 assessed postings.*8 selected/)).toBeInTheDocument();
  expect(screen.queryByRole("img", {name: "Collected job sample frequency"})).not.toBeInTheDocument();
  expect(screen.getAllByRole("link", {name: /Original source/})).toHaveLength(5);
  await userEvent.click(screen.getByRole("button", {name: "Ask about Skill 3"}));
  expect(onAsk).toHaveBeenCalledWith(expect.objectContaining({candidateIds: ["skill-3"]}), []);
});

it("uses one missing-coverage explanation instead of repeating absent ratings for every skill", async () => {
  const review = fixture();
  review.candidates.forEach(candidate => {candidate.onet_associations = [];});
  render(<CompactComparison review={review} candidateIds={review.candidates.slice(0, 5).map(row => row.candidate_id)} open onOpenChange={vi.fn()} onAsk={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button", {name: "O*NET importance"}));
  expect(screen.getByText(/No comparable reported values. Unavailable evidence is listed below./)).toBeInTheDocument();
  expect(within(screen.getByRole("list", {name: "Comparison values"})).queryAllByText(/Unavailable/)).toHaveLength(0);
  expect(within(screen.getByRole("list", {name: "Comparison values"})).getAllByRole("listitem")).toHaveLength(5);
});
