import { Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { PrerequisiteDraftEdge } from "@/features/courses/types";
import { cn } from "@/lib/utils";

interface PrerequisiteEdgeWorklistProps {
  edges: PrerequisiteDraftEdge[];
  onRemove: (edge: PrerequisiteDraftEdge) => void;
  isSaving?: boolean;
}

const CONFIDENCE_CLASS = {
  high: "border-emerald-200 text-emerald-700",
  medium: "border-amber-200 text-amber-700",
  low: "border-rose-200 text-rose-700",
} satisfies Record<PrerequisiteDraftEdge["confidence"], string>;

export function PrerequisiteEdgeWorklist({
  edges,
  onRemove,
  isSaving = false,
}: PrerequisiteEdgeWorklistProps) {
  if (edges.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
        No prerequisite edges in the draft.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {edges.map((edge) => (
        <article
          key={`${edge.prerequisite_name}->${edge.dependent_name}`}
          className="rounded-lg border bg-background p-4"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                <span>{edge.prerequisite_name}</span>
                <span className="text-muted-foreground">{"->"}</span>
                <span>{edge.dependent_name}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className={cn(CONFIDENCE_CLASS[edge.confidence])}>
                  {edge.confidence}
                </Badge>
                <Badge variant="outline">{edge.source}</Badge>
              </div>
              {edge.reasoning && (
                <p className="text-sm text-muted-foreground">{edge.reasoning}</p>
              )}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isSaving}
              onClick={() => onRemove(edge)}
              aria-label={`Remove ${edge.prerequisite_name} prerequisite`}
            >
              <Trash2 />
              Remove
            </Button>
          </div>
        </article>
      ))}
    </div>
  );
}
