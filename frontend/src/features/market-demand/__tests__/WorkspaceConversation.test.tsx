import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceConversation, type ConversationDraft, type WorkspaceConversationStream } from "@/features/market-demand/components/WorkspaceConversation";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { saveSkillReviewDraft } from "@/features/market-demand/api";
import type { ResolvedContextMetadata, SendCommand, SendResult, SkillReview } from "@/features/market-demand/types";
import { workspaceCandidateId, workspaceReviewFixture, workspaceRunId } from "@/features/market-demand/__tests__/review-fixtures";

vi.mock("@/features/market-demand/api", async importOriginal => ({...await importOriginal<typeof import("@/features/market-demand/api")>(), saveSkillReviewDraft: vi.fn()}));

function attachment(): Extract<SendCommand, {mode: "contextual"}>["context"] {
  return {kind: "run_review", version: 1, intent: "explain", run_id: workspaceRunId,
    expected_candidate_revision: 1, expected_selection_revision: 2, view: "overview",
    focused_candidate_id: workspaceCandidateId, candidate_ids: [workspaceCandidateId],
    filters: {category_ids: [], search: "", scope: "all"}, occupation_codes: [], metric: "frequency",
    descriptor_choices: [], insight_kind: null, has_unsaved_changes: false};
}
function draft(): ConversationDraft {return {text: "Why Python?", command: {mode: "contextual", context: attachment()}};}
function stream(overrides: Partial<WorkspaceConversationStream> = {}): WorkspaceConversationStream {
  return {messages: [], isStreaming: false, isLoadingHistory: false, isRestored: true,
    currentAgent: null, execution: {status: "idle", outcome: "unknown", state_updated_at: null},
    streamError: null, skillReview: workspaceReviewFixture(), closeLiveResponse: vi.fn(), reconcile: vi.fn(async () => {}), ...overrides};
}
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(done => {resolve = done;}); return {promise, resolve};}
function Harness({initial = draft(), source = stream(), submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"})), withController = false, incomingReview}: {
  initial?: ConversationDraft; source?: WorkspaceConversationStream; submit?: (command: SendCommand) => Promise<SendResult>;
  withController?: boolean; incomingReview?: SkillReview;
}) {
  const [value, setValue] = useState(initial);
  const [review, setReview] = useState(incomingReview ?? workspaceReviewFixture());
  const controller = useSkillReviewController({courseId: 1, review: incomingReview ?? review, onReviewChange: setReview});
  return <><button onClick={() => setValue(draft())}>Ask about Python</button>
    <button onClick={() => controller.setCandidate(workspaceCandidateId, true)}>Select Python locally</button>
    <WorkspaceConversation stream={source} draft={value} onDraftChange={setValue} onSubmit={submit} controller={withController ? controller : undefined}/>
  </>;
}

beforeEach(() => {vi.clearAllMocks();});

