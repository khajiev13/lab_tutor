
import { useMemo, useState } from "react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  LineChart, Line, AreaChart, Area, Bar, ComposedChart,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceLine, Cell, LabelList,
} from "recharts";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  TrendingUp, TrendingDown, ChevronDown, ChevronUp,
  AlertTriangle, CheckCircle2, ArrowRight, Target, BookOpen, Users,
} from "lucide-react";
import type { StudentPortfolio, SkillInfo, ModelInfo, TwinViewerData } from "@/features/arcd-agent/lib/types";
import { SKILL_HEX, OVERALL_HEX } from "@/features/arcd-agent/lib/colors";
import {
  buildConceptStats,
  formatPct100,
  computeWeightedFinalGrade, computeRetentionGap,
  buildAttemptedSkillIds, chapterMasteryFromFinal,
} from "@/features/arcd-agent/lib/grading";
import { InsightPanel } from "@/features/arcd-agent/components/insight-panel";

interface UnifiedTabProps {
  student: StudentPortfolio;
  modelInfo: ModelInfo;
  skills: SkillInfo[];
  datasetId: string;
  twinData?: TwinViewerData | null;
  viewMode?: "student" | "teacher";
  allStudents?: StudentPortfolio[];
}

// ── helpers ────────────────────────────────────────────────────────────────

function avgMastery(mastery: number[], subSkillIds: number[]): number {
  const vals = subSkillIds
    .filter((id) => id >= 0 && id < mastery.length)
    .map((id) => mastery[id]);
  return vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
}

// ── Section 1: Student Pulse ───────────────────────────────────────────────

interface PulseCardProps {
  label: string;
  value: string;
  sub?: string;
  trend?: "up" | "down" | "neutral";
  accent?: "default" | "success" | "warning" | "danger";
}

function PulseCard({ label, value, sub, trend, accent = "default" }: PulseCardProps) {
  const accentBorder =
    accent === "success" ? "border-l-4 border-l-emerald-500" :
    accent === "warning" ? "border-l-4 border-l-amber-500" :
    accent === "danger"  ? "border-l-4 border-l-red-500" :
    "";
  return (
    <Card className={accentBorder}>
      <CardHeader className="pb-2">
        <CardDescription className="text-xs uppercase tracking-wide">{label}</CardDescription>
        <div className="flex items-end gap-2">
          <span className="text-2xl font-bold tabular-nums">{value}</span>
          {trend === "up" && <TrendingUp className="mb-0.5 h-4 w-4 text-emerald-500" />}
          {trend === "down" && <TrendingDown className="mb-0.5 h-4 w-4 text-red-500" />}
        </div>
      </CardHeader>
      {sub && (
        <CardContent className="pt-0">
          <p className="text-xs text-muted-foreground">{sub}</p>
        </CardContent>
      )}
    </Card>
  );
}

// ── Section 3: Chapter table row (expandable) ──────────────────────────────

interface ChapterRowProps {
  chapter: SkillInfo;
  initial: number;
  final: number;
  change: number;
  color: string;
  finalMastery: number[];
  attemptedSkillIds: Set<number>;
  conceptStats: Map<number | string, { correct: number; total: number }>;
  modality?: { videoCov: number; readingCov: number } | null;
}

