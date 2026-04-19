import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
  BarChart, Bar, Cell, Legend,
} from "recharts";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  StudentPortfolio,
  SkillInfo,
  TimelineEntry,
  TwinViewerData,
} from "@/features/arcd-agent/lib/types";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);
// ── helpers ────────────────────────────────────────────────────────────────────

function masteryColor(m: number): string {
  if (m >= 0.8) return "#22c55e";
  if (m >= 0.6) return "#84cc16";
  if (m >= 0.4) return "#f59e0b";
  return "#ef4444";
}

function fmtPct(v: number, d = 1): string {
  return `${(v * 100).toFixed(d)}%`;
}

// ── stat card ──────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, accent,
}: {
  label: string; value: string; sub?: string; accent?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-1 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <p className={`text-2xl font-bold ${accent ?? ""}`}>{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ── prediction accuracy chart ───────────────────────────────────────────────

function PredictionChart({ timeline }: { timeline: TimelineEntry[] }) {
  const data = useMemo(() => {
    const step = Math.max(1, Math.floor(timeline.length / 60));
    return timeline
      .filter((_, i) => i % step === 0)
      .map((e) => ({
        step: e.step,
        predicted: +(e.predicted_prob * 100).toFixed(1),
        correct: e.response === 1,
      }));
  }, [timeline]);

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="step" tick={{ fontSize: 9 }} label={{ value: "Interaction", position: "insideBottom", offset: -2, fontSize: 10 }} />
        <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 9 }} label={{ value: "Predicted P(correct)", angle: -90, position: "insideLeft", fontSize: 10 }} />
        <Tooltip
          formatter={(v: number) => [`${v}%`, "Predicted P(correct)"]}
          labelFormatter={(l) => `Interaction ${l}`}
        />
        <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: "50%", position: "right", fontSize: 9, fill: "#94a3b8" }} />
        <Bar dataKey="predicted" name="P(correct)" maxBarSize={8}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.correct ? "#22c55e" : "#ef4444"} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── what-if simulation types ────────────────────────────────────────────────

interface SimPath {
  name: string;
  description: string;
  skills: Array<{ id: number; name: string; currentMastery: number }>;
  trajectory: Array<{ step: number; avgMastery: number }>;
  totalGain: number;
  finalAvg: number;
  coherenceScore: number;
  justification: string[];
}

const DAY_OPTIONS = [7, 14, 21, 30] as const;

function getActionableSkillCap(days: number, totalSkills: number): number {
  const cap = days <= 7 ? 5 : days <= 14 ? 10 : days <= 21 ? 15 : 20;
  return Math.min(totalSkills, cap);
}

/**
 * Lightweight coherence preview for manual skill selection UI only.
 * Full scoring runs on the backend; this is used purely for the live badge.
 */
function computeCoherencePreview(skillIds: number[], mastery: number[]): number {
  const n = skillIds.length;
  if (n < 2) return 0.5;
  let connected = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (Math.abs(skillIds[i] - skillIds[j]) <= 2) connected++;
    }
  }
  const proximity = connected / Math.max((n * (n - 1)) / 2, 1);
  const zpd = skillIds.filter((id) => {
    const m = mastery[id] ?? 0;
    return m >= 0.30 && m <= 0.70;
  }).length / n;
  return 0.6 * proximity + 0.4 * zpd;
}

/**
 * Learning-efficiency weight by current mastery for what-if gain estimates.
 * Peaks at 1.0 in the ZPD band [0.3, 0.7]. Stays > 0 below 30% so novices
 * (mastery 0%) still show non-zero projected gain — the old triangle kernel
 * `1 - |m - 0.65| / 0.55` evaluated to 0 at m=0 and broke the manual preview.
 */
function zpdLearningWeight(m: number): number {
  const x = Math.max(0, Math.min(1, m));
  if (x >= 0.3 && x <= 0.7) return 1;
  if (x < 0.3) {
    return 0.42 + (x / 0.3) * 0.58;
  }
  return Math.max(0.22, 1 - ((x - 0.7) / 0.3) * 0.78);
}

/** Label and colour for a coherence score. */
function coherenceLabel(score: number): { text: string; color: string; bg: string } {
  if (score >= 0.72) return { text: "Strong Chain", color: "text-emerald-700 dark:text-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-300 dark:border-emerald-700" };
  if (score >= 0.50) return { text: "Connected", color: "text-blue-700 dark:text-blue-400", bg: "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700" };
  if (score >= 0.28) return { text: "Loose", color: "text-amber-700 dark:text-amber-400", bg: "bg-amber-50 dark:bg-amber-950/30 border-amber-300 dark:border-amber-700" };
  return { text: "Scattered", color: "text-muted-foreground", bg: "bg-muted/30 border-border" };
}

interface WhatIfAdvice {
  best_strategy: string;
  rationale: string;
  action_items: string[];
  generated_at: string;
  source: "llm" | "rule_based";
}

function parseAdvisorRationale(text: string | undefined): { lead: string; points: string[]; embeddedActions: string[] } {
  if (!text) {
    return { lead: "", points: [], embeddedActions: [] };
  }
  const cleaned = text.replace(/\*\*/g, "").trim();
  const [mainPart, actionPart = ""] = cleaned.split(/action items?:/i);
  const sentenceChunks = mainPart
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[.!?])\s+(?=[A-Z])/))
    .map((s) => s.trim())
    .filter(Boolean);
  const lead = sentenceChunks[0] ?? "";
  const points = sentenceChunks.slice(1);
  const embeddedActions = actionPart
    .split(/\d+\.\s+/)
    .map((s) => s.trim())
    .filter(Boolean);

  return { lead, points, embeddedActions };
}

// ── main component ─────────────────────────────────────────────────────────────

interface TwinViewerTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
  datasetId: string;
  twinData?: TwinViewerData | null;
  viewMode?: "student" | "teacher";
  allStudents?: StudentPortfolio[];
  setSelectedUid?: (uid: string) => void;
}

