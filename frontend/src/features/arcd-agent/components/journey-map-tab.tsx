import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { StudentPortfolio, SkillInfo, TwinViewerData, ConceptInfo } from "@/features/arcd-agent/lib/types";
import { groupByChapter } from "@/features/arcd-agent/lib/types";
import { SKILL_HEX } from "@/features/arcd-agent/lib/colors";
import { masteryToColor, masteryTier } from "@/features/arcd-agent/lib/dag-layout";
import {
  AlertTriangle, Target, BookOpen, Zap, Star, Info, ChevronDown, ChevronRight, Layers, FolderOpen,
} from "lucide-react";
import { formatPct100, buildConceptStats, getConceptLookupKey, buildAttemptedSkillIds } from "@/features/arcd-agent/lib/grading";
import { InsightPanel } from "@/features/arcd-agent/components/insight-panel";

interface JourneyMapTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
  twinData?: TwinViewerData | null;
  datasetId?: string;
}

// ── Skill card ────────────────────────────────────────────────────────────────

interface SkillRow {
  id: number;
  name: string;
  mastery: number;
  isStarted: boolean;
  isAtRisk: boolean;
  isNextStep: boolean;
  nextStepRank?: number;
  isCascade: boolean;
}

function MasteryBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 flex-1 min-w-0">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden min-w-[60px]">
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{ width: `${Math.min(value * 100, 100)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-[11px] font-mono tabular-nums w-9 text-right shrink-0">
        {Math.round(value * 100)}%
      </span>
    </div>
  );
}

function SkillCard({
  skill,
  isSelected,
  onClick,
}: {
  skill: SkillRow;
  isSelected: boolean;
  onClick: () => void;
}) {
  const color = skill.isStarted ? masteryToColor(skill.mastery) : "#94a3b8";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-3 p-2.5 rounded-lg border transition-all hover:shadow-sm ${
        isSelected
          ? "border-primary bg-primary/5 shadow-sm"
          : "border-border/60 hover:border-border hover:bg-muted/30"
      } ${!skill.isStarted ? "opacity-60" : ""}`}
    >
      {/* Tier color strip */}
      <div className="w-1 self-stretch rounded-full shrink-0" style={{ backgroundColor: color }} />

      {/* Name */}
      <span className={`text-xs font-medium flex-1 min-w-0 text-left leading-tight line-clamp-2 ${!skill.isStarted ? "text-muted-foreground" : ""}`}>
        {skill.name}
      </span>

      {/* Mastery bar + badges */}
      <div className="flex items-center gap-1.5 shrink-0">
        {skill.isNextStep && skill.nextStepRank != null && (
          <span
            className="flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white shrink-0"
            style={{ backgroundColor: "hsl(var(--primary))" }}
          >
            <Target className="h-2.5 w-2.5" />
            {skill.nextStepRank}
          </span>
        )}
        {skill.isAtRisk && !skill.isNextStep && skill.isStarted && (
          <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
        )}
        {skill.isCascade && skill.isStarted && (
          <Zap className="h-3 w-3 text-orange-400 shrink-0" aria-label="Downstream decay risk" />
        )}
      </div>

      {/* Mastery bar or Not Started indicator */}
      <div className="w-28 shrink-0">
        {skill.isStarted ? (
          <MasteryBar value={skill.mastery} color={color} />
        ) : (
          <span className="text-[10px] text-muted-foreground/70 italic">Not started</span>
        )}
      </div>
    </button>
  );
}

// ── Chapter section ───────────────────────────────────────────────────────────

