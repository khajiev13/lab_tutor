import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AvailabilityStatus, CourseReadiness } from "../../types";
import { NextActionBanner } from "./NextActionBanner";
import { PublishCourseButton } from "./PublishCourseButton";
import { ReadinessGateTrack } from "./ReadinessGateTrack";

interface CourseReadinessRoadProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
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

export function CourseReadinessRoad({ readiness, onRefresh }: CourseReadinessRoadProps) {
  return (
    <section className="space-y-4 rounded-lg border bg-background p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">Course readiness</h2>
            <Badge
              variant="outline"
              className={cn(AVAILABILITY_CLASS[readiness.availability_status])}
            >
              {AVAILABILITY_LABEL[readiness.availability_status]}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Clear each gate before opening enrollment to students.
          </p>
        </div>
        <PublishCourseButton readiness={readiness} onRefresh={onRefresh} />
      </div>

      <NextActionBanner nextAction={readiness.next_action} />

      {readiness.blockers.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-background p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-amber-700">
            <AlertCircle className="size-4" />
            Blockers
          </div>
          <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
            {readiness.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      )}

      <ReadinessGateTrack gates={readiness.gates} />
    </section>
  );
}
