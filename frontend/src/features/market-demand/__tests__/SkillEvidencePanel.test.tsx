import {act, render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {beforeEach, expect, it, vi} from "vitest";
import {SkillEvidencePanel} from "@/features/market-demand/components/SkillEvidencePanel";
import {reviewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import type {PostingEvidence, SkillCandidate, VacancyEvidenceReference} from "@/features/market-demand/types";
vi.mock("@/features/market-demand/api", async () => ({...await vi.importActual("@/features/market-demand/api"), fetchPostingEvidence: vi.fn()}));
import {fetchPostingEvidence} from "@/features/market-demand/api";

function reference(snapshot: string, url: string, phrase: string): VacancyEvidenceReference {
  return {snapshot_id: snapshot, provider: "headhunter", original_url: url, original_phrase: phrase, evidence_kind: "extracted_text", excerpt: `${phrase} in practice`, excerpt_start: 0, excerpt_end: 20, retrieved_at: "2026-10-14", status: "active"};
}
function candidate(): SkillCandidate {
  return {...reviewFixture().candidates[0], display_name: "ETL", original_labels: ["Create ETL", "Develop ETL/ELT"], qualifying_posting_links: [], evidence_references: [reference("a", "https://jobs.test/1", "Create ETL"), reference("b", "https://jobs.test/1", "Develop ETL/ELT"), reference("c", "https://jobs.test/2", "SQL"), reference("d", "https://jobs.test/3", "Python"), reference("e", "https://jobs.test/4", "Spark")]};
}
function posting(id: string, overrides: Partial<PostingEvidence> = {}): PostingEvidence {
  return {snapshot_id: id, provider: "headhunter", native_id: id, original_url: "https://jobs.test/1", title: `Developer ${id}`, company: "Acme", description_text: `Posting body ${id}`, original_description: "Source description", raw_payload: {}, retrieved_at: "2026-10-14", status: "active", purged_at: null, ...overrides};
}
beforeEach(() => {vi.mocked(fetchPostingEvidence).mockReset();});

it("groups_two_quotes_and_two_snapshots_under_one_posting", async () => {
  vi.mocked(fetchPostingEvidence).mockImplementation(async (_, id) => posting(id));
  const error = vi.spyOn(console, "error");
  const row = candidate();
  row.evidence_references.push({...row.evidence_references[0]});
  render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  const dialog = screen.getByRole("dialog");
  expect(await within(dialog).findByText("Develop ETL/ELT in practice")).toBeInTheDocument();
  expect(within(dialog).getByText("Create ETL in practice")).toBeInTheDocument();
  expect(screen.getAllByRole("link", {name: /Original posting/})).toHaveLength(4);
  expect(within(dialog).getAllByRole("article")).toHaveLength(4);
  expect(fetchPostingEvidence).toHaveBeenCalledTimes(5);
  expect(error).not.toHaveBeenCalled();
  error.mockRestore();
});

it("rechecks_before_revealing_content_after_reopen", async () => {
  const row = {...candidate(), evidence_references: [reference("a", "https://jobs.test/1", "Create ETL")]};
  let resolveRecheck!: (value: PostingEvidence) => void;
  vi.mocked(fetchPostingEvidence).mockResolvedValueOnce(posting("a")).mockImplementationOnce(() => new Promise(resolve => {resolveRecheck = resolve;}));
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(await screen.findByText("Create ETL in practice")).toBeInTheDocument();
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={vi.fn()}/>);
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
  expect(screen.queryByText("Posting body a")).not.toBeInTheDocument();
  await act(async () => resolveRecheck(posting("a", {status: "purged", purged_at: "2026-10-15"})));
  expect(screen.getByText(/Retained provenance only/)).toBeInTheDocument();
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
});

it("limits concurrent checks to three and fetches a duplicate snapshot only once", async () => {
  const pending = new Map<string, (value: PostingEvidence) => void>();
  vi.mocked(fetchPostingEvidence).mockImplementation((_, id) => new Promise(resolve => pending.set(id, resolve)));
  const row = candidate();
  row.evidence_references.push({...row.evidence_references[0], excerpt: "Second passage"});
  render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect([...pending.keys()]).toEqual(["a", "b", "c"]);
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
  await act(async () => pending.get("a")!(posting("a")));
  expect([...pending.keys()]).toEqual(["a", "b", "c", "d"]);
  expect(screen.getByText("Second passage")).toBeInTheDocument();
  expect(screen.queryByText("Develop ETL/ELT in practice")).not.toBeInTheDocument();
  await act(async () => pending.get("b")!(posting("b")));
  expect([...pending.keys()]).toEqual(["a", "b", "c", "d", "e"]);
  expect(screen.getByText("Develop ETL/ELT in practice")).toBeInTheDocument();
});

it("retains link-only provenance and safe hostile text while withholding failed or purged passages", async () => {
  const row = candidate();
  row.qualifying_posting_links = ["https://jobs.test/link-only", "javascript:alert(1)", "https://user:password@jobs.test/secret"];
  row.evidence_references = [reference("a", "https://jobs.test/1", "<img src=x onerror=alert(1)>"), reference("b", "javascript:alert(1)", "Failed secret")];
  vi.mocked(fetchPostingEvidence).mockResolvedValueOnce(posting("a", {original_description: "<script>alert(1)</script>", raw_payload: {html: "<img src=x>"}})).mockRejectedValueOnce(new Error("Availability failed")).mockResolvedValueOnce(posting("b", {purged_at: "2026-10-15"}));
  const {baseElement} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Availability failed");
  expect(screen.queryByText("Failed secret in practice")).not.toBeInTheDocument();
  expect(screen.getByText("<img src=x onerror=alert(1)> in practice")).toBeInTheDocument();
  expect(baseElement.querySelector("script,img")).toBeNull();
  expect(screen.getAllByRole("link", {name: /Original posting/}).map(link => link.getAttribute("href"))).toEqual(["https://jobs.test/1", "https://jobs.test/link-only"]);
  const provenanceLink = screen.getAllByRole("link", {name: /Original posting/})[1];
  expect(within(provenanceLink.closest("article")!).getByText(/No retained posting content/)).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", {name: "Load full posting evidence"}));
  expect(await screen.findByText(/Posting content unavailable: purged/)).toBeInTheDocument();
  expect(screen.queryByText("Failed secret in practice")).not.toBeInTheDocument();
});

it.each(["close", "course", "candidate"])("cancels pending checks on %s and discards late content", async identity => {
  const row = {...candidate(), evidence_references: [reference("a", "https://jobs.test/1", "Create ETL")]};
  let resolveOld!: (value: PostingEvidence) => void;
  vi.mocked(fetchPostingEvidence).mockImplementationOnce(() => new Promise(resolve => {resolveOld = resolve;})).mockResolvedValueOnce(posting("a", {purged_at: "2026-10-15"}));
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  const signal = vi.mocked(fetchPostingEvidence).mock.calls[0][2]!;
  rerender(<SkillEvidencePanel courseId={identity === "course" ? 2 : 1} candidate={identity === "candidate" ? {...row, candidate_id: "next"} : row} open={identity !== "close"} onOpenChange={vi.fn()}/>);
  expect(signal.aborted).toBe(true);
  await act(async () => resolveOld(posting("a", {description_text: "Stale secret"})));
  expect(screen.queryByText("Stale secret")).not.toBeInTheDocument();
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
});

it("rejects a response for the wrong snapshot before exposing source text", async () => {
  vi.mocked(fetchPostingEvidence).mockResolvedValue(posting("wrong", {description_text: "Wrong snapshot secret"}));
  const row = {...candidate(), evidence_references: [reference("a", "https://jobs.test/1", "Create ETL")]};
  render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText("Wrong snapshot secret")).not.toBeInTheDocument();
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
});