export function TwinViewerTab({ student, skills, datasetId, twinData, viewMode = "student", allStudents = [], setSelectedUid }: TwinViewerTabProps) {
  const mastery = useMemo(() => {
    const raw = student.final_mastery ?? [];
    // mastery[i] = mastery for skills[i]. The mastery vector is already indexed by skill position.
    return skills.length === 0 ? raw : skills.map((_, idx) => raw[idx] ?? 0);
  }, [student.final_mastery, skills]);

  const skillNameMap = useMemo(
    () =>
      Object.fromEntries(
        mastery.map((_, idx) => [idx, skills[idx]?.name ?? `Skill ${idx}`]),
      ) as Record<number, string>,
    [mastery, skills],
  );
  const timeline = student.timeline;
  const THRESHOLD = 0.5;

  const storageKey = `arcd_twin_whatif_${datasetId}_${student.uid}`;
  const [simStepCount, setSimStepCount] = useState(14);
  const [mode, setMode] = useState<"auto" | "manual">("auto");
  const [manualSkillIds, setManualSkillIds] = useState<number[]>([]);
  const [whatIfAdvice, setWhatIfAdvice] = useState<WhatIfAdvice | null>(null);
  const [advisorLoading, setAdvisorLoading] = useState(false);
  const [advisorError, setAdvisorError] = useState<string | null>(null);

  // ── mastery list sorted desc ──────────────────────────────────────────────
  const masteryList = useMemo(
    () =>
      mastery
        .map((m, i) => ({
          skillIdx: i,
          name: skillNameMap[i] ?? `Skill ${i}`,
          mastery: m,
        }))
        .sort((a, b) => b.mastery - a.mastery),
    [mastery, skillNameMap],
  );

  const nSkills = mastery.length;
  const avgMastery =
    nSkills > 0 ? mastery.reduce((a, b) => a + b, 0) / nSkills : 0;
  const above60 = mastery.filter((m) => m >= 0.6).length;
  const actionableSkillCap = useMemo(
    () => getActionableSkillCap(simStepCount, nSkills),
    [simStepCount, nSkills],
  );

  // ── mastery trajectory from timeline ─────────────────────────────────────
  const trajectory = useMemo(() => {
    if (timeline.length < 2) return [];
    const maxSnaps = 16;
    const step = Math.max(1, Math.floor(timeline.length / maxSnaps));
    const indices = new Set<number>();
    for (let i = 0; i < timeline.length; i += step) indices.add(i);
    indices.add(timeline.length - 1);

    return Array.from(indices)
      .sort((a, b) => a - b)
      .map((idx) => {
        const e = timeline[idx];
        const avg =
          e.mastery.length > 0
            ? e.mastery.reduce((a, b) => a + b, 0) / e.mastery.length
            : 0;
        return {
          step: `T${e.step}`,
          date: new Date(e.timestamp).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          }),
          avgMastery: +(avg * 100).toFixed(2),
        };
      });
  }, [timeline]);

  // ── mastery delta (first → last snapshot) ────────────────────────────────
  const masteryDelta = useMemo(() => {
    if (timeline.length < 2) return null;
    const first = timeline[0];
    const last = timeline[timeline.length - 1];
    if (!first.mastery.length || !last.mastery.length) return null;
    const avg = (arr: number[]) => arr.reduce((a, b) => a + b, 0) / arr.length;
    return avg(last.mastery) - avg(first.mastery);
  }, [timeline]);

  // ── risk alerts (computed from final_mastery) ─────────────────────────────
  const riskAlerts = useMemo(
    () =>
      mastery
        .map((m, i) => ({
          skill_id: i,
          skill_name: skillNameMap[i] ?? `Skill ${i}`,
          current_mastery: m,
          priority:
            m < 0.3 ? ("HIGH" as const) : m < 0.4 ? ("MEDIUM" as const) : ("LOW" as const),
        }))
        .filter((x) => x.current_mastery < THRESHOLD)
        .sort((a, b) => a.current_mastery - b.current_mastery)
        .slice(0, 10),
    [mastery, skillNameMap],
  );

  // ── what-if simulation — consume backend-computed paths ─────────────────

  // Raw backend paths kept for horizon-fit labeling (unfiltered by simStepCount)
  const horizonPaths = useMemo(() => {
    const sc = twinData?.scenario_comparison;
    if (!sc || nSkills === 0) return null;
    return [sc.path_a, sc.path_b, sc.path_c] as const;
  }, [twinData, nSkills]);

  const simulation = useMemo(() => {
    const sc = twinData?.scenario_comparison;
    if (!sc || nSkills === 0) return null;

    const toSimPath = (bp: typeof sc.path_a): SimPath => {
      // Slice trajectory to the chosen horizon
      const filtered = bp.trajectory.filter((p) => p.step <= simStepCount);
      const startPct = filtered[0]?.avgMastery ?? 0;
      const endPct = filtered[filtered.length - 1]?.avgMastery ?? startPct;
      return {
        name: bp.name,
        description: bp.justification[0] ?? "",
        skills: bp.skills.map((id, i) => ({
          id,
          name: bp.skill_names[i] ?? skillNameMap[id] ?? `Skill ${id}`,
          currentMastery: mastery[id] ?? 0,
        })),
        trajectory: filtered,
        // Derive gain and final avg AT the selected horizon, not the full-run value
        totalGain: (endPct - startPct) / 100,
        finalAvg: endPct / 100,
        coherenceScore: bp.coherence_score,
        justification: bp.justification,
      };
    };

    const pathA = toSimPath(sc.path_a);
    const pathB = toSimPath(sc.path_b);
    const pathC = toSimPath(sc.path_c);

    // Manual path D: lightweight ZPD-based preview — anchored to the same
    // starting point as the backend paths so it sits correctly on the chart.
    let pathD: SimPath | null = null;
    if (mode === "manual" && manualSkillIds.length > 0) {
      const ids = manualSkillIds.filter((id) => id >= 0 && id < nSkills).slice(0, actionableSkillCap);
      if (ids.length > 0) {
        const coherenceScore = computeCoherencePreview(ids, mastery);

        // Use the step-0 value from any backend path as the shared anchor so
        // all four lines start at exactly the same point on the chart.
        const anchorPct = pathA.trajectory[0]?.avgMastery
          ?? (nSkills > 0 ? (mastery.reduce((a, b) => a + b, 0) / nSkills) * 100 : 0);
        const startAvg = anchorPct / 100;

        // ZPD-weighted gain per selected skill, spread across total skills.
        // Use exponential saturation (τ≈3.5d) so that a 7-day plan captures ~86%
        // of the 30-day gain, matching the rapid-plateau shape the backend produces.
        const timeScale = 1 - Math.exp(-simStepCount / 3.5);
        const gainPerSkill = ids.reduce((sum, id) => {
          const m = mastery[id] ?? 0;
          const w = zpdLearningWeight(m);
          return sum + (1 - m) * 0.11 * w * (1 + coherenceScore * 0.25) * timeScale;
        }, 0);
        const totalGain = gainPerSkill / nSkills;
        const finalAvg = Math.min(1, startAvg + totalGain);

        // Build trajectory: slight S-curve so it doesn't look like a ruler line
        const trajectory = Array.from({ length: simStepCount + 1 }, (_, i) => {
          const t = i / Math.max(simStepCount, 1);
          // ease-in-out cubic
          const eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
          return {
            step: i,
            avgMastery: +((startAvg + (finalAvg - startAvg) * eased) * 100).toFixed(2),
          };
        });

        pathD = {
          name: "Custom Selection",
          description: "Your manual skill selection — preview trajectory (full simulation on the backend)",
          skills: ids.map((id) => ({
            id,
            name: skillNameMap[id] ?? `Skill ${id}`,
            currentMastery: mastery[id] ?? 0,
          })),
          trajectory,
          totalGain,
          finalAvg,
          coherenceScore,
          justification: [
            `${ids.length} of ${nSkills} skills targeted over ${simStepCount} days.`,
            `Coherence score: ${Math.round(coherenceScore * 100)}% — ${
              coherenceScore >= 0.72 ? "strong chain" : coherenceScore >= 0.50 ? "connected" : "loosely linked"
            }.`,
          ],
        };
      }
    }

    return { pathA, pathB, pathC, pathD };
  }, [twinData, nSkills, mastery, skillNameMap, simStepCount, mode, manualSkillIds, actionableSkillCap]);

  const manualImpactPreview = useMemo(() => {
    if (mode !== "manual" || nSkills === 0 || manualSkillIds.length === 0) return null;

    const selectedIds = manualSkillIds
      .slice(0, nSkills)
      .filter((id) => id >= 0 && id < nSkills);

    if (selectedIds.length === 0) return null;

    const coherenceScore = computeCoherencePreview(selectedIds, mastery);
    const avgBefore = mastery.reduce((a, b) => a + b, 0) / Math.max(nSkills, 1);
    // Exponential saturation: most mastery gain plateaus within a few days,
    // so 7d ≈ 86% of 30d gain (not 23% as linear 7/30 would give).
    const timeScale = 1 - Math.exp(-simStepCount / 3.5);

    const perSkill = selectedIds
      .map((id) => {
        const m = mastery[id] ?? 0;
        const w = zpdLearningWeight(m);
        const gain = (1 - m) * 0.13 * w * (1 + coherenceScore * 0.2) * timeScale;
        return { id, name: skillNameMap[id] ?? `Skill ${id}`, current: m, projectedGain: gain };
      })
      .sort((a, b) => b.projectedGain - a.projectedGain);

    const totalGain = perSkill.reduce((sum, x) => sum + x.projectedGain, 0) / Math.max(nSkills, 1);

    return {
      count: perSkill.length,
      avgBefore,
      projectedGain: totalGain,
      avgAfter: avgBefore + totalGain,
      topContributors: perSkill.slice(0, 5),
      coherenceScore,
    };
  }, [mode, nSkills, manualSkillIds, mastery, skillNameMap, simStepCount]);

  // ── twin confidence (RMSE of predicted_prob vs actual response) ───────────
  const confidence = useMemo(() => {
    const pairs = timeline.filter((e) => e.predicted_prob != null);
    if (pairs.length < 2) return null;

    const brierScore =
      pairs.reduce((s, e) => s + (e.predicted_prob - e.response) ** 2, 0) /
      pairs.length;
    const mae =
      pairs.reduce((s, e) => s + Math.abs(e.predicted_prob - e.response), 0) /
      pairs.length;

    // Calibration: how often the model is "directionally correct"
    // (predicted > 0.5 when response = 1, predicted < 0.5 when response = 0)
    const directionallyCorrect = pairs.filter(
      (e) => (e.predicted_prob >= 0.5) === (e.response === 1),
    ).length;
    const classificationAcc = directionallyCorrect / pairs.length;

    // Actual accuracy
    const accuracy = pairs.filter((e) => e.response === 1).length / pairs.length;
    const avgPredicted = pairs.reduce((s, e) => s + e.predicted_prob, 0) / pairs.length;

    return {
      brierScore,
      rmse: Math.sqrt(brierScore),
      mae,
      classificationAcc,
      accuracy,
      avgPredicted,
      n: pairs.length,
    };
  }, [timeline]);

  const lastTs = timeline.length > 0 ? timeline[timeline.length - 1].timestamp : null;

  // Best path — horizon-aware: at short horizons focused retrieval leads;
  // at longer horizons spaced/desirable-difficulty compounds and overtakes.
  const bestSimName = useMemo(() => {
    if (!simulation) return null;

    const scoreAt = (path: SimPath) =>
      (path.trajectory.find((p) => p.step === simStepCount) ??
        path.trajectory[path.trajectory.length - 1])?.avgMastery ?? 0;

    const candidates = [
      { name: simulation.pathA.name, score: scoreAt(simulation.pathA) },
      { name: simulation.pathB.name, score: scoreAt(simulation.pathB) },
      { name: simulation.pathC.name, score: scoreAt(simulation.pathC) },
    ];
    return candidates.reduce((best, p) => (p.score > best.score ? p : best), candidates[0]).name;
  }, [simulation, simStepCount]);

  /**
   * For each path, find the horizon windows (from DAY_OPTIONS) where it is
   * the top-scoring strategy — computed from the FULL (unfiltered) backend
   * trajectories so the badge stays stable regardless of the selected simStepCount.
   */
  const horizonFitLabel = useMemo(() => {
    if (!horizonPaths) return {} as Record<string, string | null>;

    const winDays = (bp: typeof horizonPaths[number]) =>
      DAY_OPTIONS.filter((day) => {
        const mine = bp.trajectory.find((t) => t.step === day)?.avgMastery ?? 0;
        return horizonPaths.every(
          (other) => (other.trajectory.find((t) => t.step === day)?.avgMastery ?? 0) <= mine + 0.05,
        );
      });

    const label = (days: readonly number[]) => {
      if (days.length === 0) return null;
      if (days.every((d) => d <= 14)) return "Short-term (≤14d)";
      if (days.every((d) => d >= 21)) return "Long-term (≥21d)";
      if (days.length === DAY_OPTIONS.length) return "All horizons";
      return `${Math.min(...days)}–${Math.max(...days)}d`;
    };

    return Object.fromEntries(
      horizonPaths.map((p) => [p.name, label(winDays(p))]),
    ) as Record<string, string | null>;
  }, [horizonPaths]);

  const effectiveBestName = whatIfAdvice?.best_strategy ?? bestSimName ?? null;
  const rationaleParts = useMemo(
    () => parseAdvisorRationale(whatIfAdvice?.rationale),
    [whatIfAdvice?.rationale],
  );
  const advisorActions = useMemo(() => {
    const merged = [...(whatIfAdvice?.action_items ?? []), ...rationaleParts.embeddedActions];
    const seen = new Set<string>();
    return merged.filter((item) => {
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [whatIfAdvice?.action_items, rationaleParts.embeddedActions]);

  useEffect(() => {
    setManualSkillIds((prev) =>
      prev.length > actionableSkillCap ? prev.slice(0, actionableSkillCap) : prev,
    );
  }, [actionableSkillCap]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        simStepCount?: number;
        mode?: "auto" | "manual";
        manualSkillIds?: number[];
        whatIfAdvice?: WhatIfAdvice | null;
      };
      if (parsed.simStepCount && DAY_OPTIONS.includes(parsed.simStepCount as (typeof DAY_OPTIONS)[number])) {
        setSimStepCount(parsed.simStepCount);
      }
      if (parsed.mode === "auto" || parsed.mode === "manual") setMode(parsed.mode);
      if (Array.isArray(parsed.manualSkillIds)) setManualSkillIds(parsed.manualSkillIds);
      if (parsed.whatIfAdvice) setWhatIfAdvice(parsed.whatIfAdvice);
    } catch {
      // ignore corrupt localStorage
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, student.uid]);

  useEffect(() => {
    try {
      localStorage.setItem(
        storageKey,
        JSON.stringify({
          simStepCount,
          mode,
          manualSkillIds,
          whatIfAdvice,
        }),
      );
    } catch {
      // ignore quota errors
    }
  }, [storageKey, simStepCount, mode, manualSkillIds, whatIfAdvice]);

  useEffect(() => {
    if (viewMode !== "student" || !simulation) return;
    const options = [simulation.pathA, simulation.pathB, simulation.pathC, simulation.pathD]
      .filter((p): p is SimPath => p != null)
      .map((p) => ({
        name: p.name,
        total_gain: p.totalGain,
        final_avg: p.finalAvg,
        target_skills: p.skills.map((s) => s.name),
        coherence_score: p.coherenceScore,
      }));
    const controller = new AbortController();
    const run = async () => {
      setAdvisorLoading(true);
      setAdvisorError(null);
      try {
        const token = localStorage.getItem("access_token");
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) headers.Authorization = `Bearer ${token}`;
        const resp = await fetch(`${API_BASE}/diagnosis/what-if-analysis`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            mastery_vector: mastery,
            strategy_options: options,
            recommended_strategy: bestSimName ?? null,
          }),
          signal: controller.signal,
        });
        if (!resp.ok) throw new Error(`Advisor request failed (${resp.status})`);
        const data = (await resp.json()) as WhatIfAdvice;
        setWhatIfAdvice(data);
      } catch (e: unknown) {
        if ((e as { name?: string })?.name !== "AbortError") {
          setAdvisorError(e instanceof Error ? e.message : "Failed to load strategy advisor");
        }
      } finally {
        setAdvisorLoading(false);
      }
    };
    run();
    return () => controller.abort();
  }, [viewMode, simulation, mastery, bestSimName]);

  // ─────────────────────────────────────────────────────────────────────────────
  // ── Teacher dashboard helpers ─────────────────────────────────────────────────

  const classStats = useMemo(() => {
    if (viewMode !== "teacher" || allStudents.length === 0) return null;
    return allStudents.map((s) => {
      const m = s.final_mastery ?? [];
      const avgM = m.length > 0 ? m.reduce((a, b) => a + b, 0) / m.length : 0;
      const atRisk = m.filter((v) => v < 0.5).length;
      const above75 = m.filter((v) => v >= 0.75).length;
      // Simple trend: compare first half avg mastery vs second half of timeline
      const tl = s.timeline;
      let trend: "up" | "down" | "neutral" = "neutral";
      if (tl.length >= 4) {
        const mid = Math.floor(tl.length / 2);
        const firstHalfAvg = tl.slice(0, mid).reduce((a, e) => {
          const mv = e.mastery.length > 0 ? e.mastery.reduce((x, y) => x + y, 0) / e.mastery.length : 0;
          return a + mv;
        }, 0) / mid;
        const secondHalfAvg = tl.slice(mid).reduce((a, e) => {
          const mv = e.mastery.length > 0 ? e.mastery.reduce((x, y) => x + y, 0) / e.mastery.length : 0;
          return a + mv;
        }, 0) / (tl.length - mid);
        if (secondHalfAvg - firstHalfAvg > 0.01) trend = "up";
        else if (firstHalfAvg - secondHalfAvg > 0.01) trend = "down";
      }
      return { uid: s.uid, avgM, atRisk, above75, nSkills: m.length, trend, isCurrentStudent: s.uid === student.uid };
    }).sort((a, b) => a.avgM - b.avgM); // sort: most at-risk first
  }, [viewMode, allStudents, student.uid]);

  // Cohort mastery trajectory: average of all students' timelines per step
  const cohortTrajectory = useMemo(() => {
    if (viewMode !== "teacher" || allStudents.length < 2) return null;
    // Sample max 20 points, use the sampled steps of the current student as reference
    const maxPoints = 20;
    const refTl = student.timeline;
    if (refTl.length < 2) return null;
    const step = Math.max(1, Math.floor(refTl.length / maxPoints));
    const indices: number[] = [];
    for (let i = 0; i < refTl.length; i += step) indices.push(i);
    if (indices[indices.length - 1] !== refTl.length - 1) indices.push(refTl.length - 1);

    return indices.map((idx) => {
      const refEntry = refTl[idx];
      // Average mastery at this point across all students who have enough timeline data
      let sum = 0; let count = 0;
      for (const s of allStudents) {
        const i = Math.min(idx, s.timeline.length - 1);
        if (i < 0) continue;
        const e = s.timeline[i];
        const mv = e.mastery.length > 0 ? e.mastery.reduce((a, b) => a + b, 0) / e.mastery.length : 0;
        sum += mv; count++;
      }
      return {
        step: `T${refEntry.step}`,
        cohortAvg: count > 0 ? +(sum / count * 100).toFixed(2) : 0,
        studentMastery: +(refEntry.mastery.length > 0
          ? refEntry.mastery.reduce((a, b) => a + b, 0) / refEntry.mastery.length * 100
          : 0).toFixed(2),
      };
    });
  }, [viewMode, allStudents, student]);

  // ─────────────────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Teacher Mode: Class Overview ─────────────────────────────────── */}
      {viewMode === "teacher" && classStats && (
        <>
          {/* Risk tier summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Critical (<30%)", tier: (s: typeof classStats[0]) => s.avgM < 0.3, color: "text-red-600", bg: "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800" },
              { label: "High Risk (30–50%)", tier: (s: typeof classStats[0]) => s.avgM >= 0.3 && s.avgM < 0.5, color: "text-amber-600", bg: "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800" },
              { label: "Moderate (50–75%)", tier: (s: typeof classStats[0]) => s.avgM >= 0.5 && s.avgM < 0.75, color: "text-blue-600", bg: "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800" },
              { label: "Proficient (≥75%)", tier: (s: typeof classStats[0]) => s.avgM >= 0.75, color: "text-emerald-600", bg: "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800" },
            ].map(({ label, tier, color, bg }) => {
              const count = classStats.filter(tier).length;
              return (
                <Card key={label} className={`border ${bg}`}>
                  <CardHeader className="pb-1 pt-4 px-4">
                    <CardTitle className={`text-xs font-medium ${color}`}>{label}</CardTitle>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    <p className={`text-3xl font-bold ${color}`}>{count}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      of {classStats.length} students
                    </p>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Cohort trajectory vs current student */}
          {cohortTrajectory && cohortTrajectory.length >= 2 && (
            <Card>
              <CardHeader>
                <CardTitle>Cohort Mastery Trajectory</CardTitle>
                <CardDescription>
                  Class average vs. Student {student.uid} over time
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={cohortTrajectory} margin={{ right: 12 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="step" tick={{ fontSize: 10 }} />
                    <YAxis domain={["auto", "auto"]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
                    <Tooltip formatter={(v: number, name: string) => [`${v}%`, name === "cohortAvg" ? "Class Average" : `Student ${student.uid}`]} />
                    <Legend formatter={(v) => v === "cohortAvg" ? "Class Average" : `Student ${student.uid}`} wrapperStyle={{ fontSize: "11px" }} />
                    <ReferenceLine y={75} stroke="#10b981" strokeDasharray="4 4" label={{ value: "Proficient", position: "right", fontSize: 9, fill: "#10b981" }} />
                    <Line type="monotone" dataKey="cohortAvg" name="cohortAvg" stroke="#94a3b8" strokeWidth={2} strokeDasharray="6 3" dot={false} />
                    <Line type="monotone" dataKey="studentMastery" name="studentMastery" stroke="#f97316" strokeWidth={2.5} dot={{ r: 3, fill: "#f97316" }} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {/* Student comparison table */}
          <Card>
            <CardHeader>
              <CardTitle>Student Comparison</CardTitle>
              <CardDescription>
                All students ranked by average mastery — click to load a student's twin
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="text-left p-2">Student</th>
                      <th className="text-right p-2">Avg Mastery</th>
                      <th className="text-right p-2">At-Risk Skills</th>
                      <th className="text-right p-2">Proficient</th>
                      <th className="text-center p-2">Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {classStats.map((s) => (
                      <tr
                        key={s.uid}
                        onClick={() => setSelectedUid?.(s.uid)}
                        className={`border-b cursor-pointer hover:bg-muted/30 transition-colors ${s.isCurrentStudent ? "bg-primary/5" : ""}`}
                      >
                        <td className="p-2 font-mono text-xs">
                          {s.uid}
                          {s.isCurrentStudent && <Badge className="ml-2 text-[9px] bg-primary text-primary-foreground">Viewing</Badge>}
                        </td>
                        <td className="p-2 text-right font-mono tabular-nums">
                          <span className={s.avgM < 0.5 ? "text-red-600 font-semibold" : s.avgM >= 0.75 ? "text-emerald-600" : "text-blue-600"}>
                            {(s.avgM * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="p-2 text-right">
                          {s.atRisk > 0
                            ? <Badge variant="destructive" className="text-[10px]">{s.atRisk}</Badge>
                            : <span className="text-emerald-600 text-xs">0</span>
                          }
                        </td>
                        <td className="p-2 text-right text-xs text-muted-foreground">
                          {s.above75}/{s.nSkills}
                        </td>
                        <td className="p-2 text-center text-sm">
                          {s.trend === "up" ? "↑" : s.trend === "down" ? "↓" : "→"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Intervention recommendations */}
          <Card>
            <CardHeader>
              <CardTitle>Intervention Recommendations</CardTitle>
              <CardDescription>
                Students who need immediate attention based on mastery and trend
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {classStats
                  .filter((s) => s.avgM < 0.5 || s.trend === "down")
                  .slice(0, 8)
                  .map((s) => (
                    <div
                      key={s.uid}
                      className="flex items-center justify-between gap-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/10 p-3"
                    >
                      <div>
                        <p className="text-sm font-medium font-mono">{s.uid}</p>
                        <p className="text-xs text-muted-foreground">
                          Avg mastery: {(s.avgM * 100).toFixed(1)}% · {s.atRisk} skills below 50%
                        </p>
                      </div>
                      <Badge
                        variant={s.avgM < 0.3 ? "destructive" : "default"}
                        className="text-[10px] shrink-0"
                      >
                        {s.avgM < 0.3
                          ? "Schedule review session"
                          : s.trend === "down"
                          ? "Assign practice exercises"
                          : "Monitor closely"}
                      </Badge>
                    </div>
                  ))}
                {classStats.filter((s) => s.avgM < 0.5 || s.trend === "down").length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    ✓ No students currently flagged for intervention.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <div className="border-t pt-4">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Individual Student Twin — Student {student.uid}
            </p>
          </div>
        </>
      )}

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-orange-200 bg-gradient-to-r from-orange-50 to-amber-50 dark:from-orange-950/20 dark:to-amber-950/20 p-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-bold">Digital Twin</span>
            <Badge
              variant="outline"
              className="text-[11px] border-orange-400 text-orange-700 dark:text-orange-400"
            >
              Live · {datasetId.toUpperCase()}
            </Badge>
            <Badge variant="secondary" className="text-[11px]">
              {nSkills} skills
            </Badge>
            <Badge variant="secondary" className="text-[11px]">
              {timeline.length} interactions
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Student{" "}
            <code className="font-mono text-foreground">{student.uid}</code>
            {lastTs && (
              <>
                {" · "}Last interaction{" "}
                {new Date(lastTs).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </>
            )}
          </p>
        </div>
        {masteryDelta !== null && (
          <div className="text-right shrink-0">
            <p
              className={`text-xl font-bold ${masteryDelta >= 0 ? "text-emerald-600" : "text-red-500"}`}
            >
              {masteryDelta >= 0 ? "+" : ""}
              {fmtPct(masteryDelta, 2)}
            </p>
            <p className="text-xs text-muted-foreground">mastery Δ</p>
          </div>
        )}
      </div>

      {/* ── Stat cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Avg Mastery" value={fmtPct(avgMastery)} />
        <StatCard
          label="Skills ≥ 60%"
          value={String(above60)}
          sub={`of ${nSkills} (${fmtPct(above60 / nSkills, 0)})`}
          accent="text-emerald-600"
        />
        <StatCard
          label="At-Risk Skills"
          value={String(riskAlerts.length)}
          sub={`below ${fmtPct(THRESHOLD, 0)} threshold`}
          accent={riskAlerts.length > 0 ? "text-red-500" : "text-emerald-600"}
        />
        {confidence ? (
          <StatCard
            label="Prediction Quality"
            value={fmtPct(confidence.classificationAcc, 0)}
            sub={`over ${confidence.n} interactions`}
            accent={confidence.classificationAcc >= 0.65 ? "text-emerald-600" : "text-amber-500"}
          />
        ) : (
          <StatCard
            label="Accuracy"
            value={
              student.summary.accuracy !== undefined
                ? fmtPct(student.summary.accuracy)
                : "—"
            }
            sub="overall response accuracy"
          />
        )}
      </div>

      {/* ── Current mastery list ─────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Current Skill Mastery</CardTitle>
          <CardDescription>
            All {nSkills} skills — sorted by mastery · computed from final twin state
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3 text-xs mb-4">
            {[
              { color: "#22c55e", label: "≥ 80% Strong" },
              { color: "#84cc16", label: "60–79% Good" },
              { color: "#f59e0b", label: "40–59% Developing" },
              { color: "#ef4444", label: "< 40% At risk" },
            ].map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1.5">
                <span
                  className="w-2.5 h-2.5 rounded-full inline-block shrink-0"
                  style={{ background: color }}
                />
                {label}
              </span>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 max-h-[520px] overflow-y-auto pr-1">
            {masteryList.map((item) => (
              <div key={item.skillIdx} className="flex items-center gap-2 py-0.5">
                <div className="w-20 shrink-0 h-2 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(100, item.mastery * 100)}%`,
                      background: masteryColor(item.mastery),
                    }}
                  />
                </div>
                <span className="text-[11px] font-mono shrink-0 w-10 text-right">
                  {fmtPct(item.mastery, 0)}
                </span>
                <span
                  className="text-[11px] truncate text-muted-foreground"
                  title={item.name}
                >
                  {item.name}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* ── Mastery trajectory + Risk alerts ─────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

        {/* Trajectory */}
        <Card>
          <CardHeader>
            <CardTitle>Mastery Trajectory</CardTitle>
            <CardDescription>
              Average mastery at {trajectory.length} sampled timeline checkpoints
            </CardDescription>
          </CardHeader>
          <CardContent>
            {trajectory.length < 2 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Not enough interactions to show trajectory.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={trajectory} margin={{ right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="step" tick={{ fontSize: 10 }} />
                  <YAxis
                    domain={["auto", "auto"]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 10 }}
                  />
                  <Tooltip
                    formatter={(v: number) => [`${v}%`, "Avg Mastery"]}
                    labelFormatter={(_, payload) =>
                      payload?.[0]?.payload?.date ?? ""
                    }
                  />
                  <ReferenceLine
                    y={60}
                    stroke="#f59e0b"
                    strokeDasharray="4 4"
                    label={{
                      value: "60%",
                      position: "right",
                      fontSize: 10,
                      fill: "#f59e0b",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="avgMastery"
                    stroke="#f97316"
                    strokeWidth={2}
                    dot={{ r: 3, fill: "#f97316" }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Risk alerts */}
        <Card>
          <CardHeader>
            <CardTitle>Risk Forecast</CardTitle>
            <CardDescription>
              Skills below {fmtPct(THRESHOLD, 0)} mastery, ranked by urgency
            </CardDescription>
          </CardHeader>
          <CardContent>
            {riskAlerts.length === 0 ? (
              <div className="text-center py-8 space-y-1">
                <p className="text-3xl">✓</p>
                <p className="text-sm font-medium text-emerald-600">
                  No at-risk skills
                </p>
                <p className="text-xs text-muted-foreground">
                  All {nSkills} skills are at or above {fmtPct(THRESHOLD, 0)}
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[270px] overflow-y-auto pr-1">
                {riskAlerts.map((skill) => (
                  <div
                    key={skill.skill_id}
                    className="flex items-start gap-3 rounded-lg border p-3 bg-red-50/50 dark:bg-red-950/10 border-red-200 dark:border-red-900"
                  >
                    <Badge
                      variant={
                        skill.priority === "HIGH"
                          ? "destructive"
                          : skill.priority === "MEDIUM"
                          ? "default"
                          : "secondary"
                      }
                      className="mt-0.5 text-[10px] shrink-0"
                    >
                      {skill.priority}
                    </Badge>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium leading-tight">
                        {skill.skill_name}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Mastery:{" "}
                        <b className="text-foreground">
                          {fmtPct(skill.current_mastery)}
                        </b>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── What-if Simulation ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>What-if Simulation</CardTitle>
              <CardDescription>
                Projected mastery trajectory under three different study strategies
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Mode:</span>
              {(["auto", "manual"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                    mode === m
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  {m === "auto" ? "Auto" : "Manual"}
                </button>
              ))}
              <span className="text-xs text-muted-foreground">Days:</span>
              {DAY_OPTIONS.map((n) => (
                <button
                  key={n}
                  onClick={() => setSimStepCount(n)}
                  className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                    simStepCount === n
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {mode === "manual" && (
            <div className="mb-5 space-y-2 rounded-lg border p-3 bg-muted/20">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-muted-foreground">
                  Select up to <b className="text-foreground">{actionableSkillCap}</b> skills for your custom path over <b className="text-foreground">{simStepCount} days</b>.
                  Skills in the <span className="text-blue-600 dark:text-blue-400 font-medium">ZPD range (30–70%)</span> give the highest gains.
                </p>
                {manualSkillIds.length > 0 && (
                  <button
                    onClick={() => setManualSkillIds([])}
                    className="text-[11px] text-muted-foreground hover:text-destructive transition-colors shrink-0 underline underline-offset-2"
                  >
                    Clear all
                  </button>
                )}
              </div>
              <div className="max-h-52 overflow-y-auto pr-1 rounded border bg-background/60 p-2">
                <div className="flex flex-wrap gap-1.5">
                  {masteryList.slice().reverse().map((s) => {
                    const active = manualSkillIds.includes(s.skillIdx);
                    const inZpd = s.mastery >= 0.30 && s.mastery <= 0.70;
                    const atCap = !active && manualSkillIds.length >= actionableSkillCap;
                    return (
                      <button
                        key={s.skillIdx}
                        disabled={atCap}
                        onClick={() => {
                          setManualSkillIds((prev) => {
                            if (prev.includes(s.skillIdx)) return prev.filter((id) => id !== s.skillIdx);
                            if (prev.length >= actionableSkillCap) return prev;
                            return [...prev, s.skillIdx];
                          });
                        }}
                        className={`text-[11px] rounded border px-2 py-0.5 transition-colors flex items-center gap-1 ${
                          active
                            ? "bg-primary text-primary-foreground border-primary"
                            : atCap
                            ? "opacity-40 cursor-not-allowed border-border bg-background"
                            : inZpd
                            ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/30 hover:bg-blue-100 dark:hover:bg-blue-950/50 text-blue-800 dark:text-blue-200"
                            : "bg-background hover:bg-muted border-border"
                        }`}
                        title={`${s.name} — mastery ${(s.mastery * 100).toFixed(0)}%${inZpd ? " · in ZPD range" : ""}`}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full shrink-0 inline-block"
                          style={{ background: masteryColor(s.mastery) }}
                        />
                        <span className="inline-block max-w-[160px] truncate align-middle">{s.name}</span>
                        <span className="shrink-0 font-mono text-[9px] opacity-60">{(s.mastery * 100).toFixed(0)}%</span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">
                {manualSkillIds.length}/{actionableSkillCap} selected
                {manualSkillIds.length > 0 && (
                  <> · <span className="text-blue-600 dark:text-blue-400">
                    {manualSkillIds.filter((id) => {
                      const m = mastery[id] ?? 0;
                      return m >= 0.30 && m <= 0.70;
                    }).length} in ZPD
                  </span></>
                )}
              </p>
              <div className="pt-2">
                {manualImpactPreview ? (
                  <div className="rounded-lg border bg-background/70 p-3 space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                        Selection Impact Preview
                      </p>
                      <Badge variant="secondary" className="text-[10px]">
                        {manualImpactPreview.count}/{actionableSkillCap} selected
                      </Badge>
                      {(() => {
                        const cl = coherenceLabel(manualImpactPreview.coherenceScore);
                        return (
                          <span className={`text-[10px] font-medium border rounded-full px-2 py-0.5 ${cl.bg} ${cl.color}`}>
                            {cl.text}
                          </span>
                        );
                      })()}
                    </div>
                    {/* Coherence meter */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-muted-foreground">Chain coherence</span>
                        <span className="text-[10px] font-semibold text-foreground">
                          {Math.round(manualImpactPreview.coherenceScore * 100)}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            manualImpactPreview.coherenceScore >= 0.72 ? "bg-emerald-500" :
                            manualImpactPreview.coherenceScore >= 0.50 ? "bg-blue-500" :
                            manualImpactPreview.coherenceScore >= 0.28 ? "bg-amber-400" : "bg-muted-foreground/40"
                          }`}
                          style={{ width: `${manualImpactPreview.coherenceScore * 100}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-muted-foreground mt-1">
                        {manualImpactPreview.coherenceScore >= 0.72
                          ? "Great choice — these skills form a strong learning chain."
                          : manualImpactPreview.coherenceScore >= 0.50
                          ? "Good connection — adding adjacent skills will improve retention."
                          : manualImpactPreview.coherenceScore >= 0.28
                          ? "Loosely connected — try selecting prerequisite or follow-on skills."
                          : "Scattered selection — chained skills produce higher real-world gains."}
                      </p>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      <div className="rounded border p-2">
                        <p className="text-[10px] text-muted-foreground">Current avg</p>
                        <p className="text-sm font-semibold">{fmtPct(manualImpactPreview.avgBefore, 1)}</p>
                      </div>
                      <div className="rounded border p-2">
                        <p className="text-[10px] text-muted-foreground">Projected gain</p>
                        <p className="text-sm font-semibold text-emerald-600">
                          +{fmtPct(manualImpactPreview.projectedGain, 2)}
                        </p>
                      </div>
                      <div className="rounded border p-2">
                        <p className="text-[10px] text-muted-foreground">Projected avg</p>
                        <p className="text-sm font-semibold">{fmtPct(manualImpactPreview.avgAfter, 1)}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] text-muted-foreground mb-1">Top gain contributors</p>
                      <div className="flex flex-wrap gap-1.5">
                        {manualImpactPreview.topContributors.map((c) => (
                          <span
                            key={c.id}
                            className="text-[10px] rounded border px-1.5 py-0.5 bg-background"
                            title={`${c.name}: +${fmtPct(c.projectedGain, 2)} projected`}
                          >
                            <span className="inline-block max-w-[180px] truncate align-middle">{c.name}</span> (+{fmtPct(c.projectedGain, 2)})
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-[11px] text-muted-foreground">
                    Pick at least one skill to preview manual-path impact.
                  </p>
                )}
              </div>
            </div>
          )}
          {simulation ? (
            <div className="space-y-6">
              {/* Trajectory comparison chart */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Projected average mastery over {simStepCount} days — strategies may cross; the winner depends on your learning horizon
                </p>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart margin={{ right: 20, top: 8, left: 4, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
                    <XAxis
                      dataKey="step"
                      type="number"
                      domain={[0, simStepCount]}
                      tick={{ fontSize: 10 }}
                      label={{ value: "Days", position: "insideBottom", offset: -4, fontSize: 10 }}
                      allowDuplicatedCategory={false}
                    />
                    <YAxis
                      domain={["auto", "auto"]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 10 }}
                    />
                    <Tooltip
                      formatter={(v: number, name: string) => [`${v}%`, name]}
                      contentStyle={{ fontSize: 11 }}
                    />
                    <Legend verticalAlign="top" height={30} />
                    <Line
                      data={simulation.pathA.trajectory}
                      dataKey="avgMastery"
                      name={simulation.pathA.name}
                      type="monotone"
                      stroke="#ef4444"
                      strokeWidth={2.5}
                      dot={{ r: 2.5, fill: "#ef4444", strokeWidth: 0 }}
                      activeDot={{ r: 5, strokeWidth: 1, stroke: "#fff" }}
                    />
                    <Line
                      data={simulation.pathB.trajectory}
                      dataKey="avgMastery"
                      name={simulation.pathB.name}
                      type="monotone"
                      stroke="#f59e0b"
                      strokeWidth={2.5}
                      dot={{ r: 2.5, fill: "#f59e0b", strokeWidth: 0 }}
                      activeDot={{ r: 5, strokeWidth: 1, stroke: "#fff" }}
                    />
                    <Line
                      data={simulation.pathC.trajectory}
                      dataKey="avgMastery"
                      name={simulation.pathC.name}
                      type="monotone"
                      stroke="#6366f1"
                      strokeWidth={2.5}
                      dot={{ r: 2.5, fill: "#6366f1", strokeWidth: 0 }}
                      activeDot={{ r: 5, strokeWidth: 1, stroke: "#fff" }}
                    />
                    {simulation.pathD && (
                      <Line
                        data={simulation.pathD.trajectory}
                        dataKey="avgMastery"
                        name={simulation.pathD.name}
                        type="monotone"
                        stroke="#14b8a6"
                        strokeWidth={2}
                        dot={{ r: 2, fill: "#14b8a6", strokeWidth: 0 }}
                        activeDot={{ r: 4, strokeWidth: 1, stroke: "#fff" }}
                        strokeDasharray="5 3"
                      />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Strategy cards */}
              <div className={`grid grid-cols-1 ${simulation.pathD ? "sm:grid-cols-2 lg:grid-cols-4" : "sm:grid-cols-3"} gap-4`}>
                {[simulation.pathA, simulation.pathB, simulation.pathC, simulation.pathD]
                  .filter((path): path is SimPath => path != null)
                  .map((path) => {
                  const isBest = effectiveBestName === path.name;
                  const cl = coherenceLabel(path.coherenceScore);
                  return (
                    <div
                      key={path.name}
                      className={`rounded-xl border p-4 space-y-3 transition-all ${
                        isBest
                          ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-950/20 shadow-sm"
                          : "border-border opacity-80"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-sm leading-tight">
                          {path.name}
                        </span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {isBest && (
                            <Badge className="bg-emerald-500 hover:bg-emerald-500 text-white text-[10px]">
                              Best
                            </Badge>
                          )}
                          {(() => {
                            const fit = horizonFitLabel[path.name];
                            if (!fit) return null;
                            const isShort = fit.includes("Short");
                            const isLong = fit.includes("Long");
                            return (
                              <Badge
                                variant="outline"
                                className={`text-[9px] px-1.5 py-0 border shrink-0 ${
                                  isShort
                                    ? "border-sky-400 text-sky-600 dark:text-sky-400"
                                    : isLong
                                    ? "border-violet-400 text-violet-600 dark:text-violet-400"
                                    : "border-muted-foreground/40 text-muted-foreground"
                                }`}
                              >
                                {fit}
                              </Badge>
                            );
                          })()}
                          <span className={`text-[10px] font-medium border rounded-full px-2 py-0.5 ${cl.bg} ${cl.color}`}>
                            {cl.text}
                          </span>
                        </div>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-snug">
                        {path.description}
                      </p>
                      {path.justification.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Justification</p>
                          {path.justification.slice(0, 3).map((line, idx) => (
                            <p key={idx} className="text-[10px] leading-snug text-muted-foreground">
                              {line}
                            </p>
                          ))}
                        </div>
                      )}
                      {/* Coherence meter */}
                      <div>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] text-muted-foreground">Chain coherence</span>
                          <span className={`text-[10px] font-semibold ${cl.color}`}>
                            {Math.round(path.coherenceScore * 100)}%
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              path.coherenceScore >= 0.72 ? "bg-emerald-500" :
                              path.coherenceScore >= 0.50 ? "bg-blue-500" :
                              path.coherenceScore >= 0.28 ? "bg-amber-400" : "bg-muted-foreground/40"
                            }`}
                            style={{ width: `${path.coherenceScore * 100}%` }}
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <p className="text-xs text-muted-foreground">Mastery gain</p>
                          <p className={`text-lg font-bold ${path.totalGain >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                            {path.totalGain >= 0 ? "+" : ""}
                            {fmtPct(path.totalGain, 2)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Final avg</p>
                          <p className="text-lg font-bold">{fmtPct(path.finalAvg)}</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1.5">
                          Target skills ({path.skills.length}):
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {path.skills.map((s) => (
                            <span
                              key={s.id}
                              className="text-[10px] bg-background border rounded px-1.5 py-0.5 truncate max-w-[150px]"
                              title={`${s.name} (${fmtPct(s.currentMastery, 0)})`}
                            >
                              {s.name}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="rounded-xl border border-blue-200 dark:border-blue-900 bg-gradient-to-r from-blue-50/70 to-indigo-50/40 dark:from-blue-950/20 dark:to-indigo-950/10 p-4 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold">
                      Strategy Advisor
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      Personalized recommendation based on your current mastery profile and simulated paths
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {advisorLoading && (
                      <Badge variant="secondary" className="text-[10px]">
                        Updating...
                      </Badge>
                    )}
                    {whatIfAdvice?.source && (
                      <Badge variant="outline" className="text-[10px]">
                        {whatIfAdvice.source === "llm" ? "LLM-guided" : "Rule-based"}
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="rounded-lg border bg-background/70 p-3">
                  <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
                    Recommended Strategy
                  </p>
                  <p className="text-sm font-semibold">
                    {effectiveBestName || "Analyzing options..."}
                  </p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">
                    {simStepCount <= 14
                      ? `Short-term horizon (${simStepCount}d) — focused retrieval practice yields fastest gains`
                      : `Long-term horizon (${simStepCount}d) — spaced repetition & desirable difficulty compound over time`}
                  </p>
                </div>

                {advisorError ? (
                  <div className="rounded-lg border border-red-200 dark:border-red-900 bg-red-50/50 dark:bg-red-950/10 p-3">
                    <p className="text-xs text-red-600">{advisorError}</p>
                  </div>
                ) : (
                  <>
                    <div className="rounded-lg border bg-background/70 p-3 space-y-2.5">
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
                        Why this strategy
                      </p>
                      {rationaleParts.lead ? (
                        <p className="text-xs leading-relaxed text-foreground font-medium">
                          {rationaleParts.lead}
                        </p>
                      ) : (
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          Comparing strategies based on your mastery profile...
                        </p>
                      )}
                      {rationaleParts.points.length > 0 && (
                        <div className="space-y-1.5">
                          {rationaleParts.points.map((point, idx) => (
                            <div key={idx} className="flex items-start gap-2">
                              <span className="mt-1 h-1.5 w-1.5 rounded-full bg-blue-500 shrink-0" />
                              <p className="text-xs leading-relaxed text-muted-foreground">{point}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="rounded-lg border bg-background/70 p-3">
                      <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-2">
                        Action Plan
                      </p>
                      {advisorActions.length ? (
                        <div className="space-y-2">
                          {advisorActions.map((it, idx) => (
                            <div key={idx} className="flex items-start gap-2">
                              <span className="mt-0.5 h-4 w-4 rounded-full bg-primary/10 text-primary text-[10px] font-bold flex items-center justify-center shrink-0">
                                {idx + 1}
                              </span>
                              <p className="text-xs text-muted-foreground leading-relaxed">{it}</p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">Action items will appear after analysis.</p>
                      )}
                    </div>
                  </>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">
              No mastery data available for simulation.
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── Twin Confidence ────────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Twin Confidence</CardTitle>
          <CardDescription>
            {confidence
              ? `How well the model predicted your performance over ${confidence.n} interactions`
              : "No prediction data available"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {confidence ? (
            <div className="space-y-5">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="text-center p-3 rounded-lg bg-muted/40">
                  <p className="text-2xl font-bold">{fmtPct(confidence.classificationAcc, 0)}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Prediction Quality</p>
                  <p className="text-[10px] text-muted-foreground">How often the model correctly predicted your answer</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/40">
                  <p className="text-2xl font-bold">{confidence.brierScore.toFixed(3)}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Calibration Score</p>
                  <p className="text-[10px] text-muted-foreground">Lower is better (0 = perfect)</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/40">
                  <p className="text-2xl font-bold">{fmtPct(confidence.avgPredicted, 0)}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">Avg P(correct)</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/40">
                  <Badge
                    variant={
                      confidence.brierScore > 0.25
                        ? "destructive"
                        : confidence.brierScore > 0.15
                        ? "default"
                        : "secondary"
                    }
                    className="text-xs"
                  >
                    {confidence.brierScore > 0.25
                      ? "Needs Calibration"
                      : confidence.brierScore > 0.15
                      ? "Fair"
                      : "Well Calibrated"}
                  </Badge>
                  <p className="text-xs text-muted-foreground mt-1.5">Quality</p>
                </div>
              </div>

              {/* Calibration note */}
              <div className="rounded-lg border border-blue-200 bg-blue-50/50 dark:bg-blue-950/10 dark:border-blue-900 p-3">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  <b className="text-foreground">How to read:</b> Each bar shows the model's
                  predicted probability that the student would answer correctly.{" "}
                  <span className="text-emerald-600 font-medium">Green</span> = student answered
                  correctly,{" "}
                  <span className="text-red-500 font-medium">red</span> = incorrectly.
                  A well-calibrated model should predict ~60% for interactions where the student
                  gets it right 60% of the time.
                  The student's actual accuracy is <b className="text-foreground">{fmtPct(confidence.accuracy, 0)}</b> while
                  the model's average prediction is <b className="text-foreground">{fmtPct(confidence.avgPredicted, 0)}</b>.
                </p>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Model predicted P(correct) per interaction
                </p>
                <PredictionChart timeline={timeline} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-6">
              No prediction probability data recorded for this student.
            </p>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
