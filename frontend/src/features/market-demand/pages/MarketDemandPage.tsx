import { useParams, Link } from "react-router-dom";
import { Globe2, Loader2 } from "lucide-react";
import { useState, useCallback, useEffect, useRef, useMemo, lazy, Suspense, Component, type ReactNode } from "react";

import {Checkbox} from "@/components/ui/checkbox";
import {Input} from "@/components/ui/input";
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
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  CourseDetailProvider,
  useCourseDetail,
} from "@/features/courses/context/CourseDetailContext";
import { getAgentById } from "@/features/agents/config";
import { DEFAULT_MARKET_DEMAND_COUNTRY, MARKET_DEMAND_COUNTRIES } from "@/features/market-demand/countries";
import { useSkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
import { ConnectionStatus } from "@/features/market-demand/components/ConnectionStatus";
import { SelectionCard, type SelectionItem } from "@/features/market-demand/components/SelectionPanel";
import type { AgentState, ChatMessage, SourceConfiguration, JobSourceAvailability, WorkspaceQuestion, WorkspaceContext, SendCommand, SendResult } from "@/features/market-demand/types";

import { SkillReviewPanel } from "@/features/market-demand/components/SkillReviewPanel";
import { JobSourcePicker } from "@/features/market-demand/components/JobSourcePicker";
import { OnetOccupationPicker } from "@/features/market-demand/components/OnetOccupationPicker";
import { fetchJobSources, confirmOnetOccupations } from "@/features/market-demand/api";

import {WorkspaceConversation, type ConversationDraft} from "@/features/market-demand/components/WorkspaceConversation";
import {WorkspaceOverview} from "@/features/market-demand/components/WorkspaceOverview";
import {WorkspaceDataTable} from "@/features/market-demand/components/WorkspaceDataTable";
import {SkillEvidencePanel} from "@/features/market-demand/components/SkillEvidencePanel";
import {OccupationReferencePanel} from "@/features/market-demand/components/OccupationReferencePanel";
import {PipelineStepper} from "@/features/market-demand/components/PipelineStepper";
import {buildWorkspaceData} from "@/features/market-demand/workspace-data";
import {buildRunReviewContext, removeContextFocus} from "@/features/market-demand/workspace-context";
import {useWorkspaceNavigationGuard} from "@/features/market-demand/hooks/useWorkspaceNavigationGuard";
import {cn} from "@/lib/utils";
const WorkspaceCompare = lazy(() => import("@/features/market-demand/components/WorkspaceCompare"));
class ChartViewBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
 state = {failed: false};
 static getDerivedStateFromError() {return {failed: true};}
 render() {return this.state.failed ? <p role="alert">Charts unavailable. Open Data to inspect the evidence and shortlist.</p> : this.props.children;}
}

// ── Pending selection detection ──

// Helpers: treat null, [], and {} as "not set"
function hasItems(v: unknown): boolean {
  if (v == null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return true;
}

type PendingSelection =
  | { kind: "search_queries"; items: SelectionItem[] }
  | { kind: "job_groups"; items: SelectionItem[] }
  | null;

/** Extract quoted search terms from agent message text */
function extractSearchTerms(messages: ChatMessage[]): string[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== "agent") continue;
    const text = msg.content;
    if (!text.includes("Search Terms") && !text.includes("search terms") && !text.includes("search queries")) continue;
    const matches = text.match(/"([^"]+)"/g);
    if (matches && matches.length >= 2) {
      return matches.map((m) => m.replace(/"/g, ""));
    }
    break;
  }
  return [];
}

