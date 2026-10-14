import { useParams, Link } from "react-router-dom";
import { Globe2, Loader2 } from "lucide-react";
import { useState, useCallback, useEffect, useRef, useMemo } from "react";

import {Checkbox} from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  CourseDetailProvider,
  useCourseDetail,
} from "@/features/courses/context/CourseDetailContext";
import { DEFAULT_MARKET_DEMAND_COUNTRY, MARKET_DEMAND_COUNTRIES } from "@/features/market-demand/countries";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
import type { SourceConfiguration, JobSourceAvailability, WorkspaceQuestion, DescriptorChoice, WorkspaceContext, SendCommand, SendResult } from "@/features/market-demand/types";

import { JobSourcePicker } from "@/features/market-demand/components/JobSourcePicker";
import { OnetOccupationPicker } from "@/features/market-demand/components/OnetOccupationPicker";
import { fetchJobSources, confirmOnetOccupations } from "@/features/market-demand/api";

import {WorkspaceConversation, type ConversationDraft} from "@/features/market-demand/components/WorkspaceConversation";
import {SkillEvidencePanel} from "@/features/market-demand/components/SkillEvidencePanel";
import {OccupationReferencePanel} from "@/features/market-demand/components/OccupationReferencePanel";
import {buildRunReviewContext, removeContextFocus} from "@/features/market-demand/workspace-context";
import {useWorkspaceNavigationGuard} from "@/features/market-demand/hooks/useWorkspaceNavigationGuard";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SkillChoice } from "@/features/market-demand/components/SkillChoice";
import { CompactComparison } from "@/features/market-demand/components/CompactComparison";
import { IntegrationReview } from "@/features/market-demand/components/IntegrationReview";
import { hasItems, detectPendingSelection, resolveTeacherDecision } from "@/features/market-demand/teacher-decision";

// ── Main Page (wraps with CourseDetailProvider) ──

export default function MarketDemandPage() {
  const { id } = useParams<{ id: string }>();
  const courseId = id ? parseInt(id, 10) : undefined;

  if (!courseId || isNaN(courseId)) {
    return <p className="p-6 text-muted-foreground">Invalid course ID.</p>;
  }

  return (
    <CourseDetailProvider courseId={courseId}>
      <MarketDemandContent key={courseId} />
    </CourseDetailProvider>
  );
}

// ── Content ──

