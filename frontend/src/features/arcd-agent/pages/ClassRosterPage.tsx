import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useTeacherData } from "@/features/arcd-agent/context/TeacherDataContext";
import { type StudentMasterySummary } from "@/features/arcd-agent/api/teacher-twin";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronDown,
  AlertTriangle,
  CheckCircle2,
  Search,
  ExternalLink,
  RefreshCw,
  Clock,
} from "lucide-react";

// ── Mastery badge ──────────────────────────────────────────────────────────

export function MasteryBadge({ mastery }: { mastery: number }) {
  const pct = Math.round(mastery * 100);
  if (mastery >= 0.8)
    return (
      <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200 border-green-200 font-medium">
        {pct}%
      </Badge>
    );
  if (mastery >= 0.5)
    return (
      <Badge className="bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200 border-yellow-200 font-medium">
        {pct}%
      </Badge>
    );
  return (
    <Badge className="bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200 border-red-200 font-medium">
      {pct}%
    </Badge>
  );
}

// ── Course Progress Bar ────────────────────────────────────────────────────

interface ProgressProps {
  progressPct: number; // weighted course progress %
  mastered: number;   // skills with mastery ≥ 80 %
  developing: number; // skills 50–80 %
  struggling: number; // skills < 50 %
  total: number;      // total course skills
}

function CourseProgressBar({ progressPct, mastered, developing, struggling, total }: ProgressProps) {
  if (total === 0)
    return <span className="text-xs text-muted-foreground tabular-nums">—</span>;

  const safeProgress = Math.max(0, Math.min(100, progressPct));
  const masteredPct    = Math.round((mastered    / total) * 100);
  const developingPct  = Math.round((developing  / total) * 100);
  const strugglingPct  = Math.round((struggling  / total) * 100);
  const notStartedPct  = Math.max(0, 100 - masteredPct - developingPct - strugglingPct);

  // Colour by weighted progress tier (updates continuously as mastery changes)
  const labelColor =
    safeProgress >= 70
      ? "text-emerald-600 dark:text-emerald-400"
      : safeProgress >= 40
        ? "text-amber-600 dark:text-amber-400"
        : "text-red-600 dark:text-red-400";

  const barColor =
    safeProgress >= 70
      ? "#10b981"
      : safeProgress >= 40
        ? "#f59e0b"
        : "#ef4444";

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 min-w-[160px] cursor-default">
            {/* Weighted progress bar */}
            <div className="flex-1 h-2.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
              <div
                className="h-full transition-all duration-500"
                style={{ width: `${safeProgress}%`, backgroundColor: barColor }}
              />
            </div>
            {/* Progress label */}
            <span className={`text-xs font-semibold tabular-nums w-9 text-right ${labelColor}`}>
              {Math.round(safeProgress)}%
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs space-y-1 p-2.5">
          <p className="font-semibold mb-1 text-foreground">Course Progress</p>
          <p className="text-muted-foreground mb-1">
            Weighted formula: avg mastery × selected skills / total course skills
          </p>
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full inline-block bg-emerald-500 flex-shrink-0" />
            <span>Mastered: <strong>{mastered}</strong> skills ({masteredPct}%)</span>
          </div>
          {developing > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full inline-block bg-amber-500 flex-shrink-0" />
              <span>Developing: <strong>{developing}</strong> skills ({developingPct}%)</span>
            </div>
          )}
          {struggling > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full inline-block bg-red-500 flex-shrink-0" />
              <span>Struggling: <strong>{struggling}</strong> skills ({strugglingPct}%)</span>
            </div>
          )}
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <span className="w-2 h-2 rounded-full inline-block bg-zinc-300 flex-shrink-0" />
            <span>Not started: <strong>{total - mastered - developing - struggling}</strong> skills ({notStartedPct}%)</span>
          </div>
          <p className="text-muted-foreground pt-1 border-t border-border">
            Total course skills: <strong>{total}</strong>
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ── Sorting ────────────────────────────────────────────────────────────────

