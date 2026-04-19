import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTeacherData } from "@/features/arcd-agent/context/TeacherDataContext";
import {
  Users,
  AlertTriangle,
  TrendingUp,
  BookOpen,
  ArrowRight,
  Trophy,
  Target,
  Lightbulb,
} from "lucide-react";

// ── Utilities ──────────────────────────────────────────────────────────────

function masteryColor(m: number): string {
  if (m >= 0.8) return "text-green-600 dark:text-green-400";
  if (m >= 0.5) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

// ── KPI Card ───────────────────────────────────────────────────────────────

function KpiCard({
  title,
  value,
  sub,
  icon: Icon,
  variant = "default",
}: {
  title: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  variant?: "default" | "warning" | "success";
}) {
  const colorMap = {
    default: "text-primary",
    warning: "text-amber-500",
    success: "text-green-500",
  };
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold">{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div className={`p-2 rounded-lg bg-muted ${colorMap[variant]}`}>
            <Icon className="size-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Skill Difficulty Bars ──────────────────────────────────────────────────

function SkillDifficultyChart() {
  const { skillDifficulty } = useTeacherData();
  const top = skillDifficulty?.skills.slice(0, 8) ?? [];

  if (!top.length) {
    return <p className="text-sm text-muted-foreground">No skill data available.</p>;
  }

  return (
    <div className="space-y-2">
      {top.map((s) => (
        <div key={s.skill_name} className="space-y-1">
          <div className="flex items-center justify-between text-sm">
            <span className="truncate max-w-[200px]" title={s.skill_name}>
              {s.skill_name}
            </span>
            <span className={`font-medium text-xs ${masteryColor(s.avg_mastery)}`}>
              {pct(s.avg_mastery)} mastery
            </span>
          </div>
          <div className="h-2 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                s.perceived_difficulty > 0.6
                  ? "bg-red-500"
                  : s.perceived_difficulty > 0.4
                  ? "bg-yellow-500"
                  : "bg-green-500"
              }`}
              style={{ width: `${s.perceived_difficulty * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Rule-based Next Steps ──────────────────────────────────────────────────

interface InsightItem {
  text: string;
  type: "warning" | "next-step" | "tip";
}

const COURSE_TEACHING_TIPS = [
  "Break complex skills into 2–3 sub-concepts before assessing mastery.",
  "Use spaced repetition: revisit skills 3 and 7 days after initial teaching.",
  "Pair high-mastery and low-mastery students for peer instruction exercises.",
  "Set a 70% mastery threshold before advancing to dependent skills in the path.",
  "Frequent low-stakes quizzes (5 questions) outperform single high-stakes assessments for retention.",
  "Review the learning path order — skills with prerequisite gaps slow the whole class.",
  "Label struggling skills early; waiting until exams makes recovery harder.",
];

function useNextSteps(): InsightItem[] {
  const data = useTeacherData();
  return useMemo(() => {
    const items: InsightItem[] = [];
    const { classMastery, skillDifficulty, studentGroups, skillPopularity } = data;

    if ((classMastery?.at_risk_count ?? 0) > 0) {
      const count = classMastery!.at_risk_count;
      items.push({
        text: `${count} student${count > 1 ? "s are" : " is"} at risk (avg mastery < 40%). Schedule a targeted review session before the next topic.`,
        type: "warning",
      });
    }
    if ((skillDifficulty?.skills[0]?.perceived_difficulty ?? 0) > 0.6) {
      const skill = skillDifficulty!.skills[0];
      items.push({
        text: `"${skill.skill_name}" has the highest perceived difficulty (${pct(skill.perceived_difficulty)}). Allocate extra class time or add practice exercises.`,
        type: "next-step",
      });
    }
    if ((classMastery?.class_avg_mastery ?? 1) < 0.5) {
      items.push({
        text: "Class average mastery is below 50%. Consider slowing the pace and reinforcing foundational concepts before introducing new material.",
        type: "next-step",
      });
    }
    if ((studentGroups?.total_groups ?? 0) >= 2) {
      items.push({
        text: `Students are grouped into ${studentGroups!.total_groups} distinct skill clusters. Use group-specific exercises in Teacher Twin to differentiate instruction.`,
        type: "tip",
      });
    }
    if ((skillPopularity?.most_popular[0]?.selection_count ?? 0) > 0) {
      items.push({
        text: `"${skillPopularity!.most_popular[0].skill_name}" is the most-selected skill. Prioritize it in upcoming lectures to meet student interest.`,
        type: "tip",
      });
    }
    if ((classMastery?.class_avg_mastery ?? 0) >= 0.75) {
      items.push({
        text: `Strong class performance — ${pct(classMastery!.class_avg_mastery)} average. Consider introducing stretch goals or advanced topics.`,
        type: "tip",
      });
    }
    return items;
  }, [data]);
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ClassOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const courseId = id ?? "";
  const { loading, error, refresh, classMastery, skillDifficulty, skillPopularity } =
    useTeacherData();
  const base = `/courses/${courseId}/arcd`;

  const ranked = useMemo(
    () =>
      [...(classMastery?.students ?? [])].sort((a, b) => b.avg_mastery - a.avg_mastery),
    [classMastery],
  );

  const nextSteps = useNextSteps();

  const totalStudents = classMastery?.total_students ?? 0;
  const atRisk = classMastery?.at_risk_count ?? 0;
  const classAvg = classMastery?.class_avg_mastery ?? 0;
  const topSkill = skillPopularity?.most_popular[0]?.skill_name ?? "—";
  const hardestSkill = skillDifficulty?.skills[0]?.skill_name ?? "—";

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Loading class data…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 p-8">
        <div className="text-center space-y-3">
          <h2 className="text-xl font-semibold text-destructive">Could not load class data</h2>
          <p className="text-sm text-muted-foreground">{error}</p>
          <button
            onClick={refresh}
            className="px-4 py-2 bg-primary text-primary-foreground text-sm rounded-lg hover:bg-primary/90"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const insightIcon = (type: InsightItem["type"]) => {
    if (type === "warning")
      return <AlertTriangle className="size-3.5 text-amber-500 shrink-0 mt-0.5" />;
    if (type === "next-step")
      return <Target className="size-3.5 text-blue-500 shrink-0 mt-0.5" />;
    return <Lightbulb className="size-3.5 text-primary shrink-0 mt-0.5" />;
  };

  return (
    <div className="p-6 space-y-6">
      {/* ── Header ── */}
      <div>
        <h1 className="text-2xl font-bold">Class Overview</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Real-time analytics for your course
        </p>
      </div>

      {/* ── KPI Strip ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard title="Total Students" value={String(totalStudents)} icon={Users} />
        <KpiCard
          title="Class Avg Mastery"
          value={pct(classAvg)}
          sub="across all selected skills"
          icon={TrendingUp}
          variant={classAvg >= 0.6 ? "success" : "warning"}
        />
        <KpiCard
          title="At-Risk Students"
          value={String(atRisk)}
          sub={`${totalStudents > 0 ? Math.round((atRisk / totalStudents) * 100) : 0}% of class`}
          icon={AlertTriangle}
          variant={atRisk > 0 ? "warning" : "success"}
        />
        <KpiCard
          title="Most Popular Skill"
          value={topSkill.length > 18 ? topSkill.slice(0, 15) + "…" : topSkill}
          icon={BookOpen}
        />
      </div>

      {/* ── Main Section: Skill analysis + insights ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left col (2/3): Skill difficulty + quick actions */}
        <div className="lg:col-span-2 space-y-5">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Top Difficult Skills</CardTitle>
            </CardHeader>
            <CardContent>
              <SkillDifficultyChart />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {[
                {
                  label: "View class roster & scores",
                  href: `${base}/roster`,
                  icon: Users,
                  desc: "Full student list with mastery scores",
                },
                {
                  label: "Teacher Twin",
                  href: `${base}/teacher-twin`,
                  icon: Target,
                  desc: "Cohort analysis, skill simulation & what-if scenarios",
                },
              ].map((action) => (
                <Link
                  key={action.label}
                  to={action.href}
                  className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-md bg-primary/10 text-primary">
                      <action.icon className="size-4" />
                    </div>
                    <div>
                      <p className="text-sm font-medium">{action.label}</p>
                      <p className="text-xs text-muted-foreground">{action.desc}</p>
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                </Link>
              ))}

              {atRisk > 0 && (
                <div className="mt-2 p-3 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/30 dark:border-amber-800">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="size-4 text-amber-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                        {atRisk} student{atRisk > 1 ? "s" : ""} at risk
                      </p>
                      <p className="text-xs text-amber-700 dark:text-amber-300 mt-0.5">
                        Consider reviewing{" "}
                        <span className="font-medium">{hardestSkill}</span> — highest
                        difficulty in class.
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right col (1/3): Suggested next steps */}
        <div>
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="size-4 text-primary" />
                Suggested Next Steps
              </CardTitle>
            </CardHeader>
            <CardContent>
              {nextSteps.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Class is performing well — no urgent actions needed.
                </p>
              ) : (
                <ul className="space-y-3">
                  {nextSteps.map((step, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      {insightIcon(step.type)}
                      <p className="text-sm">{step.text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── Bottom Section: Student ranking + Teaching tips ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Student Ranking */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Trophy className="size-4 text-yellow-500" />
              Student Ranking
            </CardTitle>
          </CardHeader>
          <CardContent>
            {ranked.length === 0 ? (
              <p className="text-sm text-muted-foreground">No student data yet.</p>
            ) : (
              <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                {ranked.map((s, i) => (
                  <Link
                    key={s.user_id}
                    to={`${base}/student/${s.user_id}`}
                    className="flex items-center gap-3 py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors group"
                  >
                    <span
                      className={`w-6 text-center text-xs font-bold shrink-0 ${
                        i === 0
                          ? "text-yellow-500"
                          : i === 1
                          ? "text-slate-400"
                          : i === 2
                          ? "text-amber-600"
                          : "text-muted-foreground"
                      }`}
                    >
                      #{i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                        {s.full_name}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <div className="h-1.5 flex-1 rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              s.avg_mastery >= 0.8
                                ? "bg-green-500"
                                : s.avg_mastery >= 0.5
                                ? "bg-yellow-500"
                                : "bg-red-500"
                            }`}
                            style={{ width: `${s.avg_mastery * 100}%` }}
                          />
                        </div>
                        <span
                          className={`text-xs font-medium shrink-0 ${masteryColor(s.avg_mastery)}`}
                        >
                          {pct(s.avg_mastery)}
                        </span>
                      </div>
                    </div>
                    {s.at_risk && (
                      <AlertTriangle className="size-3.5 text-amber-500 shrink-0" />
                    )}
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Teaching Tips */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Lightbulb className="size-4 text-primary" />
              Course Teaching Tips
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2.5">
              {COURSE_TEACHING_TIPS.map((tip, i) => (
                <li key={i} className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-semibold">
                    {i + 1}
                  </span>
                  <p className="text-sm text-muted-foreground">{tip}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