function MarketDemandContent() {
  const { course, courseId } = useCourseDetail();
  const [sourceOverride, setSourceOverride] = useState<SourceConfiguration | null>(null);
  const [sourceCatalog, setSourceCatalog] = useState<JobSourceAvailability[]>([]);
  const [catalogCountry, setCatalogCountry] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [occupationError, setOccupationError] = useState<string | null>(null);
  const [occupationConfirming, setOccupationConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const sendPending = useRef(false);
  const [sending, setSending] = useState(false);
  const [workflowActive, setWorkflowActive] = useState(false);
  const occupationGeneration = useRef(0);
  useEffect(() => () => {
    occupationGeneration.current += 1;
  }, []);
  const [selectedCountryOverride, setSelectedCountryOverride] = useState<string | null>(null);
  const stream = useAgentStream(courseId, selectedCountryOverride, sourceOverride);
  const {
    messages,
    isStreaming,
    isLoadingHistory,
    isRestored,
    retryRestoration,
    agentState,
    skillReview,
    refreshSkillReview,
    applySkillReview,
    send,
    clearConversation,
    error,
  } = stream;

  const skillReviewController = useSkillReviewController({
    courseId, review: agentState.run_id && skillReview?.run_id !== agentState.run_id ? null : skillReview, onReviewChange: applySkillReview,
    disabled: !isRestored || resetting || sending || isStreaming || stream.execution.status === "busy" || occupationConfirming,
  });
  const [editingCurriculum, setEditingCurriculum] = useState(false);
  const [executionChecked, setExecutionChecked] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [inspectId, setInspectId] = useState<string | null>(null);
  const inspectionOrigin = useRef<{courseId: number; element: HTMLElement | null} | null>(null);
  const [choiceDialog, setChoiceDialog] = useState(false);
  const [choicePage, setChoicePage] = useState(1);
  const [choices, setChoices] = useState<{key: string; ids: string[]}>({key: "", ids: []});
  const [actionError, setActionError] = useState<string | null>(null);
  const [reconcileRequired, setReconcileRequired] = useState(false);
  const [decisionBusy, setDecisionBusy] = useState(false);
  const [coverageAfterSave, setCoverageAfterSave] = useState<{run: string | null; candidate: number; selection: number} | null>(null);
  const decisionPending = useRef(false);
  const [setupOpen, setSetupOpen] = useState(false);
  const [referenceOpen, setReferenceOpen] = useState(false);
  const [newAnalysisOpen, setNewAnalysisOpen] = useState(false);
  const resetPending = useRef(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const pageGeneration = useRef(0);
  useEffect(() => () => {pageGeneration.current += 1;}, []);
  const [conversationDraft, setConversationDraft] = useState<ConversationDraft>({text: "", command: {mode: "workflow"}});
  const workflowExplicit = useRef(false);
  const completedCommand = useRef<SendCommand | null>(null);
  const review = skillReviewController.review;
  const minimalContext = () => review ? buildRunReviewContext({review, dirty: skillReviewController.dirty, intent: "explain",
    view: {...skillReviewController.view, view: "overview", focusedCandidateId: null, filters: {category_ids: [], search: "", scope: "all"},
      occupationCodes: [], activeOccupationCode: null, metric: "frequency", descriptorChoices: []}}) : null;
  const defaultContext = minimalContext();
  const draft: ConversationDraft = !workflowExplicit.current && conversationDraft.command.mode === "workflow" && defaultContext?.ok
    ? {...conversationDraft, command: {mode: "contextual", context: defaultContext.context}} : conversationDraft;
  const handleDraftChange = (next: ConversationDraft) => {
    const completed = completedCommand.current;
    completedCommand.current = null;
    if (completed?.mode === "workflow" && next.command.mode === "workflow") workflowExplicit.current = false;
    const justCompleted = completed?.mode === "contextual" && next.command.mode === "contextual" &&
      JSON.stringify(next.command.context) === JSON.stringify({...removeContextFocus(completed.context), intent: "explain"});
    const attached = next.command.mode === "contextual" ? next.command.context : null;
    const ordinary = attached?.kind === "run_review" && attached.intent === "explain" && !attached.focused_candidate_id && !attached.candidate_ids.length && !attached.insight_kind;
    const minimal = minimalContext();
    setConversationDraft(!workflowExplicit.current && minimal?.ok && (next.command.mode === "workflow" || ordinary || justCompleted)
      ? {...next, command: {mode: "contextual", context: {...minimal.context,
        ...(ordinary && !justCompleted ? {expected_candidate_revision: attached.expected_candidate_revision, expected_selection_revision: attached.expected_selection_revision} : {})}}} : next);
  };
  const navigation = useWorkspaceNavigationGuard({dirty: skillReviewController.dirty, save: skillReviewController.save});

  const stageContext = (context: WorkspaceContext, text: string) => {completedCommand.current = null; workflowExplicit.current = false; setConversationDraft({text, command: {mode: "contextual", context}});};
  const [askError, setAskError] = useState<string | null>(null);
  const handleAsk = (request: WorkspaceQuestion, descriptorChoices: DescriptorChoice[] = []) => {
    if (!review) return;
    const result = buildRunReviewContext({review, dirty: skillReviewController.dirty, intent: "explain", candidateIds: request.candidateIds,
      insightKind: request.insightKind, view: {...skillReviewController.view, view: request.occupationCodes?.length ? "demand_importance" : "overview", activeOccupationCode: request.occupationCodes?.[0] ?? null, focusedCandidateId: request.candidateIds?.[0] ?? null,
        occupationCodes: request.occupationCodes ?? [], metric: request.occupationCodes?.length ? "IM" : "frequency", descriptorChoices}});
    if (result.ok) {setCompareOpen(false); setAskError(null); stageContext(result.context, request.text);}
    else setAskError(result.reason === "save_required" ? "Save the shortlist before attaching selected-only evidence." : "This evidence attachment is unavailable. Check the current roles and descriptor choices.");
  };
  const selectedCountry =
    selectedCountryOverride ??
    (agentState.job_search_country_confirmed
      ? agentState.job_search_country ?? DEFAULT_MARKET_DEMAND_COUNTRY
      : "");

  const configuration = useMemo<SourceConfiguration>(() => sourceOverride ?? {
    sources: agentState.sources ?? ["indeed", "linkedin"],
    evidence_sources: agentState.evidence_sources ?? ["jobs"],
    onet_release: agentState.onet_release ?? null,
    onet_occupation_codes: agentState.selected_onet_occupations ?? [],
  }, [
    sourceOverride,
    agentState.sources,
    agentState.evidence_sources,
    agentState.onet_release,
    agentState.selected_onet_occupations,
  ]);
  const configurationRef = useRef(configuration);
  useEffect(() => {
    configurationRef.current = configuration;
  }, [configuration]);
  const handleConfigurationChange = (next: SourceConfiguration) => {
    occupationGeneration.current += 1;
    setSourceOverride(next);
  };
  const catalogMarket = selectedCountry || DEFAULT_MARKET_DEMAND_COUNTRY;
  useEffect(() => {
    if (isLoadingHistory) return;
    const abort = new AbortController();
    setCatalogError(null);
    fetchJobSources(courseId, catalogMarket, abort.signal)
      .then((items) => {
        if (abort.signal.aborted) return;
        setSourceCatalog(items);
        setCatalogCountry(catalogMarket);
      })
      .catch((cause) => {
        if (abort.signal.aborted) return;
        setCatalogError(cause instanceof Error ? cause.message : "Source catalog unavailable");
        setCatalogCountry(null);
      });
    return () => abort.abort();
  }, [courseId, catalogMarket, isLoadingHistory]);
  const configurationStarted = !!review?.candidates.length || hasItems(agentState.extracted_skills) || hasItems(agentState.fetched_jobs) ||
    Object.values(agentState.source_outcomes ?? {}).some((outcome) => outcome.status !== "idle");
  const settingsDisabled = !isRestored || isLoadingHistory || isStreaming || sending || resetting || stream.execution.status === "busy" || skillReviewController.busy ||
    occupationConfirming || configurationStarted;
  const hasUnavailableProvider = configuration.sources.some(
    (source) => !sourceCatalog.some((item) => item.id === source && item.availability === "available")
  );
  const jobConfigurationInvalid = !configurationStarted && (
    catalogCountry !== catalogMarket ||
    !!catalogError ||
    configuration.sources.length === 0 ||
    hasUnavailableProvider
  );
  const onetConfigurationInvalid = !configuration.onet_release ||
    configuration.onet_occupation_codes.length === 0;
  const sourceInputDisabled = !isRestored || isLoadingHistory || occupationConfirming ||
    configuration.evidence_sources.length === 0 ||
    (configuration.evidence_sources.includes("jobs") && jobConfigurationInvalid) ||
    (configuration.evidence_sources.includes("onet") && onetConfigurationInvalid);
  const workPending = sending || isStreaming || stream.execution.status === "busy" || skillReviewController.busy || resetting || occupationConfirming;
  const workflowDisabled = sourceInputDisabled || workPending || reconcileRequired || stream.execution.status === "unknown";
  const handleOccupationConfirm = async (release: string, codes: string[]) => {
    const generation = ++occupationGeneration.current;
    const isCurrent = () => generation === occupationGeneration.current;
    setOccupationError(null);
    setOccupationConfirming(true);
    const runId = skillReview?.run_id ?? agentState.run_id;
    try {
      // Pending settings are validated together by the authoritative chat update.
      // The occupation endpoint only accepts the run's already-persisted config.
      if (runId && !sourceOverride && !selectedCountryOverride) {
        await confirmOnetOccupations(courseId, {
          run_id: runId,
          expected_candidate_revision: skillReview?.candidate_revision ?? agentState.candidate_revision ?? 0,
          release,
          soc_codes: codes,
        });
        if (!isCurrent()) return;
        await refreshSkillReview();
        if (!isCurrent()) return;
      }
      if (isCurrent()) {
        setSourceOverride({
          ...configurationRef.current,
          onet_release: release,
          onet_occupation_codes: codes,
        });
      }
    } catch (cause) {
      if (isCurrent()) {
        setOccupationError(cause instanceof Error ? cause.message : "Occupation confirmation failed");
      }
    } finally {
      if (isCurrent()) setOccupationConfirming(false);
    }
  };

  // Track confirmed selections so the card flips to a summary
  const [confirmedSelection, setConfirmedSelection] = useState<{
    kind: string;
    ids: string[];
  } | null>(null);

  const handleSubmit = async (command: SendCommand, fromComposer = true): Promise<SendResult> => {
    if (sendPending.current || workPending || !isRestored || isLoadingHistory) return {outcome: "failed", error: {code: "workspace_busy", message: "The workspace is already processing an operation.", recovery: "Wait for the current operation to finish."}};
    if (command.mode === "workflow" && (reconcileRequired || stream.execution.status !== "idle")) return {outcome:"failed",error:{code:"execution_unconfirmed",message:"Execution is not confirmed idle.",recovery:"Check workflow status before retrying."}};
    if (command.mode === "workflow" && sourceInputDisabled) return {outcome: "failed", error: {code: "configuration_unavailable", message: "Choose available sources before starting.", recovery: "Open analysis setup."}};
    const generation = pageGeneration.current;
    sendPending.current = true; setSending(true); setWorkflowActive(command.mode === "workflow");
    completedCommand.current = null;
    // Keep an initial workflow attachment unchanged until the conversation's
    // exact submitted-draft completion callback has processed it.
    if (fromComposer && command.mode === "workflow") workflowExplicit.current = true;
    try {
      const result = await send(command);
      if (pageGeneration.current === generation && result.outcome === "completed") {
        if (fromComposer) {
          completedCommand.current = command;
          if (command.mode === "contextual") workflowExplicit.current = false;
        }
        setSetupOpen(false);
      }
      return result;
    } finally {
      if (pageGeneration.current === generation) {sendPending.current = false; setSending(false); setWorkflowActive(false);}
    }
  };
  const handleSend = (text: string) => {
    if (sendPending.current || workflowDisabled) return;
    setConfirmedSelection(null); setSetupOpen(false); void handleSubmit({mode: "workflow", text}, false).catch(() => {});
  };

  const handleCountryChange = useCallback((country: string) => {
    occupationGeneration.current += 1;
    setSelectedCountryOverride(country);
  }, []);

  const handleClear = async (saveFirst: boolean) => {
    if (sendPending.current || resetPending.current || isStreaming || stream.execution.status === "busy" || occupationConfirming || skillReviewController.busy) return;
    if (saveFirst && !isRestored) return;
    resetPending.current = true; setResetting(true); setResetError(null);
    const generation = pageGeneration.current;
    try {
      if (saveFirst) await skillReviewController.save();
      if (pageGeneration.current !== generation) return;
      await clearConversation();
      if (pageGeneration.current !== generation) return;
      occupationGeneration.current += 1;
      setOccupationConfirming(false); setOccupationError(null);
      setConfirmedSelection(null); setSourceOverride(null); setSelectedCountryOverride(null);
      completedCommand.current = null; workflowExplicit.current = false;
      setConversationDraft({text: "", command: {mode: "workflow"}});
      skillReviewController.updateView({view: "overview", focusedCandidateId: null, filters: {category_ids: [], search: "", scope: "all"}, occupationCodes: [], activeOccupationCode: null, metric: "frequency", descriptorChoices: [], page: 1});
      setReferenceOpen(false); setSetupOpen(true); setNewAnalysisOpen(false); setHistoryOpen(true); setActionError(null); setReconcileRequired(false); setEditingCurriculum(false);
    } catch (cause) {
      if (pageGeneration.current === generation) setResetError(cause instanceof Error ? cause.message : "New analysis could not be started. Current workspace retained.");
    } finally {
      if (pageGeneration.current === generation) {resetPending.current = false; setResetting(false);}
    }
  };

  const pending = detectPendingSelection(agentState, messages);
  const choiceKey = pending ? JSON.stringify([pending.kind, pending.items.map(item => item.id)]) : "";
  const chosen = choices.key === choiceKey ? choices.ids : [];
  const decision = workflowActive || decisionBusy || (isStreaming && !review) || (stream.execution.status === "busy" && !isStreaming) ? "working" : resolveTeacherDecision(agentState, messages, review);
  const unresolved = review?.reconciliations?.filter(record => !record.resolved) ?? [];
  const toggleChoice = (id: string, checked: boolean) => setChoices({key: choiceKey, ids: checked ? [...chosen, id] : chosen.filter(value => value !== id)});
  const advance = async () => {
    if (decisionPending.current || workPending || workflowDisabled || reconcileRequired) return;
    decisionPending.current = true; setDecisionBusy(true); setActionError(null);
    const generation = pageGeneration.current;
    let workflowRequested = false;
    try {
      let command: SendCommand;
      if (pending) {
        if (!chosen.length) return;
        command = {mode: "workflow", text: pending.kind === "search_queries" ? chosen.map(term => JSON.stringify(term)).join(", ") : `Select these job groups by exact name: ${JSON.stringify(chosen)}. Preserve these names; do not convert them to indices.`};
      } else {
        const confirmed = await skillReviewController.reviewMappings();
        if (pageGeneration.current !== generation || confirmed.run_id !== review?.run_id) return;
        command = {mode: "workflow", text: "Map the confirmed selected skills to the curriculum and prepare the curriculum fit review. Do not approve or publish."};
      }
      workflowRequested = true;
      const result = await handleSubmit(command, false);
      if (pageGeneration.current !== generation) return;
      if (result.outcome === "completed") {
        if (pending) setConfirmedSelection({kind: pending.kind, ids: chosen});
        setEditingCurriculum(false);
      } else {
        setReconcileRequired(true);
        setActionError(result.error?.message ?? "The workflow outcome is unknown. Check its status before retrying.");
      }
    } catch (cause) {
      if (pageGeneration.current === generation) {setReconcileRequired(workflowRequested); setActionError(cause instanceof Error ? cause.message : "Unable to continue. Your choices are retained.");}
    } finally {
      if (pageGeneration.current === generation) {decisionPending.current = false; setDecisionBusy(false);}
    }
  };
  const checkExecution = async () => {
    if (decisionPending.current) return;
    decisionPending.current = true; setDecisionBusy(true);
    const generation = pageGeneration.current;
    try {await stream.reconcile(); if (pageGeneration.current === generation) setExecutionChecked(true);}
    catch (cause) {if (pageGeneration.current === generation) setActionError(cause instanceof Error ? cause.message : "Status unavailable; check again before retrying.");}
    finally {if (pageGeneration.current === generation) {decisionPending.current = false; setDecisionBusy(false);}}
  };
  useEffect(() => {
    if (!executionChecked) return;
    setExecutionChecked(false);
    const idle = stream.isRestored && stream.execution.status === "idle";
    setReconcileRequired(!idle);
    setActionError(idle ? null : stream.execution.status === "busy" ? "The analysis is still running. Check again before retrying." : "Execution status is unknown. Check again before retrying.");
  }, [executionChecked, stream.isRestored, stream.execution.status]);
  const acknowledgeEvidence = async () => {
    if (decisionPending.current || workPending) return;
    decisionPending.current = true; setDecisionBusy(true); setActionError(null);
    const generation = pageGeneration.current;
    try {
      const saved = skillReviewController.dirty ? await skillReviewController.save() : review;
      if (pageGeneration.current === generation && saved) setCoverageAfterSave({run:saved.run_id,candidate:saved.candidate_revision,selection:saved.selection_revision});
    } catch (cause) {
      if (pageGeneration.current === generation) {setActionError(cause instanceof Error ? cause.message : "Evidence acknowledgement failed");decisionPending.current=false;setDecisionBusy(false);}
    }
  };
  // Save can replace the controller revision. Acknowledge only from the render
  // that has accepted that saved snapshot, never through the old action closure.
  useEffect(() => {
    if (!coverageAfterSave) return;
    const expected=coverageAfterSave;
    setCoverageAfterSave(null);
    const generation=pageGeneration.current;
    const action=review?.run_id===expected.run && review.candidate_revision===expected.candidate && review.selection_revision===expected.selection
      ? skillReviewController.acknowledgeAvailableEvidence() : Promise.reject(new Error("The review changed. Check the current evidence before acknowledging it."));
    void action.catch(cause=>{if(pageGeneration.current===generation)setActionError(cause instanceof Error ? cause.message : "Evidence acknowledgement failed");})
      .finally(()=>{if(pageGeneration.current===generation){decisionPending.current=false;setDecisionBusy(false);}});
  }, [coverageAfterSave, review, skillReviewController]);
  const choiceRows = (all: boolean) => pending?.items.slice(all ? (choicePage - 1) * 10 : 0, all ? choicePage * 10 : 5).map(item => <label key={item.id} className="flex min-h-9 items-center gap-3 rounded-md border px-3 py-2 text-sm">
    <Checkbox aria-label={item.label} checked={chosen.includes(item.id)} disabled={workflowDisabled || decisionBusy} onCheckedChange={checked => toggleChoice(item.id, checked === true)}/>
    <span className="min-w-0 flex-1 truncate">{item.label}</span>{item.count !== undefined && <span className="text-xs text-muted-foreground">{item.count} jobs</span>}
  </label>);
  const countrySelectorDisabled = settingsDisabled;
  const metadata = review?.analysis_metadata;
  const started = configurationStarted || !!review?.candidates.length || messages.length > 0;
  const resetRecoveryRequired = stream.resetRecovery === "required";
  const resetDisabled = workPending || decisionBusy || isLoadingHistory || (!isRestored && !resetRecoveryRequired);
  const step = pending?.kind === "search_queries" ? "Confirm search terms" : pending?.kind === "job_groups" ? "Choose job groups" : review?.integration_review ? "Review curriculum fit" : review?.candidates.length ? "Choose skills" : "Getting started";
  const focused = review?.candidates.find(candidate => candidate.candidate_id === inspectId);
  const selectionWaiting = !!pending && confirmedSelection?.kind === pending.kind && confirmedSelection.ids.every(id => chosen.includes(id));
  const gates = skillReviewController.reviewRequired || skillReviewController.needsEvidenceAcknowledgement || unresolved.length > 0;
  const curriculum = decision === "curriculum";
  const showSkillEditor = decision === "skills" || (curriculum && (editingCurriculum || skillReviewController.dirty || skillReviewController.reviewRequired));
  const sourceFailures = Object.entries(review?.source_outcomes ?? agentState.source_outcomes ?? {}).filter(([,outcome]) => outcome.status === "error" || outcome.status === "partial");
  const noCandidates = started && !review?.candidates.length && !pending;
  const decisionContent = <div aria-label="Current teacher decision" className="shrink-0 space-y-2 px-3">
    {isLoadingHistory ? <p><Loader2 className="inline size-4 animate-spin"/> Restoring conversation...</p> : decision === "working" ? <p className="text-sm">{workPending || decisionBusy ? "Working on your current decision… You can keep typing below." : started ? "No skills are ready yet. Review the collection result below." : "Start an analysis to collect job evidence for this course."}</p> : null}
    {!started && <Button disabled={workflowDisabled} onClick={() => handleSend("Analyze the job market for this course and find relevant postings")}>Start an analysis</Button>}
    {sourceInputDisabled && !isLoadingHistory && <div role="alert" className="text-sm">{catalogError ? `Source catalog unavailable: ${catalogError}` : "Review analysis setup before continuing."} <Button size="sm" variant="outline" onClick={() => {setHistoryOpen(true); setSetupOpen(true);}}>Open analysis setup</Button></div>}
    {(sourceFailures.length > 0 || (noCandidates && !workPending && !isLoadingHistory)) && <section aria-label="Source recovery" className="flex items-center gap-2 text-xs">
      <div role="alert" className="min-w-0 flex-1">{sourceFailures.length ? <p>{sourceFailures.map(([source,outcome]) => `${source}: ${outcome.status === "error" ? "collection failed" : "collection incomplete"}`).join("; ")}. Retry collection; details are in History.</p> : <p>No usable skills were collected. Retry sources or change setup in a new analysis.</p>}</div>
      <Button size="sm" variant="outline" className="shrink-0" disabled={workflowDisabled || decisionBusy} onClick={() => handleSend("Retry all providers and reassess the collected evidence")}>Retry failed sources</Button>
    </section>}
    {pending && decision !== "working" && <>
      <p className="text-sm">{pending.kind === "search_queries" ? "Which search terms should we use?" : "Which job groups should we analyze?"}</p>
      <div className="space-y-1">{choiceRows(false)}</div>
      <div className="flex gap-2"><Button size="sm" variant="ghost" onClick={() => setChoices({key:choiceKey,ids:pending.items.map(item=>item.id)})}>Select all</Button>
      {pending.items.length > 5 && <Button size="sm" variant="outline" onClick={() => {setChoicePage(1);setChoiceDialog(true);}}>Review all {pending.items.length}</Button>}<span className="self-center text-xs">{chosen.length} chosen</span></div>
      {selectionWaiting ? <p className="text-sm">Your choice was sent. Waiting for the next decision.</p> : <Button disabled={workflowDisabled || !chosen.length || reconcileRequired} onClick={() => void advance()}>Continue</Button>}
    </>}
    {review && !pending && <div className="space-y-2">
      {curriculum && <div className="flex items-center gap-2"><Button size="sm" variant="outline" disabled={workPending} onClick={() => setEditingCurriculum(true)}>Edit skills</Button>{showSkillEditor && !skillReviewController.dirty && !skillReviewController.reviewRequired && <Button size="sm" variant="ghost" onClick={() => setEditingCurriculum(false)}>Back to curriculum fit</Button>}</div>}
      {showSkillEditor && <><SkillChoice controller={skillReviewController} visibleLimit={reconcileRequired || skillReviewController.reviewRequired || !!skillReviewController.error || unresolved.length > 0 ? 3 : 5} onInspect={(id, element) => {inspectionOrigin.current = {courseId, element}; setInspectId(id);}} secondaryAction={<Button size="sm" variant="ghost" onClick={() => setCompareOpen(true)}>Compare skills</Button>}/></>}
      {skillReviewController.needsEvidenceAcknowledgement && <div role="alert" className="flex flex-col items-start gap-2 text-xs sm:flex-row sm:items-center"><p className="min-w-0 flex-1">Some job evidence is incomplete. {review.extraction_coverage.assessed_postings !== undefined && review.extraction_coverage.selected_postings !== undefined ? `${review.extraction_coverage.assessed_postings} of ${review.extraction_coverage.selected_postings} postings assessed.` : "Assessment counts unavailable."} Review before continuing.</p><Button size="sm" className="shrink-0" disabled={workPending || skillReviewController.reviewRequired || unresolved.length > 0} onClick={() => void acknowledgeEvidence()}>Acknowledge available evidence</Button></div>}
      {unresolved.length > 0 && <section aria-label="Candidate reconciliation" className="space-y-1 text-sm"><p role="alert">Review changed choices before continuing ({unresolved.length}).</p><div className="max-h-28 space-y-1 overflow-y-auto">{unresolved.map(record => <label key={record.reconciliation_id} className="flex items-center gap-2"><Checkbox aria-label={`Acknowledge reconciliation for ${record.previous_candidates.map(item=>item.display_name).join(", ")}`} checked={skillReviewController.pendingReconciliationIds.includes(record.reconciliation_id)} disabled={workPending} onCheckedChange={checked=>skillReviewController.acknowledgeReconciliation(record.reconciliation_id,checked===true)}/>{record.previous_candidates.map(item=>item.display_name).join(", ")} · {record.reason.replaceAll("_", " ")}</label>)}</div><Button disabled={workPending || skillReviewController.reviewRequired || !unresolved.every(record=>skillReviewController.pendingReconciliationIds.includes(record.reconciliation_id))} onClick={()=>void skillReviewController.save().catch(()=>{})}>Save reviewed choices</Button></section>}
      {(decision === "skills" || curriculum) && !skillReviewController.needsEvidenceAcknowledgement && unresolved.length === 0 && <Button variant={curriculum && !showSkillEditor ? "outline" : "default"} disabled={workflowDisabled || gates || !skillReviewController.draft.selected_candidate_ids.length || reconcileRequired} onClick={() => void advance()}>{curriculum ? "Remap skills" : "Continue"}</Button>}
      <div hidden={decision === "working" || (curriculum && showSkillEditor)}><IntegrationReview courseId={courseId} review={review} onReviewChange={skillReviewController.onReviewChange} disabled={workPending} publicationDisabled={skillReviewController.dirty || gates}/></div>
    </div>}
    {actionError && <p role="alert" className="text-sm text-destructive">{actionError} Your choices are retained.</p>}
    {askError && <p role="alert" className="text-sm text-destructive">{askError}</p>}
    {reconcileRequired && <Button disabled={decisionBusy || isStreaming} onClick={() => void checkExecution()}>Check workflow status before retrying</Button>}
    {stream.execution.status !== "idle" && !isStreaming && !reconcileRequired && <Button variant="outline" onClick={() => void checkExecution()}>Check workflow status</Button>}
  </div>;
  return (<div aria-label="Teacher evidence workspace" className="flex h-dvh min-w-0 flex-col overflow-hidden bg-background">
    <header className="flex shrink-0 items-center justify-between px-5 py-3"><Link to={`/courses/${courseId}`} className="text-sm text-muted-foreground">← {course?.title ?? "Course"}</Link><ThemeToggle/></header>
    <main aria-label="Evidence workspace" className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col overflow-y-auto px-2 pb-3 sm:overflow-hidden sm:px-6">
      <Button variant="ghost" size="sm" className="mb-1 self-start text-xs text-muted-foreground" onClick={() => setHistoryOpen(true)}>{step} · History and setup</Button>
      {error && <div role="alert" className="shrink-0 text-sm text-destructive">{error}{!isRestored && !isLoadingHistory && <Button variant="outline" size="sm" onClick={retryRestoration}>Retry restoration</Button>}</div>}
      {resetRecoveryRequired && <Button disabled={resetDisabled} onClick={() => setNewAnalysisOpen(true)}>Retry reset</Button>}
      <WorkspaceConversation stream={{...stream,isRestored:stream.isRestored && !resetting && (draft.command.mode === "contextual" || !sourceInputDisabled)}} draft={draft} onDraftChange={handleDraftChange} onSubmit={handleSubmit} controller={skillReviewController} decision={decisionContent}/>
    </main>
    <Dialog open={historyOpen} onOpenChange={setHistoryOpen}><DialogContent className="max-h-[85dvh] overflow-y-auto" maxWidthClassName="sm:max-w-2xl"><DialogHeader><DialogTitle>History and analysis setup</DialogTitle><DialogDescription>Previous decisions, source details and recovery actions.</DialogDescription></DialogHeader>
      <div className="flex gap-2"><Button size="sm" variant="outline" onClick={()=>setSetupOpen(!setupOpen)}>Analysis setup</Button><Button size="sm" variant="ghost" disabled={resetDisabled} onClick={()=>{setHistoryOpen(false);setNewAnalysisOpen(true);}}>New analysis</Button></div>
          {(setupOpen || !started) && <section aria-label="Analysis setup" className="space-y-3 rounded-md border p-3">
          <Select
            value={selectedCountry}
            onValueChange={handleCountryChange}
            disabled={countrySelectorDisabled}
          >
            <SelectTrigger
              size="sm"
              className="h-8 w-[150px] text-xs"
              aria-label="Market country"
            >
              <Globe2 className="size-3.5" />
              <SelectValue placeholder="Choose country" />
            </SelectTrigger>
            <SelectContent align="end">
              {MARKET_DEMAND_COUNTRIES.map((country) => (
                <SelectItem key={country.value} value={country.value}>
                  {country.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        <JobSourcePicker
          sources={configuration.sources}
          evidenceSources={configuration.evidence_sources}
          catalog={sourceCatalog}
          disabled={settingsDisabled}
          onSourcesChange={(sources) => handleConfigurationChange({ ...configuration, sources })}
          onEvidenceChange={(evidence_sources) => handleConfigurationChange({ ...configuration, evidence_sources })}
        />
        {catalogError && (
          <p role="alert" className="text-xs text-destructive">
            Source catalog unavailable: {catalogError}
          </p>
        )}
        {!configurationStarted && configuration.evidence_sources.includes("jobs") && hasUnavailableProvider && (
          <p className="text-xs text-muted-foreground">
            Remove unavailable providers and explicitly select an available provider for this market.
          </p>
        )}
        {configurationStarted && (
          <p className="text-xs text-muted-foreground">
            Source settings are fixed for this analysis. Start a new analysis to change sources,
            market, or occupations.
          </p>
        )}
        {configuration.evidence_sources.includes("onet") && (
          <OnetOccupationPicker
            courseId={courseId}
            release={configuration.onet_release}
            selectedCodes={configuration.onet_occupation_codes}
            disabled={settingsDisabled}
            onReleaseChange={(onet_release) =>
              handleConfigurationChange({ ...configuration, onet_release, onet_occupation_codes: [] })
            }
            onConfirm={handleOccupationConfirm}
          />
        )}
        {occupationError && <p role="alert" className="text-xs text-destructive">{occupationError}</p>}

          </section>}

      {metadata && <section aria-label="Analysis source summary" className="text-xs">Market: {metadata.country ?? "Not reported"} · Job sources: {metadata.job_sources.join(", ")} · O*NET release: {metadata.onet_release ?? "Not used"} · {metadata.occupations.map(item=>item.title).join(", ")}</section>}
      <section aria-label="Source progress" className="space-y-2 text-xs">{Object.entries(review?.source_outcomes ?? agentState.source_outcomes ?? {}).map(([source,outcome])=><div key={source}>{source}: {outcome.status} · {outcome.usable_count}/{outcome.received_count} usable{outcome.warnings.map((warning,index)=><p key={index}>{warning}</p>)}</div>)}<Button variant="outline" size="sm" disabled={resetDisabled || !isRestored} onClick={()=>{setHistoryOpen(false);handleSend("Retry all providers and reassess the collected evidence");}}>Retry all providers and reassess</Button></section>
      <Button variant="outline" size="sm" onClick={()=>setReferenceOpen(!referenceOpen)}>Explore O*NET occupations</Button>{referenceOpen && <OccupationReferencePanel courseId={courseId} onAsk={(context,text)=>{setHistoryOpen(false);stageContext(context,text);}}/>}
      <Button variant="outline" size="sm" disabled={resetDisabled || !isRestored} onClick={()=>{workflowExplicit.current=true;setConversationDraft({text:"Continue the current workflow",command:{mode:"workflow"}});setHistoryOpen(false);}}>Stage workflow response</Button>
      <div className="space-y-3" aria-label="Full conversation history">{messages.map(message=><div key={message.id} className="whitespace-pre-wrap text-sm"><strong>{message.role === "agent" ? "Assistant" : "You"}</strong><p>{message.content}</p></div>)}</div>
    </DialogContent></Dialog>
    <Dialog open={choiceDialog} onOpenChange={setChoiceDialog}><DialogContent className="max-h-[85dvh] overflow-y-auto"><DialogHeader><DialogTitle>{step}</DialogTitle><DialogDescription>All choices are retained across pages.</DialogDescription></DialogHeader><div className="space-y-2">{choiceRows(true)}</div><div className="flex justify-between"><Button disabled={choicePage===1} onClick={()=>setChoicePage(choicePage-1)}>Previous page</Button><span>Page {choicePage}</span><Button disabled={choicePage*10 >= (pending?.items.length ?? 0)} onClick={()=>setChoicePage(choicePage+1)}>Next page</Button></div></DialogContent></Dialog>
    {review && <CompactComparison review={review} candidateIds={skillReviewController.draft.selected_candidate_ids} open={compareOpen} onOpenChange={setCompareOpen} onAsk={handleAsk}/>}
    {focused && <SkillEvidencePanel courseId={courseId} candidate={focused} returnFocusTo={inspectionOrigin.current?.courseId === courseId ? inspectionOrigin.current.element : null} open onOpenChange={open=>{if(!open)setInspectId(null);}}/>}
      <AlertDialog open={newAnalysisOpen} onOpenChange={open => {if (!resetting) setNewAnalysisOpen(open);}}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Start a new analysis?</AlertDialogTitle><AlertDialogDescription>Saved evidence and published skills remain. The current analysis will no longer be resumable here.{skillReviewController.dirty ? isRestored ? " Save or discard your unsaved shortlist before continuing." : " Retrying reset will discard your unsaved shortlist, which cannot be saved until restoration succeeds." : ""}</AlertDialogDescription></AlertDialogHeader>
          {resetError && <p role="alert">{resetError}</p>}
          <AlertDialogFooter><AlertDialogCancel disabled={resetting}>Cancel</AlertDialogCancel>
            {skillReviewController.dirty && isRestored && <Button disabled={resetDisabled} onClick={() => void handleClear(true)}>Save and start new analysis</Button>}
            <Button disabled={resetDisabled} onClick={() => void handleClear(false)}>{resetRecoveryRequired ? "Confirm reset retry" : skillReviewController.dirty ? "Discard and start new analysis" : "Start new analysis"}</Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={!!navigation.blockedDestination} onOpenChange={open => {if (!open) navigation.stay();}}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Unsaved shortlist</AlertDialogTitle><AlertDialogDescription>Save your draft before leaving, discard it, or stay in this workspace.</AlertDialogDescription></AlertDialogHeader>
          {navigation.error && <p role="alert">{navigation.error}</p>}
          <AlertDialogFooter><Button disabled={navigation.saving} variant="outline" onClick={navigation.stay}>Cancel</Button><Button disabled={navigation.saving} variant="outline" onClick={navigation.discardAndLeave}>Discard</Button><Button disabled={navigation.saving} onClick={() => void navigation.saveAndLeave().catch(() => {})}>Save</Button></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
