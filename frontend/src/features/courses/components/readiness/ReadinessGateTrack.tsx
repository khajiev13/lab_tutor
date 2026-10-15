import { Link } from "react-router-dom";
import { Check, LockKeyhole } from "lucide-react";

import { cn } from "@/lib/utils";
import type { NextActionId, ReadinessGate } from "@/features/courses/types";
import { SETUP_STEPS } from "@/features/courses/components/readiness/setup-steps";

interface ReadinessGateTrackProps {
  gates: ReadinessGate[];
  currentStep: NextActionId;
}

export function ReadinessGateTrack({ gates, currentStep }: ReadinessGateTrackProps) {
  return (
    <ol aria-label="Course setup steps" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {gates.map((gate, index) => {
        const complete = gate.status === "complete";
        const locked = gate.status === "locked" || gate.status === "blocked";
        const current = gate.id === currentStep && !locked;
        const title = SETUP_STEPS[gate.id].title;
        const status = complete ? "Complete · Revisit" : locked ? "Locked" : "Up next";
        const detail = gate.status === "blocked" || (locked && index === 0)
          ? gate.detail
          : locked ? `Complete step ${index} first` : complete ? "Saved and ready" : "Ready when you are";
        const content = (
          <div className="flex items-center gap-3 sm:block">
            <span className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold",
              complete && "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
              current && "border-primary bg-primary text-primary-foreground",
              locked && "text-muted-foreground",
            )}>
              {complete ? <Check className="size-4" /> : index + 1}
            </span>
            <div className="min-w-0 flex-1 sm:mt-4">
              <h3 className="text-sm font-semibold">{title}</h3>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{detail}</p>
            </div>
            <span className={cn("flex shrink-0 items-center gap-1 text-xs sm:absolute sm:right-4 sm:top-6", complete ? "text-emerald-700 dark:text-emerald-300" : "text-muted-foreground")}>
              {locked && <LockKeyhole className="size-3" />}
              {complete ? gate.id === "publish" ? "Published" : <>Complete<span className="hidden sm:inline"> · Revisit</span></> : status}
            </span>
          </div>
        );
        const className = cn(
          "relative block h-full rounded-lg border p-4 transition-colors",
          current ? "border-primary bg-primary/5" : "border-border",
          locked && "bg-muted/30",
          !locked && gate.route && "hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        );

        return (
          <li key={gate.id}>
            {gate.route && !locked ? (
              <Link to={gate.route} className={className} aria-label={`Step ${index + 1}: ${title}. ${status}`} aria-current={current ? "step" : undefined}>
                {content}
              </Link>
            ) : (
              <div className={className} aria-disabled={locked || undefined} aria-current={current ? "step" : undefined}>
                {content}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
