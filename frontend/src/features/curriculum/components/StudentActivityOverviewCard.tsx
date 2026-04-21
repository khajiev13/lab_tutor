import { BarChart3, Briefcase, Library, Sparkles, Users } from 'lucide-react';
import type { ReactNode } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { StudentInsightsOverview } from '@/features/curriculum/types';

function SummaryStat({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tracking-tight">{value}</p>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
        <div className="rounded-2xl border border-border/60 bg-background p-2 text-muted-foreground">
          {icon}
        </div>
      </div>
    </div>
  );
}

export function StudentActivityOverviewCard({
  overview,
}: {
  overview: StudentInsightsOverview;
}) {
  const { summary, students } = overview;

  return (
    <Card className="mb-5 border-border/60 shadow-none">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4 text-muted-foreground" />
              Student Activity
            </CardTitle>
            <CardDescription>
              See which skills students are actually carrying into their learning paths, then
              inspect one student&apos;s saved selection directly in the banks below.
            </CardDescription>
          </div>
          <Badge variant="secondary">
            {students.length} enrolled student{students.length === 1 ? '' : 's'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <SummaryStat
            icon={<Sparkles className="h-4 w-4" />}
            label="Students building"
            value={`${summary.students_with_learning_paths}`}
            detail="Saved learning paths"
          />
          <SummaryStat
            icon={<Library className="h-4 w-4" />}
            label="Students selecting"
            value={`${summary.students_with_selections}`}
            detail="With persisted skill choices"
          />
          <SummaryStat
            icon={<BarChart3 className="h-4 w-4" />}
            label="Average draft"
            value={summary.avg_selected_skill_count.toFixed(1)}
            detail="Selected skills per student"
          />
          <SummaryStat
            icon={<Briefcase className="h-4 w-4" />}
            label="Top posting hits"
            value={`${summary.top_interested_postings.length}`}
            detail="Posting trends surfaced"
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Most Selected Skills
            </p>
            <div className="flex flex-wrap gap-2">
              {summary.top_selected_skills.length > 0 ? (
                summary.top_selected_skills.map((skill) => (
                  <Badge key={skill.name} variant="outline" className="gap-1">
                    {skill.name}
                    <span className="text-muted-foreground">{skill.student_count}</span>
                  </Badge>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No saved student skills yet.</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Job Posting Momentum
            </p>
            <div className="flex flex-wrap gap-2">
              {summary.top_interested_postings.length > 0 ? (
                summary.top_interested_postings.map((posting) => (
                  <Badge key={posting.url} variant="outline" className="gap-1">
                    {posting.title || posting.url}
                    <span className="text-muted-foreground">{posting.student_count}</span>
                  </Badge>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">No persisted job-posting interest yet.</p>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
