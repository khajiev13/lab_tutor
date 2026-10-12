import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import {beforeEach, expect, it, vi} from "vitest";
import {OccupationReferencePanel} from "@/features/market-demand/components/OccupationReferencePanel";
import * as api from "@/features/market-demand/api";
import type {OnetEvidence, OnetMetric} from "@/features/market-demand/types";

vi.mock("@/features/market-demand/api", () => ({
  fetchOnetReleases: vi.fn(), searchOnetOccupations: vi.fn(), getOccupationSkills: vi.fn(),
  saveSkillReviewDraft: vi.fn(), confirmOnetOccupations: vi.fn(), streamMarketDemandChat: vi.fn(), approveSkillIntegration: vi.fn(),
}));
const releases = {items: [{version: "31.0", active: true, attribution: "O*NET attribution"}, {version: "30.0", active: false, attribution: "Older attribution"}]};
const occupations = {release: "31.0", total: 2, items: [
  {soc_code: "15-2051.00", title: "Data Scientists", description: "Analyze data"},
  {soc_code: "15-1252.00", title: "Software Developers", description: "Develop software"},
]};
const metric = (scale: "IM" | "LV", value: number | null, status: OnetMetric["status"] = "reported"): OnetMetric =>
  ({scale_id: scale, value, minimum: scale === "IM" ? 1 : 0, maximum: scale === "IM" ? 5 : 7, status, date: "2026-01", quality: {standard_error: 0.1}});
function evidence(label = "Critical Thinking", changes: Partial<OnetEvidence> = {}): OnetEvidence {
  return {id: "evidence-1", release: "31.0", soc_code: "15-2051.00", occupation_title: "Data Scientists", family: "essential", element_id: "2.A.2.a",
    label, definition: "Evaluate alternatives", workplace_example: "Review a result", ratings: {IM: metric("IM", 4), LV: metric("LV", 5)},
    flags: {hot: true}, source_url: "https://www.onetcenter.org/database.html", attribution: "Descriptor attribution", ...changes};
}
function deferred<T>() {let resolve!: (value: T) => void; let reject!: (cause: Error) => void;
  const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject};}
async function search(value = "data") {
  await waitFor(() => expect(screen.getByRole("button", {name: "Search"})).toBeEnabled());
  fireEvent.change(screen.getByRole("textbox", {name: "Search occupations"}), {target: {value}});
  await act(async () => {fireEvent.click(screen.getByRole("button", {name: "Search"}));});
}
async function browse() {await search(); const button = await screen.findByRole("button", {name: "Browse Data Scientists (15-2051.00)"}); await act(async () => {fireEvent.click(button);});}
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.fetchOnetReleases).mockResolvedValue(releases);
  vi.mocked(api.searchOnetOccupations).mockResolvedValue(occupations);
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [evidence()]});
});

