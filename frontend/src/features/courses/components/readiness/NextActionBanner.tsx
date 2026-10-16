import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { CourseReadiness } from "@/features/courses/types";
import { PublishCourseButton } from "@/features/courses/components/readiness/PublishCourseButton";
import { SETUP_STEPS } from "@/features/courses/components/readiness/setup-steps";

interface NextActionBannerProps {
  readiness: CourseReadiness;
  onRefresh: () => void | Promise<void>;
  onLearnMore?: () => void;
}

export function NextActionBanner({ readiness, onRefresh, onLearnMore }: NextActionBannerProps) {
  const { next_action: nextAction, gates } = readiness;
  if (nextAction.id === "none") {
    return (
      <div className="flex items-start gap-4 rounded-lg border border-emerald-200 bg-emerald-50/40 p-5 dark:border-emerald-900 dark:bg-emerald-950/20 sm:p-6">
        <CheckCircle2 className="mt-1 size-6 shrink-0 text-emerald-600" />
        <div>
          <h3 className="text-lg font-semibold">Your course is ready for students</h3>
          <p className="mt-1 text-sm text-muted-foreground">Students can enroll and start learning. You can revisit any completed step above.</p>
        </div>
      </div>
    );
  }

  const step = SETUP_STEPS[nextAction.id];
  const gateIndex = gates.findIndex((gate) => gate.id === nextAction.id);
  const gate = gates[gateIndex];
  const available = gate?.status === "ready" || gate?.status === "complete";
  const Icon = step.icon;
  const nextGate = gates[gateIndex + 1];

  return (
    <div className="rounded-lg bg-muted/40 p-5 sm:p-6">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:gap-4">
        <div className="hidden size-11 shrink-0 items-center justify-center rounded-xl border bg-background sm:flex"><Icon className="size-5" /></div>
        <div className="min-w-0 flex-1 space-y-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Your next step · Step {gateIndex + 1} of {gates.length}</p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight">{step.title}</h3>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{step.description}</p>
          </div>
          <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
            {nextAction.id === "publish" ? (
              <PublishCourseButton readiness={readiness} onRefresh={onRefresh} />
            ) : nextAction.route && available ? (
              <Button asChild className="h-auto min-h-10 w-full whitespace-normal sm:w-auto">
                <Link to={nextAction.route}>{step.action}<ArrowRight className="size-4" /></Link>
              </Button>
            ) : <p className="text-sm text-muted-foreground">{gate?.detail}</p>}
            {onLearnMore && <Button variant="ghost" size="sm" onClick={onLearnMore}>How this step works</Button>}
          </div>
          {nextGate && <p className="text-xs text-muted-foreground">Next, you’ll unlock: {SETUP_STEPS[nextGate.id].title.toLowerCase()}.</p>}
        </div>
      </div>
    </div>
  );
}
