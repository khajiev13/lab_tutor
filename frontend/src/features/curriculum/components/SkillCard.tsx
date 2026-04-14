import { useState } from "react";
import {
  BookOpen,
  BookOpenText,
  TrendingUp,
  ChevronDown,
  Briefcase,
  ExternalLink,
  Lightbulb,
  Video,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import type { SkillRead } from "../types";

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  low: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
};

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  gap: {
    label: "Gap",
    className: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  },
  new_topic_needed: {
    label: "New Topic",
    className: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  },
  covered: {
    label: "Covered",
    className: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  },
};

export function SkillCard({ skill }: { skill: SkillRead }) {
  const [jobsOpen, setJobsOpen] = useState(false);
  const [readingsOpen, setReadingsOpen] = useState(false);
  const [videosOpen, setVideosOpen] = useState(false);
  const isMarket = skill.source === "market_demand";

  return (
    <Card className="gap-0 py-0 shadow-none">
      <CardHeader className="px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            {isMarket ? (
              <Badge
                className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 shrink-0"
              >
                <TrendingUp className="size-3" />
                Market
              </Badge>
            ) : (
              <Badge variant="outline" className="shrink-0">
                <BookOpen className="size-3" />
                Book
              </Badge>
            )}
            <span className="font-medium text-sm truncate">{skill.name}</span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            {isMarket && skill.priority && (
              <Badge
                className={cn(
                  "border-transparent text-[10px] px-1.5",
                  PRIORITY_COLORS[skill.priority]
                )}
              >
                {skill.priority}
              </Badge>
            )}
            {isMarket && skill.status && STATUS_LABELS[skill.status] && (
              <Badge
                className={cn(
                  "border-transparent text-[10px] px-1.5",
                  STATUS_LABELS[skill.status].className
                )}
              >
                {STATUS_LABELS[skill.status].label}
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-3 pt-0 space-y-2.5">
        {/* Description (book skills) */}
        {!isMarket && skill.description && (
          <p className="text-xs text-muted-foreground">{skill.description}</p>
        )}

        {/* Demand bar (market skills) */}
        {isMarket && skill.demand_pct != null && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Market demand</span>
              <span className="font-medium">{skill.demand_pct.toFixed(1)}%</span>
            </div>
            <Progress value={Math.min(skill.demand_pct, 100)} className="h-1.5" />
          </div>
        )}

        {/* Reasoning (market skills) */}
        {isMarket && skill.reasoning && (
          <p className="text-xs text-muted-foreground leading-relaxed">
            {skill.reasoning}
          </p>
        )}

        {/* Concepts */}
        {skill.concepts.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <Lightbulb className="size-3 text-muted-foreground mt-0.5 shrink-0" />
            {skill.concepts.map((c) => (
              <Badge
                key={c.name}
                variant="secondary"
                className="text-[10px] px-1.5 py-0"
              >
                {c.name}
              </Badge>
            ))}
          </div>
        )}

        {/* Job postings (market skills, collapsible) */}
        {isMarket && skill.job_postings.length > 0 && (
          <Collapsible open={jobsOpen} onOpenChange={setJobsOpen}>
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <Briefcase className="size-3" />
              <span>{skill.job_postings.length} job postings</span>
              <ChevronDown
                className={cn(
                  "size-3 transition-transform",
                  jobsOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1.5 space-y-1 pl-[18px]">
                {skill.job_postings.map((jp) => (
                  <li key={jp.url} className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {jp.title ?? "Job"}
                    </span>
                    {jp.company && (
                      <span className="text-muted-foreground">
                        {" "}
                        at {jp.company}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Reading resources (collapsible) */}
        {skill.readings?.length > 0 && (
          <Collapsible open={readingsOpen} onOpenChange={setReadingsOpen}>
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <BookOpenText className="size-3" />
              <span>{skill.readings.length} readings</span>
              <ChevronDown
                className={cn(
                  "size-3 transition-transform",
                  readingsOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1.5 space-y-1 pl-[18px]">
                {skill.readings.map((r) => (
                  <li key={r.url} className="text-xs">
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-foreground hover:underline inline-flex items-center gap-1"
                    >
                      {r.title}
                      <ExternalLink className="size-2.5" />
                    </a>
                    <span className="text-muted-foreground">
                      {" "}
                      ({r.domain})
                    </span>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Video resources (collapsible) */}
        {skill.videos?.length > 0 && (
          <Collapsible open={videosOpen} onOpenChange={setVideosOpen}>
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors">
              <Video className="size-3" />
              <span>{skill.videos.length} videos</span>
              <ChevronDown
                className={cn(
                  "size-3 transition-transform",
                  videosOpen && "rotate-180"
                )}
              />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1.5 space-y-1 pl-[18px]">
                {skill.videos.map((v) => (
                  <li key={v.url} className="text-xs">
                    <a
                      href={v.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-foreground hover:underline inline-flex items-center gap-1"
                    >
                      {v.title}
                      <ExternalLink className="size-2.5" />
                    </a>
                  </li>
                ))}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
    </Card>
  );
}
