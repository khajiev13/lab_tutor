import { Link } from "react-router-dom";
import { useData } from "@/features/arcd-agent/context/DataContext";
import { useTwin } from "@/features/arcd-agent/context/TwinContext";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  BarChart3,
  BookOpen,
  CalendarDays,
  FlaskConical,
  GitBranch,
  MapPin,
  Route,
  Sparkles,
  Flame,
  ArrowRight,
} from "lucide-react";

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
  const { student, currentDataset, portfolioData } = useData();
  const { twinData } = useTwin();

  const accuracy = student
    ? (student.summary.accuracy * 100).toFixed(1)
    : null;
  const avgMastery = student
    ? (student.summary.avg_mastery * 100).toFixed(1)
    : null;
  const atRiskCount = twinData?.risk_forecast?.total_at_risk ?? null;

  // Next recommended skill from learning path
  const nextStep = student?.learning_path?.steps?.[0] ?? null;

  // Streak / consistency indicator
  const activeDays = student?.summary.active_days ?? 0;

  return (
    <div className="space-y-6">
      {/* Welcome section */}
      <div className="flex items-center space-x-3">
        <div className="p-2 rounded-full bg-primary/10">
          <Sparkles className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="text-3xl font-bold">
            Welcome back
            {student ? `, Student ${student.uid}` : ""}!
          </h1>
          <p className="text-muted-foreground">
            {currentDataset
              ? `${currentDataset.name} · ${currentDataset.model_info.n_students.toLocaleString()} students · ${currentDataset.model_info.n_skills} skills`
              : "Ready to explore your learning data today?"}
          </p>
        </div>
      </div>

      {/* Student stat pills */}
      {student && (
        <div className="flex flex-wrap gap-3 text-sm">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted">
            <span className="text-muted-foreground">Accuracy</span>
            <span className="font-semibold">{accuracy}%</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted">
            <span className="text-muted-foreground">Avg. Mastery</span>
            <span className="font-semibold">{avgMastery}%</span>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted">
            <span className="text-muted-foreground">Interactions</span>
            <span className="font-semibold">
              {student.summary.total_interactions.toLocaleString()}
            </span>
          </div>
          {/* Streak / consistency pill */}
          <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${activeDays >= 5 ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted"}`}>
            <Flame className={`h-4 w-4 ${activeDays >= 5 ? "text-amber-500" : "text-muted-foreground"}`} />
            <span className="text-muted-foreground">Active Days</span>
            <span className={`font-semibold ${activeDays >= 5 ? "text-amber-600 dark:text-amber-400" : ""}`}>{activeDays}</span>
          </div>
          {atRiskCount !== null && (
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg ${atRiskCount > 0 ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted"}`}>
              <span className="text-muted-foreground">Skills to Strengthen</span>
              <span className={`font-semibold ${atRiskCount > 0 ? "text-amber-600 dark:text-amber-400" : ""}`}>{atRiskCount}</span>
            </div>
          )}
        </div>
      )}

      {/* Continue Learning CTA */}
      {student && nextStep && (
        <Link to="review">
          <Card className="border-primary/30 bg-primary/5 hover:bg-primary/10 transition-colors cursor-pointer">
            <CardContent className="py-4 px-5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-4 min-w-0">
                <div className="p-2.5 rounded-full bg-primary/15 shrink-0">
                  <ArrowRight className="h-5 w-5 text-primary" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide font-medium">Continue Learning</p>
                  <p className="font-semibold text-sm truncate">{nextStep.skill_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Current mastery {(nextStep.current_mastery * 100).toFixed(0)}% · Projected gain +{(nextStep.predicted_mastery_gain * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
              <Badge className="shrink-0 bg-primary text-primary-foreground">Start Now</Badge>
            </CardContent>
          </Card>
        </Link>
      )}

      <Separator />

      {/* Quick-nav grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {quickLinks.map((link) => (
          <Link key={link.url} to={link.url}>
            <Card className="hover:shadow-lg transition-shadow cursor-pointer h-full">
              <CardHeader>
                <div className="flex items-center space-x-2">
                  <div className={`p-2 rounded-lg ${link.colorClass}`}>
                    <link.icon className={`h-5 w-5 ${link.iconClass}`} />
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
        ))}
      </div>

      {/* Footer */}
      <div className="pb-4 text-center text-xs text-muted-foreground">
        Generated{" "}
        {portfolioData
          ? new Date(portfolioData.generated_at).toLocaleString()
          : "—"}{" "}
        &middot; {portfolioData?.datasets.length ?? 0} dataset
        {portfolioData && portfolioData.datasets.length !== 1 ? "s" : ""}{" "}
        &middot; ARCD Model
      </div>
    </div>
  );
}
