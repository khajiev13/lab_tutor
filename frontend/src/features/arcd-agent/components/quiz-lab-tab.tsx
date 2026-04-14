
import { useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import {
  Card, CardHeader, CardTitle, CardContent, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ChevronDown, ChevronUp, BookOpen, TrendingUp, TrendingDown,
  Minus, FlaskConical, CheckCircle2, XCircle, Target, Lightbulb,
} from "lucide-react";
import type { StudentPortfolio, SkillInfo, TimelineEntry } from "@/features/arcd-agent/lib/types";
import { buildSubSkillNameMap } from "@/features/arcd-agent/lib/types";
import { SKILL_HEX } from "@/features/arcd-agent/lib/colors";
import { formatPct100 } from "@/features/arcd-agent/lib/grading";

interface QuizLabTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
}

// ── Quiz data structure ────────────────────────────────────────────────────

interface QuizQuestion {
  step: number;
  timestamp: string;
  question_id: number;
  skill_id: number;
  skill_name: string;
  response: number;
  predicted_prob: number;
  mastery_after: number;   // mastery of this skill right after this question
}

interface Quiz {
  id: number;
  skill_id: number;
  skill_name: string;
  domain_name: string;
  domain_idx: number;
  date: Date;
  questions: QuizQuestion[];
  mastery_before: number;  // mastery of skill at start of quiz
  mastery_after: number;   // mastery of skill at end of quiz
  correct: number;
  total: number;
  score_pct: number;       // correct / total × 100
  attempt: number;         // nth attempt on this skill (1-based)
  totalAttempts: number;   // total quizzes on this skill
}

// ── Grouping logic: consecutive events on the same skill = one quiz ────────

