import { useParams, Link } from "react-router-dom";
import { BrainCircuit, Globe2, Loader2, PanelRightClose, PanelRightOpen, Trash2 } from "lucide-react";
import { useState, useCallback } from "react";

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
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  ChatContainerRoot,
  ChatContainerContent,
  ChatContainerScrollAnchor,
} from "@/components/ui/chat-container";
import { ScrollButton } from "@/components/ui/scroll-button";
import { PromptSuggestion } from "@/components/ui/prompt-suggestion";
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
import { DEFAULT_MARKET_DEMAND_COUNTRY, MARKET_DEMAND_COUNTRIES } from "../countries";
import { useAgentStream } from "../hooks/useAgentStream";
import { AgentMessage } from "../components/AgentMessage";
import { UserMessage } from "../components/UserMessage";
import { ChatInput } from "../components/ChatInput";
import { ConnectionStatus } from "../components/ConnectionStatus";
import { StatePanel } from "../components/StatePanel";
import { SelectionCard, type SelectionItem } from "../components/SelectionPanel";
import type { AgentState, ChatMessage, SkillEntry } from "../types";

const PROMPT_SUGGESTIONS = [
  "Analyze the job market for this course and find relevant postings",
  "What skills are most demanded in the industry for this curriculum?",
  "Check how well the current curriculum covers market demands",
  "Find skill gaps between our course and industry requirements",
];

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
  | { kind: "skill_categories"; items: SelectionItem[] }
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

  // Skill category selection: skills extracted but no mapping yet
  if (hasItems(state.extracted_skills) && !hasItems(state.curriculum_mapping)) {
    const skills = state.extracted_skills!;
    const byCategory = new Map<string, SkillEntry[]>();
    for (const s of skills) {
      const list = byCategory.get(s.category) || [];
      list.push(s);
      byCategory.set(s.category, list);
    }

    const items: SelectionItem[] = Array.from(byCategory.entries())
      .sort((a, b) => b[1].length - a[1].length)
      .map(([category, catSkills]) => ({
        id: category,
        label: category.replace(/_/g, " "),
        description: catSkills
          .slice(0, 2)
          .map((s) => s.name)
          .join(", "),
        badge: `${catSkills.length} skills`,
      }));

    return { kind: "skill_categories", items };
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
      <MarketDemandContent />
    </CourseDetailProvider>
  );
}

// ── Content ──

