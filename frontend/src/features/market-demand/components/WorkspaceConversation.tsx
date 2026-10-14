import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { ChatInput } from "@/features/market-demand/components/ChatInput";
import { AgentMessage } from "@/features/market-demand/components/AgentMessage";
import { UserMessage } from "@/features/market-demand/components/UserMessage";
import { AGENT_IDENTITIES } from "@/features/market-demand/agent-config";
import { buildOccupationReferenceContext, buildRunReviewContext, copyWorkspaceContext, isWorkspaceMessageValid, removeContextFocus, validateWorkspaceContext } from "@/features/market-demand/workspace-context";
import type { UseAgentStreamReturn } from "@/features/market-demand/hooks/useAgentStream";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import type { RunReviewContext, SendCommand, SendResult, WorkspaceContext, WorkspaceViewState } from "@/features/market-demand/types";

export interface ConversationDraft {
  text: string;
  command: {mode: "workflow"} | {mode: "contextual"; context: WorkspaceContext};
}
export type WorkspaceConversationStream = Pick<UseAgentStreamReturn, "messages" | "isStreaming" | "isLoadingHistory" | "isRestored" | "currentAgent" | "execution" | "streamError" | "skillReview" | "closeLiveResponse" | "reconcile">;
interface Props {
  stream: WorkspaceConversationStream;
  draft: ConversationDraft;
  onDraftChange: (draft: ConversationDraft) => void;
  onSubmit: (command: SendCommand) => Promise<SendResult>;
  controller?: SkillReviewController;
  decision?: ReactNode;
  historyOpen?: boolean;
  onHistoryOpenChange?: (open: boolean) => void;
}
function contextView(context: RunReviewContext): WorkspaceViewState {
  return {view: context.view, filters: context.filters, focusedCandidateId: context.focused_candidate_id,
    occupationCodes: context.occupation_codes, activeOccupationCode: context.occupation_codes[0] ?? null,
    metric: context.metric, descriptorChoices: context.descriptor_choices, sort: {field: "name", direction: "asc"}, page: 1};
}
function unfocused(context: WorkspaceContext): WorkspaceContext {
  const clean = removeContextFocus(context);
  return {...clean, intent: "explain"};
}
function errorText(error: unknown) {return error instanceof Error ? error.message : "The request failed. Your question has been retained.";}