function buildQuizzes(
  timeline: TimelineEntry[],
  subSkillNames: Record<number, string>,
  skills: SkillInfo[],
): Quiz[] {
  if (timeline.length === 0) return [];

  // Build skill → domain mapping (skill IS the domain now)
  const skillToDomain: Record<number, { name: string; idx: number }> = {};
  skills.forEach((skill, di) => {
    skillToDomain[skill.id] = { name: skill.name, idx: di };
  });

  const quizzes: Quiz[] = [];
  let currentGroup: TimelineEntry[] = [];
  let currentSkillId: number = timeline[0].skill_id;
  let quizCounter = 0;
  const attemptCounter: Record<number, number> = {};

  function flushGroup(group: TimelineEntry[]) {
    if (group.length === 0) return;
    const skillId = group[0].skill_id;
    const skillName = subSkillNames[skillId] ?? `Skill ${skillId}`;
    const domain = skillToDomain[skillId] ?? { name: "Unknown", idx: 0 };

    // mastery before = mastery vector at the step before this group
    const firstIdx = timeline.findIndex((e) => e.step === group[0].step);
    const prevEntry = firstIdx > 0 ? timeline[firstIdx - 1] : null;
    const masteryBefore =
      prevEntry != null ? (prevEntry.mastery[skillId] ?? 0.5) : 0.5;
    const masteryAfter = group[group.length - 1].mastery[skillId] ?? masteryBefore;

    const correct = group.filter((e) => e.response === 1).length;
    const total = group.length;

    const questions: QuizQuestion[] = group.map((e) => ({
      step: e.step,
      timestamp: e.timestamp,
      question_id: e.question_id,
      skill_id: skillId,
      skill_name: skillName,
      response: e.response,
      predicted_prob: e.predicted_prob,
      mastery_after: e.mastery[skillId] ?? masteryBefore,
    }));

    attemptCounter[skillId] = (attemptCounter[skillId] ?? 0) + 1;
    quizCounter++;
    quizzes.push({
      id: quizCounter,
      skill_id: skillId,
      skill_name: skillName,
      domain_name: domain.name,
      domain_idx: domain.idx,
      date: new Date(group[0].timestamp),
      questions,
      mastery_before: masteryBefore,
      mastery_after: masteryAfter,
      correct,
      total,
      score_pct: total > 0 ? (correct / total) * 100 : 0,
      attempt: attemptCounter[skillId],
      totalAttempts: 0, // filled in second pass
    });
  }

  for (const entry of timeline) {
    if (entry.skill_id !== currentSkillId) {
      flushGroup(currentGroup);
      currentGroup = [entry];
      currentSkillId = entry.skill_id;
    } else {
      currentGroup.push(entry);
    }
  }
  flushGroup(currentGroup);

  // Second pass: set totalAttempts per skill
  for (const q of quizzes) {
    q.totalAttempts = attemptCounter[q.skill_id] ?? 1;
  }

  return quizzes;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function masteryDeltaLabel(delta: number): { text: string; color: string; icon: React.ReactNode } {
  if (delta > 0.02) return { text: `+${(delta * 100).toFixed(1)}%`, color: "text-emerald-600 dark:text-emerald-400", icon: <TrendingUp className="h-3.5 w-3.5" /> };
  if (delta < -0.02) return { text: `${(delta * 100).toFixed(1)}%`, color: "text-red-600 dark:text-red-400", icon: <TrendingDown className="h-3.5 w-3.5" /> };
  return { text: "±0%", color: "text-muted-foreground", icon: <Minus className="h-3.5 w-3.5" /> };
}

function masteryBar(value: number, color: string) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(value * 100, 100)}%`, backgroundColor: color }} />
      </div>
      <span className="font-mono tabular-nums text-xs w-10 text-right">{formatPct100(value * 100)}</span>
    </div>
  );
}

// ── Insight generator ──────────────────────────────────────────────────────

interface Insight {
  text: string;
  tone: "positive" | "warning" | "neutral";
}

function buildInsight(quiz: Quiz): Insight {
  const delta = quiz.mastery_after - quiz.mastery_before;
  const accuracy = quiz.score_pct / 100;
  const isFirstAttempt = quiz.attempt === 1;
  const isRepeatAttempt = quiz.attempt > 1;
  const consistentCorrect = quiz.questions.every((q) => q.response === 1);
  const consistentWrong = quiz.questions.every((q) => q.response === 0);
  const wrongStreak = (() => {
    let streak = 0;
    let max = 0;
    for (const q of quiz.questions) {
      streak = q.response === 0 ? streak + 1 : 0;
      max = Math.max(max, streak);
    }
    return max;
  })();
  const correctStreak = (() => {
    let streak = 0;
    let max = 0;
    for (const q of quiz.questions) {
      streak = q.response === 1 ? streak + 1 : 0;
      max = Math.max(max, streak);
    }
    return max;
  })();
  const avgPredicted = quiz.questions.reduce((s, q) => s + q.predicted_prob, 0) / quiz.questions.length;
  const modelUnderestimated = accuracy > 0.7 && avgPredicted < 0.5;
  const modelOverestimated = accuracy < 0.4 && avgPredicted > 0.6;

  // Positive cases
  if (consistentCorrect && delta > 0.01) {
    return { text: `Perfect score — answered every question correctly. This strong performance directly boosted mastery by ${(delta * 100).toFixed(1)}%.`, tone: "positive" };
  }
  if (accuracy >= 0.8 && delta > 0.02) {
    if (isRepeatAttempt) return { text: `Attempt ${quiz.attempt} shows clear improvement over earlier tries. High accuracy (${quiz.score_pct.toFixed(0)}%) consolidated mastery with a +${(delta * 100).toFixed(1)}% gain.`, tone: "positive" };
    if (correctStreak >= 3) return { text: `A streak of ${correctStreak} consecutive correct answers drove a solid mastery gain of +${(delta * 100).toFixed(1)}%.`, tone: "positive" };
    return { text: `Strong performance at ${quiz.score_pct.toFixed(0)}% accuracy. Consistent correct responses gave the model confidence to raise mastery by +${(delta * 100).toFixed(1)}%.`, tone: "positive" };
  }
  if (delta > 0.03 && accuracy >= 0.6) {
    return { text: `Mastery rose +${(delta * 100).toFixed(1)}% because the student demonstrated solid understanding on the majority of questions in this skill area.`, tone: "positive" };
  }
  if (modelUnderestimated && delta > 0) {
    return { text: `The model initially expected a low success probability (${(avgPredicted * 100).toFixed(0)}%), but the student outperformed expectations. This positive surprise drove a mastery update of +${(delta * 100).toFixed(1)}%.`, tone: "positive" };
  }

  // Warning / decline cases
  if (consistentWrong) {
    return { text: `Every question was answered incorrectly. The model interprets this as a persistent gap, reducing mastery by ${(delta * 100).toFixed(1)}%. Targeted review of this skill is recommended.`, tone: "warning" };
  }
  if (delta < -0.02 && accuracy < 0.4) {
    if (isRepeatAttempt) return { text: `Attempt ${quiz.attempt} still shows difficulty — ${quiz.score_pct.toFixed(0)}% accuracy and a −${Math.abs(delta * 100).toFixed(1)}% mastery drop. Revisiting prerequisites may help before the next attempt.`, tone: "warning" };
    if (wrongStreak >= 3) return { text: `A run of ${wrongStreak} consecutive wrong answers signalled to the model that this skill needs more work, pulling mastery down by ${(delta * 100).toFixed(1)}%.`, tone: "warning" };
    return { text: `Low accuracy (${quiz.score_pct.toFixed(0)}%) led the model to revise mastery down by ${(Math.abs(delta) * 100).toFixed(1)}%. More practice on this skill is suggested.`, tone: "warning" };
  }
  if (modelOverestimated && delta < 0) {
    return { text: `The model expected higher performance (avg P=${(avgPredicted * 100).toFixed(0)}%) but the student struggled. This negative surprise caused a mastery correction of ${(delta * 100).toFixed(1)}%.`, tone: "warning" };
  }

  // Neutral / mixed
  if (Math.abs(delta) <= 0.01 && accuracy >= 0.5) {
    return { text: `Mixed results (${quiz.score_pct.toFixed(0)}% accuracy) produced no net mastery change. The correct and incorrect responses roughly balanced out.`, tone: "neutral" };
  }
  if (delta > 0 && accuracy < 0.6) {
    return { text: `Despite a modest score of ${quiz.score_pct.toFixed(0)}%, the model recorded a small mastery gain (+${(delta * 100).toFixed(1)}%) — likely because the correct answers were on harder questions.`, tone: "neutral" };
  }
  if (isFirstAttempt && quiz.total === 1) {
    return {
      text: quiz.questions[0].response === 1
        ? `Single-question quiz answered correctly. Mastery nudged up slightly (+${(delta * 100).toFixed(1)}%).`
        : `Single-question quiz answered incorrectly. One data point has limited impact but mastery dipped by ${(Math.abs(delta) * 100).toFixed(1)}%.`,
      tone: quiz.questions[0].response === 1 ? "positive" : "warning",
    };
  }
  return { text: `Score of ${quiz.score_pct.toFixed(0)}% produced a mastery change of ${delta >= 0 ? "+" : ""}${(delta * 100).toFixed(1)}% based on the model's assessment of response patterns.`, tone: "neutral" };
}

