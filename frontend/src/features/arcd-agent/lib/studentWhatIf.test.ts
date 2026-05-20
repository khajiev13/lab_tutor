import { describe, expect, it } from "vitest";

import {
  estimateStudentSkillBoost,
  estimateStudentWhatIf,
} from "./studentWhatIf";
import type { SkillInfo, StudentPortfolio, TwinSkillAlert } from "./types";

const buildSkill = (id: number, name: string): SkillInfo => ({
  id,
  chapter_id: 1,
  domain_id: 1,
  chapter_order: 1,
  chapter_name: "Chapter 1",
  name,
  concepts: [],
  n_concepts: 0,
});

const buildPortfolio = (
  finalMastery: number[],
  baseMastery?: number[],
): StudentPortfolio => ({
  uid: "stu_1",
  summary: {
    student_id: "stu_1",
    n_skills: finalMastery.length,
  } as never,
  final_mastery: finalMastery,
  base_mastery: baseMastery,
  timeline: [],
});

describe("estimateStudentSkillBoost", () => {
  it("applies a peak ZPD multiplier in the 0.4-0.7 band", () => {
    const result = estimateStudentSkillBoost(0.5, 0.2);
    // delta * 1.0 (ZPD peak) = 0.2; simulated = 0.7
    expect(result.simulated).toBeCloseTo(0.7, 4);
    expect(result.rationale).toContain("ZPD sweet spot");
  });

  it("dampens the boost for foundation gaps (mastery < 0.2)", () => {
    const result = estimateStudentSkillBoost(0.1, 0.2);
    // delta * 0.6 = 0.12; simulated = 0.22
    expect(result.simulated).toBeCloseTo(0.22, 4);
    expect(result.rationale).toContain("foundation gap");
  });

  it("dampens the boost for already-mastered skills (>= 0.9)", () => {
    const result = estimateStudentSkillBoost(0.95, 0.2);
    // delta * 0.3 = 0.06; simulated = min(1, 1.01) = 1.0
    expect(result.simulated).toBeCloseTo(1.0, 4);
    expect(result.rationale).toContain("already mastered");
  });

  it("adds a regression bonus when base_mastery > current", () => {
    const noSignal = estimateStudentSkillBoost(0.5, 0.2);
    const withRegression = estimateStudentSkillBoost(0.5, 0.2, {
      base_mastery: 0.8,
    });
    // regression bonus = 0.5 * (0.8 - 0.5) = 0.15
    expect(withRegression.simulated).toBeGreaterThan(noSignal.simulated);
    expect(withRegression.rationale).toContain("regression");
  });

  it("adds a risk bonus when predicted_decay > 0", () => {
    const noRisk = estimateStudentSkillBoost(0.5, 0.2);
    const withRisk = estimateStudentSkillBoost(0.5, 0.2, {
      predicted_decay: 0.6,
    });
    expect(withRisk.simulated).toBeGreaterThan(noRisk.simulated);
    expect(withRisk.rationale).toContain("at-risk");
  });

  it("adds a downstream-impact bonus and mentions skill count", () => {
    const result = estimateStudentSkillBoost(0.5, 0.2, {
      downstream_at_risk: 3,
    });
    expect(result.rationale).toContain("3 downstream skills");
  });

  it("caps simulated mastery at 1.0", () => {
    const result = estimateStudentSkillBoost(0.95, 0.5, {
      base_mastery: 1.0,
      predicted_decay: 1,
      downstream_at_risk: 4,
    });
    expect(result.simulated).toBeLessThanOrEqual(1.0);
    expect(result.simulated).toBeCloseTo(1.0, 4);
  });
});

describe("estimateStudentWhatIf", () => {
  it("produces per-skill differentiated gains (not uniform)", () => {
    // Three skills at the same current mastery should still differ when one
    // has a regression signal and another has risk.
    const portfolio = buildPortfolio([0.5, 0.5, 0.5], [0.5, 0.8, 0.5]);
    const skills = [
      buildSkill(1, "no_signal"),
      buildSkill(2, "regressing"),
      buildSkill(3, "at_risk"),
    ];
    const alerts: TwinSkillAlert[] = [
      {
        skill_id: 3,
        skill_name: "at_risk",
        current_mastery: 0.5,
        predicted_decay: 0.7,
        downstream_at_risk: 2,
        priority: "HIGH",
      },
    ];

    const rows = estimateStudentWhatIf(portfolio, skills, 0.2, 3, alerts);
    const byName = Object.fromEntries(rows.map((r) => [r.skill_name, r.gain]));

    // All three differ — no uniform delta.
    expect(new Set(Object.values(byName)).size).toBe(3);
    // Regressing and at-risk both beat the plain ZPD-only signal.
    expect(byName.regressing).toBeGreaterThan(byName.no_signal);
    expect(byName.at_risk).toBeGreaterThan(byName.no_signal);
  });

  it("ranks weakest skill first when gains tie (delta=0)", () => {
    // delta=0 makes every skill produce gain=0 exactly (no FP noise from
    // current+delta arithmetic), so the tie-breaker is fully exercised.
    const portfolio = buildPortfolio([0.6, 0.5, 0.4]);
    const skills = [
      buildSkill(1, "skill_high"),
      buildSkill(2, "skill_mid"),
      buildSkill(3, "skill_low"),
    ];
    const rows = estimateStudentWhatIf(portfolio, skills, 0, 3);
    expect(rows.map((r) => r.skill_name)).toEqual([
      "skill_low",
      "skill_mid",
      "skill_high",
    ]);
  });

  it("respects topK and never returns more than requested", () => {
    const portfolio = buildPortfolio([0.5, 0.5, 0.5, 0.5, 0.5]);
    const skills = [1, 2, 3, 4, 5].map((i) => buildSkill(i, `s_${i}`));
    const rows = estimateStudentWhatIf(portfolio, skills, 0.2, 2);
    expect(rows).toHaveLength(2);
  });

  it("handles missing final_mastery entries by treating them as zero", () => {
    const portfolio: StudentPortfolio = {
      uid: "x",
      summary: { student_id: "x", n_skills: 2 } as never,
      final_mastery: [],
      timeline: [],
    };
    const skills = [buildSkill(1, "a"), buildSkill(2, "b")];
    const rows = estimateStudentWhatIf(portfolio, skills, 0.2, 2);
    expect(rows[0].current_mastery).toBe(0);
  });
});
