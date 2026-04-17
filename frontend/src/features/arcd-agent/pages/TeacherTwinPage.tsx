import { useState, useMemo, useEffect, useCallback } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from "recharts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useTeacherData } from "@/features/arcd-agent/context/TeacherDataContext";
import {
  simulateSkills,
  runWhatIf,
  fetchStudentPortfolioForTeacher,
  fetchStudentTwinForTeacher,
  type MultiSkillSimulationResponse,
  type SkillSimResult,
  type WhatIfResponse,
  type SkillDifficultyItem,
  type StudentMasterySummary,
} from "@/features/arcd-agent/api/teacher-twin";
import { TwinViewerTab } from "@/features/arcd-agent/components/twin-viewer-tab";
import type { StudentPortfolio, SkillInfo, TwinViewerData } from "@/features/arcd-agent/lib/types";
import {
  Users,
  BookOpen,
  Target,
  AlertTriangle,
  TrendingUp,
  ChevronRight,
  Loader2,
  Play,
  BarChart3,
  LinkIcon,
  Layers,
  ArrowRight,
  CheckCircle2,
  Activity,
  Brain,
  Zap,
  RefreshCw,
  Star,
  UserSearch,
  ChevronDown,
  Lightbulb,
  X,
} from "lucide-react";

// ── Constants ──────────────────────────────────────────────────────────────

const TIER_COLORS = {
  advanced: "#10b981",
  developing: "#f59e0b",
  foundational: "#ef4444",
  class_avg: "#6366f1",
};

const TIER_META = {
  advanced: { label: "Advanced", color: TIER_COLORS.advanced, threshold: [0.8, 1.0] },
  developing: { label: "Developing", color: TIER_COLORS.developing, threshold: [0.5, 0.8] },
  foundational: { label: "Foundational", color: TIER_COLORS.foundational, threshold: [0.0, 0.5] },
};

const TIER_BG: Record<string, string> = {
  advanced: "bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800",
  developing: "bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800",
  foundational: "bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800",
};

const SKILL_PALETTE = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
  "#06b6d4", "#f97316", "#84cc16", "#ec4899", "#14b8a6",
];

// ── Learning Curve Math ────────────────────────────────────────────────────

/**
 * Combined learning-with-decay model.
 * Equilibrium: m_eq = α/(α+λ)   Convergence rate per step: (1−α−λ)
 * When λ=0 degenerates to the classic asymptotic model.
 */
function projectMastery(m0: number, alpha: number, step: number, lambda: number = 0): number {
  const denom = alpha + lambda;
  if (denom <= 0) return Math.min(1, m0);
  const eq   = alpha / denom;              // equilibrium mastery
  const rate = Math.max(0, 1 - denom);     // clamp; sliders keep sum < 1
  return Math.max(0, Math.min(1, eq + (m0 - eq) * Math.pow(rate, step)));
}

function projectDecay(m0: number, lambda: number, step: number): number {
  return Math.max(0.05, m0 * Math.pow(1 - lambda, step));
}

function tierOf(m: number): "advanced" | "developing" | "foundational" {
  if (m >= 0.8) return "advanced";
  if (m >= 0.5) return "developing";
  return "foundational";
}

// ── Utility helpers ────────────────────────────────────────────────────────

function pct(n: number, decimals = 0): string {
  return `${(n * 100).toFixed(decimals)}%`;
}

function masteryBadge(m: number) {
  if (m >= 0.8)
    return (
      <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 text-xs font-semibold">
        {pct(m)}
      </Badge>
    );
  if (m >= 0.5)
    return (
      <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 text-xs font-semibold">
        {pct(m)}
      </Badge>
    );
  return (
    <Badge className="bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 text-xs font-semibold">
      {pct(m)}
    </Badge>
  );
}

// ── Rule-based insights ────────────────────────────────────────────────────

interface RecommendationItem {
  text: string;
  type: "warning" | "next-step" | "tip";
}