it("browses and stages reference-only IDs without a run or any mutation", async () => {
  const onAsk = vi.fn(); render(<OccupationReferencePanel courseId={7} onAsk={onAsk}/>);
  await browse(); const card = await screen.findByRole("article", {name: "Critical Thinking"});
  expect(within(card).getByText("IM: 4 (1–5)")).toBeInTheDocument();
  expect(within(card).getByText("LV: 5 (0–7)")).toBeInTheDocument();
  expect(within(card).getByRole("link", {name: "O*NET source"})).toHaveAttribute("href", evidence().source_url);
  expect(within(card).getByText("Descriptor attribution")).toBeInTheDocument();
  expect(within(card).getByText(/31.0.*2.A.2.a/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", {name: "Reference question metric"}), {target: {value: "LV"}});
  fireEvent.click(within(card).getByRole("button", {name: "Ask about Critical Thinking"}));
  expect(onAsk).toHaveBeenCalledWith({kind: "occupation_reference", version: 1, intent: "explain", release: "31.0", occupation_codes: ["15-2051.00"], element_ids: ["2.A.2.a"], metric: "LV"}, expect.any(String));
  expect(api.saveSkillReviewDraft).not.toHaveBeenCalled(); expect(api.confirmOnetOccupations).not.toHaveBeenCalled();
  expect(api.streamMarketDemandChat).not.toHaveBeenCalled(); expect(api.approveSkillIntegration).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", {name: /Approve integration|Start an analysis|Confirm occupations/})).toBeNull();
});

it("renders unavailable statuses separately and software as categorical", async () => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [
    evidence("Missing", {id: "a", ratings: {}}), evidence("Suppressed", {id: "b", ratings: {IM: metric("IM", 3, "suppressed")}}),
    evidence("Not relevant", {id: "c", ratings: {LV: metric("LV", 2, "not_relevant")}}),
    evidence("Python", {id: "d", family: "software", ratings: {IM: metric("IM", 4)}}),
  ]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await browse();
  expect(within(await screen.findByRole("article", {name: "Missing"})).getByText("IM: unavailable (missing)")).toBeInTheDocument();
  expect(within(screen.getByRole("article", {name: "Suppressed"})).getByText("IM: unavailable (suppressed)")).toBeInTheDocument();
  expect(within(screen.getByRole("article", {name: "Not relevant"})).getByText("LV: unavailable (not relevant)")).toBeInTheDocument();
  const software = within(screen.getByRole("article", {name: "Python"}));
  expect(software.getByText(/Categorical software evidence/)).toBeInTheDocument(); expect(software.queryByText(/^IM:|^LV:/)).toBeNull();
});
it.each([
  {value: NaN}, {value: Infinity}, {value: 0}, {value: 6}, {value: null}, {value: 3, minimum: 0}, {value: 3, maximum: 7}, {value: 3, scale_id: "LV"},
])("does not show a numeric IM value with invalid reported metadata %j", async (invalid) => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [evidence("Invalid", {ratings: {IM: {...metric("IM", 3), ...invalid} as OnetMetric}})]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await browse();
  expect(within(await screen.findByRole("article", {name: "Invalid"})).getByText("IM: unavailable (invalid reported value or scale)")).toBeInTheDocument();
});
it("bounds searches, trims valid input, and only offers explicit release selection when none is active", async () => {
  vi.mocked(api.fetchOnetReleases).mockResolvedValue({items: [{...releases.items[0], active: false}]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>);
  await screen.findByText(/none is active/); expect(screen.getByRole("button", {name: "Search"})).toBeDisabled();
  fireEvent.change(screen.getByRole("combobox", {name: "O*NET release"}), {target: {value: "31.0"}});
  for (const value of [" ", " x ", "x".repeat(121)]) {await search(value); expect(await screen.findByRole("alert")).toHaveTextContent("2–120");}
  expect(api.searchOnetOccupations).not.toHaveBeenCalled(); await search(" data ");
  await screen.findByRole("button", {name: /Browse Data Scientists/});
  expect(api.searchOnetOccupations).toHaveBeenCalledWith(7, "31.0", "data", 0, 20, expect.any(AbortSignal));
});
it.each(["empty", "error"])("offers retry for %s catalog without inventing an occupation", async (kind) => {
  if (kind === "empty") vi.mocked(api.fetchOnetReleases).mockResolvedValueOnce({items: []});
  else vi.mocked(api.fetchOnetReleases).mockRejectedValueOnce(new Error("Catalog offline"));
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>);
  fireEvent.click(await screen.findByRole("button", {name: "Retry catalog"}));
  await search(); expect(await screen.findByRole("button", {name: /Browse Data Scientists/})).toBeInTheDocument();
});
it.each(["empty", "error"])("offers retry for %s occupation results", async (kind) => {
  if (kind === "empty") vi.mocked(api.searchOnetOccupations).mockResolvedValueOnce({...occupations, total: 0, items: []});
  else vi.mocked(api.searchOnetOccupations).mockRejectedValueOnce(new Error("Search offline"));
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await search();
  fireEvent.click(await screen.findByRole("button", {name: "Retry search"}));
  expect(await screen.findByRole("button", {name: /Browse Data Scientists/})).toBeInTheDocument();
});
it.each(["empty", "error"])("offers retry for %s imported evidence without staged fallback", async (kind) => {
  if (kind === "empty") vi.mocked(api.getOccupationSkills).mockResolvedValueOnce({release: "31.0", soc_code: "15-2051.00", items: []});
  else vi.mocked(api.getOccupationSkills).mockRejectedValueOnce(new Error("Evidence offline"));
  const onAsk = vi.fn(); render(<OccupationReferencePanel courseId={7} onAsk={onAsk}/>); await browse();
  const retry = await screen.findByRole("button", {name: "Retry evidence"});
  expect(screen.queryByRole("button", {name: "Ask about this occupation"})).toBeNull(); expect(onAsk).not.toHaveBeenCalled();
  fireEvent.click(retry); expect(await screen.findByRole("article", {name: "Critical Thinking"})).toBeInTheDocument();
});
it("aborts and ignores superseded occupation evidence even when it resolves after abort", async () => {
  const old = deferred<Awaited<ReturnType<typeof api.getOccupationSkills>>>();
  vi.mocked(api.getOccupationSkills).mockReturnValueOnce(old.promise).mockResolvedValueOnce({release: "31.0", soc_code: "15-1252.00", items: [evidence("Current", {soc_code: "15-1252.00"})]});
  const onAsk = vi.fn(); render(<OccupationReferencePanel courseId={7} onAsk={onAsk}/>); await browse();
  const signal = vi.mocked(api.getOccupationSkills).mock.calls[0][3]!;
  fireEvent.click(screen.getByRole("button", {name: /Browse Software Developers/}));
  expect(await screen.findByRole("article", {name: "Current"})).toBeInTheDocument(); expect(signal.aborted).toBe(true);
  await act(async () => {old.resolve({release: "31.0", soc_code: "15-2051.00", items: [evidence("Stale")]});});
  expect(screen.queryByRole("article", {name: "Stale"})).toBeNull();
  fireEvent.click(screen.getByRole("button", {name: "Ask about this occupation"}));
  expect(onAsk.mock.calls[0][0].occupation_codes).toEqual(["15-1252.00"]);
});
it.each(["search", "evidence"])("clears and ignores late %s on release change", async (boundary) => {
  const pendingSearch = deferred<typeof occupations>(); const pendingEvidence = deferred<Awaited<ReturnType<typeof api.getOccupationSkills>>>();
  if (boundary === "search") vi.mocked(api.searchOnetOccupations).mockReturnValueOnce(pendingSearch.promise);
  else vi.mocked(api.getOccupationSkills).mockReturnValueOnce(pendingEvidence.promise);
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); if (boundary === "search") await search(); else await browse();
  const signal = boundary === "search" ? vi.mocked(api.searchOnetOccupations).mock.calls[0][5]! : vi.mocked(api.getOccupationSkills).mock.calls[0][3]!;
  fireEvent.change(screen.getByRole("combobox", {name: "O*NET release"}), {target: {value: "30.0"}});
  expect(signal.aborted).toBe(true);
  await act(async () => {pendingSearch.resolve(occupations); pendingEvidence.resolve({release: "31.0", soc_code: "15-2051.00", items: [evidence("Stale")]});});
  expect(screen.queryByRole("button", {name: /Browse Data Scientists/})).toBeNull(); expect(screen.queryByRole("article", {name: "Stale"})).toBeNull();
});
it.each(["catalog", "search", "evidence"])("clears and ignores late %s on course change", async (boundary) => {
  const catalog = deferred<typeof releases>(); const results = deferred<typeof occupations>(); const data = deferred<Awaited<ReturnType<typeof api.getOccupationSkills>>>();
  if (boundary === "catalog") vi.mocked(api.fetchOnetReleases).mockReturnValueOnce(catalog.promise);
  if (boundary === "search") vi.mocked(api.searchOnetOccupations).mockReturnValueOnce(results.promise);
  if (boundary === "evidence") vi.mocked(api.getOccupationSkills).mockReturnValueOnce(data.promise);
  const {rerender} = render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>);
  if (boundary === "search") await search(); if (boundary === "evidence") await browse();
  const signal = boundary === "catalog" ? vi.mocked(api.fetchOnetReleases).mock.calls[0][1]! : boundary === "search" ? vi.mocked(api.searchOnetOccupations).mock.calls[0][5]! : vi.mocked(api.getOccupationSkills).mock.calls[0][3]!;
  rerender(<OccupationReferencePanel courseId={8} onAsk={vi.fn()}/>); expect(signal.aborted).toBe(true);
  await act(async () => {catalog.resolve({items: [{version: "29.0", active: true, attribution: "Stale catalog"}]}); results.resolve(occupations); data.resolve({release: "31.0", soc_code: "15-2051.00", items: [evidence("Stale")]});});
  expect(screen.queryByText("Stale catalog")).toBeNull(); expect(screen.queryByRole("button", {name: /Browse Data Scientists/})).toBeNull(); expect(screen.queryByRole("article", {name: "Stale"})).toBeNull();
});
it("rejects invalid descriptor IDs through the shared context bounds", async () => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [evidence("Too long", {element_id: "x".repeat(31)})]});
  const onAsk = vi.fn(); render(<OccupationReferencePanel courseId={7} onAsk={onAsk}/>); await browse();
  expect(within(await screen.findByRole("article", {name: "Too long"})).getByRole("button", {name: "Ask about Too long"})).toBeDisabled();
  expect(onAsk).not.toHaveBeenCalled();
});

