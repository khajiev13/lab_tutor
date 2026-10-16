import type { ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, LockKeyhole } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/context/AuthContext";
import { useCourseReadiness } from "@/features/courses/hooks/useCourseReadiness";
import type { ReadinessGateId } from "@/features/courses/types";
import { CourseProgressFeedback } from "@/features/courses/components/readiness/CourseProgressFeedback";
import { SETUP_STEPS } from "@/features/courses/components/readiness/setup-steps";

interface CourseSetupGateProps {
  gateId: ReadinessGateId;
  children: ReactNode;
}

function TeacherSetupGate({ courseId, gateId, children }: CourseSetupGateProps & { courseId: number }) {
  const { readiness, error, refresh } = useCourseReadiness(courseId);

  if (!readiness) return <CourseProgressFeedback error={error} onRetry={refresh} />;

  const gate = readiness.gates.find((item) => item.id === gateId);
  if (gate?.status === "ready" || gate?.status === "complete") return children;

  const next = readiness.next_action;
  const nextStep = next.id !== "none" ? SETUP_STEPS[next.id] : null;

  return (
    <section className="mx-auto w-full max-w-2xl space-y-6 py-8">
      <Button asChild variant="ghost" className="pl-0">
        <Link to={`/courses/${courseId}`}><ArrowLeft className="size-4" />Back to course setup</Link>
      </Button>
      <div className="space-y-5 rounded-xl border bg-card p-6 sm:p-8">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted"><LockKeyhole className="size-5" /></div>
        <div className="space-y-2">
          <p className="text-sm font-medium text-muted-foreground">{SETUP_STEPS[gateId].title}</p>
          <h1 className="text-2xl font-semibold tracking-tight">Complete the earlier steps first</h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            This step will open when the earlier course setup steps are complete. Your progress is saved as you go.
          </p>
        </div>
        {next.route && nextStep && next.id !== gateId && (
          <Button asChild className="h-auto min-h-10 w-full whitespace-normal sm:w-auto">
            <Link to={next.route}>{nextStep.action}<ArrowRight className="size-4" /></Link>
          </Button>
        )}
      </div>
    </section>
  );
}

export function CourseSetupGate(props: CourseSetupGateProps) {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const courseId = Number(id);

  if (user?.role !== "teacher") return props.children;
  if (!Number.isInteger(courseId) || courseId <= 0) return <Navigate to="/courses" replace />;

  return <TeacherSetupGate key={`${courseId}-${props.gateId}`} courseId={courseId} {...props} />;
}