describe("WorkspaceConversation", () => {
  it("stages an editable Ask question without sending and keeps keyboard focus", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    render(<Harness initial={{text: "", command: {mode: "workflow"}}} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Ask about Python"}));
    const input = screen.getByRole("textbox");
    expect(input).toHaveValue("Why Python?");
    await userEvent.type(input, " More detail.");
    expect(input).toHaveValue("Why Python? More detail.");
    expect(input).toHaveFocus();
    expect(submit).not.toHaveBeenCalled();
  });
  it("removes focus without converting ordinary review questions to workflow", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    render(<Harness submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Remove focus"}));
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({mode: "contextual", context: expect.objectContaining({intent: "explain", focused_candidate_id: null, candidate_ids: []})}));
  });
  it("returns a proposal attachment to read-only Explain when its focus is removed", async () => {
    const initial = draft(); if (initial.command.mode === "contextual" && initial.command.context.kind === "run_review") initial.command.context.intent = "propose_selection";
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async () => ({outcome: "completed"}));
    render(<Harness initial={initial} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Remove focus"}));
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({mode: "contextual", context: expect.objectContaining({intent: "explain", focused_candidate_id: null, candidate_ids: []})}));
  });
  it("freezes submitted text and nested context and preserves typed follow-up without inheriting submitted focus", async () => {
    const response = deferred<SendResult>(); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(() => response.promise); const original = draft();
    render(<Harness initial={original} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    if (original.command.mode === "contextual" && original.command.context.kind === "run_review") original.command.context.filters.search = "changed externally";
    expect(submit.mock.calls[0][0]).toMatchObject({text: "Why Python?", context: {filters: {search: ""}}});
    if (original.command.mode === "contextual" && original.command.context.kind === "run_review") original.command.context.filters.search = "";
    await userEvent.type(screen.getByRole("textbox"), " Follow up");
    await act(async () => response.resolve({outcome: "completed"}));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python? Follow up");
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit.mock.calls[1][0]).toMatchObject({mode: "contextual", context: {focused_candidate_id: null, candidate_ids: [], intent: "explain"}});
  });
  it.each(["failed", "detached"] as const)("retains question after %s send", async outcome => {
    render(<Harness submit={vi.fn(async () => ({outcome, error: {code: "context_stale", message: "Refresh needed", recovery: "Refresh context"}}))}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Refresh needed"));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("clears only the completed draft and does not carry its focus into the next turn", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"})); render(<Harness submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
    await userEvent.type(screen.getByRole("textbox"), "Another question{enter}");
    expect(submit.mock.calls[1][0]).toMatchObject({mode: "contextual", context: {focused_candidate_id: null, candidate_ids: [], intent: "explain"}});
  });
  it("retains a replacement attachment even if submitted text did not change", async () => {
    const pending = deferred<SendResult>(); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(() => pending.promise);
    const initial = draft(); if (initial.command.mode === "contextual" && initial.command.context.kind === "run_review") initial.command.context.candidate_ids = [];
    render(<Harness initial={initial} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    await userEvent.click(screen.getByRole("button", {name: "Ask about Python"}));
    await act(async () => pending.resolve({outcome: "completed"}));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("allows busy staging and typing while blocking concurrent sends", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    render(<Harness source={stream({isStreaming: true, execution: {status: "busy", outcome: "unknown", state_updated_at: null}})} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Ask about Python"}));
    await userEvent.type(screen.getByRole("textbox"), " Follow up{enter}");
    expect(screen.getByRole("textbox")).toHaveValue("Why Python? Follow up");
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText(/waiting for the current work/i)).toBeInTheDocument();
  });
  it("prevents a second send before the parent streaming state updates", async () => {
    const pending = deferred<SendResult>(); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(() => pending.promise);
    render(<Harness submit={submit}/>);
    const button = screen.getByRole("button", {name: "Send message"});
    act(() => {fireEvent.click(button); fireEvent.click(button);});
    expect(submit).toHaveBeenCalledOnce();
    await userEvent.type(screen.getByRole("textbox"), " Follow up{enter}");
    expect(submit).toHaveBeenCalledOnce();
    await act(async () => pending.resolve({outcome: "failed"}));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python? Follow up");
  });
  it("allows an explicit read refresh after detachment while the server is still busy", async () => {
    const reconcile = vi.fn(async () => {});
    render(<Harness source={stream({execution: {status: "busy", outcome: "unknown", state_updated_at: null}, reconcile})}/>);
    expect(screen.getByRole("button", {name: "Send message"})).toBeDisabled();
    await userEvent.click(screen.getByRole("button", {name: "Refresh context"}));
    expect(reconcile).toHaveBeenCalledOnce();
    expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
    expect(screen.getByRole("button", {name: "Send message"})).toBeDisabled();
  });
  it("close live response detaches and explains continued server work", async () => {
    const close = vi.fn(); render(<Harness source={stream({isStreaming: true, closeLiveResponse: close})}/>);
    await userEvent.click(screen.getByRole("button", {name: "Close live response"}));
    expect(close).toHaveBeenCalledOnce();
    expect(screen.getByText(/server work may continue/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("does not claim execution success for an idle observation or a rejected request", async () => {
    render(<Harness submit={vi.fn(async (): Promise<SendResult> => ({outcome: "failed", error: {status: 409, code: "context_stale", message: "Request rejected", recovery: "Refresh context"}}))}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Request rejected"));
    expect(screen.getByText(/execution outcome unknown/i)).toBeInTheDocument();
    expect(screen.queryByText("Work completed")).not.toBeInTheDocument();
  });
  it.each(["completed", "failed"] as const)("shows proven %s execution outcome", outcome => {
    render(<Harness source={stream({execution: {status: "idle", outcome, state_updated_at: null}})}/>);
    expect(screen.getByText(outcome === "completed" ? "Work completed" : "Work failed")).toBeInTheDocument();
  });
  it("uses Unicode message bounds and rejects oversized context without sending", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    const initial = draft(); initial.text = "😀".repeat(8000);
    const {rerender} = render(<WorkspaceConversation stream={stream()} draft={initial} onDraftChange={vi.fn()} onSubmit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).toHaveBeenCalledOnce(); submit.mockClear();
    initial.text += "😀"; rerender(<WorkspaceConversation stream={stream()} draft={initial} onDraftChange={vi.fn()} onSubmit={submit}/>);
    expect(screen.getByRole("button", {name: "Send message"})).toBeDisabled();
    initial.text = "Question"; if (initial.command.mode === "contextual" && initial.command.context.kind === "run_review") initial.command.context.filters.search = "x".repeat(17000);
    rerender(<WorkspaceConversation stream={stream()} draft={initial} onDraftChange={vi.fn()} onSubmit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).not.toHaveBeenCalled();
  });
  it("refreshes only after reconciliation and rebuilds from the newly accepted review", async () => {
    const pending = deferred<void>(); const reconcile = vi.fn(() => pending.promise); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    const source = stream({reconcile}); const {rerender} = render(<Harness source={source} submit={submit}/>);
    await userEvent.click(screen.getByRole("button", {name: "Refresh context"}));
    expect(reconcile).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", {name: "Send message"})).toBeDisabled();
    const refreshed = {...workspaceReviewFixture(), candidate_revision: 8, selection_revision: 9};
    await act(async () => {rerender(<Harness source={{...source, skillReview: refreshed}} submit={submit}/>); pending.resolve();});
    await waitFor(() => expect(screen.getByRole("button", {name: "Send message"})).toBeEnabled());
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({context: expect.objectContaining({expected_candidate_revision: 8, expected_selection_revision: 9})}));
  });
  it("retains attachment and question after failed refresh", async () => {
    render(<Harness source={stream({reconcile: vi.fn(async () => {throw new Error("Read unavailable");})})}/>);
    await userEvent.click(screen.getByRole("button", {name: "Refresh context"}));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Read unavailable"));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("saves before suggesting using the returned saved revision", async () => {
    const saved = deferred<SkillReview>(); vi.mocked(saveSkillReviewDraft).mockReturnValue(saved.promise);
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"})); render(<Harness submit={submit} withController/>);
    await userEvent.click(screen.getByRole("button", {name: "Select Python locally"}));
    await userEvent.click(screen.getByRole("button", {name: "Save draft and suggest"}));
    expect(submit).not.toHaveBeenCalled();
    await act(async () => saved.resolve({...workspaceReviewFixture(), selection_revision: 7, selected_candidate_ids: [workspaceCandidateId]}));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({mode: "contextual", context: expect.objectContaining({intent: "propose_selection", expected_selection_revision: 7, has_unsaved_changes: false})}));
  });
  it("never sends when saving the draft fails", async () => {
    vi.mocked(saveSkillReviewDraft).mockRejectedValue(new Error("Save unavailable")); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async (): Promise<SendResult> => ({outcome: "completed"}));
    render(<Harness submit={submit} withController/>);
    await userEvent.click(screen.getByRole("button", {name: "Save draft and suggest"}));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Save unavailable"));
    expect(submit).not.toHaveBeenCalled(); expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("displays immutable proposals and applies only to the existing local controller draft", async () => {
    const review = {...workspaceReviewFixture(), recommendations: [{id: "suggestion", candidate_revision: 1, base_selection_revision: 2, changes: [{candidate_id: workspaceCandidateId, action: "add" as const, reason: "Supported by postings"}]}]};
    render(<Harness incomingReview={review} withController/>);
    expect(screen.getByText(/Supported by postings/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", {name: "Apply proposal to draft"}));
    expect(screen.getByText(/unsaved shortlist changes are not included/i)).toBeInTheDocument();
    expect(review.selected_candidate_ids).toEqual([]); expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  });
  it("disables stale proposals and protects an explicit exclusion", async () => {
    const review = {...workspaceReviewFixture(), excluded_candidate_ids: [workspaceCandidateId], recommendations: [
      {id: "stale", candidate_revision: 0, base_selection_revision: 2, changes: [{candidate_id: workspaceCandidateId, action: "add" as const, reason: "Old"}]},
      {id: "current", candidate_revision: 1, base_selection_revision: 2, changes: [{candidate_id: workspaceCandidateId, action: "add" as const, reason: "New"}]}]};
    render(<Harness incomingReview={review} withController/>);
    const buttons = screen.getAllByRole("button", {name: "Apply proposal to draft"}); expect(buttons[0]).toBeDisabled();
    await userEvent.click(buttons[1]);
    expect(screen.queryByText(/unsaved shortlist changes are not included/i)).not.toBeInTheDocument();
    expect(saveSkillReviewDraft).not.toHaveBeenCalled();
  });
  it("resets a completed proposal attachment to Explain while preserving a typed follow-up", async () => {
    vi.mocked(saveSkillReviewDraft).mockResolvedValue({...workspaceReviewFixture(), selection_revision: 7});
    const pending = deferred<SendResult>(); const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(() => pending.promise);
    render(<Harness submit={submit} withController/>);
    await userEvent.click(screen.getByRole("button", {name: "Save draft and suggest"}));
    await waitFor(() => expect(submit).toHaveBeenCalledOnce());
    await userEvent.type(screen.getByRole("textbox"), " Follow up");
    await act(async () => pending.resolve({outcome: "completed"}));
    expect(screen.getByRole("textbox")).toHaveValue("Why Python? Follow up");
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit.mock.calls[1][0]).toMatchObject({mode: "contextual", context: {intent: "explain", focused_candidate_id: null, candidate_ids: [], expected_selection_revision: 7}});
  });
  it("includes a truthful unsaved notice when the existing local controller changes after staging", async () => {
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async () => ({outcome: "completed"}));
    render(<Harness submit={submit} withController/>);
    await userEvent.click(screen.getByRole("button", {name: "Select Python locally"}));
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({context: expect.objectContaining({intent: "explain", has_unsaved_changes: true})}));
  });
  it("requires save before sending a selected-only question from a dirty shortlist", async () => {
    const initial = draft(); if (initial.command.mode === "contextual" && initial.command.context.kind === "run_review") initial.command.context.filters.scope = "selected";
    const submit = vi.fn<(command: SendCommand) => Promise<SendResult>>(async () => ({outcome: "completed"}));
    render(<Harness initial={initial} submit={submit} withController/>);
    await userEvent.click(screen.getByRole("button", {name: "Select Python locally"}));
    await userEvent.click(screen.getByRole("button", {name: "Send message"}));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/save/i));
    expect(submit).not.toHaveBeenCalled(); expect(screen.getByRole("textbox")).toHaveValue("Why Python?");
  });
  it("keeps reading position on new output and offers an explicit unread button", async () => {
    const source = stream(); const {rerender} = render(<Harness source={source}/>);
    const transcript = screen.getByRole("log"); const scroll = vi.fn(); Object.defineProperty(transcript, "scrollTo", {value: scroll});
    Object.defineProperties(transcript, {scrollHeight: {configurable: true, value: 1000}, clientHeight: {configurable: true, value: 200}, scrollTop: {configurable: true, writable: true, value: 50}});
    fireEvent.scroll(transcript); scroll.mockClear();
    rerender(<Harness source={{...source, messages: [{id: "reply", role: "agent", agent: "workspace_review", content: "New output", toolCalls: [], isStreaming: true}]}}/>);
    expect(scroll).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", {name: "Show new messages"}));
    expect(scroll).toHaveBeenCalledOnce();
  });
  it("follows new output only when already near the bottom", () => {
    const source = stream(); const {rerender} = render(<Harness source={source}/>); const transcript = screen.getByRole("log"); const scroll = vi.fn();
    Object.defineProperty(transcript, "scrollTo", {value: scroll});
    Object.defineProperties(transcript, {scrollHeight: {configurable: true, value: 1000}, clientHeight: {configurable: true, value: 200}, scrollTop: {configurable: true, writable: true, value: 790}});
    fireEvent.scroll(transcript); scroll.mockClear();
    rerender(<Harness source={{...source, messages: [{id: "reply", role: "agent", content: "New output", toolCalls: [], isStreaming: true}]}}/>);
    expect(scroll).toHaveBeenCalledOnce(); expect(screen.queryByRole("button", {name: "Show new messages"})).not.toBeInTheDocument();
  });
  it("shows safe historical attachment details and warns when current evidence is removed", () => {
    const metadata: ResolvedContextMetadata = {kind: "run_review", version: 1, intent: "explain", run_id: workspaceRunId, candidate_revision: 1, selection_revision: 2, release: null, view: "overview", metric: "frequency", occupation_codes: [], occupations: [], candidate_ids: [workspaceCandidateId], candidate_labels: {[workspaceCandidateId]: "Python"}, filters: null, descriptor_choices: [], insight_kind: null, matching_count: 4, included_count: 1, omitted_count: 3, evidence_included_count: 1, evidence_omitted_count: 2, facts: [{body: "PRIVATE SOURCE BODY"}], coverage: {}, notices: []};
    render(<Harness source={stream({skillReview: {...workspaceReviewFixture(), candidates: []}, messages: [{id: "human", role: "user", content: "Why?", toolCalls: [], isStreaming: false, workspace_context: metadata}]})}/>);
    expect(screen.getByText(/historical attachment/i)).toBeInTheDocument(); expect(screen.getByText(/evidence unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/PRIVATE SOURCE BODY/)).not.toBeInTheDocument();
  });
});

it("keeps only the recent exchange beside the decision and exposes full history on request", async () => {
 const messages = ["Old decision", "Current decision"].map((content,index) => ({id:String(index),role:"agent" as const,content,agent:"supervisor" as const,toolCalls:[],isStreaming:false,timestamp:Date.now()}));
 const props = {stream:stream({messages}),draft:draft(),onDraftChange:vi.fn(),onSubmit:vi.fn(),decision:<p>Choose skills now</p>};
 const {rerender}=render(<WorkspaceConversation {...props} historyOpen={false}/>);
 expect(screen.queryByText("Old decision")).not.toBeInTheDocument();
 expect(screen.getByText("Current decision")).toBeInTheDocument();
 expect(screen.getByText("Choose skills now")).toBeInTheDocument();
 rerender(<WorkspaceConversation {...props} historyOpen/>);
 expect(screen.getByText("Old decision")).toBeInTheDocument();
});
