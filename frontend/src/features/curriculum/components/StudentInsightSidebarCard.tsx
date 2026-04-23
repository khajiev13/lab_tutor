import { BookOpen, Loader2, Users } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type {
  StudentInsightsOverview,
  TeacherStudentInsightDetail,
} from '@/features/curriculum/types';

function ChapterStatusBadge({
  label,
  count,
}: {
  label: string;
  count: number;
}) {
  return (
    <Badge variant="outline" className="justify-center">
      {label}: {count}
    </Badge>
  );
}

export function StudentInsightSidebarCard({
  overview,
  selectedStudentId,
  onSelectStudent,
  detail,
  isLoadingDetail,
}: {
  overview: StudentInsightsOverview;
  selectedStudentId: string | null;
  onSelectStudent: (value: string) => void;
  detail: TeacherStudentInsightDetail | null;
  isLoadingDetail: boolean;
}) {
  const activeStudents = overview.students.filter(
    (student) => student.selected_skill_count > 0 || student.has_learning_path,
  );

  return (
    <Card className="border-border/60 shadow-none">
      <CardHeader className="pb-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-muted-foreground" />
            Student Drill-Down
          </CardTitle>
          <CardDescription>
            Pick a student to overlay their saved learning-path choices onto the current skill
            banks.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <Select value={selectedStudentId ?? undefined} onValueChange={onSelectStudent}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select a student" />
          </SelectTrigger>
          <SelectContent>
            {overview.students.map((student) => (
              <SelectItem key={student.id} value={String(student.id)}>
                {student.full_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {overview.students.length === 0 ? (
          <p className="text-sm text-muted-foreground">No enrolled students yet.</p>
        ) : activeStudents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Students are enrolled, but none have saved learning-path activity yet.
          </p>
        ) : isLoadingDetail ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading student insight…
          </div>
        ) : detail ? (
          <div className="space-y-4">
            <div className="space-y-1">
              <p className="font-medium">{detail.student.full_name}</p>
              <p className="text-xs text-muted-foreground">{detail.student.email}</p>
            </div>

            <div className="grid gap-2">
              <Badge variant="secondary" className="justify-center">
                {detail.learning_path_summary.total_selected_skills} selected skills
              </Badge>
              <Badge variant="secondary" className="justify-center">
                {detail.learning_path_summary.skills_with_resources} skills with resources
              </Badge>
              <Badge
                variant={detail.learning_path_summary.has_learning_path ? 'default' : 'outline'}
                className="justify-center"
              >
                {detail.learning_path_summary.has_learning_path
                  ? 'Saved learning path ready'
                  : 'No saved learning path yet'}
              </Badge>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Chapter Status
              </p>
              <div className="grid gap-2">
                <ChapterStatusBadge
                  label="Locked"
                  count={detail.learning_path_summary.chapter_status_counts.locked}
                />
                <ChapterStatusBadge
                  label="Quiz required"
                  count={detail.learning_path_summary.chapter_status_counts.quiz_required}
                />
                <ChapterStatusBadge
                  label="Learning"
                  count={detail.learning_path_summary.chapter_status_counts.learning}
                />
                <ChapterStatusBadge
                  label="Completed"
                  count={detail.learning_path_summary.chapter_status_counts.completed}
                />
              </div>
            </div>

            <div className="rounded-xl border border-border/60 bg-muted/20 p-3 text-xs text-muted-foreground">
              <div className="flex items-start gap-2">
                <BookOpen className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <p>
                  The overlays in the tabs show which skills {detail.student.full_name} saved and
                  which classmates selected the same skill.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Pick an active student to inspect their saved skills and chapter readiness.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