export function WorkspaceConversation({stream, draft, onDraftChange, onSubmit, controller, decision, historyOpen = false, onHistoryOpenChange}: Props) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detached, setDetached] = useState(false);
  const [unread, setUnread] = useState(false);
  const [refresh, setRefresh] = useState<{command: ConversationDraft["command"]} | null>(null);
  const locked = useRef(false);
  const mounted = useRef(true);
  const latest = useRef({draft, onDraftChange, stream, controller});
  const transcript = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  useLayoutEffect(() => {latest.current = {draft, onDraftChange, stream, controller};});
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const busy = pending || stream.isStreaming || stream.execution.status === "busy" || !!controller?.busy;
  const unavailable = !stream.isRestored || stream.isLoadingHistory;
  const context = draft.command.mode === "contextual" ? draft.command.context : null;
  const unsaved = !!controller?.dirty || (context?.kind === "run_review" && context.has_unsaved_changes);

  const scrollToBottom = () => {
    const node = transcript.current;
    node?.scrollTo?.({top: node.scrollHeight, behavior: "auto"});
    nearBottom.current = true;
    setUnread(false);
  };
  useEffect(() => {
    if (nearBottom.current) scrollToBottom();
    else setUnread(true);
  }, [stream.messages]);

  // Reconciliation publishes React state before this effect consumes it. Reading
  // the accepted review here avoids a pre-await snapshot in the refresh callback.
  useEffect(() => {
    if (!refresh) return;
    const current = latest.current;
    const command = refresh.command;
    if (command.mode === "contextual" && JSON.stringify(current.draft.command) === JSON.stringify(command)) {
      const attached = command.context;
      const review = current.stream.skillReview;
      const result = attached.kind === "occupation_reference"
        ? buildOccupationReferenceContext({release: attached.release, occupationCodes: attached.occupation_codes, elementIds: attached.element_ids, metric: attached.metric})
        : review ? buildRunReviewContext({review, view: contextView(attached), dirty: current.controller?.dirty ?? attached.has_unsaved_changes,
          intent: attached.intent, candidateIds: attached.candidate_ids, insightKind: attached.insight_kind}) : null;
      if (result?.ok) current.onDraftChange({...current.draft, command: {mode: "contextual", context: copyWorkspaceContext(result.context)}});
      else setError(result?.reason === "save_required" ? "Save the shortlist before refreshing selected-only or proposal context." : "This attachment is unavailable. Remove focus or attach current evidence.");
    }
    locked.current = false;
    setPending(false);
    setRefresh(null);
  }, [refresh]);

  const submit = async (suggest = false) => {
    if (locked.current || busy || unavailable || !draft.text.trim() || !isWorkspaceMessageValid(draft.text)) return;
    if (context && !validateWorkspaceContext(context)) {setError("The attachment is invalid or exceeds the context limits. Refresh context."); return;}
    const original: ConversationDraft = {text: draft.text, command: draft.command.mode === "workflow" ? {mode: "workflow"} : {mode: "contextual", context: copyWorkspaceContext(draft.command.context)}};
    locked.current = true;
    setPending(true); setError(null); setDetached(false);
    try {
      let attached = original.command.mode === "contextual" ? original.command.context : null;
      if (!suggest && attached?.kind === "run_review") {
        const currentReview = controller?.review ?? stream.skillReview;
        if (currentReview) {
          if (currentReview.run_id !== attached.run_id) throw new Error("The active review changed. Refresh context before sending.");
          const built = buildRunReviewContext({review: currentReview, view: contextView(attached), dirty: controller?.dirty ?? attached.has_unsaved_changes,
            intent: attached.intent, candidateIds: attached.candidate_ids, insightKind: attached.insight_kind});
          if (!built.ok) throw new Error(built.reason === "save_required" ? "Save the shortlist before sending selected-only or proposal context." : "This attachment is unavailable. Remove focus or attach current evidence.");
          // Only an explicit Refresh context updates staged revision expectations.
          attached = copyWorkspaceContext({...built.context, expected_candidate_revision: attached.expected_candidate_revision,
            expected_selection_revision: attached.expected_selection_revision});
        }
      }
      if (suggest) {
        if (!controller || attached?.kind !== "run_review") throw new Error("A saved skill review is required for suggestions.");
        const saved = await controller.save();
        const built = buildRunReviewContext({review: saved, view: contextView(attached), dirty: false, intent: "propose_selection",
          candidateIds: attached.candidate_ids, insightKind: attached.insight_kind});
        if (!built.ok) throw new Error("The saved review changed. Refresh context before suggesting.");
        attached = copyWorkspaceContext(built.context);
      }
      const command: SendCommand = attached ? {mode: "contextual", text: original.text.trim(), context: attached} : {mode: "workflow", text: original.text.trim()};
      const result = await onSubmit(command);
      if (!mounted.current) return;
      if (result.outcome === "completed") {
        const current = latest.current;
        if (JSON.stringify(current.draft.command) === JSON.stringify(original.command)) {
          current.onDraftChange({text: current.draft.text === original.text ? "" : current.draft.text,
            command: attached ? {mode: "contextual", context: unfocused(attached)} : {mode: "workflow"}});
        }
      } else {
        setError(result.error ? `${result.error.message} ${result.error.recovery}` : result.outcome === "failed" ? "The request failed. Your question has been retained." : "Response detached. The execution outcome is unknown; your question has been retained.");
        setDetached(result.outcome === "detached");
      }
    } catch (cause) {if (mounted.current) setError(errorText(cause));}
    finally {locked.current = false; if (mounted.current) setPending(false);}
  };
  const refreshContext = async () => {
    if (locked.current || pending || stream.isStreaming || controller?.busy || !context) return;
    locked.current = true; setPending(true); setError(null);
    const command: ConversationDraft["command"] = {mode: "contextual", context: copyWorkspaceContext(context)};
    try {
      await stream.reconcile();
      if (mounted.current) setRefresh({command});
    } catch (cause) {
      locked.current = false;
      if (mounted.current) {setError(errorText(cause)); setPending(false);}
    }
  };
  const closeLiveResponse = () => {stream.closeLiveResponse(); setDetached(true);};
  const currentTool = stream.messages.flatMap(message => message.toolCalls).slice().reverse().find(tool => tool.status === "loading");
  const activity = stream.currentAgent ? AGENT_IDENTITIES[stream.currentAgent]?.displayName : "Assistant";
  const shownError = error ?? (stream.streamError ? `${stream.streamError.message} ${stream.streamError.recovery}` : null);
  const review = controller?.review ?? stream.skillReview;

  const shownMessages = decision && !historyOpen ? stream.messages.slice(-1) : stream.messages;
  return <section aria-label="Workspace conversation" className="flex min-h-0 flex-1 flex-col gap-2">
    <div className="shrink-0 space-y-1 px-3 text-sm" aria-live="polite">
      <p hidden={!!decision && !busy}>{stream.isStreaming ? `${activity} · ${currentTool ? `Using ${currentTool.name.replaceAll("_", " ")}` : "Preparing response"}` : stream.execution.status === "busy" ? "Server work is running" : "Conversation ready"}</p>
      <p hidden={!!decision && stream.execution.outcome !== "failed"}>{stream.execution.outcome === "completed" ? "Work completed" : stream.execution.outcome === "failed" ? "Work failed" : "Execution outcome unknown"}</p>
      {busy && <p className="text-xs text-muted-foreground">Waiting for the current work. You can edit or stage a question; send when it is ready.</p>}
      {detached && <p className="text-xs">Live response closed. Server work may continue; refresh to check its state before sending again.</p>}
    </div>
    <div ref={transcript} role="log" aria-label="Conversation messages" aria-live="off" className="min-h-0 flex-1 space-y-3 overflow-y-auto" onScroll={() => {
      const node = transcript.current;
      if (!node) return;
      nearBottom.current = node.scrollHeight - node.clientHeight - node.scrollTop <= 80;
      if (nearBottom.current) setUnread(false);
    }}>
      {shownMessages.map(message => message.role === "agent" ? <AgentMessage key={message.id} message={message}/> : <UserMessage key={message.id} content={message.content} context={message.workspace_context}
        evidenceUnavailable={!!message.workspace_context && message.workspace_context.run_id === review?.run_id && message.workspace_context.candidate_ids.some(id => {
          const candidate = review?.candidates.find(item => item.candidate_id === id);
          return !candidate || candidate.evidence_references.some(item => item.status !== "active");
        })}/>)}
    {controller?.review?.recommendations.map(proposal => {
      const stale = proposal.candidate_revision !== controller.review!.candidate_revision || proposal.base_selection_revision !== controller.review!.selection_revision;
      return <details key={proposal.id} className="mx-3 rounded-md border p-2 text-sm" open>
        <summary>Suggested draft changes{stale ? " · Stale proposal" : ""}</summary>
        {proposal.changes.map((change, index) => <p key={index}>{change.action === "add" ? "Add" : "Remove"} {controller.review!.candidates.find(item => item.candidate_id === change.candidate_id)?.display_name ?? "Unavailable skill"}: {change.reason}</p>)}
        <p className="text-xs text-muted-foreground">Applying changes edits your local draft. Explicit exclusions remain protected; save and review separately.</p>
        <Button type="button" size="sm" variant="outline" disabled={stale || busy || unavailable || controller.disabled || controller.reviewRequired} onClick={() => controller.applyProposal(proposal.id)}>Apply proposal to draft</Button>
      </details>;
    })}
    </div>
    {decision}
    {onHistoryOpenChange && <Button variant="ghost" size="sm" onClick={() => onHistoryOpenChange(!historyOpen)}>{historyOpen ? "Recent conversation" : "Conversation history"}</Button>}
    {unread && <Button type="button" size="sm" variant="outline" onClick={scrollToBottom}>Show new messages</Button>}
    <div className="shrink-0 space-y-1 px-3 pb-1 [&_textarea]:max-h-20">
      {context && <details className="space-y-1 rounded-md border p-2 text-xs" aria-label="Attached context" open={!decision}><summary>Question context · {context.intent === "explain" ? "Explain" : "Suggest changes"}</summary>
        <p>{context.kind === "run_review" ? `Review attachment · ${context.intent === "explain" ? "Explain" : "Suggest changes"}` : `Occupation reference · O*NET ${context.release}`}</p>
        <p>{context.kind === "run_review" ? [...new Set([context.focused_candidate_id, ...context.candidate_ids].filter(Boolean))].map(id => review?.candidates.find(item => item.candidate_id === id)?.display_name ?? id).join(", ") || "No focused skills" : context.element_ids.join(", ") || "No focused descriptors"}</p>
        <p>{context.occupation_codes.join(", ")} · {context.metric}</p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => onDraftChange({...draft, command: {mode: "contextual", context: unfocused(context)}})}>Remove focus</Button>
          <Button type="button" size="sm" variant="outline" disabled={pending || stream.isStreaming || controller?.busy} onClick={() => void refreshContext()}>Refresh context</Button>
          {context.kind === "run_review" && controller && <Button type="button" size="sm" variant="outline" disabled={busy || unavailable || controller.disabled || controller.reviewRequired || !draft.text.trim() || !isWorkspaceMessageValid(draft.text)} onClick={() => void submit(true)}>Save draft and suggest</Button>}
        </div>
      </details>}
      {unsaved && <p className="text-xs">Unsaved shortlist changes are not included</p>}
      {shownError && <p role="alert" className="text-sm text-destructive">{shownError}</p>}
      <ChatInput value={draft.text} onChange={text => onDraftChange({...draft, text})} onSend={() => void submit()} onCloseLiveResponse={closeLiveResponse} isStreaming={stream.isStreaming} disabled={unavailable} sendDisabled={busy}/>
    </div>
  </section>;
}
