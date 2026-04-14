import {
  Briefcase,
  ExternalLink,
  TrendingUp,
  Building2,
  Globe,
  Search,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { MarketSkillBankJobPosting, MarketSkillBankSkill } from "../types";

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  medium:
    "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  low: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
};

const STATUS_COLORS: Record<string, { label: string; className: string }> = {
  gap: {
    label: "Gap",
    className:
      "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400",
  },
  new_topic_needed: {
    label: "New Topic",
    className: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400",
  },
  covered: {
    label: "Covered",
    className:
      "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400",
  },
};

const SITE_ICONS: Record<string, React.ReactNode> = {
  linkedin: <Globe className="size-3 text-blue-600" />,
  indeed: <Globe className="size-3 text-purple-600" />,
};

export function MarketSkillBank({
  jobPostings,
}: {
  jobPostings: MarketSkillBankJobPosting[];
}) {
  if (jobPostings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <TrendingUp className="size-10 text-muted-foreground/40 mb-3" />
        <p className="text-sm font-medium text-muted-foreground">
          No market skills analyzed yet
        </p>
        <p className="text-xs text-muted-foreground/60 mt-1">
          Run the Market Demand Analyst to discover industry-relevant skills
        </p>
      </div>
    );
  }

  const totalSkills = new Set(
    jobPostings.flatMap((jp) => jp.skills.map((s) => s.name))
  ).size;

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <Badge
          className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 gap-1"
        >
          <Briefcase className="size-3" />
          {jobPostings.length} job postings
        </Badge>
        <Badge
          className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 gap-1"
        >
          <TrendingUp className="size-3" />
          {totalSkills} unique skills
        </Badge>
      </div>

      {/* Job posting accordion */}
      <Accordion type="multiple" className="w-full">
        {jobPostings.map((jp) => (
          <AccordionItem key={jp.url} value={jp.url}>
            <AccordionTrigger className="hover:no-underline gap-3">
              <div className="flex flex-1 items-center gap-3 min-w-0">
                <div className="flex items-center justify-center size-7 rounded-md bg-emerald-100 dark:bg-emerald-950 shrink-0">
                  <Briefcase className="size-3.5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div className="min-w-0 text-left">
                  <span className="font-medium text-sm truncate block">
                    {jp.title}
                  </span>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {jp.company && (
                      <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                        <Building2 className="size-2.5" />
                        {jp.company}
                      </span>
                    )}
                    {jp.site && (
                      <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                        {SITE_ICONS[jp.site] ?? (
                          <Globe className="size-2.5" />
                        )}
                        {jp.site}
                      </span>
                    )}
                    {jp.search_term && (
                      <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                        <Search className="size-2.5" />
                        {jp.search_term}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <Badge
                className="border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 text-[10px] px-1.5 py-0 gap-0.5 shrink-0 mr-2"
              >
                <TrendingUp className="size-2.5" />
                {jp.skills.length}
              </Badge>
            </AccordionTrigger>
            <AccordionContent>
              <div className="pl-10 space-y-3">
                {/* Link to job posting */}
                <a
                  href={jp.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
                >
                  View job posting
                  <ExternalLink className="size-2.5" />
                </a>

                {/* Skills list */}
                <div className="grid gap-2">
                  {jp.skills.map((skill) => (
                    <MarketSkillRow key={skill.name} skill={skill} />
                  ))}
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}

function MarketSkillRow({ skill }: { skill: MarketSkillBankSkill }) {
  return (
    <div className="flex items-center gap-3 rounded-md border px-3 py-2">
      <span className="text-xs font-medium flex-1 min-w-0 truncate">
        {skill.name}
      </span>

      <div className="flex items-center gap-1.5 shrink-0">
        {skill.category && (
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            {skill.category}
          </Badge>
        )}
        {skill.priority && (
          <Badge
            className={cn(
              "border-transparent text-[10px] px-1.5 py-0",
              PRIORITY_COLORS[skill.priority]
            )}
          >
            {skill.priority}
          </Badge>
        )}
        {skill.status && STATUS_COLORS[skill.status] && (
          <Badge
            className={cn(
              "border-transparent text-[10px] px-1.5 py-0",
              STATUS_COLORS[skill.status].className
            )}
          >
            {STATUS_COLORS[skill.status].label}
          </Badge>
        )}
      </div>

      {skill.demand_pct != null && (
        <div className="w-16 shrink-0 space-y-0.5">
          <Progress
            value={Math.min(skill.demand_pct, 100)}
            className="h-1"
          />
          <p className="text-[9px] text-muted-foreground text-right">
            {skill.demand_pct.toFixed(0)}%
          </p>
        </div>
      )}
    </div>
  );
}