function ChapterSection({
  chapterName,
  skills: skillRows,
  color,
  selectedId,
  onSelect,
  defaultOpen,
}: {
  chapterName: string;
  chapterId: number;
  skills: SkillRow[];
  color: string;
  selectedId: number | null;
  onSelect: (id: number) => void;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const avgMastery = skillRows.length > 0
    ? skillRows.reduce((s, r) => s + (r.isStarted ? r.mastery : 0), 0) / skillRows.length
    : 0;
  const proficient = skillRows.filter((r) => r.isStarted && r.mastery >= 0.75).length;
  const notStarted = skillRows.filter((r) => !r.isStarted).length;
  const nextSteps  = skillRows.filter((r) => r.isNextStep).length;
  const atRisk     = skillRows.filter((r) => r.isStarted && r.isAtRisk).length;

  return (
    <div className="rounded-xl border overflow-hidden">
      {/* Chapter header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
        style={{ borderLeft: `4px solid ${color}` }}
      >
        <FolderOpen className="h-4 w-4 shrink-0" style={{ color }} />

        <div className="flex-1 min-w-0">
          <span className="font-semibold text-sm">{chapterName || "Uncategorized"}</span>
          <span className="text-xs text-muted-foreground ml-2">{skillRows.length} skill{skillRows.length !== 1 ? "s" : ""}</span>
        </div>

        {/* Chapter stats */}
        <div className="flex items-center gap-2 shrink-0">
          {nextSteps > 0 && (
            <Badge className="text-[10px] py-0 h-4" style={{ backgroundColor: "hsl(var(--primary))", color: "white" }}>
              {nextSteps} next
            </Badge>
          )}
          {atRisk > 0 && (
            <Badge variant="outline" className="text-[10px] py-0 h-4 border-amber-400 text-amber-600">
              {atRisk} at-risk
            </Badge>
          )}
          {notStarted > 0 && (
            <Badge variant="secondary" className="text-[10px] py-0 h-4 text-muted-foreground">
              {notStarted} not started
            </Badge>
          )}
          <span className="text-xs text-muted-foreground font-mono w-10 text-right">
            {Math.round(avgMastery * 100)}%
          </span>
          <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.min(avgMastery * 100, 100)}%`, backgroundColor: color }}
            />
          </div>
          <span className="text-xs text-muted-foreground">
            {proficient}/{skillRows.length}
          </span>
          {open
            ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
            : <ChevronRight className="h-4 w-4 text-muted-foreground" />
          }
        </div>
      </button>

      {/* Skills grid */}
      {open && (
        <div className="p-3 grid grid-cols-1 sm:grid-cols-2 gap-2 bg-background">
          {skillRows.map((skill) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              isSelected={selectedId === skill.id}
              onClick={() => onSelect(skill.id === selectedId ? -1 : skill.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Concept name helper ───────────────────────────────────────────────────────

function conceptDisplayName(c: ConceptInfo): string {
  return (c.name_en || c.name_zh || `Concept ${c.numeric_id ?? c.id}`).trim() || `Concept ${c.numeric_id ?? c.id}`;
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DetailPanel({
  skillId,
  allSkills,
  masteryVector,
  student,
  twinData,
  conceptStats,
  onClose,
}: {
  skillId: number;
  allSkills: SkillInfo[];
  masteryVector: number[];
  student: StudentPortfolio;
  twinData?: TwinViewerData | null;
  conceptStats: Map<number | string, { total: number; correct: number }>;
  onClose: () => void;
}) {
  const [conceptsOpen, setConceptsOpen] = useState(true);
  const mastery = masteryVector[skillId] ?? 0;
  const color = masteryToColor(mastery);
  const tier = masteryTier(mastery);

  // Find skill name + chapter + concepts
  let skillName = `Skill ${skillId}`;
  let chapterName = "";
  let concepts: ConceptInfo[] = [];
  const matchedSkill = allSkills.find((s) => s.id === skillId);
  if (matchedSkill) {
    skillName = matchedSkill.name;
    chapterName = matchedSkill.chapter_name;
    concepts = matchedSkill.concepts ?? [];
  }

  const step = student.learning_path?.steps?.find((s) => s.skill_id === skillId);
  const alert = twinData?.risk_forecast?.at_risk_skills?.find((a) => a.skill_id === skillId);
  const isAtRisk = mastery < 0.5;

  // Quiz history for this skill from timeline
  const quizAttempts = student.timeline.filter((e) => e.skill_id === skillId);
  const correct = quizAttempts.filter((e) => e.response === 1).length;

  // Concept-level stats
  const attemptedConcepts = concepts.filter((c) => conceptStats.has(c.id)).length;
  const totalConcepts = concepts.length;

  return (
    <Card className="border-primary/30">
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="text-sm leading-snug">{skillName}</CardTitle>
            <CardDescription className="text-xs">{chapterName}</CardDescription>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span
              className="text-[11px] font-semibold px-2 py-0.5 rounded-full text-white"
              style={{ backgroundColor: color }}
            >
              {tier}
            </span>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground text-xs px-1"
            >
              ✕
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4 space-y-3 text-sm">
        {/* Mastery */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Current Mastery</span>
            <span className="font-mono font-semibold">{formatPct100(mastery * 100)}</span>
          </div>
          <div className="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${Math.min(mastery * 100, 100)}%`, backgroundColor: color }}
            />
          </div>
        </div>

        {/* Practice history + coverage */}
        <div className="space-y-1">
          {quizAttempts.length > 0 && (
            <div className="text-xs text-muted-foreground">
              <BookOpen className="inline h-3 w-3 mr-1" />
              {quizAttempts.length} questions attempted · {correct}/{quizAttempts.length} correct (
              {Math.round((correct / quizAttempts.length) * 100)}%)
            </div>
          )}
          {totalConcepts > 0 && (
            <div className="text-xs text-muted-foreground">
              <Layers className="inline h-3 w-3 mr-1" />
              {attemptedConcepts}/{totalConcepts} concepts covered
            </div>
          )}
        </div>

        {/* At-risk warning */}
        {isAtRisk && (
          <div className="flex items-start gap-2 p-2 rounded-md bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-500 mt-0.5 shrink-0" />
            <p className="text-xs text-amber-700 dark:text-amber-300">
              {alert
                ? `Decay forecast active.${alert.downstream_at_risk > 0 ? ` ${alert.downstream_at_risk} downstream skills at risk.` : ""}`
                : "Mastery below 50% — needs practice."}
            </p>
          </div>
        )}

        {/* Learning path step */}
        {step && (
          <div className="flex items-start gap-2 p-2 rounded-md bg-primary/5 border border-primary/20">
            <Target className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
            <div className="text-xs space-y-0.5">
              <p className="font-semibold text-primary">Recommended Step #{step.rank}</p>
              {step.rationale && (
                <p className="text-muted-foreground italic leading-snug">{step.rationale}</p>
              )}
              <p className="text-muted-foreground">
                Projected mastery: {formatPct100(step.current_mastery * 100)} →{" "}
                <span className="font-semibold text-foreground">
                  {formatPct100(step.projected_mastery * 100)}
                </span>
              </p>
            </div>
          </div>
        )}

        {/* ── Concept breakdown ──────────────────────────────────────────── */}
        {totalConcepts > 0 && (
          <div className="border rounded-lg overflow-hidden">
            <button
              onClick={() => setConceptsOpen((v) => !v)}
              className="flex items-center gap-2 w-full px-3 py-2 hover:bg-accent/40 transition-colors text-left text-xs font-medium"
            >
              {conceptsOpen
                ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
              <span>Concept Breakdown</span>
              <span className="ml-auto text-muted-foreground font-normal">
                {attemptedConcepts}/{totalConcepts}
              </span>
            </button>
            {conceptsOpen && (
              <div className="border-t divide-y divide-border/30 max-h-64 overflow-y-auto">
                {concepts.map((concept, ci) => {
                  const stat = conceptStats.get(concept.id);
                  return (
                    <div
                      key={`${concept.numeric_id ?? concept.id}-${ci}`}
                      className="flex items-center gap-2 py-1.5 px-3 text-xs"
                    >
                      <BookOpen className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="flex-1 min-w-0 truncate">{conceptDisplayName(concept)}</span>
                      {stat ? (
                        <Badge
                          variant={stat.correct / stat.total >= 0.5 ? "default" : "destructive"}
                          className={`text-[9px] px-1.5 shrink-0 ${stat.correct / stat.total >= 0.5 ? "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30" : ""}`}
                        >
                          {stat.correct === stat.total
                            ? "correct"
                            : stat.correct === 0
                              ? "incorrect"
                              : `${stat.correct}/${stat.total}`}
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-[9px] px-1.5 text-muted-foreground shrink-0">
                          Not started
                        </Badge>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Practice CTA */}
        <Link
          to="../review"
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors w-full justify-center"
        >
          <BookOpen className="h-3 w-3" />
          Practice this skill
        </Link>
      </CardContent>
    </Card>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function JourneyMapTab({ student, skills, twinData, datasetId = "" }: JourneyMapTabProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Build concept-level stats (reuses same logic as the old Skill Map)
  const conceptStats = useMemo(() => {
    const base = buildConceptStats(student.timeline);
    const extended = new Map<number | string, { total: number; correct: number }>();
    for (const [k, v] of base) extended.set(k, v);
    for (const skill of skills) {
      for (const c of (skill.concepts ?? [])) {
        const lookupKey = getConceptLookupKey(c);
        if (base.has(lookupKey)) {
          extended.set(c.id, base.get(lookupKey)!);
        }
      }
    }
    return extended;
  }, [student.timeline, skills]);

  const masteryVector = useMemo(() => {
    if (twinData?.current_twin?.mastery?.length) return twinData.current_twin.mastery;
    return student.final_mastery;
  }, [twinData, student.final_mastery]);

  const atRiskIds = useMemo<Set<number>>(() => {
    const ids = new Set<number>();
    if (twinData?.risk_forecast?.at_risk_skills) {
      for (const a of twinData.risk_forecast.at_risk_skills) ids.add(a.skill_id);
    } else {
      for (let i = 0; i < masteryVector.length; i++) {
        if (masteryVector[i] < 0.5) ids.add(i);
      }
    }
    return ids;
  }, [twinData, masteryVector]);

  const cascadeIds = useMemo<Set<number>>(() => {
    const ids = new Set<number>();
    if (twinData?.risk_forecast?.at_risk_skills) {
      for (const a of twinData.risk_forecast.at_risk_skills) {
        if (a.downstream_at_risk > 0) ids.add(a.skill_id);
      }
    }
    return ids;
  }, [twinData]);

  const nextStepIds = useMemo<Map<number, number>>(() => {
    const map = new Map<number, number>();
    for (const step of student.learning_path?.steps ?? []) {
      map.set(step.skill_id, step.rank);
    }
    return map;
  }, [student.learning_path]);

  // Skills that have been assessed (timeline skill_id OR any child concept attempted)
  const assessedIds = useMemo(
    () => buildAttemptedSkillIds(student.timeline, skills, conceptStats),
    [student.timeline, skills, conceptStats]
  );

  // ── Build skill rows grouped by chapter ─────────────────────────────────
  const chapterRows = useMemo(() => {
    // Build a SkillRow for each skill
    const skillRowMap = new Map<number, SkillRow>();
    for (const skill of skills) {
      skillRowMap.set(skill.id, {
        id: skill.id,
        name: skill.name,
        mastery: masteryVector[skill.id] ?? 0,
        isStarted: assessedIds.has(skill.id),
        isAtRisk: atRiskIds.has(skill.id),
        isNextStep: nextStepIds.has(skill.id),
        nextStepRank: nextStepIds.get(skill.id),
        isCascade: cascadeIds.has(skill.id),
      });
    }

    // Group skills by chapter using groupByChapter
    const chapters = groupByChapter(skills);
    return chapters.map((chapter) => {
      const rows = chapter.skills
        .map((sk) => skillRowMap.get(sk.id)!)
        .filter(Boolean)
        .sort((a, b) => {
          if (a.isNextStep !== b.isNextStep) return a.isNextStep ? -1 : 1;
          if (a.isStarted !== b.isStarted) return a.isStarted ? -1 : 1;
          if (a.isAtRisk !== b.isAtRisk) return a.isAtRisk ? -1 : 1;
          return a.mastery - b.mastery;
        });
      return { chapterId: chapter.chapter_id, chapterName: chapter.chapter_name, rows };
    });
  }, [skills, masteryVector, atRiskIds, nextStepIds, cascadeIds, assessedIds]);

  // ── Summary stats ────────────────────────────────────────────────────────
  const allRows = useMemo(() => chapterRows.flatMap((d) => d.rows), [chapterRows]);
  const notStartedCount  = allRows.filter((r) => !r.isStarted).length;
  const proficientCount  = allRows.filter((r) => r.isStarted && r.mastery >= 0.75).length;
  const progressingCount = allRows.filter((r) => r.isStarted && r.mastery >= 0.50 && r.mastery < 0.75).length;
  const atRiskCount      = allRows.filter((r) => r.isStarted && r.mastery >= 0.30 && r.mastery < 0.50).length;
  const criticalCount    = allRows.filter((r) => r.isStarted && r.mastery < 0.30).length;
  const total = allRows.length;

  const assessedCount = allRows.filter((r) => assessedIds.has(r.id)).length;
  const masteredCount = allRows.filter((r) => r.mastery >= 0.75).length;

  return (
    <div className="space-y-5">

      {/* ── ARCD Insight Engine ───────────────────────────────────────────── */}
      <InsightPanel student={student} skills={skills} datasetId={datasetId} />

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold">Journey Map</h1>
          <p className="text-sm text-muted-foreground">
            Skills grouped by chapter · click any skill to see details · sorted by priority
          </p>
        </div>
        {/* Legend */}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {[
            { color: "#10b981", label: "Proficient ≥75%" },
            { color: "#3b82f6", label: "Progressing 50–74%" },
            { color: "#f59e0b", label: "At Risk 30–49%" },
            { color: "#ef4444", label: "Critical <30%" },
            { color: "#94a3b8", label: "Not started", dashed: true },
          ].map(({ color, label, dashed }) => (
            <span key={label} className="flex items-center gap-1.5">
              <span
                className={`w-2.5 h-2.5 rounded-full shrink-0 ${dashed ? "border-2 border-dashed" : ""}`}
                style={{ backgroundColor: dashed ? "transparent" : color, borderColor: dashed ? color : undefined }}
              />
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Coverage summary ─────────────────────────────────────────────── */}
      {total > 0 && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Info className="h-3.5 w-3.5 shrink-0" />
          <span>
            <span className="font-medium text-foreground">{assessedCount}</span> of{" "}
            <span className="font-medium text-foreground">{total}</span> skills assessed
            {" · "}
            <span className="font-medium text-emerald-600 dark:text-emerald-400">{masteredCount}</span> mastered (≥75%)
          </span>
        </div>
      )}

      {/* ── Mastery distribution bar ──────────────────────────────────────── */}
      {total > 0 && (
        <div className="space-y-1.5">
          <div className="flex h-3 rounded-full overflow-hidden gap-px">
            {proficientCount  > 0 && <div className="bg-emerald-500" style={{ flex: proficientCount }}  title={`Proficient: ${proficientCount}`}  />}
            {progressingCount > 0 && <div className="bg-blue-500"    style={{ flex: progressingCount }} title={`Progressing: ${progressingCount}`} />}
            {atRiskCount      > 0 && <div className="bg-amber-500"   style={{ flex: atRiskCount }}      title={`At Risk: ${atRiskCount}`}          />}
            {criticalCount    > 0 && <div className="bg-red-500"     style={{ flex: criticalCount }}    title={`Critical: ${criticalCount}`}        />}
            {notStartedCount  > 0 && <div className="bg-muted"       style={{ flex: notStartedCount }}  title={`Not Started: ${notStartedCount}`}   />}
          </div>
          <div className="flex flex-wrap justify-between text-[11px] text-muted-foreground gap-x-3">
            <span className="text-emerald-600 dark:text-emerald-400 font-medium">{proficientCount} proficient</span>
            <span className="text-blue-600 dark:text-blue-400 font-medium">{progressingCount} progressing</span>
            <span className="text-amber-600 dark:text-amber-400 font-medium">{atRiskCount} at-risk</span>
            <span className="text-red-600 dark:text-red-400 font-medium">{criticalCount} critical</span>
            {notStartedCount > 0 && <span className="text-muted-foreground font-medium">{notStartedCount} not started</span>}
          </div>
        </div>
      )}

      {/* ── Main layout ──────────────────────────────────────────────────── */}
      <div className={`grid gap-5 ${selectedId !== null ? "lg:grid-cols-[1fr_320px]" : ""}`}>

        {/* Chapter accordion */}
        <div className="space-y-3">
          {chapterRows.map(({ chapterId, chapterName, rows }, di) => (
            <ChapterSection
              key={chapterId}
              chapterId={chapterId}
              chapterName={chapterName}
              skills={rows}
              color={SKILL_HEX[di % SKILL_HEX.length]}
              selectedId={selectedId}
              onSelect={(id) => setSelectedId(id === -1 ? null : id)}
              defaultOpen={di === 0 || rows.some((r) => r.isNextStep)}
            />
          ))}
        </div>

        {/* Detail panel — appears only when a skill is selected */}
        {selectedId !== null && (
          <div className="space-y-4">
            <DetailPanel
              skillId={selectedId}
              allSkills={skills}
              masteryVector={masteryVector}
              student={student}
              twinData={twinData}
              conceptStats={conceptStats}
              onClose={() => setSelectedId(null)}
            />
            {!twinData && (
              <p className="text-xs text-muted-foreground flex items-start gap-1.5">
                <Star className="h-3 w-3 shrink-0 mt-0.5" />
                Run the digital twin notebook to enable decay-based risk alerts.
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Empty state hint ─────────────────────────────────────────────── */}
      {selectedId === null && (
        <p className="text-xs text-muted-foreground text-center pt-2 flex items-center justify-center gap-1.5">
          <Info className="h-3 w-3" />
          Click any skill card to see mastery details, practice history, and learning path guidance.
        </p>
      )}

    </div>
  );
}
