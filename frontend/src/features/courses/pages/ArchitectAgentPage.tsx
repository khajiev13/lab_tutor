import { Suspense, lazy } from "react";
import { useParams, Navigate, useSearchParams, Link } from "react-router-dom";
import { Loader2, Activity } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { StepContent } from "@/components/ui/stepper";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
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
import { CourseStepperHeader } from "@/features/courses/components/CourseStepperHeader";
import { MaterialsStep } from "@/features/courses/components/steps/MaterialsStep";
import { NormalizationStep } from "@/features/courses/components/steps/NormalizationStep";
import { BuildChaptersStep } from "@/features/curriculum-planning/components/BuildChaptersStep";
import { BookSelectionStep } from "@/features/courses/components/steps/BookSelectionStep";
import { AgentActivityFeed } from "@/features/agents/components/AgentActivityFeed";

/* Lazy-load heavy steps */
const AnalysisStep = lazy(() =>
  import("@/features/courses/components/steps/AnalysisStep").then((m) => ({
    default: m.AnalysisStep,
  }))
);
const VisualizationStep = lazy(() =>
  import("@/features/courses/components/steps/VisualizationStep").then((m) => ({
    default: m.VisualizationStep,
  }))
);

function StepSkeleton() {
  return (
    <div className="space-y-4 pt-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

/* ── Content (rendered inside provider) ──────────────────────── */

function ArchitectContent() {
  const { activeStep, isLoading, course, canNavigateToStep } = useCourseDetail();

  if (isLoading || !course) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full min-w-0 max-w-6xl space-y-6">
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
              <Link to={`/courses/${course.id}`}>{course.title}</Link>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>Prepare course</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Prepare course</h1>
        <p className="mt-2 text-sm text-muted-foreground">Turn your course materials into a foundation for your students’ learning.</p>
      </div>

      <CourseStepperHeader />

      <div id="prepare-workspace" tabIndex={-1} className="scroll-mt-6 space-y-4 outline-none" aria-label="Current preparation step">
        {canNavigateToStep(activeStep) && <>
          <StepContent activeIndex={activeStep} index={0}>
            <MaterialsStep />
          </StepContent>

          <StepContent activeIndex={activeStep} index={1}>
            <NormalizationStep />
          </StepContent>

          <StepContent activeIndex={activeStep} index={2}>
            <BuildChaptersStep />
          </StepContent>

          <StepContent activeIndex={activeStep} index={3}>
            <BookSelectionStep />
          </StepContent>

          <Suspense fallback={<StepSkeleton />}>
            <StepContent activeIndex={activeStep} index={4}>
              <AnalysisStep />
            </StepContent>
          </Suspense>

          <Suspense fallback={<StepSkeleton />}>
            <StepContent activeIndex={activeStep} index={5}>
              <VisualizationStep />
            </StepContent>
          </Suspense>
        </>}
      </div>

      <Accordion type="single" collapsible className="rounded-xl border px-5">
        <AccordionItem value="activity" className="border-0">
          <AccordionTrigger><span className="flex items-center gap-2 text-sm"><Activity className="size-4" />Preparation activity</span></AccordionTrigger>
          <AccordionContent><AgentActivityFeed /></AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────── */

export default function ArchitectAgentPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();

  const courseId = Number(id);
  if (!id || !Number.isInteger(courseId) || courseId <= 0) return <Navigate to="/courses" replace />;

  return (
    <CourseDetailProvider key={`${courseId}:${searchParams.get("step") ?? ""}`} courseId={courseId} pollStepStatuses initialStep={searchParams.get("step") === "materials" ? "materials" : searchParams.get("step") === "build-chapters" ? "build-chapters" : undefined}>
      <ArchitectContent />
    </CourseDetailProvider>
  );
}
