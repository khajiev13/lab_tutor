import { useParams, Link } from "react-router-dom";
import { BrainCircuit, Globe2, Loader2, PanelRightOpen, Trash2 } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { isAxiosError } from "axios";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { ChatContainerRoot, ChatContainerContent, ChatContainerScrollAnchor } from "@/components/ui/chat-container";
import { ScrollButton } from "@/components/ui/scroll-button";
import { PromptSuggestion } from "@/components/ui/prompt-suggestion";
import { CourseDetailProvider, useCourseDetail } from "@/features/courses/context/CourseDetailContext";
import { MaterialsReadinessNotice } from "@/features/courses/components/readiness/MaterialsReadinessNotice";
import { DEFAULT_MARKET_DEMAND_COUNTRY, MARKET_DEMAND_COUNTRIES } from "@/features/market-demand/countries";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
import { useWorkspaceNavigationGuard } from "@/features/market-demand/hooks/useWorkspaceNavigationGuard";
import { AgentMessage } from "@/features/market-demand/components/AgentMessage";
import { UserMessage } from "@/features/market-demand/components/UserMessage";
import { ChatInput } from "@/features/market-demand/components/ChatInput";
import { ConnectionStatus } from "@/features/market-demand/components/ConnectionStatus";
import { SelectionCard } from "@/features/market-demand/components/SelectionPanel";
import { SkillSelectionCard } from "@/features/market-demand/components/SkillSelectionCard";
import { SkillEvidencePanel } from "@/features/market-demand/components/SkillEvidencePanel";
import { CompactComparison } from "@/features/market-demand/components/CompactComparison";
import { IntegrationReview } from "@/features/market-demand/components/IntegrationReview";
import { buildRunReviewContext } from "@/features/market-demand/workspace-context";
import { hasItems, detectPendingSelection } from "@/features/market-demand/teacher-decision";
import { currentPriorityAssessment, jobBackedCandidates } from "@/features/market-demand/selection";
import { skillReviewErrorMessage } from "@/features/market-demand/api";
import type { DescriptorChoice, SendCommand, SendResult, WorkspaceContext, WorkspaceQuestion } from "@/features/market-demand/types";

const PROMPT_SUGGESTIONS = [
  "Analyze the job market for this course and find relevant postings",
  "What skills are most demanded in the industry for this curriculum?",
  "Check how well the current curriculum covers market demands",
  "Find skill gaps between our course and industry requirements",
];

function isMaterialsNotReady(cause: unknown) {
  const detail = isAxiosError(cause) ? cause.response?.data?.detail : cause;
  return typeof detail === "object" && detail !== null && "code" in detail && detail.code === "materials_not_ready";
}

export default function MarketDemandPage() {
  const {id} = useParams<{id: string}>();
  const courseId = id ? parseInt(id, 10) : undefined;
  if (!courseId || isNaN(courseId)) return <p className="p-6 text-muted-foreground">Invalid course ID.</p>;
  return <CourseDetailProvider courseId={courseId}><MarketDemandContent key={courseId}/></CourseDetailProvider>;
}

