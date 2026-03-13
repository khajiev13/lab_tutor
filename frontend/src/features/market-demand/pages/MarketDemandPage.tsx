import { useParams, Link } from "react-router-dom";
import { BrainCircuit, Loader2, PanelRightClose, PanelRightOpen, Trash2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
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
import { useAgentStream } from "../hooks/useAgentStream";
import { AgentMessage } from "../components/AgentMessage";
import { UserMessage } from "../components/UserMessage";
import { ChatInput } from "../components/ChatInput";
import { ConnectionStatus } from "../components/ConnectionStatus";
import { StatePanel } from "../components/StatePanel";

const PROMPT_SUGGESTIONS = [
  "Analyze the job market for this course and find relevant postings",
  "What skills are most demanded in the industry for this curriculum?",
  "Check how well the current curriculum covers market demands",
  "Find skill gaps between our course and industry requirements",
];

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
  const { course } = useCourseDetail();
  const agent = getAgentById("market-analyst");
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
  } = useAgentStream();

  const [panelOpen, setPanelOpen] = useState(true);

  const handleSend = (text: string) => {
    send(text);
  };

  const isEmpty = messages.length === 0 && !isLoadingHistory;

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
                    onClick={clearConversation}
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
              messages.map((msg) =>
                msg.role === "user" ? (
                  <UserMessage key={msg.id} content={msg.content} />
                ) : (
                  <AgentMessage key={msg.id} message={msg} />
                )
              )
            )}
            <ChatContainerScrollAnchor />
          </ChatContainerContent>
          <div className="absolute bottom-14 left-1/2 -translate-x-1/2 z-10">
            <ScrollButton />
          </div>

          {/* Input */}
          <div className="px-4 py-3 shrink-0 sticky bottom-0 bg-background">
            <div className="mx-auto max-w-3xl">
              <ChatInput onSend={handleSend} onStop={stop} isStreaming={isStreaming} />
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
