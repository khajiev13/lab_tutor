import { Link } from "react-router-dom";
import { Clock3, Eye, Sparkles, type LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getAgentById } from "@/features/agents/config";

type TeacherExplainerAgentId = "architect" | "market-analyst";

type TeacherAgentInsight = {
  kicker: string;
  summary: string;
  teacherMomentTitle: string;
  teacherMomentBody: string;
  studentSurfaceTitle: string;
  studentSurfaceBody: string;
  note: string;
  workspaceLabel: string;
};

const INSIGHT_ICONS: Record<"teacher" | "student" | "note", LucideIcon> = {
  teacher: Clock3,
  student: Eye,
  note: Sparkles,
};

const TEACHER_AGENT_INSIGHTS: Record<TeacherExplainerAgentId, TeacherAgentInsight> = {
  architect: {
    kicker: "Feeds student skill selection",
    summary:
      "The Curricular Alignment Architect prepares the book-backed skills that students later browse on their learning-path page.",
    teacherMomentTitle: "When it runs",
    teacherMomentBody:
      "It runs in the teacher architect workflow, especially through book selection, analysis, and visualization, where course-aligned textbook skills are organized for the class.",
    studentSurfaceTitle: "Where students see it",
    studentSurfaceBody:
      "Students consume its saved results in Book Skill Banks while choosing which book-based skills to include before building a learning path.",
    note:
      "Student clicks do not rerun the architect. The student page is reading the saved book skill bank that this workflow already produced.",
    workspaceLabel: "Open architect workspace",
  },
  "market-analyst": {
    kicker: "Feeds student skill selection",
    summary:
      "The Market Demand Analyst prepares the job-posting skill options that students later review on their learning-path page.",
    teacherMomentTitle: "When it runs",
    teacherMomentBody:
      "It runs in the teacher market-analysis workspace as you confirm search queries, choose job groups, and map extracted skill categories back to the curriculum.",
    studentSurfaceTitle: "Where students see it",
    studentSurfaceBody:
      "Students consume its saved results in Job-Posting Skill Bank while staging posting-based skills before clicking Build My Learning Path.",
    note:
      "Student clicks do not rerun the market analyst. The student page is reading the saved market skill bank that this workflow already produced.",
    workspaceLabel: "Open market analyst",
  },
};

interface TeacherAgentTimingDialogProps {
  agentId: TeacherExplainerAgentId | null;
  courseId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TeacherAgentTimingDialog({
  agentId,
  courseId,
  open,
  onOpenChange,
}: TeacherAgentTimingDialogProps) {
  if (!agentId) {
    return null;
  }

  const agent = getAgentById(agentId);
  const insight = TEACHER_AGENT_INSIGHTS[agentId];

  if (!agent || !insight) {
    return null;
  }

  const AgentIcon = agent.icon;
  const TeacherIcon = INSIGHT_ICONS.teacher;
  const StudentIcon = INSIGHT_ICONS.student;
  const NoteIcon = INSIGHT_ICONS.note;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <div className={`flex size-11 items-center justify-center rounded-2xl ${agent.color}`}>
              <AgentIcon className="size-5" />
            </div>
            <div className="space-y-1">
              <Badge variant="outline" className="rounded-full">
                {insight.kicker}
              </Badge>
              <DialogTitle className="text-xl">{agent.name}</DialogTitle>
            </div>
          </div>
          <DialogDescription className="max-w-2xl text-sm leading-6">
            {insight.summary}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-border/60 shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <TeacherIcon className="size-4 text-primary" />
                {insight.teacherMomentTitle}
              </CardTitle>
              <CardDescription className="text-sm leading-6 text-muted-foreground">
                {insight.teacherMomentBody}
              </CardDescription>
            </CardHeader>
          </Card>

          <Card className="border-border/60 shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <StudentIcon className="size-4 text-primary" />
                {insight.studentSurfaceTitle}
              </CardTitle>
              <CardDescription className="text-sm leading-6 text-muted-foreground">
                {insight.studentSurfaceBody}
              </CardDescription>
            </CardHeader>
          </Card>
        </div>

        <Card className="border-primary/15 bg-primary/5 shadow-none">
          <CardContent className="flex items-start gap-3 p-4">
            <NoteIcon className="mt-0.5 size-4 shrink-0 text-primary" />
            <p className="text-sm leading-6 text-foreground/90">{insight.note}</p>
          </CardContent>
        </Card>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button asChild variant="outline">
            <Link to={`/courses/${courseId}/${agent.route}`}>{insight.workspaceLabel}</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
