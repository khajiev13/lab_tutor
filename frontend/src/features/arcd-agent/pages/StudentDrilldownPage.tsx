import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTeacherData } from "@/features/arcd-agent/context/TeacherDataContext";
import {
  fetchStudentPortfolio,
  fetchStudentTwin,
} from "@/features/arcd-agent/api/teacher-twin";
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  BookOpen,
  TrendingUp,
  User,
  Loader2,
} from "lucide-react";
import { MasteryBadge } from "./ClassRosterPage";

// ── Portfolio types (mirrors backend CognitiveDiagnosisService) ─────────────

interface SkillPortfolioItem {
  skill_name: string;
  mastery: number;
  status: string;
  last_practiced: string | null;
  practice_count: number;
}

interface PortfolioData {
  user_id: number;
  course_id: number;
  skills: SkillPortfolioItem[];
  mastered_count: number;
  struggling_count: number;
  in_progress_count: number;
  overall_mastery: number;
  learning_path: string[];
  next_recommended_skill: string | null;
}

interface TwinData {
  [key: string]: unknown;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

function statusColor(status: string) {
  if (status === "mastered") return "text-green-600 dark:text-green-400";
  if (status === "in_progress") return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function statusBg(status: string) {
  if (status === "mastered")
    return "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-800";
  if (status === "in_progress")
    return "bg-yellow-50 border-yellow-200 dark:bg-yellow-950/20 dark:border-yellow-800";
  return "bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-800";
}

// ── Portfolio Tab ──────────────────────────────────────────────────────────

function PortfolioTab({ data }: { data: PortfolioData }) {
  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="p-3 rounded-lg border text-center">
          <p className="text-2xl font-bold">{pct(data.overall_mastery)}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Overall Mastery</p>
        </div>
        <div className="p-3 rounded-lg border text-center">
          <p className="text-2xl font-bold text-green-600 dark:text-green-400">
            {data.mastered_count}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">Mastered</p>
        </div>
        <div className="p-3 rounded-lg border text-center">
          <p className="text-2xl font-bold text-yellow-600 dark:text-yellow-400">
            {data.in_progress_count}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">In Progress</p>
        </div>
        <div className="p-3 rounded-lg border text-center">
          <p className="text-2xl font-bold text-red-600 dark:text-red-400">
            {data.struggling_count}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">Struggling</p>
        </div>
      </div>

      {/* Next recommended */}
      {data.next_recommended_skill && (
        <div className="flex items-center gap-3 p-4 rounded-lg border bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800">
          <TrendingUp className="size-4 text-blue-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-blue-900 dark:text-blue-100">
              Next Recommended Skill
            </p>
            <p className="text-xs text-blue-700 dark:text-blue-300 mt-0.5">
              {data.next_recommended_skill}
            </p>
          </div>
        </div>
      )}

      {/* Skill list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Skill Breakdown ({data.skills.length} selected)</CardTitle>
        </CardHeader>
        <CardContent>
          {data.skills.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No skills selected yet.
            </p>
          ) : (
            <div className="space-y-3">
              {data.skills.map((sk) => (
                <div
                  key={sk.skill_name}
                  className={`flex items-center justify-between p-3 rounded-lg border ${statusBg(sk.status)}`}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{sk.skill_name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`text-xs font-medium capitalize ${statusColor(sk.status)}`}>
                        {sk.status.replace("_", " ")}
                      </span>
                      {sk.practice_count > 0 && (
                        <span className="text-xs text-muted-foreground">
                          · {sk.practice_count} practice{sk.practice_count > 1 ? "s" : ""}
                        </span>
                      )}
                    </div>
                  </div>
                  <MasteryBadge mastery={sk.mastery} />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Learning path */}
      {data.learning_path.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Recommended Learning Path</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {data.learning_path.map((step, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  <Badge className="text-xs">{step}</Badge>
                  {i < data.learning_path.length - 1 && (
                    <span className="text-muted-foreground text-xs">→</span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Raw Twin Tab ───────────────────────────────────────────────────────────

function RawTwinTab({ data }: { data: TwinData }) {
  return (
    <div className="rounded-lg border overflow-auto">
      <pre className="p-4 text-xs text-muted-foreground whitespace-pre-wrap break-all">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function StudentDrilldownPage() {
  const { courseId, classMastery } = useTeacherData();
  const { studentId } = useParams<{ studentId: string }>();
  const base = `/courses/${courseId}/arcd`;

  const studentIdNum = Number(studentId) || 0;

  // Find basic info from roster cache
  const student = classMastery?.students.find((s) => s.user_id === studentIdNum);

  const [portfolio, setPortfolio] = useState<PortfolioData | null>(null);
  const [twin, setTwin] = useState<TwinData | null>(null);
  const [loadingPortfolio, setLoadingPortfolio] = useState(true);
  const [portfolioError, setPortfolioError] = useState("");

  useEffect(() => {
    if (!courseId || !studentIdNum) return;

    const load = async () => {
      setLoadingPortfolio(true);
      setPortfolioError("");
      const [portfolioResult, twinResult] = await Promise.allSettled([
        fetchStudentPortfolio(courseId, studentIdNum),
        fetchStudentTwin(courseId, studentIdNum),
      ]);
      if (portfolioResult.status === "fulfilled") {
        setPortfolio(portfolioResult.value as PortfolioData);
      } else {
        setPortfolioError(
          portfolioResult.reason instanceof Error
            ? portfolioResult.reason.message
            : "Failed to load portfolio.",
        );
      }
      if (twinResult.status === "fulfilled") {
        setTwin(twinResult.value as TwinData);
      }
      setLoadingPortfolio(false);
    };

    load();
  }, [courseId, studentIdNum]);

  return (
    <div className="p-6 space-y-6">
      {/* Back link */}
      <Link
        to={`${base}/roster`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="size-3.5" />
        Back to Roster
      </Link>

      {/* Student header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <User className="size-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">
              {student?.full_name ?? `Student #${studentIdNum}`}
            </h1>
            {student?.email && (
              <p className="text-sm text-muted-foreground">{student.email}</p>
            )}
          </div>
        </div>
        {student && (
          <div className="flex items-center gap-2">
            <MasteryBadge mastery={student.avg_mastery} />
            {student.at_risk ? (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 text-amber-700 dark:text-amber-300">
                <AlertTriangle className="size-3.5" />
                <span className="text-xs font-medium">At Risk</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-green-200 bg-green-50 dark:bg-green-950/30 dark:border-green-800 text-green-700 dark:text-green-300">
                <CheckCircle2 className="size-3.5" />
                <span className="text-xs font-medium">On Track</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Content */}
      {loadingPortfolio ? (
        <div className="flex items-center justify-center h-48 gap-3">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Loading student data…</p>
        </div>
      ) : portfolioError ? (
        <div className="flex items-center justify-center h-48">
          <div className="text-center space-y-2">
            <p className="text-sm text-destructive">{portfolioError}</p>
            <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </div>
        </div>
      ) : (
        <Tabs defaultValue="portfolio">
          <TabsList>
            <TabsTrigger value="portfolio" className="flex items-center gap-1.5">
              <BookOpen className="size-3.5" />
              Portfolio
            </TabsTrigger>
            {twin && (
              <TabsTrigger value="twin" className="flex items-center gap-1.5">
                <TrendingUp className="size-3.5" />
                Twin Data
              </TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="portfolio" className="mt-6">
            {portfolio ? (
              <PortfolioTab data={portfolio} />
            ) : (
              <p className="text-sm text-muted-foreground text-center py-8">
                No portfolio data available.
              </p>
            )}
          </TabsContent>

          {twin && (
            <TabsContent value="twin" className="mt-6">
              <RawTwinTab data={twin} />
            </TabsContent>
          )}
        </Tabs>
      )}
    </div>
  );
}
