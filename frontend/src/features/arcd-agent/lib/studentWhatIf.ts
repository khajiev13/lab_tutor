/**
 * Per-student What-If estimator (frontend-only).
 *
 * The Teacher Twin's per-student What-If panel does not call a backend
 * endpoint — it computes a hypothetical "what if I taught these K skills"
 * outcome locally. The previous implementation applied a uniform
 * `current + delta` to every skill, which made every student's recommendation
 * boil down to "the K skills with the most room to grow" and gave no
 * signal-aware ranking.
 *
 * This module replaces that uniform boost with a Vygotsky-style ZPD curve
 * plus per-skill bonuses sourced from data that's already loaded:
 *
 *   - **ZPD multiplier** — peak learnability around 0.5–0.7 mastery, smaller
 *     gains for foundation gaps (<0.2) and diminishing returns above 0.9.
 *   - **Regression bonus** — when peak mastery (`base_mastery`) exceeds the
 *     current value, the skill is decaying; reinforcement has a higher payoff.
 *   - **Risk bonus** — skills flagged in the twin's `risk_forecast` get a
 *     bonus proportional to predicted decay and downstream impact.
 *
 * The teacher's `delta` slider is now a *max effort* knob that scales the
 * combined boost. The function is pure and unit-tested in
 * `studentWhatIf.test.ts`.
 */

import type { StudentPortfolio, TwinSkillAlert, SkillInfo } from "./types";

export interface StudentWhatIfRow {
  skill_name: string;
  current_mastery: number;
  simulated_mastery: number;
  gain: number;
  /**
   * Short human-readable rationale ("decaying skill", "ZPD peak", etc.).
   * Surfaced in the UI so the teacher can see why a skill was prioritized.
   */
  rationale: string;
}

/**
 * Vygotsky ZPD multiplier: how much a teaching push of `delta` actually
 * improves a skill at this current mastery level. Pure function; no I/O.
 */
function zpdMultiplier(currentMastery: number): number {
  if (currentMastery < 0.2) return 0.6; // foundation gap — needs prereqs first
  if (currentMastery < 0.4) return 0.85; // approaching ZPD
  if (currentMastery < 0.7) return 1.0; // ZPD peak — maximum payoff
  if (currentMastery < 0.9) return 0.7; // upper ZPD — diminishing returns
  return 0.3; // already mastered — small refresh only
}

/**
 * Project `current` mastery forward under `delta` reinforcement, weighted by
 * per-skill signals. Inputs come from data the page already has loaded.
 */
export function estimateStudentSkillBoost(
  current: number,
  delta: number,
  signals: {
    base_mastery?: number;
    predicted_decay?: number;
    downstream_at_risk?: number;
  } = {},
): { simulated: number; rationale: string } {
  const zpd = zpdMultiplier(current);
  const reasons: string[] = [];

  // Regression bonus — peak mastery decayed since
  let regressionBonus = 0;
  if (signals.base_mastery !== undefined && signals.base_mastery > current + 0.05) {
    regressionBonus = 0.5 * (signals.base_mastery - current);
    reasons.push(`recovering ${Math.round((signals.base_mastery - current) * 100)}pt regression`);
  }

  // Risk bonus — at-risk skill from twin forecast
  let riskBonus = 0;
  if (signals.predicted_decay !== undefined && signals.predicted_decay > 0) {
    riskBonus += 0.3 * Math.min(1, signals.predicted_decay);
    reasons.push("at-risk for forgetting");
  }
  if (signals.downstream_at_risk !== undefined && signals.downstream_at_risk > 0) {
    riskBonus += 0.05 * Math.min(4, signals.downstream_at_risk);
    reasons.push(`unblocks ${signals.downstream_at_risk} downstream skill${signals.downstream_at_risk === 1 ? "" : "s"}`);
  }

  const effectiveBoost = delta * zpd + regressionBonus + riskBonus;
  const simulated = Math.min(1.0, current + effectiveBoost);

  if (reasons.length === 0) {
    if (current < 0.2) reasons.push("foundation gap");
    else if (current < 0.7) reasons.push("ZPD sweet spot");
    else if (current < 0.9) reasons.push("upper ZPD — diminishing returns");
    else reasons.push("already mastered");
  }

  return { simulated, rationale: reasons.join("; ") };
}

/**
 * Top-level orchestrator: compute per-skill projected outcome and return the
 * top K skills sorted by gain (largest first). Equivalent gains tie-break to
 * the weakest current mastery, preserving the previous behavior.
 */
export function estimateStudentWhatIf(
  portfolio: StudentPortfolio,
  skillList: SkillInfo[],
  delta: number,
  topK: number,
  riskAlerts: TwinSkillAlert[] = [],
): StudentWhatIfRow[] {
  // Build a per-skill index of risk signals for O(1) lookup.
  const riskBySkillName = new Map<string, TwinSkillAlert>();
  for (const alert of riskAlerts) {
    if (alert?.skill_name) riskBySkillName.set(alert.skill_name, alert);
  }

  const rows: StudentWhatIfRow[] = skillList.map((sk, i) => {
    const current = portfolio.final_mastery?.[i] ?? 0;
    const base = portfolio.base_mastery?.[i];
    const risk = riskBySkillName.get(sk.name);

    const { simulated, rationale } = estimateStudentSkillBoost(current, delta, {
      base_mastery: base,
      predicted_decay: risk?.predicted_decay,
      downstream_at_risk: risk?.downstream_at_risk,
    });

    return {
      skill_name: sk.name,
      current_mastery: current,
      simulated_mastery: simulated,
      gain: simulated - current,
      rationale,
    };
  });

  rows.sort((a, b) => b.gain - a.gain || a.current_mastery - b.current_mastery);
  return rows.slice(0, Math.max(1, topK));
}
