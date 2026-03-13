import { TrendingUp, Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { ChangelogEntry } from "../types";

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

function groupByDate(entries: ChangelogEntry[]): Map<string, ChangelogEntry[]> {
  const groups = new Map<string, ChangelogEntry[]>();
  for (const entry of entries) {
    let dateKey: string;
    try {
      dateKey = new Date(entry.timestamp).toLocaleDateString(undefined, {
        month: "long",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      dateKey = "Unknown date";
    }
    const group = groups.get(dateKey) ?? [];
    group.push(entry);
    groups.set(dateKey, group);
  }
  return groups;
}

export function ChangelogTimeline({
  changelog,
}: {
  changelog: ChangelogEntry[];
}) {
  if (changelog.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Clock className="size-8 text-muted-foreground/40 mb-3" />
        <p className="text-sm font-medium text-muted-foreground">No changes yet</p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Agent modifications will appear here
        </p>
      </div>
    );
  }

  const grouped = groupByDate(changelog);

  return (
    <ScrollArea className="h-full">
      <div className="p-4 space-y-5">
        {Array.from(grouped.entries()).map(([dateLabel, entries]) => (
          <div key={dateLabel}>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              {dateLabel}
            </p>
            <div className="relative pl-4 space-y-3">
              {/* Vertical timeline line */}
              <div className="absolute left-[7px] top-1 bottom-1 w-px bg-border" />

              {entries.map((entry, i) => (
                <div key={`${entry.skill_name}-${i}`} className="relative flex gap-3">
                  {/* Dot */}
                  <div className="absolute left-[-9px] top-1.5 size-2.5 rounded-full bg-emerald-500 ring-2 ring-background shrink-0" />

                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Badge
                        className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 text-[10px] px-1.5 py-0"
                      >
                        <TrendingUp className="size-2.5" />
                        {entry.agent}
                      </Badge>
                    </div>
                    <p className="text-xs font-medium">{entry.action}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {entry.details}
                    </p>
                    {entry.chapter && (
                      <p className="text-[10px] text-muted-foreground/70 truncate">
                        in {entry.chapter}
                      </p>
                    )}
                    <p className="text-[10px] text-muted-foreground/50">
                      {formatTimestamp(entry.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <Separator className="mt-4" />
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