it("keeps every original skill label visible with provenance-only links", () => {
  const row = {...candidate(), evidence_references: [], qualifying_posting_links: ["https://jobs.test/retained-link"]};
  render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(screen.getByText("Original skill labels: Create ETL · Develop ETL/ELT")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "Original posting · Posting retained-link"})).toHaveAttribute("href", "https://jobs.test/retained-link");
  expect(fetchPostingEvidence).not.toHaveBeenCalled();
});

it("does not fetch before controlled open and reports keyboard close to its owner", async () => {
  const onOpenChange = vi.fn();
  const row = {...candidate(), evidence_references: [reference("a", "https://jobs.test/1", "Create ETL")]};
  vi.mocked(fetchPostingEvidence).mockResolvedValue(posting("a"));
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={onOpenChange}/>);
  expect(fetchPostingEvidence).not.toHaveBeenCalled();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={onOpenChange}/>);
  expect(await screen.findByText("Create ETL in practice")).toBeInTheDocument();
  await userEvent.setup().keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={onOpenChange}/>);
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
});

it("stops queued checks on close even when an aborted transport resolves later", async () => {
  let resolveOld!: (value: PostingEvidence) => void;
  vi.mocked(fetchPostingEvidence).mockImplementationOnce(() => new Promise(resolve => {resolveOld = resolve;})).mockImplementation(() => new Promise(() => {}));
  const row = candidate();
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(fetchPostingEvidence).toHaveBeenCalledTimes(3);
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={vi.fn()}/>);
  expect(vi.mocked(fetchPostingEvidence).mock.calls.every(call => call[2]!.aborted)).toBe(true);
  await act(async () => resolveOld(posting("a")));
  expect(fetchPostingEvidence).toHaveBeenCalledTimes(3);
  expect(screen.queryByText("Create ETL in practice")).not.toBeInTheDocument();
});

