import { Link, useParams } from "react-router-dom";
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  CalendarDays,
  Flame,
  FlaskConical,
  GitBranch,
  MapPin,
  Route,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useData } from "@/features/arcd-agent/context/DataContext";
import { useTwin } from "@/features/arcd-agent/context/TwinContext";
import { cn } from "@/lib/utils";

const quickLinks = [
  {
    title: "Student Profile",
    description: "Unified analytics: mastery, growth, chapters, and insights",
    body: "Get a complete picture of this student's strengths, weaknesses, and learning trajectory.",
    icon: BarChart3,
    url: "student",
    colorClass: "bg-blue-100 dark:bg-blue-900/30",
    iconClass: "text-blue-600 dark:text-blue-400",
  },
  {
    title: "Review Session",
    description: "AI-powered adaptive review with guided feedback",
    body: "Start an interactive tutoring session tailored to this student's gaps.",
    icon: BookOpen,
    url: "review",
    colorClass: "bg-green-100 dark:bg-green-900/30",
    iconClass: "text-green-600 dark:text-green-400",
  },
  {
    title: "Learning Path",
    description: "Personalized skill-order recommendations using ARCD",
    body: "Explore the optimal next skills to study, ranked by the cognitive model.",
    icon: Route,
    url: "learning-path",
    colorClass: "bg-purple-100 dark:bg-purple-900/30",
    iconClass: "text-purple-600 dark:text-purple-400",
  },
  {
    title: "Journey Map",
    description: "Skill dependency graph with decay visualization",
    body: "Browse the prerequisite graph, see dependent decay cascades, and identify at-risk paths.",
    icon: MapPin,
    url: "journey",
    colorClass: "bg-teal-100 dark:bg-teal-900/30",
    iconClass: "text-teal-600 dark:text-teal-400",
  },
  {
    title: "Quiz",
    description: "Questions grouped into scored quizzes by skill",
    body: "See how mastery changed after each quiz session, your best scores, and where to improve.",
    icon: FlaskConical,
    url: "quiz-lab",
    colorClass: "bg-violet-100 dark:bg-violet-900/30",
    iconClass: "text-violet-600 dark:text-violet-400",
  },
  {
    title: "Schedule",
    description: "Upcoming study sessions based on spaced repetition",
    body: "View the auto-generated study calendar and daily session plan.",
    icon: CalendarDays,
    url: "schedule",
    colorClass: "bg-indigo-100 dark:bg-indigo-900/30",
    iconClass: "text-indigo-600 dark:text-indigo-400",
  },
  {
    title: "Digital Twin",
    description: "Simulate future mastery trajectories and risk forecasts",
    body: "Run what-if scenarios and visualise projected knowledge decay curves.",
    icon: GitBranch,
    url: "digital-twin",
    colorClass: "bg-orange-100 dark:bg-orange-900/30",
    iconClass: "text-orange-600 dark:text-orange-400",
  },
];