function MarketDemandContent() {
  const {course, courseId, materialsReady, materialsMessage, triggerRefresh, hasChapters, chapterPlanLoading, chapterPlanError, refreshChapterPlan} = useCourseDetail();
  const [countryOverride, setCountryOverride] = useState<string | null>(null);
  const stream = useAgentStream(courseId, countryOverride);
  const {messages, agentState, isStreaming, isLoadingHistory, isRestored, skillReview} = stream;
  const [sending, setSending] = useState(false);
  const [workflowActive, setWorkflowActive] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [inspectId, setInspectId] = useState<string | null>(null);
  const inspectionOrigin = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const focusComposerAfterClose = useRef(false);
  const [draft, setDraft] = useState({text: "", context: null as WorkspaceContext | null});
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const [actionError, setActionError] = useState<string | null>(null);
  const [recoveryRequired, setRecoveryRequired] = useState(false);
  const [checking, setChecking] = useState(false);
  const [executionChecked, setExecutionChecked] = useState(false);
  const [reviewRefreshRequired, setReviewRefreshRequired] = useState(false);
  const [reviewRefreshed, setReviewRefreshed] = useState(false);
  const flight = useRef(false);
  const decisionFlight = useRef(false);
  const resetFlight = useRef(false);
  const generation = useRef(0);
  useEffect(() => () => {generation.current += 1;}, []);
  const controller = useSkillReviewController({courseId,
    review: agentState.run_id && skillReview?.run_id !== agentState.run_id ? null : skillReview,
    onReviewChange: stream.applySkillReview,
    disabled: !isRestored || resetting || workflowActive || confirming || stream.execution.status === "busy" || (isStreaming && !draft.context),
  });
  const review = controller.review;
  const navigation = useWorkspaceNavigationGuard({dirty: controller.dirty, save: controller.save});
  const pending = detectPendingSelection(agentState);
  const selectionKey = pending ? JSON.stringify([pending.kind, pending.items.map(item => item.id)]) : "";
  const [confirmed, setConfirmed] = useState<{key: string; ids: string[]} | null>(null);
  const [editingSelection, setEditingSelection] = useState(false);
  const workPending = sending || isStreaming || stream.execution.status === "busy" || controller.busy || confirming || resetting || checking;
  const unavailable = !isRestored || isLoadingHistory || resetting;
  const workflowDisabled = !materialsReady || unavailable || workPending || recoveryRequired || stream.execution.status !== "idle";
  const mappingReady = hasChapters && !chapterPlanLoading && !chapterPlanError;
  const selectedCountry = countryOverride ?? (agentState.job_search_country_confirmed ? agentState.job_search_country ?? DEFAULT_MARKET_DEMAND_COUNTRY : "");
  const configurationStarted = hasItems(agentState.fetched_jobs) || hasItems(agentState.extracted_skills) || !!review?.candidates.length ||
    Object.values(agentState.source_outcomes ?? {}).some(outcome => outcome.status !== "idle");

  const refreshMaterialsIfNeeded = (cause: unknown) => {
    if (!isMaterialsNotReady(cause)) return false;
    triggerRefresh();
    return true;
  };

  const submit = async (command: SendCommand): Promise<SendResult> => {
    if (!materialsReady || flight.current || workPending || unavailable || (command.mode === "workflow" && workflowDisabled)) {
      return {outcome: "failed", error: {code: "analysis_busy", message: "Wait for the current response or restore the conversation before retrying.", recovery: "Check analysis status."}};
    }
    flight.current = true;
    const current = generation.current;
    setSending(true); setWorkflowActive(command.mode === "workflow"); setActionError(null);
    try {
      const result = await stream.send(command);
      if (generation.current !== current) return result;
      if (result.outcome !== "completed" && !refreshMaterialsIfNeeded(result.error)) {
        if (command.mode === "workflow") setRecoveryRequired(true);
        else setReviewRefreshRequired(true);
        setActionError(result.error?.message ?? "The response ended before its outcome was confirmed. Check analysis status before retrying.");
      }
      return result;
    } catch (cause) {
      if (generation.current === current && !refreshMaterialsIfNeeded(cause)) {
        if (command.mode === "workflow") setRecoveryRequired(true);
        else setReviewRefreshRequired(true);
        setActionError(skillReviewErrorMessage(cause, "The response failed. Your question and choices are retained."));
      }
      throw cause;
    } finally {
      if (generation.current === current) {flight.current = false; setSending(false); setWorkflowActive(false);}
    }
  };
  const sendQuestion = async (text: string) => {
    const original = draftRef.current;
    const current = generation.current;
    const command: SendCommand = original.context ? {mode: "contextual", text, context: original.context} : {mode: "workflow", text};
    try {
      const result = await submit(command);
      if (generation.current === current && result.outcome === "completed") {
        if (draftRef.current === original && original.text.trim() === text.trim()) setDraft({text: "", context: null});
        else if (original.context && draftRef.current.context === original.context) setDraft({...draftRef.current, context: null});
      }
    } catch { /* Keep the exact question and attachment available for retry. */ }
  };
  const confirmChoices = async (ids?: string[]) => {
    if (decisionFlight.current || workflowDisabled || (!pending && !mappingReady)) return;
    decisionFlight.current = true; setConfirming(true); setActionError(null); setReviewRefreshRequired(false);
    const current = generation.current;
    let requestedWorkflow = false;
    try {
      let command: SendCommand;
      if (pending && ids?.length) {
        command = {mode: "workflow", text: `Select these job groups by exact name: ${JSON.stringify(ids)}. Preserve these names; do not convert them to indices.`};
      } else {
        const confirmedReview = await controller.confirmCurrentSelection();
        if (generation.current !== current || confirmedReview.run_id !== review?.run_id) return;
        command = {mode: "workflow", text: "Map the confirmed selected skills to the curriculum and prepare the curriculum fit review. Do not approve or publish."};
      }
      // This operation already owns the flight guard; sending uses the same
      // underlying stream once confirmation has succeeded for this course.
      requestedWorkflow = true; setWorkflowActive(true);
      const result = await stream.send(command);
      if (generation.current !== current) return;
      if (result.outcome === "completed") {
        if (pending && ids) setConfirmed({key: selectionKey, ids});
        else setEditingSelection(false);
      } else if (!refreshMaterialsIfNeeded(result.error)) {
        setRecoveryRequired(true);
        setActionError(result.error?.message ?? "The analysis outcome is unknown. Check status before retrying.");
      }
    } catch (cause) {
      if (generation.current === current && !refreshMaterialsIfNeeded(cause)) {
        setRecoveryRequired(requestedWorkflow);
        setReviewRefreshRequired(!requestedWorkflow);
        setActionError(skillReviewErrorMessage(cause, "Unable to confirm. Your choices are retained."));
      }
    } finally {
      if (generation.current === current) {decisionFlight.current = false; setConfirming(false); setWorkflowActive(false);}
    }
  };
  const checkStatus = async () => {
    if (decisionFlight.current || checking || isStreaming || sending) return;
    decisionFlight.current = true; setChecking(true);
    const current = generation.current;
    try {await stream.reconcile(); if (generation.current === current) setExecutionChecked(true);}
    catch (cause) {if (generation.current === current) setActionError(skillReviewErrorMessage(cause, "Status unavailable. Try checking again."));}
    finally {if (generation.current === current) {decisionFlight.current = false; setChecking(false);}}
  };
  useEffect(() => {
    if (!executionChecked) return;
    setExecutionChecked(false);
    const idle = stream.isRestored && stream.execution.status === "idle";
    setRecoveryRequired(!idle);
    setActionError(idle ? null : stream.execution.status === "busy" ? "The analysis is still running. Check again before retrying." : "The analysis status is unknown. Check again before retrying.");
  }, [executionChecked, stream.isRestored, stream.execution.status]);

  const refreshEvidence = async () => {
    if (workPending || unavailable) return;
    setChecking(true);
    const current = generation.current;
    try {
      await stream.refreshSkillReview();
      if (generation.current === current) {setReviewRefreshed(true); setReviewRefreshRequired(false); setActionError(null);}
    } catch (cause) {if (generation.current === current) setActionError(skillReviewErrorMessage(cause, "Evidence unavailable. Your question and choices are retained."));}
    finally {if (generation.current === current) setChecking(false);}
  };
  useEffect(() => {
    if (!reviewRefreshed) return;
    setReviewRefreshed(false);
    const context = draftRef.current.context;
    if (!context || context.kind !== "run_review" || !review) return;
    const rebuilt = buildRunReviewContext({review, dirty: controller.dirty, intent: "explain", candidateIds: context.candidate_ids,
      insightKind: context.insight_kind, view: {...controller.view, view: context.view, filters: context.filters,
        focusedCandidateId: context.focused_candidate_id, occupationCodes: context.occupation_codes,
        activeOccupationCode: context.occupation_codes[0] ?? null, metric: context.metric, descriptorChoices: context.descriptor_choices}});
    if (rebuilt.ok) setDraft({...draftRef.current, context: rebuilt.context});
    else setActionError("The attached chart evidence changed. Remove the attachment or choose current evidence in Details.");
  }, [reviewRefreshed, review, controller]);

  const clear = async (saveFirst: boolean) => {
    if (resetFlight.current || workPending || (!isRestored && stream.resetRecovery !== "required")) return;
    resetFlight.current = true; setResetting(true); setActionError(null);
    const current = generation.current;
    try {
      if (saveFirst) await controller.save();
      if (generation.current !== current) return;
      await stream.clearConversation();
      if (generation.current !== current) return;
      setDraft({text: "", context: null}); setCountryOverride(null); setConfirmed(null); setEditingSelection(false);
      setDetailsOpen(false); setInspectId(null); setRecoveryRequired(false); setReviewRefreshRequired(false); setClearOpen(false);
    } catch (cause) {if (generation.current === current) setActionError(skillReviewErrorMessage(cause, "Conversation could not be cleared. Your question and choices are retained."));}
    finally {if (generation.current === current) {resetFlight.current = false; setResetting(false);}}
  };
  const askAboutChart = (question: WorkspaceQuestion, descriptorChoices: DescriptorChoice[] = []) => {
    if (!review) return;
    const result = buildRunReviewContext({review, dirty: controller.dirty, intent: "explain", candidateIds: question.candidateIds,
      insightKind: question.insightKind, view: {...controller.view, view: question.occupationCodes?.length ? "demand_importance" : "overview",
        filters: {...controller.view.filters, scope: "all"}, focusedCandidateId: question.candidateIds?.[0] ?? null,
        occupationCodes: question.occupationCodes ?? [], activeOccupationCode: question.occupationCodes?.[0] ?? null,
        metric: question.occupationCodes?.length ? "IM" : "frequency", descriptorChoices}});
    if (!result.ok) {setActionError("This chart evidence is unavailable. Choose current evidence before asking."); return;}
    focusComposerAfterClose.current = true;
    setDetailsOpen(false); setActionError(null); setDraft({text: question.text, context: result.context});
  };
  const focused = review?.candidates.find(candidate => candidate.candidate_id === inspectId);
  const proposal = review?.integration_review;
  const staleFit = !!proposal && !proposal.withdrawal && (proposal.candidate_revision !== review.candidate_revision ||
    proposal.selection_revision !== review.selection_revision || !proposal.review_digest ||
    proposal.items.length !== review.selected_candidate_ids.length || proposal.items.some(item => !review.selected_candidate_ids.includes(item.candidate_id)));
  const showSkills = !!review && (review.candidates.length > 0 || controller.draft.selected_candidate_ids.length > 0) && !pending && (!proposal || editingSelection || staleFit || controller.dirty || controller.reviewRequired);
  const priorityAssessment = review ? currentPriorityAssessment(review) : null;
  const priorityProgress = agentState.skill_priority_status;
  const assessingImportance = priorityProgress?.status === "running" && Date.parse(priorityProgress.deadline_at) > Date.now() &&
    !(priorityAssessment?.assessment_id === priorityProgress.assessment_id && priorityAssessment.status !== "running");
  const sourceFailures = Object.entries(review?.source_outcomes ?? agentState.source_outcomes ?? {}).filter(([, outcome]) => outcome.status === "error" || outcome.status === "partial");
  const shownError = actionError ?? (isMaterialsNotReady(stream.streamError) ? null : stream.error) ?? (reviewRefreshRequired ? controller.error : null);
  return <div aria-label="Teacher evidence workspace" className="absolute inset-0 flex min-w-0 flex-col overflow-hidden bg-background">
    <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
      <Link to={`/courses/${courseId}`} className="min-w-0 text-sm text-muted-foreground">← {course?.title ?? "Course"} · Market Demand Analyst</Link>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={selectedCountry} onValueChange={setCountryOverride} disabled={unavailable || workPending || configurationStarted}>
          <SelectTrigger size="sm" className="h-8 w-[150px] text-xs" aria-label="Market country"><Globe2 className="size-3.5"/><SelectValue placeholder="Choose country"/></SelectTrigger>
          <SelectContent align="end">{MARKET_DEMAND_COUNTRIES.map(country => <SelectItem key={country.value} value={country.value}>{country.label}</SelectItem>)}</SelectContent>
        </Select>
        {!materialsReady && !workPending ? <span className="text-xs text-muted-foreground">Waiting for materials</span> : <ConnectionStatus isStreaming={isStreaming || sending || confirming} hasError={!!shownError}/>}
        {(messages.length > 0 || !!review?.run_id || stream.resetRecovery === "required") && <Button variant="ghost" size="sm" disabled={workPending || (unavailable && stream.resetRecovery !== "required")} onClick={() => setClearOpen(true)}><Trash2 className="size-3.5"/>Clear</Button>}
        {review && isRestored && <Button variant="ghost" size="sm" aria-label="Skills & chart" onClick={() => setDetailsOpen(true)}><PanelRightOpen className="size-4"/>Skills &amp; chart</Button>}
      </div>
    </header>
    <section aria-label="Current action" className="max-h-[45dvh] shrink-0 overflow-y-auto border-b px-4 py-3 sm:max-h-[50dvh]">
      <div className="mx-auto max-w-3xl space-y-2">
          {(workPending || assessingImportance) && !checking && <p role="status" className="text-sm text-muted-foreground"><Loader2 className="mr-2 inline size-4 animate-spin"/>{assessingImportance ? "Assessing skill importance…" : stream.currentAgent ? "The agent is working…" : "Working on your request…"}</p>}
        <h1 className="text-sm font-semibold">{!materialsReady ? "Waiting for course materials" : unavailable ? "Restore the conversation to continue" : recoveryRequired || stream.execution.status === "unknown" ? "Check analysis status before continuing" : workPending ? "Working on your request" : pending ? "Choose job groups to analyze" : showSkills ? "Confirm your skill selection" : proposal ? "Review curriculum fit" : "Ask the agent to analyze relevant jobs"}</h1>
          {pending && <SelectionCard key={selectionKey} title="Select Job Groups"
            subtitle="Choose which groups to analyze for skills"
            items={pending.items} disabled={workflowDisabled} confirmed={confirmed?.key === selectionKey}
            confirmedIds={confirmed?.key === selectionKey ? confirmed.ids : undefined} onConfirm={ids => void confirmChoices(ids)}/>}
          {showSkills && !mappingReady && <div className="space-y-2 rounded-lg border p-3 text-sm">
            {chapterPlanLoading ? <p role="status" className="text-muted-foreground">Checking your chapter plan…</p>
              : chapterPlanError ? <>
                <p role="alert">Could not check your chapter plan. Retry before mapping skills. Your choices are retained.</p>
                <Button size="sm" variant="outline" onClick={refreshChapterPlan}>Retry chapter check</Button>
              </> : <>
                <p>Build a chapter plan before mapping skills to your curriculum. You can keep extracting and reviewing skills here.</p>
                <Button asChild size="sm"><Link to={`/courses/${courseId}/architect?step=build-chapters`}>Build chapter plan</Link></Button>
              </>}
          </div>}
          {showSkills && <SkillSelectionCard controller={controller} disabled={workflowDisabled} confirmDisabled={!mappingReady} onConfirm={() => void confirmChoices()}
            onInspect={(id, element) => {inspectionOrigin.current = element; setInspectId(id);}}/>}
          {review && !pending && <section aria-label="Curriculum fit" className="space-y-2">
            {proposal && !proposal.withdrawal && !showSkills && <Button size="sm" variant="ghost" disabled={workPending || unavailable} onClick={() => setEditingSelection(true)}>Change selection</Button>}
            <div hidden={showSkills}><IntegrationReview courseId={courseId} review={review} onReviewChange={stream.applySkillReview} disabled={!materialsReady || workPending || unavailable}
              publicationDisabled={showSkills || controller.dirty || controller.reviewRequired || recoveryRequired || stream.execution.status !== "idle"}/></div>
          </section>}
        {shownError && <p role="alert" className="text-sm text-destructive">{shownError}</p>}
        {reviewRefreshRequired && !recoveryRequired && <Button variant="outline" size="sm" disabled={workPending || unavailable} onClick={() => void refreshEvidence()}>Refresh current evidence</Button>}
        {!isRestored && !isLoadingHistory && <Button variant="outline" size="sm" onClick={stream.retryRestoration}>Retry restoration</Button>}
        {(recoveryRequired || stream.execution.status !== "idle") && !isStreaming && !sending && <Button variant="outline" size="sm" disabled={checking || confirming || resetting} onClick={() => void checkStatus()}>Check analysis status{checking ? "…" : ""}</Button>}
      </div>
    </section>
    <ChatContainerRoot className="relative flex min-h-0 min-w-0 flex-1 flex-col overscroll-contain">
      <ChatContainerContent role="log" aria-label="Conversation messages" className="mx-auto w-full max-w-3xl space-y-4 px-4 py-6">
        {isLoadingHistory ? <p className="py-12 text-center text-sm text-muted-foreground"><Loader2 className="mr-2 inline size-4 animate-spin"/>Restoring conversation...</p> : <>
          {messages.length === 0 && !review?.candidates.length && !controller.draft.selected_candidate_ids.length && <div className="flex flex-col items-center justify-center py-12 text-center">
            <BrainCircuit className="mb-4 size-8 text-emerald-600"/><h1 className="text-lg font-semibold">Market Demand Analyst</h1>
            <p className="mb-6 mt-1 max-w-md text-sm text-muted-foreground">Analyze job postings, choose relevant skills, and review their fit with your curriculum.</p>
            <div className="flex w-full max-w-lg flex-wrap justify-center gap-2">{PROMPT_SUGGESTIONS.map(text => <PromptSuggestion key={text} className="h-auto max-w-full whitespace-normal text-center" disabled={workflowDisabled} onClick={() => void sendQuestion(text)}>{text}</PromptSuggestion>)}</div>
          </div>}
          {messages.map(message => message.role === "user" ? <UserMessage key={message.id} content={message.content}/> : <AgentMessage key={message.id} message={message}/>)}
          {sourceFailures.length > 0 && !workPending && <details className="text-xs text-muted-foreground"><summary>Some job sources could not finish</summary>{sourceFailures.map(([source, outcome]) => <p key={source} className="mt-1">{source}: {outcome.status}. {outcome.warnings.join(" ")}</p>)}</details>}
        </>}
        <ChatContainerScrollAnchor/>
      </ChatContainerContent>
      <div className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2"><ScrollButton/></div>
    </ChatContainerRoot>
      <div className="shrink-0 bg-background px-4 py-3"><div ref={composerRef} className="mx-auto max-w-3xl">
        {!materialsReady && <div className="mb-2"><MaterialsReadinessNotice courseId={courseId} message={materialsMessage}/></div>}
        {draft.context && <p className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">Chart evidence attached for this question<Button size="sm" variant="ghost" onClick={() => setDraft({...draft, context: null})}>Remove attachment</Button></p>}
        <ChatInput value={draft.text} onChange={text => setDraft({...draft, text})} onSend={text => void sendQuestion(text)} onCloseLiveResponse={stream.closeLiveResponse}
          isStreaming={isStreaming} disabled={unavailable} sendDisabled={!materialsReady || (draft.context ? workPending : workflowDisabled)}/>
      </div></div>
    {review && <CompactComparison courseId={courseId} onCloseAutoFocus={event => {
      if (!focusComposerAfterClose.current) return;
      event.preventDefault(); focusComposerAfterClose.current = false;
      composerRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    }} onReferenceAsk={(context, text) => {focusComposerAfterClose.current = true; setDetailsOpen(false); setActionError(null); setDraft({text, context});}} review={review} candidateIds={controller.draft.selected_candidate_ids.length ? controller.draft.selected_candidate_ids : jobBackedCandidates(review).map(item => item.candidate_id)} open={detailsOpen} onOpenChange={setDetailsOpen} onAsk={askAboutChart}>
      {!pending && <SkillSelectionCard browse controller={controller} disabled={workflowDisabled} onConfirm={() => void confirmChoices()}
        onInspect={(id, element) => {inspectionOrigin.current = element; setInspectId(id);}}/>}
    </CompactComparison>}
    {focused && <SkillEvidencePanel courseId={courseId} candidate={focused} priorityAssessment={priorityAssessment} categoryPriority={review?.categories.find(category => category.category_id === focused.category_id)?.priority} returnFocusTo={inspectionOrigin.current} open onOpenChange={open => {if (!open) setInspectId(null);}}/>}
    <AlertDialog open={clearOpen} onOpenChange={open => {if (!resetting) setClearOpen(open);}}><AlertDialogContent>
      <AlertDialogHeader><AlertDialogTitle>Clear conversation?</AlertDialogTitle><AlertDialogDescription>The current conversation and analysis will be reset. Published skills and saved student paths remain.{controller.dirty ? " Save or discard your current choices before clearing." : ""}</AlertDialogDescription></AlertDialogHeader>
      {shownError && <p role="alert" className="text-sm text-destructive">{shownError}</p>}
      <AlertDialogFooter><AlertDialogCancel disabled={resetting}>Cancel</AlertDialogCancel>
        {controller.dirty && isRestored && <Button disabled={workPending} onClick={() => void clear(true)}>Save and clear</Button>}
        <Button disabled={workPending} onClick={() => void clear(false)}>{controller.dirty ? "Discard and clear" : "Clear conversation"}</Button>
      </AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
    <AlertDialog open={!!navigation.blockedDestination} onOpenChange={open => {if (!open) navigation.stay();}}><AlertDialogContent>
      <AlertDialogHeader><AlertDialogTitle>Unsaved choices</AlertDialogTitle><AlertDialogDescription>Save your choices before leaving, discard them, or stay in this conversation.</AlertDialogDescription></AlertDialogHeader>
      {navigation.error && <p role="alert">{navigation.error}</p>}
      <AlertDialogFooter><Button disabled={navigation.saving} variant="outline" onClick={navigation.stay}>Cancel</Button><Button disabled={navigation.saving} variant="outline" onClick={navigation.discardAndLeave}>Discard</Button><Button disabled={navigation.saving} onClick={() => void navigation.saveAndLeave().catch(() => {})}>Save</Button></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </div>;
}
