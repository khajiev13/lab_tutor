import { Link } from "react-router-dom";
import { ArrowRight, Check, GitMerge, Layers, Loader2, LockKeyhole } from "lucide-react";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CourseProgressFeedback } from "@/features/courses/components/readiness/CourseProgressFeedback";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";

const PREPARATION_STEPS = [
  { index: 0, title: "Materials", description: "Upload and process course files", lockedReason: "" },
  { index: 3, title: "Books", description: "Choose books for your course", lockedReason: "Process your materials first" },
  { index: 4, title: "Analysis", description: "Build skills from your books", lockedReason: "Choose and download books first" },
  { index: 5, title: "Results", description: "Review the skills and chapters", lockedReason: "Complete analysis first" },
];

function PreparationNextAction() {
  const {
    course, activeStep, nextPreparationStep, setActiveStep, booksSkipped,
    stepStatusesLoading, stepStatusesError, refreshStepStatuses,
    bookSessionStatus, analysisRunStatus, presentationCount, startExtraction, isExtracting, materialsReady, materialsMessage,
  } = useCourseDetail();

  if (!course) return null;
  if (stepStatusesLoading || stepStatusesError) {
    return <CourseProgressFeedback error={stepStatusesError} onRetry={refreshStepStatuses} />;
  }

  let title = "Upload your course materials";
  let description = "Add your presentations or documents, then process them to find the topics your course covers.";
  let action = "Upload materials";
  let busy = false;
  const canStartExtraction = nextPreparationStep === 0 && presentationCount > 0 &&
    ["not_started", "failed"].includes(course.extraction_status);

  if (nextPreparationStep === 0) {
    if (course.extraction_status === "in_progress") {
      title = "Processing your materials";
      description = "You can follow progress below. Book selection unlocks when processing is complete.";
      action = "View processing progress";
      busy = true;
    } else if (course.extraction_status === "finished" && !materialsReady) {
      title = "Check your course materials";
      description = materialsMessage;
      action = "View materials";
    } else if (canStartExtraction) {
      title = course.extraction_status === "failed" ? "Try processing your materials again" : "Process your course materials";
      description = "Your files are uploaded. Process them to find course topics and unlock book selection.";
      action = "Start Data Extraction";
    }
  } else if (nextPreparationStep === 3) {
    title = "Choose books for your course";
    description = "Find books that match your course, then confirm your choices. Analysis unlocks once the selected books are downloaded or uploaded.";
    action = "Choose books";
    if (bookSessionStatus === "discovering" || bookSessionStatus === "scoring") {
      title = "Finding books for your course";
      description = "Book discovery is running. You’ll be able to review the suggestions before continuing.";
      action = "View book discovery";
      busy = true;
    } else if (bookSessionStatus === "awaiting_review") {
      title = "Review your book choices";
      action = "Review books";
    } else if (bookSessionStatus === "downloading") {
      title = "Preparing your selected books";
      description = "Wait for downloads to finish, or upload a copy if a download fails. Analysis unlocks when your books are ready.";
      action = "View selected books";
      busy = true;
    } else if (bookSessionStatus === "completed") {
      title = "Finish preparing your books";
      description = "Upload a copy or retry a failed download below. At least one usable book is needed to start analysis.";
      action = "Review selected books";
    }
  } else if (nextPreparationStep === 4) {
    busy = Boolean(analysisRunStatus && ["pending", "extracting", "chunking", "embedding", "scoring", "agentic_extracting"].includes(analysisRunStatus));
    title = busy ? "Analyzing your books" : analysisRunStatus === "failed" ? "Retry your book analysis" : "Analyze your selected books";
    description = busy
      ? "Follow the analysis below. Results unlock automatically when it finishes."
      : "Your books are ready. Start the analysis below to build the course’s skills and chapters.";
    action = busy ? "View analysis progress" : "Go to analysis";
    if (analysisRunStatus === "chapter_extracted") {
      title = "Review the extracted chapters";
      description = "Check the chapters below, then choose Approve & Continue to finish the analysis. Results stay locked until analysis is complete.";
      action = "Review extracted chapters";
    }
  } else if (nextPreparationStep === 5) {
    title = "Review your course results";
    description = "Analysis is complete. Review the skills and chapters, then return to course setup for the next preparation stage.";
    action = "Review results";
  } else if (booksSkipped) {
    title = "Continuing without books";
    description = "You chose to skip books. Book analysis and results aren’t needed for this path. Return to course setup to see what’s next.";
  }

  function openWorkspace() {
    if (nextPreparationStep === null) return;
    setActiveStep(nextPreparationStep);
    requestAnimationFrame(() => {
      const workspace = document.getElementById("prepare-workspace");
      workspace?.focus({ preventScroll: true });
      workspace?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  return (
    <div className="rounded-lg bg-muted/40 p-5 sm:p-6" aria-live="polite">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {booksSkipped ? "Books skipped" : `Your next step · Step ${PREPARATION_STEPS.findIndex((step) => step.index === nextPreparationStep) + 1} of 4`}
      </p>
      <h3 className="mt-2 flex items-center gap-2 text-xl font-semibold tracking-tight">
        {busy && <Loader2 className="size-5 shrink-0 animate-spin" />}{title}
      </h3>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">{description}</p>
      {booksSkipped || (nextPreparationStep === 5 && activeStep === 5) ? (
        <Button asChild className="mt-4 h-auto min-h-10 w-full whitespace-normal sm:w-auto">
          <Link to={`/courses/${course.id}`}>Back to course setup<ArrowRight className="size-4" /></Link>
        </Button>
      ) : (
        <Button className="mt-4 h-auto min-h-10 w-full whitespace-normal sm:w-auto" disabled={isExtracting} onClick={canStartExtraction ? startExtraction : openWorkspace}>
          {action}<ArrowRight className="size-4" />
        </Button>
      )}
    </div>
  );
}

export function CourseStepperHeader() {
  const { activeStep, setActiveStep, getStepStatus, canNavigateToStep, booksSkipped, stepStatusesError, stepStatusesLoading } = useCourseDetail();

  return (
    <section aria-label="Preparation guide" className="space-y-5 rounded-xl border bg-card p-4 sm:p-6">
      <div>
        <h2 className="font-semibold">Preparation checklist</h2>
        <p className="mt-1 text-sm text-muted-foreground">Follow the steps in order. You can revisit any completed step.</p>
      </div>
      <ol aria-label="Course preparation steps" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {PREPARATION_STEPS.map((step, position) => {
          const status = getStepStatus(step.index);
          const complete = status === "completed";
          const locked = status === "locked";
          const selected = activeStep === step.index && !locked;
          const skipped = booksSkipped && step.index >= 4 && !stepStatusesError && !stepStatusesLoading;
          const label = skipped ? "Not needed" : locked ? "Locked" : complete ? "Complete" : status === "active" ? "In progress" : selected ? "Current step" : "Ready";
          const detail = skipped ? "Books were skipped"
            : locked && stepStatusesError ? "Retry loading course progress"
            : locked && stepStatusesLoading ? "Checking course progress"
            : locked ? step.lockedReason : step.description;
          return (
            <li key={step.index}>
              <button
                type="button"
                disabled={locked}
                aria-current={selected ? "step" : undefined}
                aria-label={`Step ${position + 1}: ${step.title}. ${label}`}
                onClick={() => setActiveStep(step.index)}
                className={cn(
                  "flex h-full w-full items-center gap-3 rounded-lg border p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:block",
                  selected ? "border-primary bg-primary/5" : "border-border",
                  locked ? "cursor-not-allowed bg-muted/30" : "hover:bg-muted/60",
                )}
              >
                <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold", complete && "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300", selected && !complete && "border-primary bg-primary text-primary-foreground", locked && "text-muted-foreground")}>
                  {complete ? <Check className="size-4" /> : position + 1}
                </span>
                <span className="block min-w-0 flex-1 sm:mt-3">
                  <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                    {step.title}<span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">{locked && !skipped && <LockKeyhole className="size-3" />}{label}</span>
                  </span>
                  <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{detail}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <PreparationNextAction />
      <Accordion type="single" collapsible>
        <AccordionItem value="optional" className="border-0">
          <AccordionTrigger className="py-0 text-sm text-muted-foreground">Optional preparation tools</AccordionTrigger>
          <AccordionContent className="space-y-3 pb-0 pt-4">
            <p className="text-sm text-muted-foreground">Refine concepts or create a chapter plan after processing your materials. These tools don’t block the next step.</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button variant={activeStep === 1 ? "secondary" : "outline"} disabled={!canNavigateToStep(1)} onClick={() => setActiveStep(1)}><GitMerge className="size-4" />Normalize concepts</Button>
              <Button variant={activeStep === 2 ? "secondary" : "outline"} disabled={!canNavigateToStep(2)} onClick={() => setActiveStep(2)}><Layers className="size-4" />Build chapter plan</Button>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </section>
  );
}