type SortKey =
  | keyof Pick<
      StudentMasterySummary,
      "full_name" | "avg_mastery" | "selected_skill_count" | "mastered_count" | "struggling_count"
    >
  | "completion";

function calcCourseProgressPercent(s: StudentMasterySummary, totalCourseSkills: number): number {
  if (totalCourseSkills <= 0) return 0;
  const selectedRatio = s.selected_skill_count / totalCourseSkills;
  const weighted = s.avg_mastery * selectedRatio * 100;
  return Math.max(0, Math.min(100, weighted));
}

function getSortValue(s: StudentMasterySummary, key: SortKey, total: number): number | string {
  if (key === "completion") return calcCourseProgressPercent(s, total);
  return s[key];
}

function SortHeader({
  label,
  sortKey,
  current,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  current: { key: SortKey; dir: "asc" | "desc" } | null;
  onSort: (k: SortKey) => void;
}) {
  const active = current?.key === sortKey;
  const Icon = active ? (current!.dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <button
      onClick={() => onSort(sortKey)}
      className="flex items-center gap-1 text-sm font-medium hover:text-foreground transition-colors"
    >
      {label}
      <Icon className={`size-3.5 ${active ? "text-primary" : "text-muted-foreground"}`} />
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function ClassRosterPage() {
  const { courseId, classMastery, skillDifficulty, loading, error, refresh, lastUpdated } =
    useTeacherData();
  const base = `/courses/${courseId}/arcd`;

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "at_risk" | "on_track">("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" } | null>({
    key: "completion",
    dir: "desc",
  });

  const students = useMemo(() => classMastery?.students ?? [], [classMastery]);

  // Total skills in the course — used as denominator for completion %
  const totalCourseSkills = skillDifficulty?.skills.length ?? 0;

  const handleSort = (key: SortKey) => {
    setSort((prev) =>
      prev?.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" },
    );
  };

  const filtered = useMemo(() => {
    let rows = students;

    if (statusFilter === "at_risk") rows = rows.filter((s) => s.at_risk);
    else if (statusFilter === "on_track") rows = rows.filter((s) => !s.at_risk);

    const q = search.toLowerCase();
    if (q)
      rows = rows.filter(
        (s) =>
          s.full_name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q),
      );

    if (sort) {
      const { key, dir } = sort;
      rows = [...rows].sort((a, b) => {
        const av = getSortValue(a, key, totalCourseSkills);
        const bv = getSortValue(b, key, totalCourseSkills);
        const cmp =
          typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
        return dir === "asc" ? cmp : -cmp;
      });
    }

    return rows;
  }, [students, search, statusFilter, sort, totalCourseSkills]);

  // Class-wide avg completion %
  const avgCompletion =
    students.length && totalCourseSkills
      ? Math.round(
          students.reduce((sum, s) => sum + calcCourseProgressPercent(s, totalCourseSkills), 0) /
            students.length,
        )
      : null;

  // ── Loading / error states ────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Loading roster…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 p-8">
        <div className="text-center space-y-3">
          <h2 className="text-xl font-semibold text-destructive">Could not load roster</h2>
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

  const atRiskCount = students.filter((s) => s.at_risk).length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Class Roster & Scores</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {students.length} students enrolled
            {atRiskCount > 0 && (
              <span className="ml-2 text-amber-600 dark:text-amber-400 font-medium">
                · {atRiskCount} at risk
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="size-3" />
              Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <Button variant="outline" size="sm" onClick={refresh} className="gap-1.5">
            <RefreshCw className="size-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Summary stats */}
      {classMastery && (
        <div className="grid grid-cols-4 gap-4">
          <div className="p-4 rounded-lg border bg-card text-center">
            <p className="text-2xl font-bold">{classMastery.total_students}</p>
            <p className="text-xs text-muted-foreground mt-0.5">Total Students</p>
          </div>
          <div className="p-4 rounded-lg border bg-card text-center">
            <p className="text-2xl font-bold">
              {Math.round(classMastery.class_avg_mastery * 100)}%
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">Class Avg Mastery</p>
          </div>
          {avgCompletion !== null && (
            <div className="p-4 rounded-lg border bg-card text-center">
              <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                {avgCompletion}%
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">Avg Course Completion</p>
            </div>
          )}
          <div className="p-4 rounded-lg border bg-card text-center">
            <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              {classMastery.at_risk_count}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">At-Risk Students</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search by name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              {statusFilter === "all"
                ? "All Students"
                : statusFilter === "at_risk"
                  ? "At Risk"
                  : "On Track"}
              <ChevronDown className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setStatusFilter("all")}>
              All Students
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setStatusFilter("at_risk")}>
              At Risk Only
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setStatusFilter("on_track")}>
              On Track Only
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Table */}
      <div className="rounded-lg border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead>
                <SortHeader label="Name" sortKey="full_name" current={sort} onSort={handleSort} />
              </TableHead>
              <TableHead>
                <SortHeader
                  label="Course Progress"
                  sortKey="completion"
                  current={sort}
                  onSort={handleSort}
                />
              </TableHead>
              <TableHead>
                <SortHeader
                  label="Avg Mastery"
                  sortKey="avg_mastery"
                  current={sort}
                  onSort={handleSort}
                />
              </TableHead>
              <TableHead>
                <SortHeader
                  label="Skills Selected"
                  sortKey="selected_skill_count"
                  current={sort}
                  onSort={handleSort}
                />
              </TableHead>
              <TableHead>
                <SortHeader
                  label="Mastered"
                  sortKey="mastered_count"
                  current={sort}
                  onSort={handleSort}
                />
              </TableHead>
              <TableHead>
                <SortHeader
                  label="Struggling"
                  sortKey="struggling_count"
                  current={sort}
                  onSort={handleSort}
                />
              </TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length > 0 ? (
              filtered.map((s) => {
                // developing = selected but not mastered and not struggling
                const developing =
                  s.selected_skill_count - s.mastered_count - s.struggling_count;
                const progressPct = calcCourseProgressPercent(s, totalCourseSkills);

                return (
                  <TableRow
                    key={s.user_id}
                    className={s.at_risk ? "bg-amber-50/50 dark:bg-amber-950/10" : ""}
                  >
                    <TableCell>
                      <Link
                        to={`${base}/student/${s.user_id}`}
                        className="font-medium hover:text-primary hover:underline flex items-center gap-1.5"
                      >
                        {s.full_name}
                        <ExternalLink className="size-3 text-muted-foreground" />
                      </Link>
                      <p className="text-xs text-muted-foreground">{s.email}</p>
                    </TableCell>
                    <TableCell>
                      <CourseProgressBar
                        progressPct={progressPct}
                        mastered={s.mastered_count}
                        developing={Math.max(0, developing)}
                        struggling={s.struggling_count}
                        total={totalCourseSkills}
                      />
                    </TableCell>
                    <TableCell>
                      <MasteryBadge mastery={s.avg_mastery} />
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {s.selected_skill_count}
                    </TableCell>
                    <TableCell className="text-sm font-medium text-green-600 dark:text-green-400">
                      {s.mastered_count}
                    </TableCell>
                    <TableCell className="text-sm font-medium text-red-600 dark:text-red-400">
                      {s.struggling_count}
                    </TableCell>
                    <TableCell>
                      {s.at_risk ? (
                        <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                          <AlertTriangle className="size-3.5" />
                          <span className="text-xs font-medium">At Risk</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-green-600 dark:text-green-400">
                          <CheckCircle2 className="size-3.5" />
                          <span className="text-xs font-medium">On Track</span>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            ) : (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                  No students match your filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground text-right">
        Showing {filtered.length} of {students.length} students
        {totalCourseSkills > 0 && (
          <span className="ml-1">· {totalCourseSkills} total course skills</span>
        )}
      </p>
    </div>
  );
}
