import { cn } from "@/lib/utils";
import {
  Search,
  Filter,
  Zap,
  Map,
  CheckSquare,
  Link2,
  Database,
  Check,
  type LucideIcon,
} from "lucide-react";
import type { PipelineStageId, StageStatus } from "../types";

interface PipelineStepperProps {
  stages: Record<PipelineStageId, StageStatus>;
}

const STAGES: { id: PipelineStageId; label: string; icon: LucideIcon }[] = [
  { id: "fetch", label: "Fetch Jobs", icon: Search },
  { id: "select", label: "Select Groups", icon: Filter },
  { id: "extract", label: "Extract Skills", icon: Zap },
  { id: "map", label: "Map Curriculum", icon: Map },
  { id: "approve", label: "Approve Gaps", icon: CheckSquare },
  { id: "link", label: "Link Concepts", icon: Link2 },
  { id: "insert", label: "Update Knowledge Map", icon: Database },
];

function StageIcon({ status, icon: Icon }: { status: StageStatus; icon: LucideIcon }) {
  if (status === "complete") {
    return (
      <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center">
        <Check className="w-3.5 h-3.5 text-amber-600" />
      </div>
    );
  }
  if (status === "active") {
    return (
      <div className="w-6 h-6 rounded-full border-2 border-amber-500 flex items-center justify-center animate-pulse">
        <Icon className="w-3 h-3 text-amber-500" />
      </div>
    );
  }
  return (
    <div className="w-6 h-6 rounded-full border border-border flex items-center justify-center">
      <Icon className="w-3 h-3 text-muted-foreground" />
    </div>
  );
}

export function PipelineStepper({ stages }: PipelineStepperProps) {
  return (
    <div className="space-y-1 p-4">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Pipeline Progress
      </h3>
      {STAGES.map((stage, i) => {
        const status = stages[stage.id];
        return (
          <div key={stage.id} className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <StageIcon status={status} icon={stage.icon} />
              {i < STAGES.length - 1 && (
                <div
                  className={cn(
                    "w-px h-6 mt-1",
                    status === "complete" ? "bg-amber-300" : "bg-border"
                  )}
                />
              )}
            </div>
            <div className="pb-4">
              <p
                className={cn(
                  "text-sm font-medium",
                  status === "complete" && "text-muted-foreground line-through",
                  status === "active" && "text-amber-600",
                  status === "pending" && "text-muted-foreground/70"
                )}
              >
                {stage.label}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
