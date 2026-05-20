import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Circle, Lock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GateStatus, ReadinessGate } from "../../types";

interface ReadinessGateTrackProps {
  gates: ReadinessGate[];
}

const STATUS_ICON = {
  complete: CheckCircle2,
  ready: Circle,
  locked: Lock,
  blocked: AlertCircle,
} satisfies Record<GateStatus, typeof CheckCircle2>;

const STATUS_LABEL = {
  complete: "Complete",
  ready: "Ready",
  locked: "Locked",
  blocked: "Blocked",
} satisfies Record<GateStatus, string>;

const STATUS_CLASS = {
  complete: "border-emerald-200 text-emerald-700",
  ready: "border-blue-200 text-blue-700",
  locked: "text-muted-foreground",
  blocked: "border-destructive/40 text-destructive",
} satisfies Record<GateStatus, string>;

function GatePanel({ gate }: { gate: ReadinessGate }) {
  const Icon = STATUS_ICON[gate.status];
  const panel = (
    <div
      className={cn(
        "h-full rounded-lg border bg-background p-4 transition-colors",
        gate.route && gate.status !== "locked" && "hover:border-primary/50",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <Icon className={cn("size-4", STATUS_CLASS[gate.status])} />
          <h3 className="text-sm font-medium">{gate.label}</h3>
        </div>
        <Badge variant="outline" className={STATUS_CLASS[gate.status]}>
          {STATUS_LABEL[gate.status]}
        </Badge>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{gate.detail}</p>
    </div>
  );

  if (!gate.route || gate.status === "locked") {
    return panel;
  }

  return (
    <Link to={gate.route} className="block h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {panel}
    </Link>
  );
}

export function ReadinessGateTrack({ gates }: ReadinessGateTrackProps) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {gates.map((gate) => (
        <GatePanel key={gate.id} gate={gate} />
      ))}
    </div>
  );
}