function ChapterRow({ chapter, initial, final, change, color, modality }: ChapterRowProps) {
  const [open, setOpen] = useState(false);

  const quizGrade = final / 100;
  const videoCov = modality?.videoCov ?? 0;
  const readingCov = modality?.readingCov ?? 0;
  const hasModality = modality != null;
  const weightedFinal = hasModality
    ? computeWeightedFinalGrade(quizGrade, videoCov, readingCov) * 100
    : final;
  const lowVideo = hasModality && videoCov < 0.3;
  const lowReading = hasModality && readingCov < 0.3;

  return (
    <>
      <tr
        className="border-b border-border/50 hover:bg-muted/30 cursor-pointer transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <td className="p-2">
          <span className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: color }} />
            <span className="font-medium text-sm">{chapter.name}</span>
            {chapter.chapter_name && (
              <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded ml-1">
                {chapter.chapter_name}
              </span>
            )}
            <span className="ml-auto text-muted-foreground">
              {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </span>
          </span>
        </td>
        <td className="p-2 text-right text-muted-foreground text-sm">{chapter.n_concepts}</td>
        <td className="p-2 text-right font-mono tabular-nums text-sm text-muted-foreground">{formatPct100(initial)}</td>
        {hasModality ? (
          <>
            <td className="p-2 text-right font-mono tabular-nums text-sm">
              {formatPct100(final)}
            </td>
            <td className="p-2 text-right font-mono tabular-nums text-sm">
              <span className="flex items-center justify-end gap-1">
                {formatPct100(videoCov * 100)}
                {lowVideo && <AlertTriangle className="h-3 w-3 text-amber-500" />}
              </span>
            </td>
            <td className="p-2 text-right font-mono tabular-nums text-sm">
              <span className="flex items-center justify-end gap-1">
                {formatPct100(readingCov * 100)}
                {lowReading && <AlertTriangle className="h-3 w-3 text-amber-500" />}
              </span>
            </td>
            <td className="p-2 text-right font-mono tabular-nums text-sm font-semibold">
              {formatPct100(weightedFinal)}
            </td>
          </>
        ) : (
          <>
            <td className="p-2 text-right font-mono tabular-nums text-sm font-medium">{formatPct100(final)}</td>
            <td className={`p-2 text-right font-mono tabular-nums text-sm font-semibold ${change >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(1)}%
            </td>
            <td className="p-2 text-right text-sm">
              <div className="flex items-center justify-end gap-1">
                <div className="w-20 h-1.5 rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(final, 100)}%`, backgroundColor: color }} />
                </div>
              </div>
            </td>
          </>
        )}
      </tr>
      {open && chapter.concepts.map((concept, ci) => (
        <tr key={`${chapter.id}-c${ci}`} className="border-b border-border/30 bg-muted/20">
          <td className="p-2 pl-8 text-xs text-muted-foreground" colSpan={hasModality ? 4 : 2}>
            <span className="flex items-center gap-1">
              <ArrowRight className="h-3 w-3 shrink-0" />
              {concept.name_en || String(concept.id)}
            </span>
          </td>
          <td className="p-2 text-right font-mono tabular-nums text-xs" colSpan={3}>
            <span className="text-muted-foreground/60 italic text-[10px]">Concept</span>
          </td>
        </tr>
      ))}
    </>
  );
}

// ── Teacher: Class Heatmap ────────────────────────────────────────────────

interface ClassHeatmapProps {
  students: StudentPortfolio[];
  skills: SkillInfo[];
  currentUid: string;
}