it.each([
  {value: -1}, {value: 8}, {value: Infinity}, {value: 3, minimum: 1}, {value: 3, maximum: 5}, {value: 3, scale_id: "IM"},
])("does not show a numeric LV value with invalid reported metadata %j", async (invalid) => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [evidence("Invalid level", {ratings: {LV: {...metric("LV", 3), ...invalid} as OnetMetric}})]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await browse();
  expect(within(await screen.findByRole("article", {name: "Invalid level"})).getByText("LV: unavailable (invalid reported value or scale)")).toBeInTheDocument();
});
it("keeps valid declared scale endpoints and source metadata readable", async () => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: "15-2051.00", items: [
    evidence("Minimum", {id: "minimum", ratings: {IM: metric("IM", 1), LV: metric("LV", 0)}}),
    evidence("Maximum", {id: "maximum", ratings: {IM: metric("IM", 5), LV: metric("LV", 7)}}),
  ]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await browse();
  const minimum = within(await screen.findByRole("article", {name: "Minimum"}));
  expect(minimum.getByText("IM: 1 (1–5)")).toBeInTheDocument(); expect(minimum.getByText("LV: 0 (0–7)")).toBeInTheDocument();
  const maximum = within(screen.getByRole("article", {name: "Maximum"}));
  expect(maximum.getByText("IM: 5 (1–5)")).toBeInTheDocument(); expect(maximum.getByText("LV: 7 (0–7)")).toBeInTheDocument();
  expect(maximum.getByText(/IM reported scale.*2026-01.*standard_error/)).toBeInTheDocument(); expect(maximum.getByText(/Flags:.*hot/)).toBeInTheDocument();
});
it.each(["resolve", "reject"])("ignores a superseded search that later %ss on the same release", async (outcome) => {
  const old = deferred<typeof occupations>(); vi.mocked(api.searchOnetOccupations).mockReturnValueOnce(old.promise).mockResolvedValueOnce({...occupations, items: [occupations.items[1]], total: 1});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await search("data");
  const signal = vi.mocked(api.searchOnetOccupations).mock.calls[0][5]!; await search("software");
  expect(await screen.findByRole("button", {name: /Browse Software Developers/})).toBeInTheDocument(); expect(signal.aborted).toBe(true);
  await act(async () => {if (outcome === "resolve") old.resolve(occupations); else old.reject(new Error("Old search error"));});
  expect(screen.queryByRole("button", {name: /Browse Data Scientists/})).toBeNull(); expect(screen.queryByText("Old search error")).toBeNull();
});
it.each(["header", "row"])("does not stage mismatched evidence from a different occupation at %s boundary", async (boundary) => {
  vi.mocked(api.getOccupationSkills).mockResolvedValue({release: "31.0", soc_code: boundary === "header" ? "15-1252.00" : "15-2051.00", items: [evidence("Foreign", {soc_code: boundary === "row" ? "15-1252.00" : "15-2051.00"})]});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await browse();
  expect(await screen.findByRole("alert")).toHaveTextContent(/another release or occupation/); expect(screen.queryByRole("article")).toBeNull();
});
it("discloses that occupation search is limited rather than claiming all matches are shown", async () => {
  vi.mocked(api.searchOnetOccupations).mockResolvedValue({...occupations, total: 50});
  render(<OccupationReferencePanel courseId={7} onAsk={vi.fn()}/>); await search();
  expect(await screen.findByText(/Showing 2 of 50 matching occupations/)).toHaveTextContent(/Refine your search/);
});