// ── Quiz Card ──────────────────────────────────────────────────────────────

function QuizCard({ quiz, domainColor, skillHistory }: {
  quiz: Quiz;
  domainColor: string;
  skillHistory: Quiz[];   // all quizzes for this skill_id, sorted by attempt asc
}) {
  const [open, setOpen] = useState(false);
  const [showFullInsight, setShowFullInsight] = useState(false);
  const delta = quiz.mastery_after - quiz.mastery_before;
  const { text: deltaText, color: deltaColor, icon: deltaIcon } = masteryDeltaLabel(delta);

  const scoreLabel =
    quiz.score_pct >= 93 ? "A"  :
    quiz.score_pct >= 90 ? "A−" :
    quiz.score_pct >= 87 ? "B+" :
    quiz.score_pct >= 83 ? "B"  :
    quiz.score_pct >= 80 ? "B−" :
    quiz.score_pct >= 77 ? "C+" :
    quiz.score_pct >= 73 ? "C"  :
    quiz.score_pct >= 70 ? "C−" :
    quiz.score_pct >= 60 ? "D"  : "F";
  const scoreBg =
    scoreLabel.startsWith("A") ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-400" :
    scoreLabel.startsWith("B") ? "bg-blue-500/15 border-blue-500/30 text-blue-600 dark:text-blue-400" :
    scoreLabel.startsWith("C") ? "bg-yellow-500/15 border-yellow-500/30 text-yellow-600 dark:text-yellow-400" :
    scoreLabel === "D"          ? "bg-orange-500/15 border-orange-500/30 text-orange-600 dark:text-orange-400" :
    "bg-red-500/15 border-red-500/30 text-red-600 dark:text-red-400";

  const insight = buildInsight(quiz);
  const insightBg =
    insight.tone === "positive" ? "bg-emerald-50 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-900" :
    insight.tone === "warning"  ? "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900" :
                                  "bg-muted/40 border-border/50";
  const insightIconColor =
    insight.tone === "positive" ? "text-emerald-500" :
    insight.tone === "warning"  ? "text-amber-500" : "text-muted-foreground";

  return (
    <Card className="overflow-hidden flex flex-col">
      {/* Colour bar matching domain */}
      <div className="h-1 w-full shrink-0" style={{ backgroundColor: domainColor }} />

      <CardHeader className="pb-2 px-4 pt-3">
        {/* Top row: meta badges + grade badge */}
        <div className="flex items-start gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-mono text-muted-foreground shrink-0">#{quiz.id}</span>
              <Badge
                variant="outline"
                className="text-[10px] px-1.5 py-0 max-w-[120px] truncate"
                style={{ borderColor: domainColor + "66", color: domainColor }}
              >
                {quiz.domain_name}
              </Badge>
              <span className={`text-[10px] shrink-0 ${quiz.totalAttempts > 1 ? "font-medium text-foreground" : "text-muted-foreground"}`}>
                Attempt {quiz.attempt}{quiz.totalAttempts > 1 ? `/${quiz.totalAttempts}` : ""}
              </span>
            </div>
            <CardTitle className="text-sm mt-1 leading-snug line-clamp-2" title={quiz.skill_name}>
              {quiz.skill_name}
            </CardTitle>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {quiz.date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
              {" · "}{quiz.total} question{quiz.total !== 1 ? "s" : ""}
            </p>
          </div>
          {/* Grade badge */}
          <div className={`shrink-0 min-w-[36px] h-9 px-1.5 rounded-full border flex items-center justify-center text-sm font-bold ${scoreBg}`}>
            {scoreLabel}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-2.5 pt-0 px-4 pb-4 flex-1 flex flex-col min-h-0">
        {/* Score row */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            <span className="font-medium">{quiz.correct}/{quiz.total}</span>
            <span className="text-muted-foreground text-xs">correct this attempt</span>
          </div>
          <span className="font-mono tabular-nums font-semibold text-sm">{quiz.score_pct.toFixed(0)}%</span>
        </div>

        {/* Mastery before / after */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Before</span>
            <span className="font-mono">{formatPct100(quiz.mastery_before * 100)}</span>
          </div>
          {masteryBar(quiz.mastery_before, "#94a3b8")}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground">
            <span>After</span>
            <span className="font-mono">{formatPct100(quiz.mastery_after * 100)}</span>
          </div>
          {masteryBar(quiz.mastery_after, domainColor)}
        </div>

        {/* Delta row */}
        <div className={`flex items-center gap-1.5 text-xs font-semibold ${deltaColor}`}>
          {deltaIcon}
          <span>{deltaText} mastery change</span>
        </div>

        {/* Insight */}
        <div className={`flex items-start gap-2 rounded-lg border px-2.5 py-2 ${insightBg}`}>
          <Lightbulb className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${insightIconColor}`} />
          <div className="min-w-0 flex-1">
            <p className={`text-[11px] leading-relaxed text-muted-foreground ${showFullInsight ? "" : "line-clamp-3"}`}>
              {insight.text}
            </p>
            {insight.text.length > 120 && (
              <button
                onClick={() => setShowFullInsight((v) => !v)}
                className="text-[10px] text-primary hover:underline mt-0.5"
              >
                {showFullInsight ? "Show less" : "Read more"}
              </button>
            )}
          </div>
        </div>

        {/* Expand toggle — shows ALL attempts for this skill */}
        <button
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-center justify-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors py-1 rounded border border-border/50 hover:bg-muted/30 mt-auto"
        >
          {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          {open ? "Hide" : "Show"} attempt history
          {skillHistory.length > 1 && (
            <span className="ml-1 text-[10px] bg-muted rounded-full px-1.5 py-0.5">
              {skillHistory.reduce((n, q) => n + q.total, 0)} questions
            </span>
          )}
        </button>

        {/* Full attempt history — all attempts for this skill */}
        {open && (
          <div className="space-y-3">
            {skillHistory.map((attempt) => {
              const attemptDelta = attempt.mastery_after - attempt.mastery_before;
              const isCurrent = attempt.id === quiz.id;
              return (
                <div
                  key={attempt.id}
                  className={`rounded-md border overflow-hidden ${isCurrent ? "border-primary/40" : "border-border/50 opacity-80"}`}
                >
                  {/* Attempt header */}
                  <div className={`flex items-center justify-between px-2.5 py-1.5 text-[11px] font-medium ${isCurrent ? "bg-primary/5" : "bg-muted/30"}`}>
                    <div className="flex items-center gap-2">
                      <span className={isCurrent ? "text-primary" : "text-muted-foreground"}>
                        Attempt {attempt.attempt}
                        {isCurrent && <span className="ml-1 text-[9px] font-normal">(current)</span>}
                      </span>
                      <span className="text-muted-foreground font-normal">
                        {attempt.date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono">{attempt.correct}/{attempt.total} correct</span>
                      <span className={`font-semibold ${attemptDelta >= 0.01 ? "text-emerald-600" : attemptDelta <= -0.01 ? "text-red-500" : "text-muted-foreground"}`}>
                        {attemptDelta >= 0.01 ? "+" : ""}{(attemptDelta * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  {/* Questions table for this attempt */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-muted/20 border-b border-border/30">
                          <th className="p-1.5 text-left font-medium text-muted-foreground">Question</th>
                          <th className="p-1.5 text-center font-medium text-muted-foreground">Answer</th>
                          <th className="p-1.5 text-right font-medium text-muted-foreground">P(✓)</th>
                          <th className="p-1.5 text-right font-medium text-muted-foreground">Mastery</th>
                        </tr>
                      </thead>
                      <tbody>
                        {attempt.questions.map((q, i) => (
                          <tr
                            key={q.step}
                            className={`border-b border-border/20 ${i % 2 === 0 ? "" : "bg-muted/10"}`}
                          >
                            <td className="p-1.5 font-mono text-muted-foreground">Q{q.question_id}</td>
                            <td className="p-1.5 text-center">
                              {q.response === 1 ? (
                                <span className="inline-flex items-center gap-0.5 text-emerald-600 dark:text-emerald-400 font-medium">
                                  <CheckCircle2 className="h-3.5 w-3.5" />
                                  <span className="text-[10px]">Correct</span>
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-0.5 text-red-500 font-medium">
                                  <XCircle className="h-3.5 w-3.5" />
                                  <span className="text-[10px]">Wrong</span>
                                </span>
                              )}
                            </td>
                            <td className="p-1.5 text-right font-mono text-muted-foreground">
                              {(q.predicted_prob * 100).toFixed(1)}%
                            </td>
                            <td className="p-1.5 text-right font-mono">
                              {formatPct100(q.mastery_after * 100)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export function QuizLabTab({ student, skills }: QuizLabTabProps) {
  const [filterDomain, setFilterDomain] = useState<string>("all");
  const [sortBy, setSortBy] = useState<"recent" | "score" | "gain" | "loss">("recent");

  const subSkillNames = useMemo(() => buildSubSkillNameMap(skills), [skills]);

  const quizzes = useMemo(
    () => buildQuizzes(student.timeline, subSkillNames, skills),
    [student.timeline, subSkillNames, skills],
  );

  // ── summary stats ──────────────────────────────────────────────────────
  const totalQuizzes = quizzes.length;
  const avgScore = totalQuizzes > 0
    ? quizzes.reduce((s, q) => s + q.score_pct, 0) / totalQuizzes
    : 0;
  const bestQuiz = quizzes.reduce<Quiz | null>((b, q) => (!b || q.score_pct > b.score_pct ? q : b), null);
  const biggestGain = quizzes.reduce<Quiz | null>(
    (b, q) => (!b || (q.mastery_after - q.mastery_before) > (b.mastery_after - b.mastery_before) ? q : b),
    null,
  );
  const totalCorrect = quizzes.reduce((s, q) => s + q.correct, 0);
  const totalQuestions = quizzes.reduce((s, q) => s + q.total, 0);

  // ── mastery trend data across all quizzes chronologically ────────────────
  const masteryTrendData = useMemo(() => {
    return quizzes.map((q) => ({
      id: q.id,
      label: `#${q.id}`,
      mastery: +(q.mastery_after * 100).toFixed(1),
      score: +q.score_pct.toFixed(1),
      skill: q.skill_name.split(" ").slice(0, 3).join(" "),
    }));
  }, [quizzes]);

  const overallTrend = masteryTrendData.length >= 2
    ? masteryTrendData[masteryTrendData.length - 1].mastery - masteryTrendData[0].mastery
    : null;
  const displayed = useMemo(() => {
    let list = filterDomain === "all"
      ? quizzes
      : quizzes.filter((q) => q.domain_name === filterDomain);

    if (sortBy === "score")      list = [...list].sort((a, b) => b.score_pct - a.score_pct);
    else if (sortBy === "gain")  list = [...list].sort((a, b) => (b.mastery_after - b.mastery_before) - (a.mastery_after - a.mastery_before));
    else if (sortBy === "loss")  list = [...list].sort((a, b) => (a.mastery_after - a.mastery_before) - (b.mastery_after - b.mastery_before));
    // default: recent (already chronological)

    return list;
  }, [quizzes, filterDomain, sortBy]);

  const domainNames = useMemo(() => [...new Set(quizzes.map((q) => q.domain_name))], [quizzes]);

  // Build skill history map: skill_id → all quizzes sorted by attempt asc
  const skillHistoryMap = useMemo(() => {
    const map: Record<number, Quiz[]> = {};
    for (const q of quizzes) {
      if (!map[q.skill_id]) map[q.skill_id] = [];
      map[q.skill_id].push(q);
    }
    // Already chronological since buildQuizzes is ordered, but sort by attempt to be safe
    for (const key in map) map[key].sort((a, b) => a.attempt - b.attempt);
    return map;
  }, [quizzes]);

  return (
    <div className="space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-violet-500/10">
          <FlaskConical className="h-5 w-5 text-violet-500" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Quiz</h1>
          <p className="text-sm text-muted-foreground">
            Questions grouped by skill · mastery-based scoring
          </p>
        </div>
      </div>

      {/* ── Summary pills ─────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wide">Quizzes Taken</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{totalQuizzes}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">{totalQuestions} total questions</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wide">Avg Score</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{avgScore.toFixed(1)}%</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground">{totalCorrect}/{totalQuestions} correct</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wide">Best Quiz</CardDescription>
            <CardTitle className="text-2xl tabular-nums">{bestQuiz ? `${bestQuiz.score_pct.toFixed(0)}%` : "—"}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground truncate">{bestQuiz?.skill_name ?? "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="text-xs uppercase tracking-wide">Biggest Mastery Gain</CardDescription>
            {biggestGain ? (
              <CardTitle className="text-2xl tabular-nums text-emerald-600 dark:text-emerald-400">
                +{((biggestGain.mastery_after - biggestGain.mastery_before) * 100).toFixed(1)}%
              </CardTitle>
            ) : (
              <CardTitle className="text-2xl">—</CardTitle>
            )}
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-muted-foreground truncate">{biggestGain?.skill_name ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      {/* ── Mastery Trend Chart ───────────────────────────────────────── */}
      {masteryTrendData.length >= 3 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Mastery Progress Trend</CardTitle>
                <CardDescription>
                  Overall mastery after each quiz session
                </CardDescription>
              </div>
              {overallTrend !== null && (
                <div className={`flex items-center gap-1 text-sm font-semibold ${overallTrend >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                  {overallTrend >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
                  {overallTrend >= 0 ? "+" : ""}{overallTrend.toFixed(1)}% overall
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="h-[180px] pr-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={masteryTrendData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
                <XAxis dataKey="label" tick={{ fontSize: 9 }} />
                <YAxis
                  domain={[
                    (d: number) => Math.max(0, Math.floor(d) - 5),
                    (d: number) => Math.min(100, Math.ceil(d) + 5),
                  ]}
                  tickFormatter={(v) => `${v}%`}
                  tick={{ fontSize: 9 }}
                />
                <Tooltip
                  contentStyle={{ borderRadius: "8px", fontSize: "11px" }}
                  formatter={(v: number, name: string) => [
                    `${v}%`,
                    name === "mastery" ? "Mastery after quiz" : "Score",
                  ]}
                  labelFormatter={(_, payload: Array<{ payload?: { skill?: string } }>) => payload?.[0]?.payload?.skill ?? ""}
                />
                <ReferenceLine y={75} stroke="#10b981" strokeDasharray="4 3" strokeOpacity={0.6}
                  label={{ value: "Proficient", position: "right", fontSize: 9, fill: "#10b981" }} />
                <Line
                  type="monotone"
                  dataKey="mastery"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: "#6366f1" }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#94a3b8"
                  strokeWidth={1.5}
                  strokeDasharray="5 4"
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* ── Filters + Sort ────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Domain filter */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => setFilterDomain("all")}
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${filterDomain === "all" ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted/50"}`}
          >
            All Domains
          </button>
          {domainNames.map((d, i) => (
            <button
              key={d}
              onClick={() => setFilterDomain(filterDomain === d ? "all" : d)}
              className={`px-3 py-1 text-xs rounded-full border transition-colors ${filterDomain === d ? "text-white border-transparent" : "border-border hover:bg-muted/50"}`}
              style={filterDomain === d ? { backgroundColor: SKILL_HEX[i % SKILL_HEX.length] } : {}}
            >
              {d}
            </button>
          ))}
        </div>

        {/* Sort selector */}
        <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          <span>Sort:</span>
          {(["recent", "score", "gain", "loss"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSortBy(s)}
              className={`px-2.5 py-1 rounded border transition-colors ${sortBy === s ? "bg-muted text-foreground border-border" : "border-transparent hover:border-border/50"}`}
            >
              {s === "recent" ? "Recent" : s === "score" ? "Score ↓" : s === "gain" ? "Best Gain" : "Needs Work"}
            </button>
          ))}
        </div>
      </div>

      {/* ── Quiz count ────────────────────────────────────────────────── */}
      <p className="text-xs text-muted-foreground">
        Showing {displayed.length} quiz{displayed.length !== 1 ? "zes" : ""}
        {filterDomain !== "all" && ` in ${filterDomain}`}
      </p>

      {/* ── Quiz Card Grid ────────────────────────────────────────────── */}
      {displayed.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground space-y-2">
            <BookOpen className="h-8 w-8 mx-auto opacity-30" />
            <p>No quizzes found.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {displayed.map((quiz) => (
            <QuizCard
              key={quiz.id}
              quiz={quiz}
              domainColor={SKILL_HEX[quiz.domain_idx % SKILL_HEX.length]}
              skillHistory={skillHistoryMap[quiz.skill_id] ?? [quiz]}
            />
          ))}
        </div>
      )}

      {/* ── Footer note ───────────────────────────────────────────────── */}
      <p className="text-xs text-muted-foreground text-center pb-2">
        <Target className="h-3 w-3 inline mr-1" />
        Quizzes are auto-grouped by consecutive questions on the same skill. Mastery is from the ARCD neural model.
      </p>
    </div>
  );
}