function MarketDemandContent() {
  const { course, courseId } = useCourseDetail();
  const agent = getAgentById("market-analyst");
  const [selectedCountryOverride, setSelectedCountryOverride] = useState<string | null>(null);
  const {
    messages,
    isStreaming,
    isLoadingHistory,
    agentState,
    pipelineStages,
    send,
    stop,
    clearConversation,
    error,
  } = useAgentStream(courseId, selectedCountryOverride);

  const [panelOpen, setPanelOpen] = useState(true);
  const selectedCountry =
    selectedCountryOverride ??
    agentState.job_search_country ??
    DEFAULT_MARKET_DEMAND_COUNTRY;

  // Track confirmed selections so the card flips to a summary
  const [confirmedSelection, setConfirmedSelection] = useState<{
    kind: string;
    ids: string[];
  } | null>(null);

  const handleSend = (text: string) => {
    send(text);
  };

  const handleCountryChange = useCallback((country: string) => {
    setSelectedCountryOverride(country);
  }, []);

  const handleClear = useCallback(async () => {
    await clearConversation();
    setConfirmedSelection(null);
  }, [clearConversation]);

  const handleSearchQueryConfirm = useCallback(
    (selectedIds: string[]) => {
      setConfirmedSelection({ kind: "search_queries", ids: selectedIds });
      send(selectedIds.map((t) => `"${t}"`).join(", "));
    },
    [send]
  );

  const handleJobGroupConfirm = useCallback(
    (selectedIds: string[]) => {
      const groups = agentState.job_groups;
      if (!groups) return;
      const groupKeys = Object.keys(groups);
      const indices = selectedIds.map((id) => groupKeys.indexOf(id) + 1);
      setConfirmedSelection({ kind: "job_groups", ids: selectedIds });
      send(indices.join(", "));
    },
    [agentState.job_groups, send]
  );

  const handleSkillConfirm = useCallback(
    (selectedIds: string[]) => {
      setConfirmedSelection({ kind: "skill_categories", ids: selectedIds });
      send(selectedIds.join(", "));
    },
    [send]
  );

  const isEmpty = messages.length === 0 && !isLoadingHistory;
  const hasFetchedJobs = hasItems(agentState.fetched_jobs);
  const countrySelectorDisabled = isLoadingHistory || isStreaming || hasFetchedJobs;

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
    skill_categories: {
      title: "Select Skill Categories",
      subtitle: "Choose categories to map against your curriculum",
      onConfirm: handleSkillConfirm,
    },
  };

  return (
    <div className="absolute inset-0 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3 shrink-0">
        <div className="flex items-center gap-3">
          <Breadcrumb>
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
          </Breadcrumb>
        </div>

        <div className="flex items-center gap-2">
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
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              {MARKET_DEMAND_COUNTRIES.map((country) => (
                <SelectItem key={country.value} value={country.value}>
                  {country.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ConnectionStatus isStreaming={isStreaming} hasError={!!error} />
          {messages.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={isStreaming}
                  className="text-muted-foreground gap-1.5 hover:text-destructive hover:bg-destructive/10"
                >
                  <Trash2 className="size-3.5" />
                  Clear
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete all messages and analysis data from this conversation.
                    This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={handleClear}
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  >
                    Delete
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPanelOpen(!panelOpen)}
            className="text-muted-foreground"
          >
            {panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>
      </div>

      {/* Main layout: Chat + State Panel */}
      <div className="flex flex-1 min-h-0">
        {/* Chat column */}
        <ChatContainerRoot className="relative flex flex-1 flex-col min-w-0 min-h-0 overscroll-contain">
          <ChatContainerContent className="mx-auto max-w-3xl w-full px-4 py-6 space-y-4">
            {isLoadingHistory ? (
              <div className="flex flex-col items-center justify-center py-20">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
                <p className="mt-2 text-sm text-muted-foreground">Restoring conversation...</p>
              </div>
            ) : isEmpty ? (
              <EmptyState onSuggestionClick={handleSend} />
            ) : (
              <>
                {messages.map((msg) =>
                  msg.role === "user" ? (
                    <UserMessage key={msg.id} content={msg.content} />
                  ) : (
                    <AgentMessage key={msg.id} message={msg} />
                  )
                )}

                {/* Inline selection card — unified rendering */}
                {showSelection && selectionConfig[pending.kind] && (
                  <SelectionCard
                    title={selectionConfig[pending.kind].title}
                    subtitle={selectionConfig[pending.kind].subtitle}
                    items={pending.items}
                    onConfirm={selectionConfig[pending.kind].onConfirm}
                    disabled={isStreaming}
                  />
                )}

                {/* Confirmed selection summary */}
                {confirmedSelection && confirmedSelection.kind !== pending?.kind && (
                  <SelectionCard
                    title={`Selected: ${selectionConfig[confirmedSelection.kind]?.title ?? confirmedSelection.kind}`}
                    items={confirmedSelection.ids.map((id) => ({
                      id,
                      label: id.replace(/_/g, " "),
                    }))}
                    onConfirm={() => {}}
                    confirmed
                    confirmedIds={confirmedSelection.ids}
                  />
                )}
              </>
            )}
            <ChatContainerScrollAnchor />
          </ChatContainerContent>
          <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-10">
            <ScrollButton />
          </div>

          {/* Input */}
          <div className="px-4 py-3 shrink-0 sticky bottom-0 bg-background">
            <div className="mx-auto max-w-3xl">
              <ChatInput
                onSend={handleSend}
                onStop={stop}
                isStreaming={isStreaming}
                disabled={isLoadingHistory}
              />
            </div>
          </div>
        </ChatContainerRoot>

        {/* State panel */}
        {panelOpen && (
          <div className="w-80 xl:w-96 shrink-0 hidden md:block h-full overflow-hidden">
            <StatePanel agentState={agentState} pipelineStages={pipelineStages} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Empty State ──

function EmptyState({ onSuggestionClick }: { onSuggestionClick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="mb-4 rounded-full bg-emerald-50 p-4 dark:bg-emerald-950">
        <BrainCircuit className="size-8 text-emerald-600 dark:text-emerald-400" />
      </div>
      <h2 className="text-lg font-semibold mb-1">Market Demand Analyst</h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        Analyze job market trends, extract in-demand skills, and map them against
        your curriculum to identify gaps and opportunities.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2 max-w-lg">
        {PROMPT_SUGGESTIONS.map((s) => (
          <PromptSuggestion key={s} onClick={() => onSuggestionClick(s)}>
            {s}
          </PromptSuggestion>
        ))}
      </div>
    </div>
  );
}
