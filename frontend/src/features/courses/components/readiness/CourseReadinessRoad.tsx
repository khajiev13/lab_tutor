import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AvailabilityStatus, CourseReadiness } from "@/features/courses/types";
import { NextActionBanner } from "@/features/courses/components/readiness/NextActionBanner";
import { ReadinessGateTrack } from "@/features/courses/components/readiness/ReadinessGateTrack";

interface CourseReadinessRoadProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
  onLearnMore?: () => void;
}

const AVAILABILITY_LABEL = {
  draft: "Draft",
  published: "Published",
  publishing_paused: "Publishing paused",
} satisfies Record<AvailabilityStatus, string>;

const AVAILABILITY_CLASS = {
  draft: "text-muted-foreground",
  published: "border-emerald-200 text-emerald-700",
  publishing_paused: "border-amber-200 text-amber-700",
} satisfies Record<AvailabilityStatus, string>;

export function CourseReadinessRoad({ readiness, onRefresh, onLearnMore }: CourseReadinessRoadProps) {
  const completed = readiness.gates.filter((gate) => gate.status === "complete").length;

  return (
    <section className="flex flex-col gap-6 rounded-xl border bg-card p-5 sm:p-6" aria-labelledby="course-setup-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="course-setup-heading" className="text-xl font-semibold tracking-tight">Set up your course</h2>
            <Badge
              variant="outline"
              className={cn(AVAILABILITY_CLASS[readiness.availability_status])}
            >
              {AVAILABILITY_LABEL[readiness.availability_status]}
            </Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            One step at a time, from teaching materials to a course ready for students.
          </p>
        </div>
        <p className="shrink-0 text-sm text-muted-foreground sm:pt-1">{completed} of {readiness.gates.length} steps complete</p>
      </div>

      {readiness.availability_status === "publishing_paused" && (
        <div role="status" className="order-1 flex items-start gap-2 rounded-lg border border-amber-200 p-4 text-sm text-amber-800 dark:border-amber-900 dark:text-amber-300">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          Enrollment is paused while your course needs attention. Complete the next step below to restore access.
        </div>
      )}

      <div className="order-2 sm:order-3">
        <NextActionBanner readiness={readiness} onRefresh={onRefresh} onLearnMore={onLearnMore} />
      </div>
      <div className="order-3 sm:order-2">
        <ReadinessGateTrack gates={readiness.gates} currentStep={readiness.next_action.id} />
      </div>
      <p className="order-4 text-xs text-muted-foreground">Each step unlocks the next. Completed steps stay available if you need to make changes.</p>
    </section>
  );
}