it("names original links from current title and employer but drops both during recheck and purge", async () => {
  const row = {...candidate(), evidence_references: [reference("a", "https://jobs.test/1", "Create ETL")]};
  let resolveRecheck!: (value: PostingEvidence) => void;
  vi.mocked(fetchPostingEvidence).mockResolvedValueOnce(posting("a")).mockImplementationOnce(() => new Promise(resolve => {resolveRecheck = resolve;}));
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(await screen.findByRole("link", {name: "Original posting · Developer a · Acme"})).toHaveAttribute("href", "https://jobs.test/1");
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={vi.fn()}/>);
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()}/>);
  expect(screen.getByRole("link", {name: "Original posting · Posting a"})).toBeInTheDocument();
  expect(screen.queryByRole("link", {name: /Developer a|Acme/})).not.toBeInTheDocument();
  await act(async () => resolveRecheck(posting("a", {status: "purged", purged_at: "2026-10-15"})));
  expect(screen.getByRole("link", {name: "Original posting · Posting a"})).toBeInTheDocument();
  expect(screen.queryByRole("link", {name: /Developer a|Acme/})).not.toBeInTheDocument();
});

it("returns keyboard focus to the supplied surviving trigger on close", async () => {
  const trigger = document.createElement("button"); trigger.textContent = "Inspect ETL"; document.body.append(trigger); trigger.focus();
  const row = {...candidate(), evidence_references: [], qualifying_posting_links: []};
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open onOpenChange={vi.fn()} returnFocusTo={trigger}/>);
  rerender(<SkillEvidencePanel courseId={1} candidate={row} open={false} onOpenChange={vi.fn()} returnFocusTo={trigger}/>);
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(trigger).toHaveFocus();
  trigger.remove();
});

it("does not focus a removed trigger when the course or inspection closes", async () => {
  const trigger = document.createElement("button"); document.body.append(trigger);
  const focus = vi.spyOn(trigger, "focus");
  const row = {...candidate(), evidence_references: [], qualifying_posting_links: []};
  const {rerender} = render(<SkillEvidencePanel courseId={1} candidate={row} open returnFocusTo={trigger}/>);
  trigger.remove();
  rerender(<SkillEvidencePanel courseId={2} candidate={row} open={false} returnFocusTo={trigger}/>);
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(focus).not.toHaveBeenCalled();
});

it("explains score provenance, role, coverage and limitations while retaining original source links", async () => {
  const {workspaceEvidenceFixture} = await import("@/features/market-demand/__tests__/review-fixtures");
  const row = {...reviewFixture().candidates[0], evidence_references: [], onet_associations: [workspaceEvidenceFixture()],
    priority: {value: 4, basis: "onet_aggregate" as const, complete: false, expected_contexts: 2, scored_contexts: 1, display_order: 0}};
  const assessment = {assessment_id: "assessment", run_id: "run-1", candidate_revision: 1, input_fingerprint: "f", schema_version: 1 as const,
    policy_version: "1", prompt_version: "1", model_id: "model", release: "30.0", started_at: "2026-10-15", updated_at: "2026-10-15",
    deadline_at: "2026-10-16", completed_at: "2026-10-15", status: "partial" as const, expected_pair_count: 2, completed_pair_count: 1,
    posting_hashes: {}, error_reasons: ["One role could not be assessed"], summaries: {candidates: {}, categories: {}},
    contexts: [{group_id: "developers", soc_code: "15-1252.00", occupation_title: "Software Developers", posting_ids: ["snapshot-1"],
      rationale: "Role from the selected postings", inferred: true, unavailable_reason: null}],
    results: [{candidate_id: "python", context_key: "developers", soc_code: "15-1252.00", basis: "onet" as const,
      direct_reference_id: row.onet_associations[0].evidence.id, estimate: null, associations: [], supporting_evidence_ids: ["snapshot-1"],
      explanation: "Equivalent programming descriptor", limitations: ["Only one role assessed"], unavailable_reason: null, official_value: 4.2, value: 4.2}]};
  render(<SkillEvidencePanel courseId={1} candidate={row} priorityAssessment={assessment} open onOpenChange={vi.fn()}/>);
  expect(screen.getByText(/Lab Tutor summary/)).toBeInTheDocument();
  expect(screen.getByText(/1 of 2 role contexts assessed/)).toBeInTheDocument();
  expect(screen.getByText(/Software Developers.*15-1252.00/)).toBeInTheDocument();
  expect(screen.getByText(/O\*NET source value: 4.2\/5/)).toBeInTheDocument();
  expect(screen.getByText(/Only one role assessed/)).toBeInTheDocument();
  expect(screen.getByRole("link", {name: /Original posting/})).toHaveAttribute("href", "https://hh.uz/vacancy/123");
  expect(screen.getByRole("link", {name: /O\*NET reference/})).toHaveAttribute("href", "https://onetonline.org");
});