function detectPendingSelection(state: AgentState, messages: ChatMessage[]): PendingSelection {
  // Search query selection: agent proposed terms but no jobs fetched yet
  if (!hasItems(state.fetched_jobs)) {
    const terms = extractSearchTerms(messages);
    if (terms.length > 0) {
      return {
        kind: "search_queries",
        items: terms.map((term) => ({
          id: term,
          label: term,
        })),
      };
    }
  }

  // Job group selection: groups populated but no selection made yet
  if (hasItems(state.job_groups) && !hasItems(state.selected_jobs)) {
    const groups = state.job_groups!;
    const jobs = state.fetched_jobs;
    if (groups && jobs) {
      const items: SelectionItem[] = Object.entries(groups).map(
        ([name, indices]) => {
          const idxs = indices as number[];
          const companies = [
            ...new Set(
              idxs
                .map((i) => (jobs[i] as Record<string, string>)?.company)
                .filter(Boolean)
            ),
          ].slice(0, 3);
          const tooltipLines = idxs.map((i) => {
            const job = jobs[i] as Record<string, string>;
            const title = job?.title || "Untitled";
            const company = job?.company;
            return company ? `${title} — ${company}` : title;
          });
          return {
            id: name,
            label: name,
            description: companies.join(", "),
            count: idxs.length,
            tooltipLines,
          };
        }
      );
      if (items.length > 0) return { kind: "job_groups", items };
    }
  }

  return null;
}

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
  const agent = getAgentById("market-analyst");
  const [sourceOverride, setSourceOverride] = useState<SourceConfiguration | null>(null);
  const [sourceCatalog, setSourceCatalog] = useState<JobSourceAvailability[]>([]);
  const [catalogCountry, setCatalogCountry] = useState<string | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [occupationError, setOccupationError] = useState<string | null>(null);
  const [occupationConfirming, setOccupationConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const sendPending = useRef(false);
  const [sending, setSending] = useState(false);
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
    pipelineStages,
    skillReview,
    refreshSkillReview,
    applySkillReview,
    send,
    clearConversation,
    error,
  } = stream;

  const skillReviewController = useSkillReviewController({
    courseId, review: skillReview, onReviewChange: applySkillReview,
    disabled: !isRestored || resetting || sending || isStreaming || stream.execution.status === "busy" || occupationConfirming,
  });
  const [pane, setPane] = useState<"workspace" | "conversation">("workspace");
  const [wide, setWide] = useState(false);
  const [unreadConversation, setUnreadConversation] = useState(false);
  const previousMessages = useRef(messages);
  useEffect(() => {
    if (wide || pane === "conversation") setUnreadConversation(false);
    else if (previousMessages.current !== messages) setUnreadConversation(true);
    previousMessages.current = messages;
  }, [messages,wide,pane]);
  const workspaceRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = workspaceRef.current;
    if (!node) return;
    const measure = (width: number) => setWide(width >= 1000);
    measure(node.getBoundingClientRect().width);
    const observer = new ResizeObserver(entries => {for (const entry of entries) if (entry.target === node) measure(entry.contentRect.width);});
    observer.observe(node); return () => observer.disconnect();
  }, []);
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
  const data = review ? buildWorkspaceData(review, skillReviewController.draft, skillReviewController.view) : null;
  const focused = data?.rows.find(row => row.candidateId === skillReviewController.view.focusedCandidateId);
  const stageContext = (context: WorkspaceContext, text: string) => {completedCommand.current = null; workflowExplicit.current = false; setConversationDraft({text, command: {mode: "contextual", context}});};
  const [askError, setAskError] = useState<string | null>(null);
  const handleAsk = (request: WorkspaceQuestion) => {
    if (!review) return;
    const result = buildRunReviewContext({review, dirty: skillReviewController.dirty, intent: "explain", candidateIds: request.candidateIds,
      insightKind: request.insightKind, view: {...skillReviewController.view, focusedCandidateId: request.candidateIds?.[0] ?? null,
        occupationCodes: request.occupationCodes ?? [], metric: request.occupationCodes?.length ? "IM" : "frequency", descriptorChoices: skillReviewController.view.descriptorChoices.filter(choice =>
          request.candidateIds?.includes(choice.candidate_id) && review.candidates.find(item => item.candidate_id === choice.candidate_id)?.onet_associations.some(item => item.evidence.id === choice.evidence_id && request.occupationCodes?.includes(item.evidence.soc_code)))}});
    if (result.ok) {setAskError(null); stageContext(result.context, request.text);}
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
  const workflowDisabled = sourceInputDisabled || workPending;
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
    if (command.mode === "workflow" && sourceInputDisabled) return {outcome: "failed", error: {code: "configuration_unavailable", message: "Choose available sources before starting.", recovery: "Open analysis setup."}};
    const generation = pageGeneration.current;
    sendPending.current = true; setSending(true);
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
      if (pageGeneration.current === generation) {sendPending.current = false; setSending(false);}
    }
  };
  const handleSend = (text: string) => {
    if (sendPending.current || workflowDisabled) return;
    setSetupOpen(false); void handleSubmit({mode: "workflow", text}, false).catch(() => {});
  };

  const handleCountryChange = useCallback((country: string) => {
    occupationGeneration.current += 1;
    setSelectedCountryOverride(country);
  }, []);

  const handleClear = async (saveFirst: boolean) => {
    if (sendPending.current || resetPending.current || isStreaming || stream.execution.status === "busy" || occupationConfirming || skillReviewController.busy) return;
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
      setReferenceOpen(false); setSetupOpen(true); setNewAnalysisOpen(false);
    } catch (cause) {
      if (pageGeneration.current === generation) setResetError(cause instanceof Error ? cause.message : "New analysis could not be started. Current workspace retained.");
    } finally {
      if (pageGeneration.current === generation) {resetPending.current = false; setResetting(false);}
    }
  };

  const handleSearchQueryConfirm = (selectedIds: string[]) => {
    if (sendPending.current || workflowDisabled) return;
    setConfirmedSelection({ kind: "search_queries", ids: selectedIds });
    handleSend(selectedIds.map((t) => `"${t}"`).join(", "));
  };

  const handleJobGroupConfirm = (selectedIds: string[]) => {
    if (sendPending.current || workflowDisabled) return;
    const groups = agentState.job_groups;
    if (!groups) return;
    const groupKeys = Object.keys(groups);
    const indices = selectedIds.map((id) => groupKeys.indexOf(id) + 1);
    setConfirmedSelection({ kind: "job_groups", ids: selectedIds });
    handleSend(indices.join(", "));
  };

  const countrySelectorDisabled = settingsDisabled;

  // Derive pending selection from state + messages
  const pending = detectPendingSelection(agentState, messages);
  const showSelection =
    pending &&
    confirmedSelection?.kind !== pending.kind;

  // Map pending kind to confirm handler and labels
  const selectionConfig: Record<string, {
    title: string;
    subtitle: string;
    onConfirm: (ids: string[]) => void;
  }> = {
    search_queries: {
      title: "Select Search Queries",
      subtitle: "Choose which job search terms to use",
      onConfirm: handleSearchQueryConfirm,
    },
    job_groups: {
      title: "Select Job Groups",
      subtitle: "Choose which groups to analyze for skills",
      onConfirm: handleJobGroupConfirm,
    },
  };

  const metadata = review?.analysis_metadata;
  const started = configurationStarted || !!review?.candidates.length || messages.length > 0;
  const setupVisible = setupOpen || !started;
  const resetDisabled = workPending || !isRestored;
  return (
    <div ref={workspaceRef} aria-label="Teacher evidence workspace" className="absolute inset-0 flex min-w-0 flex-col overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <div>          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to="/courses">Courses</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to={`/courses/${course?.id}`}>{course?.title ?? "Course"}</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{agent?.name ?? "Market Demand Analyst"}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb></div>
        <div className="flex items-center gap-2">
          <ConnectionStatus isStreaming={isStreaming} hasError={!!error}/>
          <Button variant="outline" size="sm" onClick={() => setSetupOpen(!setupVisible)}>Analysis setup</Button>
          {started && <Button variant="ghost" size="sm" disabled={resetDisabled} onClick={() => setNewAnalysisOpen(true)}>New analysis</Button>}
        </div>
      </div>
      {error && <div role="alert" className="flex shrink-0 items-center gap-3 border-b px-4 py-2 text-sm text-destructive"><p>{error}</p>
        {!isRestored && !isLoadingHistory && <Button variant="outline" size="sm" onClick={retryRestoration}>Retry restoration</Button>}
      </div>}
      {!wide && <div role="tablist" aria-label="Workspace panes" className="flex shrink-0 gap-2 border-b p-2">
        <Button role="tab" aria-selected={pane === "workspace"} variant={pane === "workspace" ? "secondary" : "ghost"} onClick={() => setPane("workspace")}>Workspace</Button>
        <Button role="tab" aria-selected={pane === "conversation"} variant={pane === "conversation" ? "secondary" : "ghost"} onClick={() => setPane("conversation")}>Conversation{unreadConversation && <span aria-label="New conversation messages"> •</span>}</Button>
      </div>}
      <div className="flex min-h-0 flex-1">
        <main aria-label="Evidence workspace" className={cn("min-h-0 min-w-0 flex-1 space-y-4 overflow-y-auto p-4", !wide && pane !== "workspace" && "hidden")}>
          {metadata && <section aria-label="Analysis source summary" className="rounded-md border p-3 text-sm">
            <p>Market: {metadata.country ?? "Not reported"} · Job sources: {metadata.job_sources.join(", ") || "None"} · Evidence: {metadata.evidence_sources.join(", ") || "None"}</p>
            <p>O*NET release: {metadata.onet_release ?? "Not used"} · Occupations: {metadata.occupations.map(item => `${item.title} (${item.soc_code})`).join(", ") || "None"}</p>
            <p>Created: {metadata.created_at} · Updated: {metadata.updated_at}</p>
          </section>}
          {setupVisible && <section aria-label="Analysis setup" className="space-y-3 rounded-md border p-3">
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
          {isLoadingHistory ? <p className="flex items-center gap-2"><Loader2 className="size-4 animate-spin"/>Restoring conversation...</p> : !review?.candidates.length && <section className="space-y-3">
            <h2 className="text-lg font-semibold">Market Demand Analyst</h2>
            <p>{review?.run_id ? "No skills are available in this analysis yet. Review source results and teacher checkpoints below." : "Start an analysis to collect job evidence for this course."}</p>
            <Button disabled={workflowDisabled} onClick={() => handleSend("Analyze the job market for this course and find relevant postings")}>Start an analysis</Button>
            <Button variant="outline" onClick={() => setReferenceOpen(!referenceOpen)}>Explore O*NET occupations</Button>
          </section>}
          {referenceOpen && <OccupationReferencePanel courseId={courseId} onAsk={stageContext}/>}
          {Object.keys(review?.source_outcomes ?? agentState.source_outcomes ?? {}).length > 0 && <section aria-label="Source progress" className="space-y-2 text-xs">
            {Object.entries(review?.source_outcomes ?? agentState.source_outcomes ?? {}).map(([source,outcome]) => <div key={source}><p>{source}: {outcome.status}</p><p>{outcome.received_count} received · {outcome.usable_count} usable</p>{outcome.warnings.map((warning,index) => <p key={index}>{warning}</p>)}</div>)}
            <Button variant="outline" size="sm" disabled={resetDisabled} onClick={() => handleSend("Retry all providers and reassess the collected evidence")}>Retry all providers and reassess</Button>
          </section>}
          {showSelection && selectionConfig[pending.kind] && <SelectionCard title={selectionConfig[pending.kind].title} subtitle={selectionConfig[pending.kind].subtitle} items={pending.items} onConfirm={selectionConfig[pending.kind].onConfirm} disabled={workflowDisabled}/>}
          {confirmedSelection && confirmedSelection.kind !== pending?.kind && <SelectionCard title={`Selected: ${selectionConfig[confirmedSelection.kind]?.title ?? confirmedSelection.kind}`} items={confirmedSelection.ids.map(id => ({id,label:id.replace(/_/g," ")}))} onConfirm={() => {}} confirmed confirmedIds={confirmedSelection.ids}/>}
          {askError && <p role="alert">{askError}</p>}
          {data && review?.candidates.length ? <>
            <nav aria-label="Evidence views" className="flex flex-wrap gap-2">
              <Button variant={skillReviewController.view.view === "overview" ? "secondary" : "outline"} onClick={() => skillReviewController.updateView({view:"overview",page:1})}>Overview</Button>
              <Button variant={["demand_importance","occupations"].includes(skillReviewController.view.view) ? "secondary" : "outline"} onClick={() => skillReviewController.updateView({view:"demand_importance",page:1})}>Compare</Button>
              <Button variant={skillReviewController.view.view === "data" ? "secondary" : "outline"} onClick={() => skillReviewController.updateView({view:"data",page:1})}>Data</Button>
            </nav>
            {skillReviewController.view.view === "data" ? <>
              <div className="flex flex-wrap items-center gap-3">
                <Input aria-label="Filter evidence" maxLength={120} value={skillReviewController.view.filters.search} onChange={event => skillReviewController.updateView({filters:{...skillReviewController.view.filters,search:event.target.value},page:1})}/>
                <label className="text-sm">Category <select aria-label="Evidence category" value={skillReviewController.view.filters.category_ids[0] ?? ""} className="rounded-md border bg-background p-2" onChange={event => skillReviewController.updateView({filters:{...skillReviewController.view.filters,category_ids:event.target.value ? [event.target.value] : []},page:1})}><option value="">All categories</option>{review.categories.map(category => <option key={category.category_id} value={category.category_id}>{category.label}</option>)}</select></label>
                <label className="flex items-center gap-2 text-sm"><Checkbox aria-label="Only shortlisted skills" checked={skillReviewController.view.filters.scope === "selected"} onCheckedChange={checked => skillReviewController.updateView({filters:{...skillReviewController.view.filters,scope:checked === true ? "selected" : "all"},page:1})}/>Only shortlisted skills</label>
              </div>
              <WorkspaceDataTable data={data} controller={skillReviewController} onAsk={handleAsk}/>
            </> : <ChartViewBoundary key={skillReviewController.view.view}><Suspense fallback={<p>Loading charts…</p>}>
              {skillReviewController.view.view === "overview" ? <WorkspaceOverview data={data} controller={skillReviewController} onAsk={handleAsk}/> : <WorkspaceCompare data={data} controller={skillReviewController} onAsk={handleAsk}/>}
            </Suspense></ChartViewBoundary>}
            {focused && <section aria-label="Focused evidence" className="space-y-3 rounded-md border p-3"><h2>{focused.label}</h2>
              <SkillEvidencePanel courseId={courseId} candidate={focused.candidate} ratings={focused.ratings} descriptorChoices={skillReviewController.view.descriptorChoices} release={data.scope.release}
                onChooseDescriptor={(evidenceId,occupationCode) => skillReviewController.updateView({descriptorChoices:[
                  ...skillReviewController.view.descriptorChoices.filter(choice => choice.candidate_id !== focused.candidateId || !focused.candidate.onet_associations.some(item => item.evidence.id === choice.evidence_id && item.evidence.soc_code === occupationCode)),
                  ...(evidenceId ? [{candidate_id:focused.candidateId,evidence_id:evidenceId}] : []),
                ]})}/>
              <Button variant="outline" onClick={() => handleAsk({text:`Explain the evidence for ${focused.label}.`,candidateIds:[focused.candidateId],occupationCodes:skillReviewController.view.activeOccupationCode ? [skillReviewController.view.activeOccupationCode] : []})}>Ask about {focused.label}</Button>
              <Button variant="ghost" onClick={() => skillReviewController.updateView({focusedCandidateId:null})}>Close inspector</Button>
            </section>}
          </> : null}
          {review?.run_id && review.candidates.length > 0 && <SkillReviewPanel courseId={courseId} controller={skillReviewController} onRefresh={refreshSkillReview}/>}
          {started && <details><summary>Workflow progress and actions</summary><PipelineStepper stages={pipelineStages}/>
            <Button variant="outline" disabled={resetDisabled} onClick={() => {workflowExplicit.current = true; setConversationDraft({text:"Continue the current workflow",command:{mode:"workflow"}});}}>Stage workflow response</Button>
          </details>}
        </main>
        <aside aria-label="Conversation pane" className={cn("min-h-0 min-w-0 border-l pt-3", wide ? "w-[360px] shrink-0" : "flex-1", !wide && pane !== "conversation" && "hidden")}>
          <WorkspaceConversation stream={{...stream,isRestored: stream.isRestored && !sending && !resetting && (draft.command.mode === "contextual" || !sourceInputDisabled)}} draft={draft} onDraftChange={handleDraftChange} onSubmit={handleSubmit} controller={skillReviewController}/>
        </aside>
      </div>
      <AlertDialog open={newAnalysisOpen} onOpenChange={open => {if (!resetting) setNewAnalysisOpen(open);}}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Start a new analysis?</AlertDialogTitle><AlertDialogDescription>Saved evidence and published skills remain. The current analysis will no longer be resumable here.{skillReviewController.dirty ? " Save or discard your unsaved shortlist before continuing." : ""}</AlertDialogDescription></AlertDialogHeader>
          {resetError && <p role="alert">{resetError}</p>}
          <AlertDialogFooter><AlertDialogCancel disabled={resetting}>Cancel</AlertDialogCancel>
            {skillReviewController.dirty && <Button disabled={resetDisabled} onClick={() => void handleClear(true)}>Save and start new analysis</Button>}
            <Button disabled={resetDisabled} onClick={() => void handleClear(false)}>{skillReviewController.dirty ? "Discard and start new analysis" : "Start new analysis"}</Button>
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