function ClassHeatmap({ students, skills, currentUid }: ClassHeatmapProps) {
  // Each skill's mastery is at index skill.id in the mastery vector.
  const skillIds = skills.map((s) => s.id);

  const rows = useMemo(() => {
    return students.map((s) => {
      const lastEntry = s.timeline[s.timeline.length - 1];
      const mastery = lastEntry?.mastery ?? s.final_mastery ?? [];
      const chapterMastery = skillIds.map((id) =>
        id >= 0 && id < mastery.length ? mastery[id] : 0
      );
      const avg = chapterMastery.reduce((a, v) => a + v, 0) / (chapterMastery.length || 1);
      return { uid: s.uid, chapterMastery, avg };
    });
  }, [students, skillIds]);

  const heatColor = (v: number) =>
    v >= 0.75 ? "#10b981" : v >= 0.50 ? "#3b82f6" : v >= 0.30 ? "#f59e0b" : "#ef4444";

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Users className="h-4 w-4 text-muted-foreground" />
        <h2 className="text-lg font-semibold">Class Heatmap</h2>
        <Badge variant="secondary" className="text-xs">Teacher View</Badge>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Chapter Mastery Across All Students</CardTitle>
          <CardDescription>Current student highlighted · sorted by overall mastery</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="p-2 text-left font-medium w-24">Student</th>
                {skills.map((s, i) => (
                  <th key={i} className="p-2 font-medium text-center" style={{ minWidth: 70 }}>
                    <span className="truncate block max-w-[70px]" title={s.name}>
                      {s.name.split(" ").slice(0, 2).join(" ")}
                    </span>
                  </th>
                ))}
                <th className="p-2 font-medium text-center w-16">Avg</th>
              </tr>
            </thead>
            <tbody>
              {[...rows].sort((a, b) => b.avg - a.avg).map((row) => (
                <tr
                  key={row.uid}
                  className={`border-b border-border/30 ${row.uid === currentUid ? "ring-1 ring-primary ring-inset font-semibold" : ""}`}
                >
                  <td className="p-2 font-mono text-muted-foreground truncate max-w-[96px]">
                    {row.uid === currentUid ? <span className="text-primary">{row.uid}</span> : row.uid}
                  </td>
                  {row.chapterMastery.map((v, i) => (
                    <td key={i} className="p-1 text-center">
                      <span
                        className="inline-flex items-center justify-center w-12 h-6 rounded text-[10px] font-mono text-white"
                        style={{ backgroundColor: heatColor(v) }}
                      >
                        {Math.round(v * 100)}%
                      </span>
                    </td>
                  ))}
                  <td className="p-2 text-center font-mono">
                    <span
                      className="inline-flex items-center justify-center w-12 h-6 rounded text-[10px] font-mono text-white"
                      style={{ backgroundColor: heatColor(row.avg) }}
                    >
                      {Math.round(row.avg * 100)}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </section>
  );
}


// ── Main component ─────────────────────────────────────────────────────────

export function UnifiedTab({ student, modelInfo, skills, datasetId, twinData, viewMode = "student", allStudents = [] }: UnifiedTabProps) {
  const [deepOpen, setDeepOpen] = useState(false);
  const s = student.summary;

  const conceptStats = useMemo(() => buildConceptStats(student.timeline), [student.timeline]);
  // skillIds[i] = skill index for skills[i]; mastery[skillId] gives that skill's mastery.
  const chapterSubIds = useMemo(
    () => skills.map((s) => [s.id]),
    [skills]
  );

  // Set of sub-skill IDs the student has actually interacted with
  const attemptedSkillIds = useMemo(
    () => buildAttemptedSkillIds(student.timeline, skills, conceptStats),
    [student.timeline, skills, conceptStats]
  );

  // Final mastery vector (authoritative source: ARCD model output)
  const finalMasteryVec: number[] = useMemo(
    () =>
      student.final_mastery?.length
        ? student.final_mastery
        : student.timeline[student.timeline.length - 1]?.mastery ?? [],
    [student.final_mastery, student.timeline]
  );

  // ── chapter mastery deltas ───────────────────────────────────────────────
  // Coverage × mastery formula: unstarted sub-skills contribute 0 so
  // chapters with low coverage correctly show lower scores.
  const chapterDeltas = useMemo(() => {
    return skills.map((chapter, i) => {
      const ids = chapterSubIds[i];
      // Initial: neural prior from first timeline step (before any learning)
      const firstMastery =
        student.timeline.length > 0
          ? avgMastery(student.timeline[0].mastery, ids)
          : 0;
      // Final: coverage × mastery — unstarted sub-skills treated as 0
      const finalChapterMastery = chapterMasteryFromFinal(ids, finalMasteryVec, attemptedSkillIds);
      return {
        chapter: chapter.name,
        initial: firstMastery * 100,
        final:   finalChapterMastery * 100,
        change:  (finalChapterMastery - firstMastery) * 100,
      };
    });
  }, [skills, chapterSubIds, student.timeline, finalMasteryVec, attemptedSkillIds]);

  const overallFinal = chapterDeltas.length > 0
    ? chapterDeltas.reduce((a, d) => a + d.final, 0) / chapterDeltas.length
    : 0;
  const overallInitial = chapterDeltas.length > 0
    ? chapterDeltas.reduce((a, d) => a + d.initial, 0) / chapterDeltas.length
    : 0;
  const overallDelta = overallFinal - overallInitial;

  const chaptersProficient = chapterDeltas.filter((d) => d.final >= 75).length;

  // ── modality-aware Final Grade (60/20/20) ───────────────────────────────
  const modCoverage = student.modality_coverage;
  const quizGrade = overallFinal / 100;
  const videoCov = modCoverage?.video_pct ?? 0;
  const readingCov = modCoverage?.reading_pct ?? 0;
  const hasModality = modCoverage != null && (videoCov > 0 || readingCov > 0);
  const weightedFinalGrade = hasModality
    ? computeWeightedFinalGrade(quizGrade, videoCov, readingCov) * 100
    : overallFinal;
  const finalGradeBreakdown = hasModality
    ? `Quiz 60%: ${formatPct100(quizGrade * 100)} · Video 20%: ${formatPct100(videoCov * 100)} · Reading 20%: ${formatPct100(readingCov * 100)}`
    : `Quiz-only dataset · ${formatPct100(overallFinal)} accuracy`;

  // ── ZPD Target count ─────────────────────────────────────────────────────
  const zpdRange = student.learning_path?.zpd_range ?? [0.4, 0.9];
  const zpdLow = zpdRange[0] ?? 0.4;
  const zpdHigh = zpdRange[1] ?? 0.9;
  const lastMastery = student.timeline[student.timeline.length - 1]?.mastery ?? student.final_mastery ?? [];
  const zpdCount = lastMastery.filter((m) => m >= zpdLow && m <= zpdHigh).length;

  // ── PCO-aware risk alerts ────────────────────────────────────────────────
  const pcoSkills = useMemo(
    () => student.review_session?.pco_skills_detected ?? [],
    [student.review_session?.pco_skills_detected]
  );
  const riskAlerts = useMemo(() => {
    if (twinData?.risk_forecast?.at_risk_skills?.length) {
      const alerts = [...twinData.risk_forecast.at_risk_skills];
      // elevate PCO-flagged skills to HIGH priority
      return alerts.map((a) =>
        pcoSkills.includes(a.skill_id) ? { ...a, priority: "HIGH" as const } : a
      );
    }
    // client-side fallback: skills below 50% mastery OR PCO detected
    const lastEntry = student.timeline[student.timeline.length - 1];
    if (!lastEntry) return [];
    const alerts = [];
    for (const skill of skills) {
      const m = lastEntry.mastery[skill.id] ?? 0;
      const isPco = pcoSkills.includes(skill.id);
      if (m < 0.5 || isPco) {
        alerts.push({
          skill_id: skill.id,
          skill_name: skill.name,
          current_mastery: m,
          predicted_decay: 0,
          downstream_at_risk: 0,
          priority: (m < 0.3 || isPco) ? "HIGH" as const : "MEDIUM" as const,
        });
      }
    }
    return alerts.sort((a, b) => a.current_mastery - b.current_mastery).slice(0, 5);
  }, [twinData, student.timeline, skills, pcoSkills]);

  const atRiskCount = twinData?.risk_forecast?.total_at_risk ?? riskAlerts.length;
  const pcoAlertCount = pcoSkills.length;

  // ── radar data ──────────────────────────────────────────────────────────
  const radarData = useMemo(() => {
    return skills.map((chapter, i) => {
      const ids = chapterSubIds[i];
      const initialMastery =
        student.timeline.length > 0 ? avgMastery(student.timeline[0].mastery, ids) * 100 : 0;
      return {
        skill: chapter.name,
        mastery: Number(chapterDeltas[i].final.toFixed(1)),
        initial: Number(initialMastery.toFixed(1)),
      };
    });
  }, [skills, chapterSubIds, student.timeline, chapterDeltas]);

  // ── overall mastery timeline with retention gap ──────────────────────────
  const masteryTimeline = useMemo(() => {
    const step = Math.max(1, Math.floor(student.timeline.length / 200));
    const baseMasteryVec = student.base_mastery;
    void twinData?.current_twin?.mastery;
    return student.timeline
      .filter((_, i) => i % step === 0 || i === student.timeline.length - 1)
      .map((e) => {
        let sum = 0;
        let baseSum = 0;
        for (let d = 0; d < skills.length; d++) {
          sum += avgMastery(e.mastery, chapterSubIds[d]);
          if (baseMasteryVec) {
            baseSum += avgMastery(baseMasteryVec, chapterSubIds[d]);
          }
        }
        const overall = Number(((sum / (skills.length || 1)) * 100).toFixed(1));
        const baseOverall = baseMasteryVec
          ? Number(((baseSum / (skills.length || 1)) * 100).toFixed(1))
          : undefined;
        const retentionGap = baseOverall !== undefined
          ? Number(computeRetentionGap(baseOverall / 100, overall / 100) * 100).toFixed(1)
          : undefined;
        return {
          step: e.step,
          overall,
          ...(baseOverall !== undefined && { base: baseOverall }),
          ...(retentionGap !== undefined && { gap: Number(retentionGap) }),
        };
      });
  }, [student.timeline, skills, chapterSubIds, student.base_mastery, twinData]);

  const hasRetentionGap = student.base_mastery != null && student.base_mastery.length > 0;

  // ── Section 5 data: rolling accuracy ────────────────────────────────────
  const rollingData = useMemo(() => {
    const tl = student.timeline;
    const windowSize = Math.min(50, Math.max(10, Math.floor(tl.length / 10)));
    return tl
      .map((e, i) => {
        const window = tl.slice(Math.max(0, i - windowSize + 1), i + 1);
        const validPred = window.filter((w) => w.predicted_prob != null && !isNaN(w.predicted_prob));
        return {
          step: e.step,
          accuracy: Number(((window.reduce((s, w) => s + w.response, 0) / window.length) * 100).toFixed(2)),
          predicted: validPred.length > 0
            ? Number(((validPred.reduce((s, w) => s + w.predicted_prob, 0) / validPred.length) * 100).toFixed(2))
            : 0,
        };
      })
      .filter((_, i) => i % Math.max(1, Math.floor(tl.length / 300)) === 0 || i === tl.length - 1);
  }, [student.timeline]);

  // ── Section 5 data: calibration ─────────────────────────────────────────
  const calBuckets = useMemo(() => {
    const buckets = Array.from({ length: 10 }, (_, i) => ({
      range: `${i * 10}–${(i + 1) * 10}%`,
      ideal: i * 10 + 5,
      actual: 0,
      count: 0,
    }));
    for (const e of student.timeline) {
      if (e.predicted_prob == null || isNaN(e.predicted_prob)) continue;
      const idx = Math.min(Math.floor(e.predicted_prob * 10), 9);
      buckets[idx].count++;
      buckets[idx].actual += e.response;
    }
    for (const b of buckets) {
      b.actual = b.count > 0 ? Number(((b.actual / b.count) * 100).toFixed(2)) : 0;
    }
    return buckets.filter((b) => b.count > 0);
  }, [student.timeline]);

  // ── Section 5 data: per-chapter mastery evolution ────────────────────────
  const chapterEvolution = useMemo(() => {
    const stepSize = Math.max(1, Math.floor(student.timeline.length / 300));
    return student.timeline
      .filter((_, i) => i % stepSize === 0 || i === student.timeline.length - 1)
      .map((e) => {
        const row: Record<string, number | string> = { step: e.step };
        for (let d = 0; d < skills.length; d++) {
          row[`chapter_${d}`] = +(avgMastery(e.mastery, chapterSubIds[d]) * 100).toFixed(2);
        }
        row.overall = +(
          skills.reduce((sum, _, d) => sum + avgMastery(e.mastery, chapterSubIds[d]), 0) /
          (skills.length || 1) * 100
        ).toFixed(2);
        return row;
      });
  }, [student.timeline, skills, chapterSubIds]);

  // ── learning path next steps ─────────────────────────────────────────────
  const nextSteps = student.learning_path?.steps?.slice(0, 3) ?? [];

  // ── twin confidence label ────────────────────────────────────────────────
  const twinQuality = twinData?.twin_confidence?.quality;

  return (
    <div className="space-y-8">
      {/* ── Section 1: Student Pulse ──────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold">Student Pulse</h2>
            <p className="text-sm text-muted-foreground">Key outcomes at a glance</p>
          </div>
          <div className="flex items-center gap-2">
            {twinQuality && (
              <Badge variant="outline" className="text-xs gap-1">
                <span
                  className={`h-1.5 w-1.5 rounded-full inline-block ${
                    twinQuality.startsWith("Excellent") || twinQuality.startsWith("Good")
                      ? "bg-emerald-500"
                      : twinQuality.startsWith("Moderate")
                      ? "bg-amber-400"
                      : "bg-red-500"
                  }`}
                />
                Twin: {twinQuality}
              </Badge>
            )}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <PulseCard
            label="Final Grade"
            value={formatPct100(weightedFinalGrade)}
            sub={finalGradeBreakdown}
            trend={overallDelta >= 0 ? "up" : "down"}
            accent={weightedFinalGrade >= 70 ? "success" : weightedFinalGrade >= 50 ? "warning" : "danger"}
          />
          <PulseCard
            label={`ZPD Target Skills`}
            value={String(zpdCount)}
            sub={`Mastery ${Math.round(zpdLow * 100)}–${Math.round(zpdHigh * 100)}% — optimal learning zone`}
            accent={zpdCount > 0 ? "success" : "warning"}
          />
          <PulseCard
            label="Chapters Proficient"
            value={`${chaptersProficient} / ${chapterDeltas.length}`}
            sub="Chapters with mastery ≥ 75%"
            accent={chaptersProficient >= Math.ceil(chapterDeltas.length * 0.7) ? "success" : "warning"}
          />
          <PulseCard
            label="Consistency"
            value={`${s.active_days}d`}
            sub={s.active_days >= 5 ? "Strong study habit" : s.active_days >= 2 ? "Keep it going" : "Start a streak today"}
            trend={s.active_days >= 5 ? "up" : "neutral"}
            accent={s.active_days >= 5 ? "success" : s.active_days >= 2 ? "warning" : "default"}
          />
          <PulseCard
            label="Skills to Strengthen"
            value={String(atRiskCount)}
            sub={
              pcoAlertCount > 0
                ? `${pcoAlertCount} PCO-detected · ${twinData ? "Twin forecast" : "Below 50% threshold"}`
                : twinData ? "Digital Twin forecast" : "Below 50% mastery threshold"
            }
            accent={atRiskCount === 0 ? "success" : atRiskCount <= 2 ? "warning" : "danger"}
          />
        </div>
      </section>

      {/* ── Section 2: Mastery Radar + Growth Timeline ────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Mastery Overview</h2>
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Chapter Mastery Radar</CardTitle>
              <CardDescription>Final vs initial mastery — ghost shows where you started</CardDescription>
            </CardHeader>
            <CardContent className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart cx="50%" cy="50%" outerRadius="72%" data={radarData}>
                  <PolarGrid strokeOpacity={0.3} />
                  <PolarAngleAxis dataKey="skill" tick={{ fontSize: 10 }} />
                  <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} tickCount={5} />
                  <Tooltip
                    formatter={(v: number, name: string) => [`${v}%`, name === "mastery" ? "Current" : "Initial"]}
                    contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                  />
                  <Radar
                    name="initial"
                    dataKey="initial"
                    stroke="#94a3b8"
                    fill="#94a3b8"
                    fillOpacity={0.08}
                    strokeWidth={1}
                    strokeDasharray="4 3"
                  />
                  <Radar
                    name="mastery"
                    dataKey="mastery"
                    stroke={SKILL_HEX[0]}
                    fill={SKILL_HEX[0]}
                    fillOpacity={0.22}
                    strokeWidth={2}
                  />
                  <Legend
                    formatter={(v: string) => v === "mastery" ? "Current Mastery" : "Initial Mastery"}
                    wrapperStyle={{ fontSize: "11px" }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Overall Mastery Trajectory</CardTitle>
              <CardDescription>
                {hasRetentionGap
                  ? "Average mastery across all chapters per question answered. Solid = current retained mastery · Dashed = peak mastery before decay. The gap between them is knowledge lost to forgetting."
                  : "Average mastery across all chapters per question answered. Cross the green 60% line to reach proficiency."}
              </CardDescription>
            </CardHeader>
            <CardContent className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                {hasRetentionGap ? (
                  <ComposedChart data={masteryTimeline} margin={{ top: 5, right: 48, left: 0, bottom: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                    <XAxis
                      dataKey="step"
                      tick={{ fontSize: 10 }}
                      label={{ value: "Questions Answered", position: "insideBottom", offset: -10, fontSize: 10, fill: "#888" }}
                    />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                      formatter={(v: number, name: string) => [
                        `${v}%`,
                        name === "overall" ? "Current Mastery" : "Peak Mastery (before decay)",
                      ]}
                    />
                    <Legend
                      formatter={(v: string) => v === "overall" ? "Current Mastery" : "Peak Mastery (before decay)"}
                      wrapperStyle={{ fontSize: "11px" }}
                    />
                    <ReferenceLine y={60} stroke="#10b981" strokeDasharray="4 3" strokeOpacity={0.6}
                      label={{ value: "Proficient (60%)", position: "right", fontSize: 9, fill: "#10b981" }} />
                    <Area
                      type="monotone"
                      dataKey="base"
                      name="base"
                      stroke="#94a3b8"
                      fill="#e2e8f0"
                      fillOpacity={0.4}
                      strokeWidth={1.5}
                      strokeDasharray="6 4"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="overall"
                      name="overall"
                      stroke={OVERALL_HEX}
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                ) : (
                  <LineChart data={masteryTimeline} margin={{ top: 5, right: 48, left: 0, bottom: 18 }}>
                    <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                    <XAxis
                      dataKey="step"
                      tick={{ fontSize: 10 }}
                      label={{ value: "Questions Answered", position: "insideBottom", offset: -10, fontSize: 10, fill: "#888" }}
                    />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                      formatter={(v: number) => [`${v}%`, "Overall Mastery"]}
                    />
                    <ReferenceLine y={60} stroke="#10b981" strokeDasharray="4 3" strokeOpacity={0.6}
                      label={{ value: "Proficient (60%)", position: "right", fontSize: 9, fill: "#10b981" }} />
                    <Line
                      type="monotone"
                      dataKey="overall"
                      stroke={OVERALL_HEX}
                      strokeWidth={2.5}
                      dot={false}
                      activeDot={{ r: 4 }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ── Section 3: Chapter Detail Table ──────────────────────────────── */}
      <section>
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Skill Performance</CardTitle>
                <CardDescription>Click a skill to expand its concepts</CardDescription>
              </div>
              {!hasModality && (
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  Quiz-only dataset
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30 text-left">
                  <th className="p-3 font-medium">Chapter</th>
                  <th className="p-3 font-medium text-right">Sub-skills</th>
                  <th className="p-3 font-medium text-right">Initial</th>
                  {hasModality ? (
                    <>
                      <th className="p-3 font-medium text-right">Quiz (60%)</th>
                      <th className="p-3 font-medium text-right">Video (20%)</th>
                      <th className="p-3 font-medium text-right">Reading (20%)</th>
                      <th className="p-3 font-medium text-right">Final</th>
                    </>
                  ) : (
                    <>
                      <th className="p-3 font-medium text-right">Final</th>
                      <th className="p-3 font-medium text-right">Change</th>
                      <th className="p-3 font-medium text-right">Progress</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {chapterDeltas.map((d, i) => (
                  <ChapterRow
                    key={i}
                    chapter={skills[i]}
                    initial={d.initial}
                    final={d.final}
                    change={d.change}
                    color={SKILL_HEX[i % SKILL_HEX.length]}
                    finalMastery={finalMasteryVec}
                    attemptedSkillIds={attemptedSkillIds}
                    conceptStats={conceptStats}
                    modality={hasModality ? { videoCov, readingCov } : null}
                  />
                ))}
                <tr className="border-t-2 border-border font-semibold bg-muted/10">
                  <td className="p-3 flex items-center gap-2">
                    <span className="inline-block h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: OVERALL_HEX }} />
                    Overall Mastery
                  </td>
                  <td className="p-3 text-right text-muted-foreground">
                    {skills.reduce((s, sk) => s + sk.n_concepts, 0)}
                  </td>
                  <td className="p-3 text-right font-mono tabular-nums text-muted-foreground">{formatPct100(overallInitial)}</td>
                  {hasModality ? (
                    <>
                      <td className="p-3 text-right font-mono tabular-nums">{formatPct100(overallFinal)}</td>
                      <td className="p-3 text-right font-mono tabular-nums">{formatPct100(videoCov * 100)}</td>
                      <td className="p-3 text-right font-mono tabular-nums">{formatPct100(readingCov * 100)}</td>
                      <td className="p-3 text-right font-mono tabular-nums">{formatPct100(weightedFinalGrade)}</td>
                    </>
                  ) : (
                    <>
                      <td className="p-3 text-right font-mono tabular-nums">{formatPct100(overallFinal)}</td>
                      <td className={`p-3 text-right font-mono tabular-nums ${overallDelta >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                        {overallDelta >= 0 ? "+" : ""}{overallDelta.toFixed(1)}%
                      </td>
                      <td className="p-3 text-right">
                        <div className="flex items-center justify-end">
                          <div className="w-20 h-1.5 rounded-full bg-muted overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${Math.min(overallFinal, 100)}%`, backgroundColor: OVERALL_HEX }} />
                          </div>
                        </div>
                      </td>
                    </>
                  )}
                </tr>
              </tbody>
            </table>
          </CardContent>
        </Card>
      </section>

      {/* ── Section 4: Actionable Insights ───────────────────────────────── */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Actionable Insights</h2>
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Next Steps */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-primary" />
                <CardTitle className="text-base">Next Steps</CardTitle>
              </div>
              <CardDescription>Recommended skills from your learning path</CardDescription>
            </CardHeader>
            <CardContent>
              {nextSteps.length === 0 ? (
                <p className="text-sm text-muted-foreground">No learning path generated yet.</p>
              ) : (
                <ol className="space-y-3">
                  {nextSteps.map((step, i) => (
                    <li key={step.skill_id} className="flex items-start gap-3">
                      <span className="shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{step.skill_name}</p>
                        <p className="text-xs text-muted-foreground">
                          Current {formatPct100(step.current_mastery * 100)} · Gain +{formatPct100(step.predicted_mastery_gain * 100)}
                        </p>
                        <p className="text-xs text-muted-foreground italic truncate mt-0.5">{step.rationale}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          {/* Risk Alerts */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <CardTitle className="text-base">Risk Alerts</CardTitle>
              </div>
              <CardDescription>
                {twinData ? "Digital Twin decay forecast" : "Skills below 50% mastery"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {riskAlerts.length === 0 ? (
                <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-4 w-4" />
                  <span className="text-sm">No at-risk skills detected</span>
                </div>
              ) : (
                <ul className="space-y-2">
                  {riskAlerts.slice(0, 4).map((alert) => (
                    <li key={alert.skill_id} className="flex items-center justify-between gap-2">
                      <span className="text-sm truncate min-w-0">{alert.skill_name}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="font-mono tabular-nums text-xs text-muted-foreground">
                          {formatPct100(alert.current_mastery * 100)}
                        </span>
                        <Badge
                          variant={alert.priority === "HIGH" ? "destructive" : "warning"}
                          className="text-[10px] px-1.5 py-0"
                        >
                          {alert.priority}
                        </Badge>
                      </div>
                    </li>
                  ))}
                  {riskAlerts.length > 4 && (
                    <p className="text-xs text-muted-foreground pt-1">
                      +{riskAlerts.length - 4} more at-risk skills
                    </p>
                  )}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* AI Insight card placeholder — full InsightPanel below */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-violet-500" />
                <CardTitle className="text-base">Learning Snapshot</CardTitle>
              </div>
              <CardDescription>Quick stats for your session</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Active days</span>
                  <span className="font-medium">{s.active_days}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total interactions</span>
                  <span className="font-medium">{s.total_interactions.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Overall accuracy</span>
                  <span className="font-medium">{formatPct100(s.accuracy * 100)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Val AUC</span>
                  <span className="font-medium font-mono">{modelInfo.best_val_auc.toFixed(4)}</span>
                </div>
                {twinData?.twin_confidence != null && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Twin RMSE</span>
                    <span className="font-medium font-mono">{twinData.twin_confidence.rmse.toFixed(4)}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Full ARCD Insight Engine */}
        <div className="mt-6">
          <InsightPanel student={student} skills={skills} datasetId={datasetId} />
        </div>
      </section>

      {/* ── Section 5: Deep Dive (teacher mode only) ─────────────────────── */}
      {viewMode === "teacher" && (
      <section>
        <button
          onClick={() => setDeepOpen((v) => !v)}
          className="flex w-full items-center justify-between rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm font-medium hover:bg-muted/40 transition-colors"
        >
          <span className="flex items-center gap-2">
            {deepOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            Deep Dive Analytics
            {viewMode === "teacher" && <span className="text-xs text-muted-foreground">· Model diagnostics</span>}
          </span>
          <span className="text-xs text-muted-foreground">Rolling accuracy · Calibration · Chapter evolution</span>
        </button>

        {deepOpen && (
          <div className="mt-4">
            <Tabs defaultValue="rolling">
              <TabsList className="mb-4">
                <TabsTrigger value="rolling">Rolling Accuracy</TabsTrigger>
                <TabsTrigger value="calibration">Calibration</TabsTrigger>
                <TabsTrigger value="evolution">Mastery Evolution</TabsTrigger>
              </TabsList>

              <TabsContent value="rolling">
                <Card>
                  <CardHeader>
                    <CardTitle>Rolling Accuracy vs Predicted Probability</CardTitle>
                    <CardDescription>Rolling window of actual accuracy against model predictions</CardDescription>
                  </CardHeader>
                  <CardContent className="h-[320px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={rollingData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                        <XAxis dataKey="step" tick={{ fontSize: 11 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                        <Tooltip
                          contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                          formatter={(v: number, name: string) => [
                            `${v}%`,
                            name === "accuracy" ? "Actual Accuracy" : "Predicted",
                          ]}
                        />
                        <ReferenceLine y={50} stroke="#888" strokeDasharray="3 3" />
                        <Area type="monotone" dataKey="accuracy" name="accuracy" stroke={SKILL_HEX[1]} fill={SKILL_HEX[1]} fillOpacity={0.15} strokeWidth={2} />
                        <Area type="monotone" dataKey="predicted" name="predicted" stroke={SKILL_HEX[0]} fill={SKILL_HEX[0]} fillOpacity={0.1} strokeWidth={2} strokeDasharray="5 5" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="calibration">
                <Card>
                  <CardHeader>
                    <CardTitle>Calibration</CardTitle>
                    <CardDescription>
                      For each confidence range, what % did the student actually get right?
                      Bars above the dashed line = model underconfident; below = overconfident.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted-foreground pb-3">
                      <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-sm bg-emerald-500" />Well calibrated (≤5% gap)</span>
                      <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-sm bg-amber-500" />Slightly off (≤15% gap)</span>
                      <span className="flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-sm bg-red-500" />Poorly calibrated (&gt;15% gap)</span>
                    </div>
                    <div className="h-[270px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={calBuckets} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                          <XAxis dataKey="range" tick={{ fontSize: 10 }} />
                          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                          <Tooltip
                            contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                            formatter={(v: number, name: string) => [
                              `${v}%`,
                              name === "ideal" ? "Perfect Calibration" : "Actual Accuracy",
                            ]}
                          />
                          <Line dataKey="ideal" stroke="#a78bfa" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3, fill: "#a78bfa" }} legendType="none" />
                          <Bar dataKey="actual" radius={[4, 4, 0, 0]} barSize={36} legendType="none">
                            {calBuckets.map((entry, i) => {
                              const gap = Math.abs(entry.actual - entry.ideal);
                              return <Cell key={i} fill={gap <= 5 ? "#10b981" : gap <= 15 ? "#eab308" : "#f43f5e"} />;
                            })}
                            <LabelList dataKey="count" position="top" style={{ fontSize: 9, fill: "#888" }} formatter={(v: number) => `n=${v}`} />
                          </Bar>
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="evolution">
                <Card>
                  <CardHeader>
                    <CardTitle>Mastery Evolution by Chapter</CardTitle>
                    <CardDescription>Per-chapter mastery trajectories across the learning journey</CardDescription>
                  </CardHeader>
                  <CardContent className="h-[380px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chapterEvolution} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                        <XAxis dataKey="step" tick={{ fontSize: 11 }} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                        <Tooltip
                          contentStyle={{ borderRadius: "8px", fontSize: "12px" }}
                          formatter={(v: number, name: string) => {
                            if (name === "overall") return [`${v}%`, "Overall"];
                            const idx = parseInt(name.split("_")[1]);
                            return [`${v}%`, skills[idx]?.name ?? name];
                          }}
                        />
                        <Legend
                          formatter={(v: string) => {
                            if (v === "overall") return "Overall";
                            const idx = parseInt(v.split("_")[1]);
                            return skills[idx]?.name ?? v;
                          }}
                          wrapperStyle={{ fontSize: "10px" }}
                        />
                        {skills.map((_, i) => (
                          <Line
                            key={i}
                            type="monotone"
                            dataKey={`chapter_${i}`}
                            stroke={SKILL_HEX[i % SKILL_HEX.length]}
                            strokeWidth={1.5}
                            dot={false}
                            isAnimationActive={false}
                          />
                        ))}
                        <Line
                          type="monotone"
                          dataKey="overall"
                          stroke={OVERALL_HEX}
                          strokeWidth={2.5}
                          strokeDasharray="6 3"
                          dot={false}
                          isAnimationActive={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </section>
      )}

      {/* ── Teacher-only: Class Heatmap ───────────────────────────────── */}
      {viewMode === "teacher" && allStudents.length > 1 && (
        <ClassHeatmap students={allStudents} skills={skills} currentUid={student.uid} />
      )}
    </div>
  );
}