function deriveClassInsights(data: ReturnType<typeof useTeacherData>): RecommendationItem[] {
  const items: RecommendationItem[] = [];
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
      text: `"${skill.skill_name}" has the highest difficulty (${pct(skill.perceived_difficulty)}). Allocate extra class time or add practice exercises.`,
      type: "next-step",
    });
  }
  if ((classMastery?.class_avg_mastery ?? 1) < 0.5) {
    items.push({
      text: "Class average mastery is below 50%. Reinforce foundational concepts before introducing new material.",
      type: "next-step",
    });
  }
  if ((studentGroups?.total_groups ?? 0) >= 2) {
    items.push({
      text: `Students span ${studentGroups!.total_groups} performance tiers. Open the "Students Learning Curve" tab to view group-specific learning paths.`,
      type: "tip",
    });
  }
  if ((skillPopularity?.most_popular[0]?.selection_count ?? 0) > 0) {
    items.push({
      text: `"${skillPopularity!.most_popular[0].skill_name}" is the most-selected skill by students. Prioritize it in upcoming lectures.`,
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
}

// ── KPI Card ───────────────────────────────────────────────────────────────

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color?: string;
  trend?: string;
}

function KpiCard({ title, value, subtitle, icon, color = "indigo", trend }: KpiCardProps) {
  const colorMap: Record<string, string> = {
    indigo: "from-indigo-500 to-indigo-600",
    emerald: "from-emerald-500 to-emerald-600",
    amber: "from-amber-500 to-amber-600",
    red: "from-red-500 to-red-600",
  };
  return (
    <Card className="relative overflow-hidden border-0 shadow-sm bg-white dark:bg-zinc-900">
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-1">
              {title}
            </p>
            <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{value}</p>
            {subtitle && (
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{subtitle}</p>
            )}
            {trend && (
              <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400 mt-1 flex items-center gap-1">
                <TrendingUp size={11} />
                {trend}
              </p>
            )}
          </div>
          <div
            className={`w-10 h-10 rounded-xl bg-gradient-to-br ${colorMap[color]} flex items-center justify-center text-white shadow-sm`}
          >
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Overview Tab ───────────────────────────────────────────────────────────

interface OverviewTabProps {
  lastSimResult: MultiSkillSimulationResponse | null;
  lastWhatIfResult: WhatIfResponse | null;
  onNavigate: (tab: string) => void;
}

function OverviewTab({ lastSimResult, lastWhatIfResult, onNavigate }: OverviewTabProps) {
  const data = useTeacherData();
  const { skillPopularity, classMastery } = data;

  const students = classMastery?.students ?? [];
  const classInsights = useMemo(() => deriveClassInsights(data), [data]);

  const distributionData = [
    { bucket: "0–20%", count: students.filter((s) => s.avg_mastery < 0.2).length, color: "#ef4444" },
    { bucket: "20–40%", count: students.filter((s) => s.avg_mastery >= 0.2 && s.avg_mastery < 0.4).length, color: "#f97316" },
    { bucket: "40–60%", count: students.filter((s) => s.avg_mastery >= 0.4 && s.avg_mastery < 0.6).length, color: "#f59e0b" },
    { bucket: "60–80%", count: students.filter((s) => s.avg_mastery >= 0.6 && s.avg_mastery < 0.8).length, color: "#84cc16" },
    { bucket: "80–100%", count: students.filter((s) => s.avg_mastery >= 0.8).length, color: "#10b981" },
  ];

  const atRiskStudents = students.filter((s) => s.at_risk).slice(0, 8);

  const popularityData = (skillPopularity?.all_skills ?? []).slice(0, 8).map((s) => ({
    name: s.skill_name.length > 18 ? s.skill_name.slice(0, 16) + "…" : s.skill_name,
    count: s.selection_count,
  }));

  const hasSimResult = !!lastSimResult;
  const hasWhatIfResult = !!lastWhatIfResult;
  const insightCount =
    classInsights.length + (hasSimResult ? 1 : 0) + (hasWhatIfResult ? 1 : 0);

  const insightIcon = (type: "warning" | "next-step" | "tip") => {
    if (type === "warning")
      return <AlertTriangle size={13} className="text-amber-500 flex-shrink-0 mt-0.5" />;
    if (type === "next-step")
      return <Target size={13} className="text-blue-500 flex-shrink-0 mt-0.5" />;
    return <Lightbulb size={13} className="text-indigo-500 flex-shrink-0 mt-0.5" />;
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* ── Mastery Distribution ── */}
        <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <BarChart3 size={15} className="text-indigo-500" />
              Student Mastery Distribution
            </CardTitle>
            <CardDescription className="text-xs">
              Number of students by mastery level
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={distributionData} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip
                  formatter={(v: number) => [v, "Students"]}
                  contentStyle={{ fontSize: 11, borderRadius: 8 }}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} barSize={32}>
                  {distributionData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            {atRiskStudents.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-2 flex items-center gap-1">
                  <AlertTriangle size={12} />
                  At-Risk Students ({classMastery?.at_risk_count})
                </p>
                <div className="space-y-1.5">
                  {atRiskStudents.map((s) => (
                    <div
                      key={s.user_id}
                      className="flex items-center justify-between text-xs bg-red-50 dark:bg-red-900/20 px-2.5 py-1.5 rounded-lg"
                    >
                      <span className="text-zinc-700 dark:text-zinc-300 font-medium">
                        {s.full_name}
                      </span>
                      <div className="flex items-center gap-2">
                        {masteryBadge(s.avg_mastery)}
                        {s.pco_count > 0 && (
                          <span className="text-red-500 text-xs">{s.pco_count} PCO</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* ── Teacher Recommendations ── */}
        <Card className="border border-indigo-100 dark:border-indigo-900 bg-gradient-to-br from-indigo-50/60 to-white dark:from-indigo-950/20 dark:to-zinc-900 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Lightbulb size={15} className="text-indigo-500" />
              Teacher Recommendations
              {insightCount > 0 && (
                <Badge className="ml-1 bg-indigo-100 text-indigo-700 text-xs border-0">
                  {insightCount}
                </Badge>
              )}
              {(hasSimResult || hasWhatIfResult) && (
                <Badge className="ml-auto bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300 text-xs border-0 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Live
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-xs">
              Automatically updates as you run analyses
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Class status insights */}
            {classInsights.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
                  Class Status
                </p>
                <div className="space-y-1.5">
                  {classInsights.map((item, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 text-xs bg-white dark:bg-zinc-800/60 px-2.5 py-2 rounded-lg border border-zinc-100 dark:border-zinc-800"
                    >
                      {insightIcon(item.type)}
                      <p className="text-zinc-700 dark:text-zinc-300 leading-relaxed">
                        {item.text}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Simulator insights */}
            {hasSimResult && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                    Simulator Analysis
                  </p>
                  <button
                    onClick={() => onNavigate("simulator")}
                    className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 flex items-center gap-0.5"
                  >
                    View full <ChevronRight size={11} />
                  </button>
                </div>
                {lastSimResult!.llm_insights && (
                  <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg px-3 py-2.5 text-xs text-zinc-700 dark:text-zinc-300 border border-indigo-100 dark:border-indigo-800">
                    <p className="line-clamp-3 leading-relaxed">{lastSimResult!.llm_insights}</p>
                  </div>
                )}
                {(lastSimResult!.auto_selected_skills?.length ?? 0) > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="text-xs text-zinc-400">Focus skills:</span>
                    {lastSimResult!.auto_selected_skills.slice(0, 4).map((sk) => (
                      <span
                        key={sk}
                        className="text-xs px-1.5 py-0.5 rounded-full bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800"
                      >
                        {sk}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* What-if insights */}
            {hasWhatIfResult && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                    What-If Analysis
                  </p>
                  <button
                    onClick={() => onNavigate("whatif")}
                    className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 flex items-center gap-0.5"
                  >
                    View full <ChevronRight size={11} />
                  </button>
                </div>
                <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2.5 text-xs text-zinc-700 dark:text-zinc-300 border border-amber-100 dark:border-amber-800 mb-2">
                  {lastWhatIfResult!.summary}
                </div>
                {lastWhatIfResult!.recommendations?.slice(0, 2).map((r, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-1.5 text-xs text-zinc-600 dark:text-zinc-400 py-1"
                  >
                    <ChevronRight size={11} className="text-amber-400 mt-0.5 flex-shrink-0" />
                    {r}
                  </div>
                ))}
              </div>
            )}

            {/* CTA when no simulation results */}
            {!hasSimResult && !hasWhatIfResult && (
              <div className="border-t border-zinc-100 dark:border-zinc-800 pt-3">
                <p className="text-xs text-zinc-400 flex items-start gap-1.5">
                  <Zap size={11} className="text-indigo-400 mt-0.5 flex-shrink-0" />
                  <span>
                    Run the{" "}
                    <button
                      onClick={() => onNavigate("simulator")}
                      className="text-indigo-600 dark:text-indigo-400 font-medium hover:underline"
                    >
                      Skill Simulator
                    </button>{" "}
                    or{" "}
                    <button
                      onClick={() => onNavigate("whatif")}
                      className="text-indigo-600 dark:text-indigo-400 font-medium hover:underline"
                    >
                      What-If Analysis
                    </button>{" "}
                    to get personalized AI-driven recommendations that appear here.
                  </span>
                </p>
              </div>
            )}

            {classInsights.length === 0 && !hasSimResult && !hasWhatIfResult && (
              <p className="text-xs text-zinc-400 text-center py-2">
                No class data loaded yet.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Skill Popularity */}
      <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Star size={15} className="text-amber-500" />
            Skill Popularity
          </CardTitle>
          <CardDescription className="text-xs">
            How many students selected each skill
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={popularityData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip
                formatter={(v: number) => [v, "Students"]}
                contentStyle={{ fontSize: 11, borderRadius: 8 }}
              />
              <Bar dataKey="count" fill="#f59e0b" radius={[4, 4, 0, 0]} barSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Cohort Tab (Learning Curves + Groups merged) ───────────────────────────

interface LcConfig {
  steps: number;
  alpha: number;
  lambda: number;
  showBaseline: boolean;
  showIndividuals: boolean;
  mode: "groups" | "skills";
  selectedSkills: string[];
}

function CohortTab() {
  const { classMastery, skillDifficulty, studentGroups } = useTeacherData();
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  const [cfg, setCfg] = useState<LcConfig>({
    steps: 10,
    alpha: 0.15,
    lambda: 0.03,
    showBaseline: true,
    showIndividuals: false,
    mode: "groups",
    selectedSkills: [],
  });

  const students = useMemo(() => classMastery?.students ?? [], [classMastery]);
  const skills = useMemo(() => skillDifficulty?.skills ?? [], [skillDifficulty]);
  const groups = studentGroups?.groups ?? [];

  // ── Tier summary ──────────────────────────────────────────────────────────
  const groupedStudents = useMemo(() => ({
    advanced: students.filter((s) => s.avg_mastery >= 0.8),
    developing: students.filter((s) => s.avg_mastery >= 0.5 && s.avg_mastery < 0.8),
    foundational: students.filter((s) => s.avg_mastery < 0.5),
  }), [students]);

  const groupAvg = (group: StudentMasterySummary[]) =>
    group.length ? group.reduce((a, s) => a + s.avg_mastery, 0) / group.length : null;

  const classAvgM0 = students.length
    ? students.reduce((a, s) => a + s.avg_mastery, 0) / students.length
    : 0;

  // ── Learning Curves chart data ────────────────────────────────────────────
  const groupChartData = useMemo(() => {
    const rows = [];
    for (let t = 0; t <= cfg.steps; t++) {
      const row: Record<string, number | null> = { step: t };
      for (const [tid, group] of Object.entries(groupedStudents)) {
        const m0 = groupAvg(group);
        if (m0 !== null) {
          row[tid] = +(projectMastery(m0, cfg.alpha, t, cfg.lambda) * 100).toFixed(1);
          if (cfg.showBaseline)
            row[`${tid}_base`] = +(projectDecay(m0, cfg.lambda, t) * 100).toFixed(1);
        }
      }
      row["class_avg"] = +(projectMastery(classAvgM0, cfg.alpha, t, cfg.lambda) * 100).toFixed(1);
      if (cfg.showBaseline)
        row["class_avg_base"] = +(projectDecay(classAvgM0, cfg.lambda, t) * 100).toFixed(1);
      if (cfg.showIndividuals) {
        students.forEach((s) => {
          row[`stu_${s.user_id}`] = +(projectMastery(s.avg_mastery, cfg.alpha, t, cfg.lambda) * 100).toFixed(1);
        });
      }
      rows.push(row);
    }
    return rows;
  }, [cfg, groupedStudents, students, classAvgM0]);

  const skillChartData = useMemo(() => {
    const selectedSkills = cfg.selectedSkills.length
      ? skills.filter((s) => cfg.selectedSkills.includes(s.skill_name))
      : skills.slice(0, 5);
    const rows = [];
    for (let t = 0; t <= cfg.steps; t++) {
      const row: Record<string, number | null | string> = { step: t };
      selectedSkills.forEach((s) => {
        const key = s.skill_name.slice(0, 20);
        row[key] = +(projectMastery(s.avg_mastery, cfg.alpha, t, cfg.lambda) * 100).toFixed(1);
        if (cfg.showBaseline)
          row[`${key}_base`] = +(projectDecay(s.avg_mastery, cfg.lambda, t) * 100).toFixed(1);
      });
      rows.push(row);
    }
    return { data: rows, skills: selectedSkills };
  }, [cfg, skills]);

  const endClassMastery = +(projectMastery(classAvgM0, cfg.alpha, cfg.steps, cfg.lambda) * 100).toFixed(1);
  const studentsAt80 = students.filter(
    (s) => projectMastery(s.avg_mastery, cfg.alpha, cfg.steps, cfg.lambda) >= 0.8,
  ).length;
  const improvementPts = +(endClassMastery - classAvgM0 * 100).toFixed(1);

  // ── Group comparison chart ────────────────────────────────────────────────
  const groupComparisonData = groups.map((g) => ({
    name: g.group_name.replace(" Learners", ""),
    mastery: Math.round(g.group_avg_mastery * 100),
    members: g.member_count,
  }));

  return (
    <div className="space-y-5">
      {/* ── Tier Summary Strip ── */}
      <div className="grid grid-cols-3 gap-3">
        {(["advanced", "developing", "foundational"] as const).map((tier) => {
          const group = groupedStudents[tier];
          const m0 = groupAvg(group);
          const mEnd = m0 !== null ? projectMastery(m0, cfg.alpha, cfg.steps, cfg.lambda) : null;
          return (
            <div key={tier} className={`rounded-xl border p-3 ${TIER_BG[tier]}`}>
              <div className="flex items-center gap-2 mb-1.5">
                <div
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: TIER_COLORS[tier] }}
                />
                <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                  {TIER_META[tier].label}
                </span>
                <span className="text-xs text-zinc-400 ml-auto font-mono">
                  {group.length} students
                </span>
              </div>
              {m0 !== null ? (
                <p className="text-xs text-zinc-500">
                  Now: <strong>{pct(m0)}</strong>
                  {mEnd !== null && (
                    <>
                      {" "}→ W{cfg.steps}:{" "}
                      <strong style={{ color: TIER_COLORS[tier] }}>{pct(mEnd)}</strong>
                    </>
                  )}
                </p>
              ) : (
                <p className="text-xs text-zinc-400 italic">No students</p>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Section: Groups & Learning Paths ── */}
      <div className="space-y-4">
          {/* Group comparison mini chart */}
          {groupComparisonData.length > 0 && (
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BarChart3 size={15} className="text-indigo-500" />
                  Group Performance Comparison
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart
                    data={groupComparisonData}
                    margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: number, key: string) => [
                        key === "mastery" ? `${v}%` : v,
                        key === "mastery" ? "Avg Mastery" : "Students",
                      ]}
                      contentStyle={{ fontSize: 11, borderRadius: 8 }}
                    />
                    <ReferenceLine y={80} stroke="#10b981" strokeDasharray="3 3" />
                    <Bar dataKey="mastery" radius={[6, 6, 0, 0]} barSize={48}>
                      {groupComparisonData.map((_, i) => {
                        const tiers = ["advanced", "developing", "foundational"];
                        return (
                          <Cell
                            key={i}
                            fill={TIER_COLORS[tiers[i] as keyof typeof TIER_COLORS] || "#6366f1"}
                          />
                        );
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Group cards */}
          <div className="space-y-3">
            {groups.map((g) => {
              const isExpanded = expandedGroup === g.group_id;
              const tier = g.performance_tier;
              const tierColor = TIER_COLORS[tier as keyof typeof TIER_COLORS] || "#6366f1";

              return (
                <Card
                  key={g.group_id}
                  className={`border transition-all duration-200 ${TIER_BG[tier] ?? "bg-white"}`}
                >
                  <CardHeader className="pb-2">
                    <button
                      className="w-full flex items-center justify-between"
                      onClick={() => setExpandedGroup(isExpanded ? null : g.group_id)}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className="w-8 h-8 rounded-lg flex items-center justify-center"
                          style={{ backgroundColor: tierColor + "20" }}
                        >
                          {tier === "advanced" ? (
                            <Star size={14} className="text-emerald-600" />
                          ) : tier === "developing" ? (
                            <TrendingUp size={14} className="text-amber-600" />
                          ) : (
                            <AlertTriangle size={14} className="text-red-600" />
                          )}
                        </div>
                        <div className="text-left">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                              {g.group_name}
                            </span>
                            <Badge
                              className="text-xs"
                              style={{
                                backgroundColor: tierColor + "20",
                                color: tierColor,
                              }}
                            >
                              {g.member_count} students
                            </Badge>
                          </div>
                          <p className="text-xs text-zinc-500 mt-0.5">
                            Avg mastery:{" "}
                            <strong style={{ color: tierColor }}>
                              {pct(g.group_avg_mastery)}
                            </strong>
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="w-24">
                          <Progress
                            value={g.group_avg_mastery * 100}
                            className="h-1.5"
                            style={
                              {
                                "--progress-indicator-color": tierColor,
                              } as React.CSSProperties
                            }
                          />
                        </div>
                        <ChevronRight
                          size={14}
                          className={`text-zinc-400 transition-transform ${isExpanded ? "rotate-90" : ""}`}
                        />
                      </div>
                    </button>
                  </CardHeader>

                  {isExpanded && (
                    <CardContent className="pt-0">
                      <Separator className="mb-3" />
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-2 flex items-center gap-1.5">
                            <ArrowRight size={12} />
                            Suggested Learning Path
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {g.suggested_path.slice(0, 6).map((skill, i) => (
                              <span
                                key={i}
                                className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border"
                                style={{ borderColor: tierColor + "40", color: tierColor }}
                              >
                                <span className="font-medium">{i + 1}.</span> {skill}
                              </span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-2 flex items-center gap-1.5">
                            <Users size={12} />
                            Members
                          </p>
                          <div className="space-y-1.5 max-h-36 overflow-y-auto">
                            {g.members.map((m) => {
                              const fullStudent = students.find((s) => s.user_id === m.user_id);
                              return (
                                <div
                                  key={m.user_id}
                                  className="flex items-center justify-between text-xs"
                                >
                                  <span className="text-zinc-700 dark:text-zinc-300">
                                    {m.full_name}
                                  </span>
                                  <div className="flex items-center gap-2">
                                    {masteryBadge(m.avg_mastery)}
                                    {fullStudent?.at_risk && (
                                      <AlertTriangle size={11} className="text-red-500" />
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                      {g.skill_set.length > 0 && (
                        <div className="mt-3">
                          <p className="text-xs font-medium text-zinc-500 mb-1.5">
                            Shared Skills:
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {g.skill_set.slice(0, 10).map((sk) => (
                              <span
                                key={sk}
                                className="text-xs bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 px-2 py-0.5 rounded"
                              >
                                {sk}
                              </span>
                            ))}
                            {g.skill_set.length > 10 && (
                              <span className="text-xs text-zinc-400">
                                +{g.skill_set.length - 10} more
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  )}
                </Card>
              );
            })}
            {groups.length === 0 && (
              <div className="text-center text-zinc-400 py-10 text-sm">
                No student groups found for this course.
              </div>
            )}
          </div>
        </div>

      {/* ── Section: Learning Curves ── */}
      <div className="space-y-4">
          {/* Config Panel */}
          <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Activity size={15} className="text-indigo-500" />
                Simulation Parameters
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
                <div className="space-y-2">
                  <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Projection Steps (weeks):{" "}
                    <span className="text-zinc-900 dark:text-zinc-100 font-semibold">
                      {cfg.steps}
                    </span>
                  </Label>
                  <Slider
                    value={[cfg.steps]}
                    onValueChange={([v]) => setCfg((c) => ({ ...c, steps: v }))}
                    min={4}
                    max={20}
                    step={1}
                    className="w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Learning Rate (α):{" "}
                    <span className="text-zinc-900 dark:text-zinc-100 font-semibold">
                      {(cfg.alpha * 100).toFixed(0)}%/week
                    </span>
                  </Label>
                  <Slider
                    value={[cfg.alpha * 100]}
                    onValueChange={([v]) => setCfg((c) => ({ ...c, alpha: v / 100 }))}
                    min={5}
                    max={35}
                    step={1}
                    className="w-full"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Decay Rate (λ):{" "}
                    <span className="text-zinc-900 dark:text-zinc-100 font-semibold">
                      {(cfg.lambda * 100).toFixed(0)}%/week
                    </span>
                  </Label>
                  <Slider
                    value={[cfg.lambda * 100]}
                    onValueChange={([v]) => setCfg((c) => ({ ...c, lambda: v / 100 }))}
                    min={1}
                    max={15}
                    step={1}
                    className="w-full"
                  />
                </div>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="show-baseline"
                      checked={cfg.showBaseline}
                      onCheckedChange={(ch) => setCfg((c) => ({ ...c, showBaseline: !!ch }))}
                    />
                    <Label htmlFor="show-baseline" className="text-xs cursor-pointer">
                      Show decay (no intervention)
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="show-individuals"
                      checked={cfg.showIndividuals}
                      onCheckedChange={(ch) =>
                        setCfg((c) => ({ ...c, showIndividuals: !!ch }))
                      }
                    />
                    <Label htmlFor="show-individuals" className="text-xs cursor-pointer">
                      Show individual students
                    </Label>
                  </div>
                </div>
              </div>
              <div className="flex gap-2 mt-4">
                <Button
                  variant={cfg.mode === "groups" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setCfg((c) => ({ ...c, mode: "groups" }))}
                  className="text-xs h-7"
                >
                  <Users size={12} className="mr-1.5" />
                  By Performance Group
                </Button>
                <Button
                  variant={cfg.mode === "skills" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setCfg((c) => ({ ...c, mode: "skills" }))}
                  className="text-xs h-7"
                >
                  <BookOpen size={12} className="mr-1.5" />
                  By Skill
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Stats Strip */}
          <div className="grid grid-cols-3 gap-3">
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                  {endClassMastery}%
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">
                  Projected Class Avg ({cfg.steps}w)
                </p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                  {studentsAt80}
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">Students Reaching 80% Target</p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardContent className="p-4 text-center">
                <p className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                  +{improvementPts}%
                </p>
                <p className="text-xs text-zinc-500 mt-0.5">Class Mastery Gain</p>
              </CardContent>
            </Card>
          </div>

          {cfg.mode === "groups" ? (
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <TrendingUp size={15} className="text-indigo-500" />
                  Performance Group Learning Curves
                </CardTitle>
                <CardDescription className="text-xs">
                  Projected mastery over {cfg.steps} weeks · Dashed = without intervention (decay)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={380}>
                  <LineChart
                    data={groupChartData}
                    margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="step"
                      tickFormatter={(v) => `W${v}`}
                      tick={{ fontSize: 11 }}
                      label={{ value: "Week", position: "insideBottom", offset: -4, fontSize: 11 }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: number, name: string) => {
                        if (name.includes("_base")) return null;
                        return [`${v}%`, name];
                      }}
                      contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0" }}
                      labelFormatter={(l) => `Week ${l}`}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      formatter={(name) => {
                        if (name.includes("_base") || name.startsWith("stu_")) return null;
                        return name;
                      }}
                    />
                    <ReferenceLine
                      y={80}
                      stroke="#10b981"
                      strokeDasharray="4 4"
                      strokeWidth={1.5}
                      label={{ value: "80% Target", position: "right", fontSize: 10, fill: "#10b981" }}
                    />
                    {cfg.showIndividuals &&
                      students.map((s) => {
                        const tier = tierOf(s.avg_mastery);
                        return (
                          <Line
                            key={`stu_${s.user_id}`}
                            dataKey={`stu_${s.user_id}`}
                            stroke={TIER_COLORS[tier]}
                            strokeWidth={1}
                            strokeOpacity={0.25}
                            dot={false}
                            legendType="none"
                            activeDot={false}
                            name={`stu_${s.user_id}`}
                          />
                        );
                      })}
                    {cfg.showBaseline &&
                      (["advanced", "developing", "foundational"] as const).map((tid) =>
                        groupedStudents[tid].length ? (
                          <Line
                            key={`${tid}_base`}
                            dataKey={`${tid}_base`}
                            stroke={TIER_COLORS[tid]}
                            strokeWidth={1.5}
                            strokeDasharray="4 4"
                            strokeOpacity={0.5}
                            dot={false}
                            legendType="none"
                            activeDot={false}
                            name={`${tid}_base`}
                          />
                        ) : null,
                      )}
                    {(["advanced", "developing", "foundational"] as const).map((tid) =>
                      groupedStudents[tid].length ? (
                        <Line
                          key={tid}
                          dataKey={tid}
                          stroke={TIER_COLORS[tid]}
                          strokeWidth={3}
                          dot={{ r: 3, fill: TIER_COLORS[tid], strokeWidth: 0 }}
                          activeDot={{ r: 5 }}
                          name={`${TIER_META[tid].label} (${groupedStudents[tid].length})`}
                        />
                      ) : null,
                    )}
                    <Line
                      dataKey="class_avg"
                      stroke={TIER_COLORS.class_avg}
                      strokeWidth={2}
                      strokeDasharray="6 3"
                      dot={false}
                      name="Class Average"
                    />
                  </LineChart>
                </ResponsiveContainer>

                <div className="grid grid-cols-3 gap-3 mt-4">
                  {(["advanced", "developing", "foundational"] as const).map((tid) => {
                    const group = groupedStudents[tid];
                    if (!group.length) return null;
                    const m0 = groupAvg(group)!;
                    const mEnd = projectMastery(m0, cfg.alpha, cfg.steps, cfg.lambda);
                    return (
                      <div
                        key={tid}
                        className="rounded-xl border p-3"
                        style={{ borderColor: TIER_COLORS[tid] + "40" }}
                      >
                        <div className="flex items-center gap-1.5 mb-2">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: TIER_COLORS[tid] }}
                          />
                          <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300">
                            {TIER_META[tid].label}
                          </span>
                          <span className="text-xs text-zinc-400 ml-auto">{group.length}</span>
                        </div>
                        <p className="text-xs text-zinc-500">
                          Now: <strong>{pct(m0)}</strong> → Projected:{" "}
                          <strong style={{ color: TIER_COLORS[tid] }}>{pct(mEnd)}</strong>
                        </p>
                        <p className="text-xs text-zinc-400 mt-0.5">
                          +{((mEnd - m0) * 100).toFixed(1)} pts gain
                        </p>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpen size={15} className="text-indigo-500" />
                  Skill Learning Curves Comparison
                </CardTitle>
                <CardDescription className="text-xs">
                  Projected class mastery per skill over {cfg.steps} weeks
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="mb-4">
                  <p className="text-xs font-medium text-zinc-500 mb-2">
                    Select skills to compare (default: top 5 by difficulty):
                  </p>
                  <ScrollArea className="h-28">
                    <div className="grid grid-cols-2 gap-1.5">
                      {skills.map((s, i) => (
                        <div key={s.skill_name} className="flex items-center gap-1.5">
                          <Checkbox
                            id={`skill-lc-${i}`}
                            checked={cfg.selectedSkills.includes(s.skill_name)}
                            onCheckedChange={(ch) =>
                              setCfg((c) => ({
                                ...c,
                                selectedSkills: ch
                                  ? [...c.selectedSkills, s.skill_name]
                                  : c.selectedSkills.filter((n) => n !== s.skill_name),
                              }))
                            }
                          />
                          <Label htmlFor={`skill-lc-${i}`} className="text-xs cursor-pointer truncate">
                            {s.skill_name}
                          </Label>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>

                <ResponsiveContainer width="100%" height={340}>
                  <LineChart
                    data={skillChartData.data}
                    margin={{ top: 8, right: 24, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis
                      dataKey="step"
                      tickFormatter={(v) => `W${v}`}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(v: number, name: string) => {
                        if (name.includes("_base")) return null;
                        return [`${v}%`, name];
                      }}
                      contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e8f0" }}
                      labelFormatter={(l) => `Week ${l}`}
                    />
                    <Legend wrapperStyle={{ fontSize: 10 }} />
                    <ReferenceLine
                      y={80}
                      stroke="#10b981"
                      strokeDasharray="4 4"
                      strokeWidth={1.5}
                      label={{ value: "80% Target", position: "right", fontSize: 10, fill: "#10b981" }}
                    />
                    {skillChartData.skills.map((s, i) => {
                      const key = s.skill_name.slice(0, 20);
                      const color = SKILL_PALETTE[i % SKILL_PALETTE.length];
                      return (
                        <Line
                          key={key}
                          dataKey={key}
                          stroke={color}
                          strokeWidth={2.5}
                          dot={{ r: 3, fill: color, strokeWidth: 0 }}
                          activeDot={{ r: 5 }}
                          name={s.skill_name}
                        />
                      );
                    })}
                    {cfg.showBaseline &&
                      skillChartData.skills.map((s, i) => {
                        const key = s.skill_name.slice(0, 20);
                        const color = SKILL_PALETTE[i % SKILL_PALETTE.length];
                        return (
                          <Line
                            key={`${key}_base`}
                            dataKey={`${key}_base`}
                            stroke={color}
                            strokeWidth={1}
                            strokeDasharray="4 4"
                            strokeOpacity={0.4}
                            dot={false}
                            legendType="none"
                            activeDot={false}
                            name={`${key}_base`}
                          />
                        );
                      })}
                  </LineChart>
                </ResponsiveContainer>

                <div className="mt-4 rounded-xl border border-zinc-100 dark:border-zinc-800 overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-zinc-50 dark:bg-zinc-800/50">
                        <th className="text-left px-3 py-2 text-zinc-500 font-medium">Skill</th>
                        <th className="text-right px-3 py-2 text-zinc-500 font-medium">Now</th>
                        <th className="text-right px-3 py-2 text-zinc-500 font-medium">Week {cfg.steps}</th>
                        <th className="text-right px-3 py-2 text-zinc-500 font-medium">Gain</th>
                        <th className="text-right px-3 py-2 text-zinc-500 font-medium">Students</th>
                      </tr>
                    </thead>
                    <tbody>
                      {skillChartData.skills.map((s, i) => {
                        const mEnd = projectMastery(s.avg_mastery, cfg.alpha, cfg.steps, cfg.lambda);
                        const gain = ((mEnd - s.avg_mastery) * 100).toFixed(1);
                        return (
                          <tr
                            key={s.skill_name}
                            className="border-t border-zinc-100 dark:border-zinc-800 hover:bg-zinc-50 dark:hover:bg-zinc-800/30"
                          >
                            <td className="px-3 py-2 flex items-center gap-1.5">
                              <div
                                className="w-2 h-2 rounded-full flex-shrink-0"
                                style={{ backgroundColor: SKILL_PALETTE[i % SKILL_PALETTE.length] }}
                              />
                              <span className="text-zinc-700 dark:text-zinc-300 truncate max-w-[180px]">
                                {s.skill_name}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-right font-mono">{pct(s.avg_mastery)}</td>
                            <td
                              className="px-3 py-2 text-right font-mono font-semibold"
                              style={{ color: SKILL_PALETTE[i % SKILL_PALETTE.length] }}
                            >
                              {pct(mEnd)}
                            </td>
                            <td className="px-3 py-2 text-right text-emerald-600 dark:text-emerald-400 font-medium">
                              +{gain}%
                            </td>
                            <td className="px-3 py-2 text-right text-zinc-500">{s.student_count}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
      </div>
    </div>
  );
}

// ── Skill Simulation Tab ───────────────────────────────────────────────────

function CoherenceLabel({ label }: { label: string }) {
  if (label === "High")
    return (
      <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
        High Coherence
      </Badge>
    );
  if (label === "Medium")
    return (
      <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
        Medium Coherence
      </Badge>
    );
  return (
    <Badge className="bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">
      Low Coherence
    </Badge>
  );
}

function SkillExerciseCard({ result }: { result: SkillSimResult }) {
  const [revealed, setRevealed] = useState(false);
  const diff = result.perceived_difficulty;
  const diffColor = diff > 0.7 ? "#ef4444" : diff > 0.4 ? "#f59e0b" : "#10b981";

  return (
    <Card className="border border-zinc-100 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/50">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-sm font-semibold text-zinc-800 dark:text-zinc-200 leading-tight">
            {result.skill_name}
          </CardTitle>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span
              className="text-xs font-semibold px-2 py-0.5 rounded-full"
              style={{ backgroundColor: diffColor + "20", color: diffColor }}
            >
              {pct(diff)} difficulty
            </span>
          </div>
        </div>
        <div className="flex gap-3 text-xs text-zinc-500 mt-1">
          <span>Class avg: <strong>{pct(result.avg_class_mastery)}</strong></span>
          <span>Simulated: <strong>{pct(result.simulated_mastery)}</strong></span>
          <span>{result.student_count} students</span>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 mb-3">
          {result.question}
        </p>
        <div className="space-y-1.5 mb-3">
          {result.options.map((opt, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 text-xs px-3 py-2 rounded-lg border transition-all cursor-pointer
                ${revealed && i === result.correct_index
                  ? "bg-emerald-50 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300"
                  : "bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300"
                }`}
            >
              <span className="font-semibold flex-shrink-0">{String.fromCharCode(65 + i)}.</span>
              <span>{opt}</span>
              {revealed && i === result.correct_index && (
                <CheckCircle2 size={12} className="ml-auto flex-shrink-0 text-emerald-600 mt-0.5" />
              )}
            </div>
          ))}
        </div>
        {revealed ? (
          <p className="text-xs text-zinc-500 italic border-l-2 border-indigo-200 pl-2">
            {result.explanation}
          </p>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setRevealed(true)}
            className="text-xs h-7 text-indigo-600 hover:text-indigo-700"
          >
            Reveal Answer
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

interface SimTabProps {
  onResult: (r: MultiSkillSimulationResponse) => void;
}

function SkillSimulationTab({ onResult }: SimTabProps) {
  const { skillDifficulty, courseId } = useTeacherData();
  const allSkills: SkillDifficultyItem[] = skillDifficulty?.skills ?? [];

  const [simMode, setSimMode] = useState<"automatic" | "manual">("automatic");
  const [topK, setTopK] = useState(5);
  const [selected, setSelected] = useState<Record<string, number | null>>({});
  const [defaultMastery, setDefaultMastery] = useState(0.5);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MultiSkillSimulationResponse | null>(null);
  const [showPairs, setShowPairs] = useState(false);

  const filteredSkills = allSkills.filter((s) =>
    s.skill_name.toLowerCase().includes(filter.toLowerCase()),
  );
  const selectedCount = Object.keys(selected).length;

  async function runSim() {
    if (simMode === "manual" && !selectedCount) return;
    setLoading(true);
    setResult(null);
    try {
      const body =
        simMode === "automatic"
          ? { mode: "automatic" as const, top_k: topK, default_mastery: defaultMastery }
          : {
              mode: "manual" as const,
              skills: Object.entries(selected).map(([skill_name, sm]) => ({
                skill_name,
                simulated_mastery: sm,
              })),
              default_mastery: defaultMastery,
            };
      const res = await simulateSkills(courseId, body);
      setResult(res);
      onResult(res);
    } finally {
      setLoading(false);
    }
  }

  const pairChartData = useMemo(() => {
    if (!result?.coherence.pairs.length) return [];
    return result.coherence.pairs.map((p) => ({
      pair: `${p.skill_a.slice(0, 12)} / ${p.skill_b.slice(0, 12)}`,
      score: +(p.jaccard_score * 100).toFixed(1),
    }));
  }, [result]);

  const clusterChartData = useMemo(() => {
    if (!result?.coherence.clusters.length) return { data: [], clusters: [] };
    const clusters = result.coherence.clusters;
    const rows = [];
    for (let t = 0; t <= 10; t++) {
      const row: Record<string, number | string> = { step: t };
      clusters.forEach((cluster, i) => {
        const clusterSkills = result.skill_results.filter((sr) =>
          cluster.includes(sr.skill_name),
        );
        if (!clusterSkills.length) return;
        const avgM0 =
          clusterSkills.reduce((a, s) => a + s.avg_class_mastery, 0) / clusterSkills.length;
        row[`cluster_${i}`] = +(projectMastery(avgM0, 0.15, t) * 100).toFixed(1);
      });
      rows.push(row);
    }
    return { data: rows, clusters };
  }, [result]);

  return (
    <div className="space-y-5">
      {allSkills.length > 0 && (
        <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Brain size={15} className="text-indigo-500" />
              Top Difficult Skills
            </CardTitle>
            <CardDescription className="text-xs">
              Higher difficulty = lower class avg mastery — use this to guide your skill selection
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={allSkills.slice(0, 10).map((s) => ({
                    name: s.skill_name.length > 18 ? s.skill_name.slice(0, 16) + "…" : s.skill_name,
                    mastery: Math.round(s.avg_mastery * 100),
                    difficulty: Math.round(s.perceived_difficulty * 100),
                  }))}
                  layout="vertical"
                  margin={{ left: 8, right: 20, top: 4, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 10 }}
                  />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={110} />
                  <Tooltip
                    formatter={(v: number, key: string) => [
                      `${v}%`,
                      key === "mastery" ? "Avg Mastery" : "Difficulty",
                    ]}
                    contentStyle={{ fontSize: 11, borderRadius: 8 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="mastery" name="Avg Mastery" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={10} />
                  <Bar dataKey="difficulty" name="Difficulty" fill="#ef4444" radius={[0, 4, 4, 0]} barSize={10} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
        <CardContent className="pt-4 pb-3">
          <div className="flex items-center gap-3">
            <span className="text-xs font-medium text-zinc-500">Simulation Mode:</span>
            <div className="flex rounded-lg border border-zinc-200 dark:border-zinc-700 overflow-hidden">
              <button
                onClick={() => setSimMode("automatic")}
                className={`px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  simMode === "automatic"
                    ? "bg-indigo-600 text-white"
                    : "bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50"
                }`}
              >
                <Zap size={12} />
                Automatic (LLM)
              </button>
              <button
                onClick={() => setSimMode("manual")}
                className={`px-3 py-1.5 text-xs font-medium transition-colors flex items-center gap-1.5 ${
                  simMode === "manual"
                    ? "bg-indigo-600 text-white"
                    : "bg-white dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-50"
                }`}
              >
                <BookOpen size={12} />
                Manual
              </button>
            </div>
            <span className="text-xs text-zinc-400 italic">
              {simMode === "automatic"
                ? "System auto-selects top difficult skills & generates AI insights"
                : "You choose the skills to simulate"}
            </span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {simMode === "manual" && (
          <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900 lg:col-span-1">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <BookOpen size={15} className="text-indigo-500" />
                Select Skills
                {selectedCount > 0 && (
                  <Badge className="ml-1 bg-indigo-100 text-indigo-700 text-xs">
                    {selectedCount} selected
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <input
                className="w-full text-xs px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 placeholder:text-zinc-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                placeholder="Filter skills…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <ScrollArea className="h-52">
                <div className="space-y-1">
                  {filteredSkills.map((s) => {
                    const isSelected = s.skill_name in selected;
                    return (
                      <div
                        key={s.skill_name}
                        className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-colors ${
                          isSelected ? "bg-indigo-50 dark:bg-indigo-900/30" : "hover:bg-zinc-50 dark:hover:bg-zinc-800"
                        }`}
                        onClick={() =>
                          setSelected((prev) => {
                            if (isSelected) {
                              return Object.fromEntries(
                                Object.entries(prev).filter(([k]) => k !== s.skill_name),
                              );
                            }
                            return { ...prev, [s.skill_name]: null };
                          })
                        }
                      >
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={() => undefined}
                          className="pointer-events-none"
                        />
                        <span className="text-xs text-zinc-700 dark:text-zinc-300 flex-1 truncate">
                          {s.skill_name}
                        </span>
                        <span className="text-xs text-zinc-400 flex-shrink-0">
                          {pct(s.avg_mastery)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
              {selectedCount > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs h-7 text-zinc-400"
                  onClick={() => setSelected({})}
                >
                  Clear selection
                </Button>
              )}
            </CardContent>
          </Card>
        )}

        <Card
          className={`border-0 shadow-sm bg-white dark:bg-zinc-900 ${
            simMode === "manual" ? "lg:col-span-2" : "lg:col-span-3"
          }`}
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Zap size={15} className="text-amber-500" />
              Simulation Settings
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {simMode === "automatic" && (
              <div>
                <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Number of skills to analyze:{" "}
                  <span className="font-semibold text-zinc-900 dark:text-zinc-100">{topK}</span>
                </Label>
                <Slider
                  value={[topK]}
                  onValueChange={([v]) => setTopK(v)}
                  min={2}
                  max={10}
                  step={1}
                  className="mt-2"
                />
                <p className="text-xs text-zinc-400 mt-1">
                  The system will automatically pick the top {topK} most difficult skills
                </p>
              </div>
            )}
            <div>
              <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                Default simulated mastery:{" "}
                <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {pct(defaultMastery)}
                </span>
              </Label>
              <Slider
                value={[Math.round(defaultMastery * 100)]}
                onValueChange={([v]) => setDefaultMastery(v / 100)}
                min={10}
                max={100}
                step={5}
                className="mt-2"
              />
            </div>
            {simMode === "manual" && selectedCount > 0 && (
              <div className="space-y-2 max-h-44 overflow-y-auto">
                <p className="text-xs text-zinc-500 font-medium">Per-skill overrides (optional):</p>
                {Object.keys(selected).map((skill) => (
                  <div key={skill} className="flex items-center gap-3">
                    <span className="text-xs text-zinc-600 dark:text-zinc-400 w-36 truncate flex-shrink-0">
                      {skill}
                    </span>
                    <Slider
                      value={[Math.round((selected[skill] ?? defaultMastery) * 100)]}
                      onValueChange={([v]) =>
                        setSelected((prev) => ({ ...prev, [skill]: v / 100 }))
                      }
                      min={10}
                      max={100}
                      step={5}
                      className="flex-1"
                    />
                    <span className="text-xs font-semibold text-zinc-700 dark:text-zinc-300 w-10 text-right flex-shrink-0">
                      {pct(selected[skill] ?? defaultMastery)}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <Button
              className="w-full"
              disabled={(simMode === "manual" && selectedCount === 0) || loading}
              onClick={runSim}
            >
              {loading ? (
                <Loader2 size={14} className="mr-2 animate-spin" />
              ) : (
                <Play size={14} className="mr-2" />
              )}
              {loading
                ? "Simulating…"
                : simMode === "automatic"
                ? `Run Automatic Analysis (Top ${topK} skills)`
                : `Run Simulation (${selectedCount} skills)`}
            </Button>
          </CardContent>
        </Card>
      </div>

      {result && (
        <div className="space-y-5">
          {result.auto_selected_skills?.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-zinc-500 flex items-center gap-1">
                <Zap size={12} className="text-indigo-500" />
                Auto-selected skills:
              </span>
              {result.auto_selected_skills.map((sk) => (
                <span
                  key={sk}
                  className="text-xs px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-800"
                >
                  {sk}
                </span>
              ))}
            </div>
          )}

          {result.llm_insights && (
            <Card className="border border-indigo-100 dark:border-indigo-900 bg-gradient-to-br from-indigo-50 to-white dark:from-indigo-950/30 dark:to-zinc-900 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-semibold flex items-center gap-2 text-indigo-800 dark:text-indigo-300">
                  <Brain size={15} className="text-indigo-500" />
                  AI Pedagogical Insights
                  <Badge className="ml-1 bg-indigo-100 text-indigo-700 text-xs border-0">
                    {result.mode === "automatic" ? "Auto" : "Manual"} Analysis
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap leading-relaxed">
                  {result.llm_insights}
                </p>
              </CardContent>
            </Card>
          )}

          <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-3">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <LinkIcon size={15} className="text-indigo-500" />
                  Skill Coherence Analysis
                </CardTitle>
                <CoherenceLabel label={result.coherence.label} />
              </div>
              <CardDescription className="text-xs">
                Jaccard co-selection similarity · how often students study these skills together
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="text-center bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-3">
                  <p className="text-xl font-bold text-indigo-600 dark:text-indigo-400">
                    {(result.coherence.overall_score * 100).toFixed(0)}%
                  </p>
                  <p className="text-xs text-zinc-500">Coherence Score</p>
                </div>
                <div className="text-center bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-3">
                  <p className="text-xl font-bold text-zinc-700 dark:text-zinc-300">
                    {result.coherence.common_students}
                  </p>
                  <p className="text-xs text-zinc-500">Shared Students</p>
                </div>
                <div className="text-center bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-3">
                  <p className="text-xl font-bold text-zinc-700 dark:text-zinc-300">
                    {result.coherence.clusters.length}
                  </p>
                  <p className="text-xs text-zinc-500">Skill Clusters</p>
                </div>
                <div className="text-center bg-zinc-50 dark:bg-zinc-800/50 rounded-xl p-3">
                  <p className="text-xl font-bold text-zinc-700 dark:text-zinc-300">
                    {result.coherence.pairs.length}
                  </p>
                  <p className="text-xs text-zinc-500">Skill Pairs</p>
                </div>
              </div>

              <div className="mb-4">
                <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-2 flex items-center gap-1.5">
                  <ArrowRight size={12} />
                  Recommended Teaching Order (foundations first)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.coherence.teaching_order.map((sk, i) => (
                    <span
                      key={sk}
                      className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-800"
                    >
                      <span className="font-bold">{i + 1}</span>
                      {sk}
                    </span>
                  ))}
                </div>
              </div>

              {result.coherence.clusters.length > 1 && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-2 flex items-center gap-1.5">
                    <Layers size={12} />
                    Skill Clusters (Jaccard ≥ 40%)
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {result.coherence.clusters.map((cluster, ci) => (
                      <div
                        key={ci}
                        className="border rounded-xl px-3 py-2"
                        style={{
                          borderColor: SKILL_PALETTE[ci % SKILL_PALETTE.length] + "60",
                          backgroundColor: SKILL_PALETTE[ci % SKILL_PALETTE.length] + "0D",
                        }}
                      >
                        <p
                          className="text-xs font-semibold mb-1"
                          style={{ color: SKILL_PALETTE[ci % SKILL_PALETTE.length] }}
                        >
                          Cluster {ci + 1}
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {cluster.map((sk) => (
                            <span
                              key={sk}
                              className="text-xs bg-white/60 dark:bg-zinc-800/60 text-zinc-700 dark:text-zinc-300 px-1.5 py-0.5 rounded"
                            >
                              {sk}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {clusterChartData.clusters.length > 1 && (
                <div>
                  <p className="text-xs font-medium text-zinc-600 dark:text-zinc-400 mb-2 flex items-center gap-1.5">
                    <TrendingUp size={12} />
                    Cluster Learning Curves (10-week projection)
                  </p>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart
                      data={clusterChartData.data}
                      margin={{ top: 4, right: 20, bottom: 4, left: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="step" tickFormatter={(v) => `W${v}`} tick={{ fontSize: 10 }} />
                      <YAxis
                        domain={[0, 100]}
                        tickFormatter={(v) => `${v}%`}
                        tick={{ fontSize: 10 }}
                      />
                      <Tooltip
                        formatter={(v: number, name: string) => [
                          `${v}%`,
                          name.replace("cluster_", "Cluster "),
                        ]}
                        contentStyle={{ fontSize: 11, borderRadius: 8 }}
                        labelFormatter={(l) => `Week ${l}`}
                      />
                      <Legend
                        wrapperStyle={{ fontSize: 10 }}
                        formatter={(name) => name.replace("cluster_", "Cluster ")}
                      />
                      <ReferenceLine
                        y={80}
                        stroke="#10b981"
                        strokeDasharray="3 3"
                        label={{ value: "80%", fill: "#10b981", fontSize: 10 }}
                      />
                      {clusterChartData.clusters.map((_, i) => (
                        <Line
                          key={`cluster_${i}`}
                          dataKey={`cluster_${i}`}
                          stroke={SKILL_PALETTE[i % SKILL_PALETTE.length]}
                          strokeWidth={2.5}
                          dot={{ r: 3, strokeWidth: 0, fill: SKILL_PALETTE[i % SKILL_PALETTE.length] }}
                          activeDot={{ r: 5 }}
                          name={`Cluster ${i + 1} (${clusterChartData.clusters[i].slice(0, 2).join(", ")}${clusterChartData.clusters[i].length > 2 ? "…" : ""})`}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {pairChartData.length > 0 && (
                <div className="mt-4">
                  <button
                    className="text-xs text-indigo-600 dark:text-indigo-400 font-medium flex items-center gap-1 mb-2"
                    onClick={() => setShowPairs((v) => !v)}
                  >
                    <ChevronRight
                      size={12}
                      className={`transition-transform ${showPairs ? "rotate-90" : ""}`}
                    />
                    {showPairs ? "Hide" : "Show"} pairwise Jaccard scores
                  </button>
                  {showPairs && (
                    <ResponsiveContainer width="100%" height={180}>
                      <BarChart
                        data={pairChartData}
                        layout="vertical"
                        margin={{ left: 8, right: 20, top: 2, bottom: 2 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                        <XAxis
                          type="number"
                          domain={[0, 100]}
                          tickFormatter={(v) => `${v}%`}
                          tick={{ fontSize: 10 }}
                        />
                        <YAxis type="category" dataKey="pair" tick={{ fontSize: 9 }} width={130} />
                        <Tooltip
                          formatter={(v: number) => [`${v}%`, "Jaccard"]}
                          contentStyle={{ fontSize: 11, borderRadius: 8 }}
                        />
                        <Bar dataKey="score" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={10} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <div>
            <p className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-3 flex items-center gap-2">
              <Brain size={15} className="text-indigo-500" />
              Adaptive Exercises by Skill
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {result.skill_results.map((sr) => (
                <SkillExerciseCard key={sr.skill_name} result={sr} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── What-If Tab ────────────────────────────────────────────────────────────

interface WhatIfTabProps {
  onClassResult: (r: WhatIfResponse) => void;
}

interface ManualSkillEntry {
  skill_name: string;
  current_avg_mastery: number;
  hypothetical_mastery: number;
}

/** Frontend-only per-student simulation result (no backend call needed). */
interface StudentWhatIfResult {
  skill_name: string;
  current_mastery: number;
  simulated_mastery: number;
  gain: number;
}

function WhatIfTab({ onClassResult }: WhatIfTabProps) {
  const { courseId, skillDifficulty, classMastery } = useTeacherData();
  const [analysisMode, setAnalysisMode] = useState<"class" | "student">("class");

  // ── Class analysis state ──────────────────────────────────────────────────
  const [mode, setMode] = useState<"automatic" | "manual">("automatic");
  const [delta, setDelta] = useState(0.2);
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  // Manual mode — per-skill targets
  const [manualSkills, setManualSkills] = useState<ManualSkillEntry[]>([]);

  // ── Per-student state ─────────────────────────────────────────────────────
  const [selectedStudentId, setSelectedStudentId] = useState<number | null>(null);
  const [studentPortfolio, setStudentPortfolio] = useState<StudentPortfolio | null>(null);
  const [studentSkills, setStudentSkills] = useState<SkillInfo[]>([]);
  const [studentTwin, setStudentTwin] = useState<TwinViewerData | null>(null);
  const [studentDatasetId, setStudentDatasetId] = useState<string>("");
  const [studentLoading, setStudentLoading] = useState(false);
  const [studentError, setStudentError] = useState<string | null>(null);

  // Per-student manual skill targets (pre-populated from portfolio mastery)
  const [studentManualTargets, setStudentManualTargets] = useState<ManualSkillEntry[]>([]);
  const [studentSimResult, setStudentSimResult] = useState<StudentWhatIfResult[]>([]);
  const [studentMode, setStudentMode] = useState<"automatic" | "manual">("automatic");
  const [studentDelta, setStudentDelta] = useState(0.2);
  const [studentTopK, setStudentTopK] = useState(5);

  const skills = skillDifficulty?.skills ?? [];
  const students = classMastery?.students ?? [];
  const selectedStudent = students.find((s) => s.user_id === selectedStudentId) ?? null;

  // ── Class manual skills: initialise when switching to manual mode ─────────
  useEffect(() => {
    if (mode === "manual" && skills.length > 0 && manualSkills.length === 0) {
      const initial = skills
        .slice(0, Math.min(topK, skills.length))
        .map((s) => ({
          skill_name: s.skill_name,
          current_avg_mastery: s.avg_mastery,
          hypothetical_mastery: Math.min(1.0, s.avg_mastery + delta),
        }));
      setManualSkills(initial);
    }
  }, [mode, skills, manualSkills.length, topK, delta]);

  function addManualSkill(skillName: string) {
    if (manualSkills.find((ms) => ms.skill_name === skillName)) return;
    const skill = skills.find((s) => s.skill_name === skillName);
    const current = skill?.avg_mastery ?? 0;
    setManualSkills((prev) => [
      ...prev,
      {
        skill_name: skillName,
        current_avg_mastery: current,
        hypothetical_mastery: Math.min(1.0, current + delta),
      },
    ]);
  }

  function removeManualSkill(skillName: string) {
    setManualSkills((prev) => prev.filter((ms) => ms.skill_name !== skillName));
  }

  function updateHypotheticalMastery(skillName: string, value: number) {
    setManualSkills((prev) =>
      prev.map((ms) => (ms.skill_name === skillName ? { ...ms, hypothetical_mastery: value } : ms)),
    );
  }

  // ── Class analysis run ────────────────────────────────────────────────────
  async function run() {
    setLoading(true);
    setResult(null);
    setRunError(null);
    try {
      const body =
        mode === "manual"
          ? {
              mode: "manual" as const,
              skills: manualSkills.map((ms) => ({
                skill_name: ms.skill_name,
                hypothetical_mastery: ms.hypothetical_mastery,
              })),
              top_k: topK,
              enable_llm: false,
            }
          : {
              mode: "automatic" as const,
              delta,
              top_k: topK,
              target_gain: 0.1,
              enable_llm: false,
            };
      const res = await runWhatIf(courseId, body);
      setResult(res);
      onClassResult(res);
    } catch (e: unknown) {
      setRunError(e instanceof Error ? e.message : "Failed to run simulation");
    } finally {
      setLoading(false);
    }
  }

  // ── Student data load ─────────────────────────────────────────────────────
  const loadStudentData = useCallback(
    async (studentId: number) => {
      setStudentLoading(true);
      setStudentError(null);
      setStudentPortfolio(null);
      setStudentTwin(null);
      setStudentManualTargets([]);
      setStudentSimResult([]);
      try {
        const [portfolioData, twinData] = await Promise.all([
          fetchStudentPortfolioForTeacher(courseId, studentId),
          fetchStudentTwinForTeacher(courseId, studentId),
        ]);
        const dataset = portfolioData?.datasets?.[0];
        if (!dataset) throw new Error("No portfolio data returned");
        const portfolio = dataset.students?.[0] as StudentPortfolio | undefined;
        if (!portfolio) throw new Error("No student data found");
        const skillList = (dataset.skills ?? []) as SkillInfo[];
        setStudentPortfolio(portfolio);
        setStudentSkills(skillList);
        setStudentDatasetId(String(dataset.id ?? ""));
        setStudentTwin(twinData as TwinViewerData);

        // Pre-populate manual targets from actual per-skill mastery
        const targets: ManualSkillEntry[] = skillList.map((sk, i) => {
          const current = portfolio.final_mastery?.[i] ?? 0;
          return {
            skill_name: sk.name,
            current_avg_mastery: current,
            hypothetical_mastery: Math.min(1.0, current + studentDelta),
          };
        });
        setStudentManualTargets(targets);
        runStudentAutoSim(portfolio, skillList, studentDelta, studentTopK);
      } catch (e: unknown) {
        setStudentError(e instanceof Error ? e.message : "Failed to load student data");
      } finally {
        setStudentLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [courseId, studentDelta, studentTopK],
  );

  /** Frontend-only simulation against a single student's mastery array. */
  function runStudentAutoSim(
    portfolio: StudentPortfolio,
    skillList: SkillInfo[],
    d: number,
    k: number,
  ) {
    const rows: StudentWhatIfResult[] = skillList.map((sk, i) => {
      const current = portfolio.final_mastery?.[i] ?? 0;
      const simulated = Math.min(1.0, current + d);
      return { skill_name: sk.name, current_mastery: current, simulated_mastery: simulated, gain: simulated - current };
    });
    // Sort by largest gain → weakest first (ZPD order)
    rows.sort((a, b) => b.gain - a.gain || a.current_mastery - b.current_mastery);
    setStudentSimResult(rows.slice(0, k));
  }

  function runStudentManualSim() {
    const rows: StudentWhatIfResult[] = studentManualTargets.map((t) => ({
      skill_name: t.skill_name,
      current_mastery: t.current_avg_mastery,
      simulated_mastery: t.hypothetical_mastery,
      gain: t.hypothetical_mastery - t.current_avg_mastery,
    }));
    rows.sort((a, b) => b.gain - a.gain);
    setStudentSimResult(rows.slice(0, studentTopK));
  }

  useEffect(() => {
    if (analysisMode === "student" && selectedStudentId != null) {
      loadStudentData(selectedStudentId);
    }
  }, [analysisMode, selectedStudentId, loadStudentData]);

  const impactData = (result?.skill_impacts ?? []).map((si) => ({
    name: si.skill_name.length > 18 ? si.skill_name.slice(0, 16) + "…" : si.skill_name,
    full: si.skill_name,
    before: +(si.current_avg_mastery * 100).toFixed(1),
    after: +(si.simulated_avg_mastery * 100).toFixed(1),
    gain: +(si.class_gain * 100).toFixed(1),
  }));

  // avg student mastery for overall KPI card
  const studentAvgBefore =
    studentSimResult.length > 0
      ? studentSimResult.reduce((s, r) => s + r.current_mastery, 0) / studentSimResult.length
      : 0;
  const studentAvgAfter =
    studentSimResult.length > 0
      ? studentSimResult.reduce((s, r) => s + r.simulated_mastery, 0) / studentSimResult.length
      : 0;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* Analysis mode toggle */}
      <div className="flex gap-2">
        <Button
          variant={analysisMode === "class" ? "default" : "outline"}
          size="sm"
          className="text-xs h-8 gap-1.5"
          onClick={() => setAnalysisMode("class")}
        >
          <Users size={13} />
          Class Analysis
        </Button>
        <Button
          variant={analysisMode === "student" ? "default" : "outline"}
          size="sm"
          className="text-xs h-8 gap-1.5"
          onClick={() => setAnalysisMode("student")}
        >
          <UserSearch size={13} />
          Per Student
        </Button>
      </div>

      {/* ── CLASS ANALYSIS ── */}
      {analysisMode === "class" && (
        <>
          <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Zap size={15} className="text-amber-500" />
                Configure What-If Scenario
              </CardTitle>
              <CardDescription className="text-xs">
                Simulate the impact of teaching specific skills across the entire class
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Mode toggle */}
              <div className="flex gap-2">
                <Button
                  variant={mode === "automatic" ? "default" : "outline"}
                  size="sm"
                  className="text-xs h-7"
                  onClick={() => {
                    setMode("automatic");
                    setResult(null);
                  }}
                >
                  Automatic
                </Button>
                <Button
                  variant={mode === "manual" ? "default" : "outline"}
                  size="sm"
                  className="text-xs h-7"
                  onClick={() => {
                    setMode("manual");
                    setResult(null);
                    setManualSkills([]);
                  }}
                >
                  Manual
                </Button>
              </div>

              {/* ── Automatic mode: formula + Δ sliders ── */}
              {mode === "automatic" && (
                <>
                  {/* Formula card */}
                  <div className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 p-3 space-y-1.5">
                    <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                      Simulation Formula
                    </p>
                    <p className="text-xs font-mono text-zinc-800 dark:text-zinc-200">
                      Sim(s) = min(1.0, Avg(s) + Δ)
                    </p>
                    <p className="text-xs font-mono text-zinc-800 dark:text-zinc-200">
                      ClassGain(s) = Σᵢ [min(1, mᵢ + Δ) − mᵢ]
                    </p>
                    <p className="text-xs font-mono text-zinc-800 dark:text-zinc-200">
                      Score(s) = 0.5×max(0, 0.5−Avg) + 0.3×(Gain/N) + 0.2×(Helped/N)
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 pt-1">
                      Skills are ranked by <span className="font-medium">Score</span> — combining mastery gap, total gain, and breadth of students helped.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                        Lecture Impact (Δ):{" "}
                        <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                          +{pct(delta)}
                        </span>
                      </Label>
                      <Slider
                        value={[Math.round(delta * 100)]}
                        onValueChange={([v]) => setDelta(v / 100)}
                        min={5}
                        max={50}
                        step={5}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                        Top skills to rank:{" "}
                        <span className="font-semibold text-zinc-900 dark:text-zinc-100">{topK}</span>
                      </Label>
                      <Slider
                        value={[topK]}
                        onValueChange={([v]) => setTopK(v)}
                        min={1}
                        max={Math.min(10, skills.length || 10)}
                        step={1}
                      />
                    </div>
                  </div>

                  {/* Live skill preview */}
                  {skills.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Skills in scope — ZPD candidates (40–90% mastery) highlighted:
                      </p>
                      <div className="max-h-40 overflow-y-auto space-y-1 pr-1">
                        {skills.slice(0, Math.min(topK * 2, skills.length)).map((s) => {
                          const isZpd = s.avg_mastery >= 0.4 && s.avg_mastery <= 0.9;
                          const simulated = Math.min(1.0, s.avg_mastery + delta);
                          return (
                            <div
                              key={s.skill_name}
                              className={`flex items-center justify-between text-xs px-2.5 py-1.5 rounded-md ${
                                isZpd
                                  ? "bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-100 dark:border-indigo-800"
                                  : "bg-zinc-50 dark:bg-zinc-800/40"
                              }`}
                            >
                              <span className="truncate max-w-[200px] font-medium" title={s.skill_name}>
                                {s.skill_name}
                              </span>
                              <div className="flex items-center gap-2 shrink-0">
                                {isZpd && (
                                  <Badge className="text-[10px] h-4 px-1 bg-indigo-100 text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300 border-0">
                                    ZPD
                                  </Badge>
                                )}
                                <span className="text-zinc-500">{pct(s.avg_mastery)}</span>
                                <span className="text-zinc-300 dark:text-zinc-600">→</span>
                                <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                                  {pct(simulated)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* ── Manual mode: per-skill target picker ── */}
              {mode === "manual" && (
                <div className="space-y-3">
                  {/* Formula reminder */}
                  <div className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 p-3 space-y-1">
                    <p className="text-xs font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">
                      Manual Formula
                    </p>
                    <p className="text-xs font-mono text-zinc-800 dark:text-zinc-200">
                      Gain(s) = (Hypothetical − Current) × N students
                    </p>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      Set a target mastery for each skill. The backend computes the class-level gain.
                    </p>
                  </div>

                  {/* Skill picker */}
                  <div className="relative">
                    <select
                      className="w-full text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 pr-8 text-zinc-900 dark:text-zinc-100 appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
                      value=""
                      onChange={(e) => {
                        if (e.target.value) addManualSkill(e.target.value);
                        e.target.value = "";
                      }}
                    >
                      <option value="">+ Add skill to simulate…</option>
                      {skills
                        .filter((s) => !manualSkills.find((ms) => ms.skill_name === s.skill_name))
                        .map((s) => (
                          <option key={s.skill_name} value={s.skill_name}>
                            {s.skill_name} — class avg {pct(s.avg_mastery)}
                          </option>
                        ))}
                    </select>
                    <ChevronDown
                      size={13}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
                    />
                  </div>

                  {/* Selected skills with live mastery */}
                  {manualSkills.length === 0 && (
                    <p className="text-xs text-zinc-400 text-center py-3">
                      No skills selected — use the dropdown to add skills.
                    </p>
                  )}
                  <div className="space-y-3">
                    {manualSkills.map((ms) => (
                      <div
                        key={ms.skill_name}
                        className="p-3 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800/50 space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium truncate max-w-[200px]" title={ms.skill_name}>
                            {ms.skill_name}
                          </span>
                          <button
                            onClick={() => removeManualSkill(ms.skill_name)}
                            className="text-zinc-400 hover:text-red-500 transition-colors"
                          >
                            <X size={13} />
                          </button>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-zinc-500">
                          <span>
                            Current avg:{" "}
                            <span className="font-semibold text-zinc-900 dark:text-zinc-100">
                              {pct(ms.current_avg_mastery)}
                            </span>
                          </span>
                          <span>→</span>
                          <span>
                            Target:{" "}
                            <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                              {pct(ms.hypothetical_mastery)}
                            </span>
                          </span>
                          <span className="ml-auto text-indigo-500 font-semibold">
                            +{pct(ms.hypothetical_mastery - ms.current_avg_mastery)} gain
                          </span>
                        </div>
                        <Slider
                          value={[Math.round(ms.hypothetical_mastery * 100)]}
                          onValueChange={([v]) => updateHypotheticalMastery(ms.skill_name, v / 100)}
                          min={Math.ceil(ms.current_avg_mastery * 100)}
                          max={100}
                          step={5}
                        />
                      </div>
                    ))}
                  </div>

                  {/* Top K control */}
                  <div className="space-y-2">
                    <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                      Show top results:{" "}
                      <span className="font-semibold text-zinc-900 dark:text-zinc-100">{topK}</span>
                    </Label>
                    <Slider
                      value={[topK]}
                      onValueChange={([v]) => setTopK(v)}
                      min={1}
                      max={Math.min(10, manualSkills.length || 10)}
                      step={1}
                    />
                  </div>
                </div>
              )}

              {runError && (
                <div className="flex items-center gap-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/20 px-3 py-2 rounded-lg">
                  <AlertTriangle size={13} />
                  {runError}
                </div>
              )}

              <Button
                className="w-full"
                disabled={loading || (mode === "manual" && manualSkills.length === 0)}
                onClick={run}
              >
                {loading ? (
                  <Loader2 size={14} className="mr-2 animate-spin" />
                ) : (
                  <Play size={14} className="mr-2" />
                )}
                {loading ? "Running simulation…" : "Run What-If Analysis"}
              </Button>
            </CardContent>
          </Card>

          {/* Results */}
          {result && (
            <div className="space-y-4">
              <Card className="border-0 shadow-sm bg-indigo-50 dark:bg-indigo-900/20 border-indigo-100 dark:border-indigo-800">
                <CardContent className="p-4">
                  <p className="text-sm text-indigo-800 dark:text-indigo-300">{result.summary}</p>
                </CardContent>
              </Card>

              {impactData.length > 0 && (
                <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <BarChart3 size={15} className="text-indigo-500" />
                      Skill Mastery Impact
                    </CardTitle>
                    <CardDescription className="text-xs">
                      Before vs. after intervention
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div style={{ width: "100%", height: 220 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={impactData}
                          layout="vertical"
                          margin={{ left: 8, right: 20, top: 4, bottom: 4 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                          <XAxis
                            type="number"
                            domain={[0, 100]}
                            tickFormatter={(v) => `${v}%`}
                            tick={{ fontSize: 10 }}
                          />
                          <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={120} />
                          <Tooltip
                            formatter={(v: number, key: string) => [`${v}%`, key === "before" ? "Before" : "After"]}
                            contentStyle={{ fontSize: 11, borderRadius: 8 }}
                          />
                          <Legend wrapperStyle={{ fontSize: 11 }} />
                          <Bar dataKey="before" name="Before" fill="#94a3b8" radius={[0, 4, 4, 0]} barSize={10} />
                          <Bar dataKey="after" name="After" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={10} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              )}

              {result.recommendations.length > 0 && (
                <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <Target size={15} className="text-indigo-500" />
                      Recommendations
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {result.recommendations.map((r, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 text-xs text-zinc-700 dark:text-zinc-300 bg-zinc-50 dark:bg-zinc-800/50 px-3 py-2 rounded-lg"
                      >
                        <ChevronRight size={12} className="text-indigo-400 mt-0.5 flex-shrink-0" />
                        {r}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {result.pco_analysis.length > 0 && (
                <Card className="border-0 shadow-sm bg-amber-50 dark:bg-amber-900/20">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <AlertTriangle size={14} className="text-amber-500" />
                      Concept Overclaiming Risk
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {result.pco_analysis.map((line, i) => (
                      <p key={i} className="text-xs text-amber-800 dark:text-amber-300">
                        {line}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </>
      )}

      {/* ── PER-STUDENT ANALYSIS ── */}
      {analysisMode === "student" && (
        <div className="space-y-5">
          {/* Student picker */}
          <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <UserSearch size={15} className="text-indigo-500" />
                Select Student
              </CardTitle>
              <CardDescription className="text-xs">
                Mastery scores are read live from the student's knowledge tracing data
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="relative">
                <select
                  className="w-full text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 pr-8 text-zinc-900 dark:text-zinc-100 appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
                  value={selectedStudentId ?? ""}
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    setSelectedStudentId(id || null);
                    setStudentSimResult([]);
                  }}
                >
                  <option value="">— Choose a student —</option>
                  {students.map((s) => (
                    <option key={s.user_id} value={s.user_id}>
                      {s.full_name} ({(s.avg_mastery * 100).toFixed(0)}% avg)
                      {s.at_risk ? " ⚠️ At Risk" : ""}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={14}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none"
                />
              </div>

              {selectedStudent && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="text-xs">
                    {selectedStudent.selected_skill_count} skills
                  </Badge>
                  <Badge
                    variant="outline"
                    className={`text-xs ${
                      selectedStudent.at_risk
                        ? "border-red-400 text-red-600 dark:text-red-400"
                        : "border-emerald-400 text-emerald-600 dark:text-emerald-400"
                    }`}
                  >
                    {(selectedStudent.avg_mastery * 100).toFixed(0)}% avg mastery
                  </Badge>
                  {selectedStudent.struggling_count > 0 && (
                    <Badge variant="outline" className="text-xs border-amber-400 text-amber-600">
                      {selectedStudent.struggling_count} struggling
                    </Badge>
                  )}
                  {selectedStudent.mastered_count > 0 && (
                    <Badge variant="outline" className="text-xs border-emerald-400 text-emerald-600">
                      {selectedStudent.mastered_count} mastered
                    </Badge>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {studentLoading && (
            <div className="flex flex-col items-center justify-center h-40 gap-3">
              <Loader2 size={24} className="text-indigo-500 animate-spin" />
              <p className="text-sm text-zinc-500">
                Loading {selectedStudent?.full_name ?? "student"}'s mastery data…
              </p>
            </div>
          )}

          {studentError && (
            <Card className="border-0 shadow-sm bg-red-50 dark:bg-red-950/20">
              <CardContent className="p-4 flex items-center gap-2 text-sm text-red-700 dark:text-red-400">
                <AlertTriangle size={16} />
                {studentError}
              </CardContent>
            </Card>
          )}

          {!selectedStudentId && !studentLoading && (
            <div className="flex flex-col items-center justify-center h-48 gap-2 text-zinc-400">
              <UserSearch size={32} className="opacity-40" />
              <p className="text-sm">Select a student to run their personalised What-If</p>
            </div>
          )}

          {/* Per-student simulation panel */}
          {!studentLoading && !studentError && studentPortfolio && studentSkills.length > 0 && (
            <>
              {/* Student sim controls */}
              <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Zap size={14} className="text-amber-500" />
                    Simulation Parameters — {selectedStudent?.full_name}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Each mastery value is read live from this student's knowledge tracing output
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex gap-2">
                    <Button
                      variant={studentMode === "automatic" ? "default" : "outline"}
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => {
                        setStudentMode("automatic");
                        if (studentPortfolio)
                          runStudentAutoSim(studentPortfolio, studentSkills, studentDelta, studentTopK);
                      }}
                    >
                      Automatic
                    </Button>
                    <Button
                      variant={studentMode === "manual" ? "default" : "outline"}
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => setStudentMode("manual")}
                    >
                      Manual
                    </Button>
                  </div>

                  {studentMode === "automatic" && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                          Teaching Δ: <span className="font-semibold text-zinc-900 dark:text-zinc-100">+{pct(studentDelta)}</span>
                        </Label>
                        <Slider
                          value={[Math.round(studentDelta * 100)]}
                          onValueChange={([v]) => {
                            const d = v / 100;
                            setStudentDelta(d);
                            if (studentPortfolio)
                              runStudentAutoSim(studentPortfolio, studentSkills, d, studentTopK);
                          }}
                          min={5}
                          max={50}
                          step={5}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                          Top K skills: <span className="font-semibold text-zinc-900 dark:text-zinc-100">{studentTopK}</span>
                        </Label>
                        <Slider
                          value={[studentTopK]}
                          onValueChange={([v]) => {
                            setStudentTopK(v);
                            if (studentPortfolio)
                              runStudentAutoSim(studentPortfolio, studentSkills, studentDelta, v);
                          }}
                          min={1}
                          max={Math.min(10, studentSkills.length)}
                          step={1}
                        />
                      </div>
                    </div>
                  )}

                  {studentMode === "manual" && (
                    <div className="space-y-3">
                      <p className="text-xs text-zinc-500">
                        Adjust each skill's target mastery. Current values are read from this student's latest knowledge tracing run.
                      </p>
                      <div className="max-h-72 overflow-y-auto space-y-3 pr-1">
                        {studentManualTargets.slice(0, studentTopK * 2).map((t) => (
                          <div
                            key={t.skill_name}
                            className="p-2.5 rounded-lg border border-zinc-200 dark:border-zinc-700 space-y-1.5"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium truncate max-w-[180px]" title={t.skill_name}>
                                {t.skill_name}
                              </span>
                              <span
                                className={`font-semibold ${
                                  t.current_avg_mastery >= 0.8
                                    ? "text-emerald-600"
                                    : t.current_avg_mastery >= 0.5
                                    ? "text-amber-600"
                                    : "text-red-500"
                                }`}
                              >
                                {pct(t.current_avg_mastery)} now → {pct(t.hypothetical_mastery)} target
                              </span>
                            </div>
                            <Slider
                              value={[Math.round(t.hypothetical_mastery * 100)]}
                              onValueChange={([v]) =>
                                setStudentManualTargets((prev) =>
                                  prev.map((s) =>
                                    s.skill_name === t.skill_name
                                      ? { ...s, hypothetical_mastery: v / 100 }
                                      : s,
                                  ),
                                )
                              }
                              min={Math.ceil(t.current_avg_mastery * 100)}
                              max={100}
                              step={5}
                            />
                          </div>
                        ))}
                      </div>
                      <Button size="sm" className="w-full text-xs" onClick={runStudentManualSim}>
                        <Play size={13} className="mr-1.5" />
                        Apply Manual Targets
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Per-student sim results */}
              {studentSimResult.length > 0 && (
                <>
                  {/* KPI strip */}
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      {
                        label: "Skills Targeted",
                        value: String(studentSimResult.length),
                        color: "text-indigo-600",
                      },
                      {
                        label: "Avg Before",
                        value: pct(studentAvgBefore),
                        color: "text-zinc-600",
                      },
                      {
                        label: "Avg After",
                        value: pct(studentAvgAfter),
                        color: "text-emerald-600",
                      },
                    ].map((k) => (
                      <div
                        key={k.label}
                        className="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 p-3 text-center"
                      >
                        <p className={`text-lg font-bold ${k.color}`}>{k.value}</p>
                        <p className="text-xs text-zinc-500 mt-0.5">{k.label}</p>
                      </div>
                    ))}
                  </div>

                  {/* Per-skill rows — live mastery shown */}
                  <Card className="border-0 shadow-sm bg-white dark:bg-zinc-900">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2">
                        <BarChart3 size={14} className="text-indigo-500" />
                        Per-Skill Mastery Projection
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Mastery values are read dynamically from{" "}
                        <span className="font-medium">{selectedStudent?.full_name}'s</span> knowledge tracing output
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {studentSimResult.map((r) => (
                        <div key={r.skill_name} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-medium truncate max-w-[180px]" title={r.skill_name}>
                              {r.skill_name}
                            </span>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-zinc-500">{pct(r.current_mastery)}</span>
                              <span className="text-zinc-300 dark:text-zinc-600">→</span>
                              <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                                {pct(r.simulated_mastery)}
                              </span>
                              <span className="text-indigo-500 font-semibold">
                                +{pct(r.gain)}
                              </span>
                            </div>
                          </div>
                          <div className="relative h-2 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
                            <div
                              className="absolute left-0 top-0 h-full rounded-full bg-zinc-300 dark:bg-zinc-600"
                              style={{ width: `${r.current_mastery * 100}%` }}
                            />
                            <div
                              className="absolute left-0 top-0 h-full rounded-full bg-emerald-400/60 dark:bg-emerald-500/50"
                              style={{ width: `${r.simulated_mastery * 100}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </>
              )}

              {/* Full portfolio view below */}
              <div className="border-t border-zinc-100 dark:border-zinc-800 pt-4">
                <p className="text-xs text-zinc-400 mb-3">Full student portfolio</p>
                <TwinViewerTab
                  student={studentPortfolio}
                  skills={studentSkills}
                  datasetId={studentDatasetId}
                  twinData={studentTwin}
                  viewMode="teacher"
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Teacher Twin Page ─────────────────────────────────────────────────

export default function TeacherTwinPage() {
  const { loading, error, classMastery, skillDifficulty, skillPopularity, refresh } =
    useTeacherData();

  const [activeTab, setActiveTab] = useState("overview");
  const [lastSimResult, setLastSimResult] = useState<MultiSkillSimulationResponse | null>(null);
  const [lastWhatIfResult, setLastWhatIfResult] = useState<WhatIfResponse | null>(null);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <div className="w-10 h-10 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center">
          <Loader2 size={20} className="text-indigo-600 animate-spin" />
        </div>
        <p className="text-sm text-zinc-500">Loading analytics…</p>
      </div>
    );
  }

  if (error) {
    const msgs: Record<string, string> = {
      SESSION_EXPIRED: "Your session has expired. Please sign in again.",
      ACCESS_DENIED: "You don't have access to this course.",
      NEO4J_UNAVAILABLE: "Graph database is temporarily unavailable.",
      NETWORK_ERROR: "Network error. Please check your connection.",
    };
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
        <AlertTriangle size={32} className="text-amber-500" />
        <p className="text-sm text-zinc-600 dark:text-zinc-400 max-w-sm">
          {msgs[error] ?? error}
        </p>
        <Button variant="outline" size="sm" onClick={refresh} className="text-xs h-7">
          <RefreshCw size={12} className="mr-1.5" /> Retry
        </Button>
      </div>
    );
  }

  const cm = classMastery;
  const sd = skillDifficulty;
  const sp = skillPopularity;

  return (
    <div className="space-y-5 max-w-7xl mx-auto px-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <Brain size={14} className="text-white" />
            </div>
            Teacher Digital Twin
          </h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            AI-powered class analytics · forward simulations · skill intelligence
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} className="text-xs h-7">
          <RefreshCw size={12} className="mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          title="Total Students"
          value={cm?.total_students ?? 0}
          subtitle={`${cm?.at_risk_count ?? 0} at-risk`}
          icon={<Users size={16} />}
          color="indigo"
        />
        <KpiCard
          title="Class Avg Mastery"
          value={cm ? pct(cm.class_avg_mastery) : "—"}
          subtitle="across all skills"
          icon={<Target size={16} />}
          color={
            (cm?.class_avg_mastery ?? 0) >= 0.7
              ? "emerald"
              : (cm?.class_avg_mastery ?? 0) >= 0.5
                ? "amber"
                : "red"
          }
          trend={(cm?.class_avg_mastery ?? 0) >= 0.7 ? "On track" : undefined}
        />
        <KpiCard
          title="At-Risk Students"
          value={cm?.at_risk_count ?? 0}
          subtitle={`of ${cm?.total_students ?? 0} enrolled`}
          icon={<AlertTriangle size={16} />}
          color={(cm?.at_risk_count ?? 0) > 0 ? "red" : "emerald"}
        />
        <KpiCard
          title="Skills in Curriculum"
          value={sd?.total_skills ?? 0}
          subtitle={`${sp?.total_students ?? 0} student selections`}
          icon={<BookOpen size={16} />}
          color="amber"
        />
      </div>

      {/* Tabs — 4 tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid grid-cols-4 h-9 bg-zinc-100 dark:bg-zinc-800/60 rounded-xl p-1">
          <TabsTrigger value="overview" className="text-xs rounded-lg">
            <BarChart3 size={12} className="mr-1.5" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="cohort" className="text-xs rounded-lg">
            <TrendingUp size={12} className="mr-1.5" />
            Students Learning Curve
          </TabsTrigger>
          <TabsTrigger value="simulator" className="text-xs rounded-lg">
            <Brain size={12} className="mr-1.5" />
            Skill Simulator
          </TabsTrigger>
          <TabsTrigger value="whatif" className="text-xs rounded-lg">
            <Zap size={12} className="mr-1.5" />
            What-If
          </TabsTrigger>
        </TabsList>

        <div className="mt-4">
          <TabsContent value="overview" className="mt-0">
            <OverviewTab
              lastSimResult={lastSimResult}
              lastWhatIfResult={lastWhatIfResult}
              onNavigate={setActiveTab}
            />
          </TabsContent>
          <TabsContent value="cohort" className="mt-0">
            <CohortTab />
          </TabsContent>
          <TabsContent value="simulator" className="mt-0">
            <SkillSimulationTab onResult={setLastSimResult} />
          </TabsContent>
          <TabsContent value="whatif" className="mt-0">
            <WhatIfTab onClassResult={setLastWhatIfResult} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
