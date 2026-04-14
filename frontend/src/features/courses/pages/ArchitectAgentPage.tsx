import { Suspense, lazy } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Loader2, ListTree, Activity } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { StepContent } from "@/components/ui/stepper";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  COURSE_STEPS,
} from "@/features/courses/context/CourseDetailContext";
import { CourseStepperHeader } from "@/features/courses/components/CourseStepperHeader";
import { MaterialsStep } from "@/features/courses/components/steps/MaterialsStep";
import { NormalizationStep } from "@/features/courses/components/steps/NormalizationStep";
import { BuildChaptersStep } from "@/features/curriculum-planning/components/BuildChaptersStep";
import { BookSelectionStep } from "@/features/courses/components/steps/BookSelectionStep";
import { getAgentById } from "@/features/agents/config";
import { AgentPageHeader } from "@/features/agents/components/AgentPageHeader";
import { AgentActivityFeed } from "@/features/agents/components/AgentActivityFeed";
import type { AgentStatus } from "@/features/agents/components/AgentCard";

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

/* ── Derive overall agent status ─────────────────────────────── */

function useArchitectAgentStatus(): AgentStatus {
  const { course, getStepStatus } = useCourseDetail();
  if (!course) return "not-started";

  let completedSteps = 0;
  for (let i = 0; i < COURSE_STEPS.length; i++) {
    if (getStepStatus(i) === "completed") completedSteps++;
  }

  if (completedSteps === COURSE_STEPS.length) return "completed";
  if (
    completedSteps > 0 ||
    course.extraction_status === "in_progress"
  )
    return "in-progress";
  return "not-started";
}

/* ── Content (rendered inside provider) ──────────────────────── */

function ArchitectContent() {
  const { activeStep, isLoading, course } = useCourseDetail();
  const agentStatus = useArchitectAgentStatus();
  const agent = getAgentById("architect")!;

  if (isLoading || !course) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
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
            <BreadcrumbPage>{agent.name}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <AgentPageHeader agent={agent} status={agentStatus} />

      <Tabs defaultValue="workflow">
        <TabsList>
          <TabsTrigger value="workflow">
            <ListTree className="size-4" />
            Workflow
          </TabsTrigger>
          <TabsTrigger value="activity">
            <Activity className="size-4" />
            Activity
          </TabsTrigger>
        </TabsList>

        <TabsContent value="workflow" className="space-y-4">
          <CourseStepperHeader />

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
        </TabsContent>

        <TabsContent value="activity">
          <AgentActivityFeed />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────── */

export default function ArchitectAgentPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const courseId = Number(id);
  if (!id || isNaN(courseId)) {
    navigate("/courses");
    return null;
  }

  return (
    <CourseDetailProvider courseId={courseId}>
      <ArchitectContent />
    </CourseDetailProvider>
  );
}