it.each([false, true])("resolves new priority references with readable sources and no duplicate legacy cards (legacy present: %s)", async legacy => {
  const {workspaceEvidenceFixture} = await import("@/features/market-demand/__tests__/review-fixtures");
  const direct = workspaceEvidenceFixture({id: "priority-direct", label: "Programming systems", source_url: "https://www.onetonline.org/link/summary/15-1252.00", attribution: "O*NET Database 30.0 · National Center for O*NET Development"});
  const anchor = workspaceEvidenceFixture({id: "priority-anchor", label: "Systems analysis", source_url: "https://www.onetonline.org/link/summary/15-1211.00"}).evidence;
  const unused = workspaceEvidenceFixture({id: "another-candidate", label: "Unrelated descriptor"}).evidence;
  const row = {...reviewFixture().candidates[0], evidence_references: [], onet_associations: legacy ? [direct] : [],
    priority: {value: 4, basis: "onet" as const, complete: true, expected_contexts: 1, scored_contexts: 1, display_order: 0}};
  const assessment = {assessment_id: "assessment", run_id: "run-1", candidate_revision: 1, input_fingerprint: "f", schema_version: 1 as const,
    policy_version: "1", prompt_version: "1", model_id: "technical-model", release: "30.0", started_at: "2026-10-15", updated_at: "2026-10-15",
    deadline_at: "2026-10-16", completed_at: "2026-10-15", status: "ready" as const, expected_pair_count: 1, completed_pair_count: 1,
    posting_hashes: {}, error_reasons: [], summaries: {candidates: {}, categories: {}}, contexts: [], references: [direct.evidence, anchor, unused],
    results: [{candidate_id: "python", context_key: "role", soc_code: "15-1252.00", basis: "onet" as const,
      direct_reference_id: "priority-direct", estimate: null, associations: [{reference_id: "priority-anchor", relation: "related" as const, rationale: "Contextual systems reference"}],
      supporting_evidence_ids: ["passage-private-a", "passage-private-b"], explanation: "Equivalent descriptor", limitations: [], unavailable_reason: null, official_value: 4, value: 4}]};
  render(<SkillEvidencePanel courseId={1} candidate={row} priorityAssessment={assessment} open onOpenChange={vi.fn()}/>);
  expect(screen.getAllByRole("link", {name: "O*NET reference: Programming systems (Developer)"})).toHaveLength(1);
  expect(screen.getByRole("link", {name: "O*NET reference: Programming systems (Developer)"})).toHaveAttribute("href", direct.evidence.source_url);
  expect(screen.getByText("O*NET Database 30.0 · National Center for O*NET Development")).toBeInTheDocument();
  expect(screen.getByRole("link", {name: "O*NET reference: Systems analysis (Developer)"})).toHaveAttribute("href", anchor.source_url);
  expect(screen.getByText(/related reference: Systems analysis/)).toHaveTextContent("Contextual systems reference");
  expect(screen.getByText("2 verified passages · see posting evidence below.")).toBeInTheDocument();
  expect(screen.queryByText(/passage-private|Matched reference: priority-direct/)).not.toBeInTheDocument();
  expect(screen.queryByText("O*NET unavailable: no association.")).not.toBeInTheDocument();
  expect(screen.queryByText(/Unrelated descriptor/)).not.toBeInTheDocument();
  expect(screen.getByRole("dialog").querySelectorAll('[data-evidence-id="priority-direct"]')).toHaveLength(1);
  expect(screen.getByText(/technical-model/)).not.toBeVisible();
  expect(screen.getByRole("link", {name: /Original posting/})).toHaveAttribute("href", "https://hh.uz/vacancy/123");
});