export default function DashboardPage() {
  const { id: courseId } = useParams();
  const { student, currentDataset, portfolioData } = useData();
  const { twinData } = useTwin();

  const accuracy = student ? (student.summary.accuracy * 100).toFixed(1) : null;
  const avgMastery = student ? (student.summary.avg_mastery * 100).toFixed(1) : null;
  const atRiskCount = twinData?.risk_forecast?.total_at_risk ?? null;
  const nextStep = student?.learning_path?.steps?.[0] ?? null;
  const activeDays = student?.summary.active_days ?? 0;
  const hasActivatedSkills =
    (currentDataset?.model_info.n_skills ?? 0) > 0 &&
    (student?.final_mastery.length ?? 0) > 0;

  const studentGreeting = student ? ", Student " + student.uid : "";
  const learningPathHref = courseId ? "/courses/" + courseId + "/learning-path" : "/courses";
  const nextStepSkillName = nextStep?.skill_name ?? "";
  const nextStepMasteryText = nextStep
    ? (nextStep.current_mastery * 100).toFixed(0) + "%"
    : "";
  const nextStepGainText = nextStep
    ? "+" + (nextStep.predicted_mastery_gain * 100).toFixed(1) + "%"
    : "";
  const nextStepSummaryText = nextStep
    ? "Current mastery " + nextStepMasteryText + ". Projected gain " + nextStepGainText
    : "";
  const dashboardSubtitle = currentDataset
    ? currentDataset.name +
      " - " +
      currentDataset.model_info.n_students.toLocaleString() +
      " students - " +
      currentDataset.model_info.n_skills +
      " skills"
    : "Ready to explore your learning data today?";
  const generatedAtText = portfolioData
    ? new Date(portfolioData.generated_at).toLocaleString()
    : "-";
  const datasetCount = portfolioData?.datasets.length ?? 0;
  const datasetLabel = datasetCount === 1 ? "dataset" : "datasets";

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-3">
        <div className="rounded-full bg-primary/10 p-2">
          <Sparkles className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">
            Welcome back
            {studentGreeting}!
          </h1>
          <p className="text-muted-foreground">{dashboardSubtitle}</p>
        </div>
      </div>

      {student && !hasActivatedSkills ? (
        <Card className="border-dashed border-primary/40 bg-primary/5">
          <CardHeader>
            <CardTitle>Activate ARCD</CardTitle>
            <CardDescription>
              Select your book skills and job posting skills first to activate the student dashboard.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Tracked skills: <span className="font-semibold text-foreground">0</span>
            </p>
            <p className="text-sm text-muted-foreground">
              Open My Learning Path and select skills there first. Until then, Student Profile, Journey
              Map, Schedule, Learning Path, Quiz, Review, and Digital Twin will stay inactive.
            </p>
            <Link
              to={learningPathHref}
              className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Select Skills in My Learning Path
            </Link>
          </CardContent>
        </Card>
      ) : null}

      {student ? (
        <div className="flex flex-wrap gap-3 text-sm">
          <div className="flex items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5">
            <span className="text-muted-foreground">Accuracy</span>
            <span className="font-semibold">{accuracy}%</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5">
            <span className="text-muted-foreground">Avg. Mastery</span>
            <span className="font-semibold">{avgMastery}%</span>
          </div>
          <div className="flex items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5">
            <span className="text-muted-foreground">Interactions</span>
            <span className="font-semibold">{student.summary.total_interactions.toLocaleString()}</span>
          </div>
          <div
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5",
              activeDays >= 5 ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted",
            )}
          >
            <Flame
              className={cn(
                "h-4 w-4",
                activeDays >= 5 ? "text-amber-500" : "text-muted-foreground",
              )}
            />
            <span className="text-muted-foreground">Active Days</span>
            <span
              className={cn(
                "font-semibold",
                activeDays >= 5 && "text-amber-600 dark:text-amber-400",
              )}
            >
              {activeDays}
            </span>
          </div>
          {atRiskCount !== null ? (
            <div
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5",
                atRiskCount > 0 ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted",
              )}
            >
              <span className="text-muted-foreground">Skills to Strengthen</span>
              <span
                className={cn(
                  "font-semibold",
                  atRiskCount > 0 && "text-amber-600 dark:text-amber-400",
                )}
              >
                {atRiskCount}
              </span>
            </div>
          ) : null}
        </div>
      ) : null}

      {student && nextStep ? (
        <Link to="review">
          <Card className="cursor-pointer border-primary/30 bg-primary/5 transition-colors hover:bg-primary/10">
            <CardContent className="flex items-center justify-between gap-4 px-5 py-4">
              <div className="flex min-w-0 items-center gap-4">
                <div className="shrink-0 rounded-full bg-primary/15 p-2.5">
                  <ArrowRight className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Continue Learning
                  </p>
                  <p className="truncate text-sm font-semibold">{nextStepSkillName}</p>
                  <p className="text-xs text-muted-foreground">{nextStepSummaryText}</p>
                </div>
              </div>
              <Badge className="shrink-0 bg-primary text-primary-foreground">Start Now</Badge>
            </CardContent>
          </Card>
        </Link>
      ) : null}

      <Separator />

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {quickLinks.map((link) => {
          const Icon = link.icon;

          return (
            <Link key={link.url} to={link.url}>
              <Card className="h-full cursor-pointer transition-shadow hover:shadow-lg">
                <CardHeader>
                  <div className="flex items-center space-x-2">
                    <div className={cn("rounded-lg p-2", link.colorClass)}>
                      <Icon className={cn("h-5 w-5", link.iconClass)} />
                    </div>
                    <CardTitle className="text-lg">{link.title}</CardTitle>
                  </div>
                  <CardDescription>{link.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{link.body}</p>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="pb-4 text-center text-xs text-muted-foreground">
        Generated {generatedAtText} | {datasetCount} {datasetLabel} | ARCD Model
      </div>
    </div>
  );
}
