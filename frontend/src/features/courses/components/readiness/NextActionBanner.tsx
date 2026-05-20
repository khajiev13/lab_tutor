import { Link } from "react-router-dom";
import { ArrowRight, ClipboardCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ReadinessNextAction } from "../../types";

interface NextActionBannerProps {
  nextAction: ReadinessNextAction;
}

export function NextActionBanner({ nextAction }: NextActionBannerProps) {
  const isComplete = nextAction.id === "none";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border bg-background p-4 sm:flex-row sm:items-center sm:justify-between",
        isComplete && "border-emerald-200",
      )}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-md border p-2">
          <ClipboardCheck className="size-4" />
        </div>
        <div>
          <p className="text-sm font-medium">Next action</p>
          <p className="text-sm text-muted-foreground">{nextAction.label}</p>
        </div>
      </div>
      {nextAction.route && (
        <Button asChild size="sm" className="w-full sm:w-auto">
          <Link to={nextAction.route}>
            {nextAction.label}
            <ArrowRight className="size-4" />
          </Link>
        </Button>
      )}
    </div>
  );
}
