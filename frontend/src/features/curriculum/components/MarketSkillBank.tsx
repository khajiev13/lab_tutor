import {
  Briefcase,
  Building2,
  ExternalLink,
  Globe,
  Search,
  TrendingUp,
  Users,
} from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { SkillBankDisplayJobPosting } from '@/features/curriculum/types';

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  low: 'bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-400',
};

const SITE_ICONS: Record<string, ReactNode> = {
  linkedin: <Globe className="size-3 text-blue-600" />,
  indeed: <Globe className="size-3 text-purple-600" />,
};

export function MarketSkillBank({
  jobPostings,
  selectedStudentName,
}: {
  jobPostings: SkillBankDisplayJobPosting[];
  selectedStudentName?: string | null;
}) {
  if (jobPostings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <TrendingUp className="mb-3 size-10 text-muted-foreground/40" />
        <p className="text-sm font-medium text-muted-foreground">No market skills analyzed yet</p>
        <p className="mt-1 text-xs text-muted-foreground/60">
          Run the Market Demand Analyst to discover industry-relevant skills
        </p>
      </div>
    );
  }

  const totalSkills = new Set(jobPostings.flatMap((posting) => posting.skills.map((skill) => skill.name))).size;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <Badge className="gap-1 border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
          <Briefcase className="size-3" />
          {jobPostings.length} job postings
        </Badge>
        <Badge className="gap-1 border-transparent bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
          <TrendingUp className="size-3" />
          {totalSkills} unique skills
        </Badge>
        {selectedStudentName && (
          <Badge variant="secondary">Overlaying {selectedStudentName}&apos;s saved selections</Badge>
        )}
      </div>

      <Accordion
        type="multiple"
        defaultValue={jobPostings.map((posting) => posting.url)}
        className="w-full"
      >
        {jobPostings.map((posting) => (
          <AccordionItem key={posting.url} value={posting.url}>
            <AccordionTrigger className="gap-3 hover:no-underline">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-md bg-emerald-100 dark:bg-emerald-950">
                  <Briefcase className="size-3.5 text-emerald-600 dark:text-emerald-400" />
                </div>
                <div className="min-w-0 text-left">
                  <span className="block truncate text-sm font-medium">{posting.title}</span>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                    {posting.company && (
                      <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                        <Building2 className="size-2.5" />
                        {posting.company}
                      </span>
                    )}
                    {posting.site && (
                      <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                        {SITE_ICONS[posting.site.toLowerCase()] ?? <Globe className="size-2.5" />}
                        {posting.site}
                      </span>
                    )}
                    {posting.search_term && (
                      <span className="flex items-center gap-0.5 text-[10px] text-muted-foreground">
                        <Search className="size-2.5" />
                        {posting.search_term}
                      </span>
                    )}
                  </div>
                  {posting.overlay?.isInterested && selectedStudentName && (
                    <Badge variant="outline" className="mt-2 text-[10px]">
                      Interested by {selectedStudentName}
                    </Badge>
                  )}
                </div>
              </div>
              <Badge className="mr-2 shrink-0 gap-0.5 border-transparent bg-emerald-100 px-1.5 py-0 text-[10px] text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                <TrendingUp className="size-2.5" />
                {posting.skills.length}
              </Badge>
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-3 pl-10">
                <a
                  href={posting.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
                >
                  View job posting
                  <ExternalLink className="size-2.5" />
                </a>

                <div className="grid gap-2">
                  {posting.skills.map((skill) => (
                    <MarketSkillRow
                      key={`${posting.url}-${skill.name}`}
                      skill={skill}
                      selectedStudentName={selectedStudentName}
                    />
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

function MarketSkillRow({
  skill,
  selectedStudentName,
}: {
  skill: SkillBankDisplayJobPosting['skills'][number];
  selectedStudentName?: string | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2">
      <span className="min-w-0 flex-1 truncate text-xs font-medium">{skill.name}</span>

      <div className="flex flex-wrap items-center gap-1.5 shrink-0">
        {skill.overlay?.isSelected && selectedStudentName && (
          <Badge variant="outline" className="text-[10px]">
            Selected by {selectedStudentName}
          </Badge>
        )}
        {(skill.overlay?.peerCount ?? 0) > 0 && (
          <Badge variant="outline" className="gap-1 text-[10px]">
            <Users className="size-3" />
            {skill.overlay?.peerCount}
          </Badge>
        )}
        {skill.category && (
          <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
            {skill.category}
          </Badge>
        )}
        {skill.priority && (
          <Badge
            className={cn(
              'border-transparent px-1.5 py-0 text-[10px]',
              PRIORITY_COLORS[skill.priority] ?? '',
            )}
          >
            {skill.priority}
          </Badge>
        )}
      </div>

      {skill.demand_pct != null && (
        <div className="w-16 shrink-0 space-y-0.5">
          <Progress value={Math.min(skill.demand_pct, 100)} className="h-1" />
          <p className="text-right text-[9px] text-muted-foreground">{skill.demand_pct.toFixed(0)}%</p>
        </div>
      )}
    </div>
  );
}
