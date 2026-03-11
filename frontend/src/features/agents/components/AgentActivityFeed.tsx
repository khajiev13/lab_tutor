import { CheckCircle2, AlertCircle, Info } from "lucide-react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Spinner } from "@/components/ui/spinner";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";

interface ActivityEvent {
  id: string;
  message: string;
  status: "active" | "completed" | "error" | "info";
}

function StatusIcon({ status }: { status: ActivityEvent["status"] }) {
  switch (status) {
    case "active":
      return <Spinner className="size-4 text-primary" />;
    case "completed":
      return <CheckCircle2 className="size-4 text-green-600" />;
    case "error":
      return <AlertCircle className="size-4 text-destructive" />;
    case "info":
      return <Info className="size-4 text-muted-foreground" />;
  }
}

function deriveActivityEvents(ctx: {
  extractionStatus?: string;
  extractionProgress: { processed: number; total: number } | null;
  isExtracting: boolean;
  bookSessionStatus: string | null;
  analysisRunStatus: string | null;
}): ActivityEvent[] {
  const events: ActivityEvent[] = [];

  // Materials / extraction events
  if (ctx.isExtracting || ctx.extractionStatus === "in_progress") {
    const pct = ctx.extractionProgress
      ? `${ctx.extractionProgress.processed}/${ctx.extractionProgress.total}`
      : "";
    events.push({
      id: "extraction",
      message: `Extracting data from course materials${pct ? ` (${pct})` : ""}…`,
      status: "active",
    });
  } else if (ctx.extractionStatus === "finished") {
    events.push({
      id: "extraction",
      message: "Data extraction complete.",
      status: "completed",
    });
  } else if (ctx.extractionStatus === "failed") {
    events.push({
      id: "extraction",
      message: "Data extraction failed.",
      status: "error",
    });
  }

  // Book selection events
  if (ctx.bookSessionStatus) {
    switch (ctx.bookSessionStatus) {
      case "discovering":
        events.push({ id: "books-discover", message: "Discovering books…", status: "active" });
        break;
      case "scoring":
        events.push({ id: "books-score", message: "Scoring discovered books…", status: "active" });
        break;
      case "downloading":
        events.push({ id: "books-download", message: "Downloading selected books…", status: "active" });
        break;
      case "completed":
        events.push({ id: "books-done", message: "Book selection complete.", status: "completed" });
        break;
    }
  }

  // Analysis events
  if (ctx.analysisRunStatus) {
    switch (ctx.analysisRunStatus) {
      case "agentic_extracting":
      case "extracting":
        events.push({ id: "analysis-extract", message: "Extracting book content…", status: "active" });
        break;
      case "chunking":
        events.push({ id: "analysis-chunk", message: "Chunking extracted content…", status: "active" });
        break;
      case "embedding":
        events.push({ id: "analysis-embed", message: "Generating embeddings…", status: "active" });
        break;
      case "scoring":
        events.push({ id: "analysis-score", message: "Scoring book alignment…", status: "active" });
        break;
      case "completed":
      case "agentic_completed":
        events.push({ id: "analysis-done", message: "Analysis complete.", status: "completed" });
        break;
      case "curriculum_built":
        events.push({ id: "analysis-done", message: "Curriculum built.", status: "completed" });
        break;
      case "book_picked":
        events.push({ id: "analysis-pick", message: "Book picked for analysis.", status: "info" });
        break;
    }
  }

  return events;
}

export function AgentActivityFeed() {
  const ctx = useCourseDetail();

  const events = deriveActivityEvents({
    extractionStatus: ctx.course?.extraction_status,
    extractionProgress: ctx.extractionProgress,
    isExtracting: ctx.isExtracting,
    bookSessionStatus: ctx.bookSessionStatus,
    analysisRunStatus: ctx.analysisRunStatus,
  });

  if (events.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Info />
          </EmptyMedia>
          <EmptyTitle>No activity yet</EmptyTitle>
          <EmptyDescription>
            Start by uploading course materials. Activity will appear here as the
            agent works.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <ScrollArea className="h-[400px] pr-3">
      <ul className="space-y-3">
        {events.map((event) => (
          <li key={event.id} className="flex items-start gap-3">
            <div className="mt-0.5 shrink-0">
              <StatusIcon status={event.status} />
            </div>
            <span className="text-sm">{event.message}</span>
          </li>
        ))}
      </ul>
    </ScrollArea>
  );
}
