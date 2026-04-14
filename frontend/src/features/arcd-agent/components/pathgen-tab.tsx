
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { MathText } from "@/features/arcd-agent/components/math-text";
import type { StudentPortfolio, SkillInfo } from "@/features/arcd-agent/lib/types";
import { buildSubSkillNameMap } from "@/features/arcd-agent/lib/types";
import { masteryTierColor } from "@/features/arcd-agent/lib/colors";

interface PathGenTabProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
  datasetId: string;
  onStartPractice?: (skillId: number, skillName: string) => void;
}

const SESSION_TYPE_STYLE: Record<string, { label: string; className: string }> = {
  guided_learning:           { label: "Guided",     className: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300" },
  deliberate_practice:       { label: "Practice",   className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300" },
  challenge:                 { label: "Challenge",  className: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" },
  spaced_review:             { label: "Review",     className: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300" },
  prerequisite_remediation:  { label: "Prereq",     className: "bg-slate-100 text-slate-800 dark:bg-slate-900/40 dark:text-slate-300" },
  deep_diagnostic:           { label: "Diagnostic", className: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300" },
};

function resolveSkillName(
  skillId: number,
  rawName: string,
  skills: SkillInfo[],
  nameMap: Record<number, string>
): string {
  if (rawName && !rawName.match(/^Skill \d+$/)) return rawName;
  if (nameMap[skillId]) return nameMap[skillId];
  const domain = skills.find((s) => s.id === skillId);
  if (domain) return domain.name;
  return rawName || `Skill ${skillId}`;
}

export function PathGenTab({ student, skills, onStartPractice }: PathGenTabProps) {
  const path = student.learning_path;
  const nameMap = buildSubSkillNameMap(skills);
  const [expandedRank, setExpandedRank] = useState<number | null>(null);

  if (!path || !path.steps || path.steps.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground max-w-md mx-auto">
        <p className="text-lg font-medium">No learning path generated yet</p>
        <p className="text-sm mt-2">
          Run <code className="bg-muted px-1.5 py-0.5 rounded text-xs">PathGen.ipynb</code> (sections
          <strong> 7 · Generate Paths</strong> and <strong>9 · Export</strong>) to generate
          personalised learning paths for all datasets, including this one.
        </p>
        <p className="text-xs mt-3 opacity-80">
          PathGen reads <code className="bg-muted/70 px-1 rounded">student_portfolio.json</code> and
          writes <code className="bg-muted/70 px-1 rounded">learning_path</code> for each student.
        </p>
      </div>
    );
  }

  const steps = path.steps;
  const totalSteps = steps.length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="space-y-1">
        <h2 className="text-xl font-bold">Recommended Learning Path</h2>
        <p className="text-sm text-muted-foreground">
          {totalSteps} skills recommended · click any node to see details
        </p>
      </div>

      {/* Progress bar */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${(steps.filter((s) => s.current_mastery >= 0.75).length / totalSteps) * 100}%` }}
          />
        </div>
        <span className="shrink-0">
          {steps.filter((s) => s.current_mastery >= 0.75).length}/{totalSteps} mastered
        </span>
      </div>

      {/* Winding path */}
      <div className="relative">
        {steps.map((step, i) => {
          const displayName = resolveSkillName(step.skill_id, step.skill_name, skills, nameMap);
          const color = masteryTierColor(step.current_mastery);
          const isMastered = step.current_mastery >= 0.75;
          const isExpanded = expandedRank === step.rank;
          // Alternate left and right like a winding path
          const isLeft = i % 2 === 0;
          const sessionStyle = step.action_plan?.session_type
            ? SESSION_TYPE_STYLE[step.action_plan.session_type]
            : null;

          return (
            <div
              key={step.rank}
              className={`relative flex items-start gap-4 mb-2 ${isLeft ? "flex-row" : "flex-row-reverse"}`}
            >
              {/* Connector line */}
              {i < steps.length - 1 && (
                <div
                  className={`absolute top-12 w-0.5 bg-border z-0 ${isLeft ? "left-6" : "right-6"}`}
                  style={{ height: "calc(100% - 8px)" }}
                />
              )}

              {/* Node circle */}
              <button
                onClick={() => setExpandedRank(isExpanded ? null : step.rank)}
                className={`relative z-10 flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-md transition-all hover:scale-110 focus:outline-none ${
                  isExpanded ? "ring-4 ring-offset-2 ring-primary/50 scale-110" : ""
                }`}
                style={{ backgroundColor: color }}
              >
                {isMastered ? "✓" : step.rank}
              </button>

              {/* Content card */}
              <div className={`flex-1 min-w-0 pb-4 ${!isLeft ? "text-right" : ""}`}>
                <button
                  onClick={() => setExpandedRank(isExpanded ? null : step.rank)}
                  className={`w-full text-left rounded-xl border transition-all p-3 hover:shadow-sm ${
                    isExpanded ? "bg-primary/5 border-primary/30" : "bg-card border-border hover:border-primary/20"
                  } ${!isLeft ? "text-right" : ""}`}
                >
                  {/* Name row */}
                  <div className={`flex items-center gap-2 flex-wrap ${!isLeft ? "justify-end" : ""}`}>
                    <span className="font-semibold text-sm leading-tight">{displayName}</span>
                    {sessionStyle && (
                      <Badge className={`text-[10px] ${sessionStyle.className}`}>
                        {sessionStyle.label}
                      </Badge>
                    )}
                    <Badge className="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 text-[10px] font-mono">
                      +{(step.predicted_mastery_gain * 100).toFixed(1)}%
                    </Badge>
                  </div>

                  {/* Mastery bar */}
                  <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full rounded-full relative">
                      <div
                        className="absolute inset-y-0 left-0 rounded-full bg-slate-400 opacity-60"
                        style={{ width: `${step.current_mastery * 100}%` }}
                      />
                      <div
                        className="absolute inset-y-0 left-0 rounded-full opacity-40"
                        style={{ width: `${step.projected_mastery * 100}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                  <div className={`flex items-center gap-3 mt-1 text-[11px] text-muted-foreground font-mono ${!isLeft ? "justify-end" : ""}`}>
                    <span>{(step.current_mastery * 100).toFixed(0)}% → <span className="text-foreground font-semibold">{(step.projected_mastery * 100).toFixed(0)}%</span></span>
                    {step.action_plan?.estimated_minutes && (
                      <span>~{step.action_plan.estimated_minutes} min</span>
                    )}
                  </div>
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <Card className="mt-2 border-primary/20">
                    <CardContent className="pt-4 space-y-3 text-sm">
                      {/* Scores row */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span>Score: <b className="text-foreground font-mono">{(step.score * 100).toFixed(1)}</b></span>
                        <span style={{ color: "#e76f51" }}>ZPD: {(step.zpd_score * 100).toFixed(1)}</span>
                        <span style={{ color: "#2a9d8f" }}>Prereq: {(step.prereq_score * 100).toFixed(1)}</span>
                        <span style={{ color: "#264653" }} className="dark:!text-slate-300">Decay: {(step.decay_score * 100).toFixed(1)}</span>
                        <span style={{ color: "#e9c46a" }}>Momentum: {(step.momentum_score * 100).toFixed(1)}</span>
                      </div>

                      {/* Exercises */}
                      {step.action_plan?.exercises && step.action_plan.exercises.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          Exercises:{" "}
                          {Object.entries(
                            step.action_plan.exercises.reduce<Record<string, number>>((acc, e) => {
                              acc[e.difficulty_band] = (acc[e.difficulty_band] || 0) + e.count;
                              return acc;
                            }, {})
                          ).map(([band, count]) => `${count} ${band}`).join(", ")}
                        </p>
                      )}

                      {/* Review date */}
                      {step.action_plan?.next_review_date && (
                        <p className="text-xs text-muted-foreground">
                          Review by:{" "}
                          {new Date(step.action_plan.next_review_date).toLocaleDateString()}
                        </p>
                      )}

                      {/* Success criteria */}
                      {step.action_plan?.success_criteria && (
                        <p className="text-xs text-muted-foreground">
                          Success: {step.action_plan.success_criteria}
                        </p>
                      )}

                      {/* Rationale */}
                      <p className="text-xs text-muted-foreground italic leading-relaxed">
                        <MathText text={step.rationale} />
                      </p>

                      {/* Practice button */}
                      {onStartPractice && (
                        <button
                          onClick={() => onStartPractice(step.skill_id, displayName)}
                          className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors shadow-sm"
                        >
                          <span className="text-[13px]">&#9654;</span>
                          Practice Now
                        </button>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
