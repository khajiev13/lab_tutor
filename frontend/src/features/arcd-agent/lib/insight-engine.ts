import type {
  StudentPortfolio,
  SkillInfo,
  InsightResponse,
  TimelineEntry,
} from "./types";
import { buildSubSkillNameMap } from "./types";

interface SkillTrajectory {
  skillId: number;
  skillName: string;
  earlyMastery: number;
  lateMastery: number;
  delta: number;
  recentAccuracy: number;
  entryCount: number;
}

function computeSkillTrajectories(
  student: StudentPortfolio,
  nameMap: Record<number, string>
): SkillTrajectory[] {
  const skillEntries: Record<number, TimelineEntry[]> = {};
  for (const e of student.timeline) {
    const sid = e.skill_id;
    if (sid >= 0) {
      (skillEntries[sid] ??= []).push(e);
    }
  }

  const trajectories: SkillTrajectory[] = [];
  for (const [sidStr, entries] of Object.entries(skillEntries)) {
    const sid = Number(sidStr);
    if (entries.length < 2) continue;

    const split = Math.max(1, Math.floor(entries.length * 0.3));
    const earlySlice = entries.slice(0, split);
    const lateSlice = entries.slice(-split);

    const earlyAcc =
      earlySlice.reduce((s, e) => s + e.response, 0) / earlySlice.length;
    const lateAcc =
      lateSlice.reduce((s, e) => s + e.response, 0) / lateSlice.length;

    trajectories.push({
      skillId: sid,
      skillName: nameMap[sid] ?? `Skill ${sid}`,
      earlyMastery: earlyAcc,
      lateMastery: lateAcc,
      delta: lateAcc - earlyAcc,
      recentAccuracy: lateAcc,
      entryCount: entries.length,
    });
  }

  return trajectories.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
}

function computeRecentMomentum(timeline: TimelineEntry[]): {
  trend: "improving" | "stable" | "declining";
  recentAccuracy: number;
  earlierAccuracy: number;
} {
  if (timeline.length < 4) {
    const acc =
      timeline.length > 0
        ? timeline.reduce((s, e) => s + e.response, 0) / timeline.length
        : 0;
    return { trend: "stable", recentAccuracy: acc, earlierAccuracy: acc };
  }

  const mid = Math.floor(timeline.length / 2);
  const earlier = timeline.slice(0, mid);
  const recent = timeline.slice(mid);

  const earlierAcc =
    earlier.reduce((s, e) => s + e.response, 0) / earlier.length;
  const recentAcc =
    recent.reduce((s, e) => s + e.response, 0) / recent.length;
  const diff = recentAcc - earlierAcc;

  let trend: "improving" | "stable" | "declining";
  if (diff > 0.05) trend = "improving";
  else if (diff < -0.05) trend = "declining";
  else trend = "stable";

  return { trend, recentAccuracy: recentAcc, earlierAccuracy: earlierAcc };
}

function masteryLevel(avg: number): string {
  if (avg >= 0.85) return "strong";
  if (avg >= 0.65) return "developing";
  if (avg >= 0.4) return "emerging";
  return "early-stage";
}

function buildGreetingSummary(student: StudentPortfolio): string {
  if (student.final_mastery.length === 0) {
    return "You have not activated any study skills yet. Select skills in your learning path to unlock ARCD guidance.";
  }

  const avg = student.summary.avg_mastery;
  const level = masteryLevel(avg);
  const { trend, recentAccuracy } = computeRecentMomentum(student.timeline);

  const levelPhrases: Record<string, string> = {
    strong: `You have a strong overall mastery of ${(avg * 100).toFixed(2)}% across your skills`,
    developing: `Your overall mastery sits at ${(avg * 100).toFixed(2)}% — a solid developing foundation`,
    emerging: `Your mastery is at ${(avg * 100).toFixed(2)}%, with clear room for growth`,
    "early-stage": `You're just getting started with an overall mastery of ${(avg * 100).toFixed(2)}%`,
  };

  const trendPhrases: Record<string, string> = {
    improving: `Your recent sessions show upward momentum with ${(recentAccuracy * 100).toFixed(2)}% accuracy — great progress!`,
    stable: `Your recent performance is steady — a consistent foundation to build upon.`,
    declining: `Your recent accuracy has dipped slightly — a focused review session could help reinforce what you've learned.`,
  };

  return `${levelPhrases[level]}. ${trendPhrases[trend]}`;
}

function buildKnowledgeTracingInsight(
  student: StudentPortfolio,
  nameMap: Record<number, string>
): string {
  if (student.final_mastery.length === 0) {
    return "No skills are being tracked yet. Select skills in your learning path first, then ARCD will analyze your progress.";
  }

  const trajectories = computeSkillTrajectories(student, nameMap);
  if (trajectories.length === 0) {
    return "Not enough interaction history to identify a specific skill trajectory yet — keep practicing!";
  }

  const pcoSkills = student.review_session?.pco_skills_detected ?? [];
  if (pcoSkills.length > 0) {
    const pcoName = nameMap[pcoSkills[0]] ?? `Skill ${pcoSkills[0]}`;
    const m =
      pcoSkills[0] < student.final_mastery.length
        ? student.final_mastery[pcoSkills[0]]
        : 0;
    return `"${pcoName}" shows persistent difficulty (mastery at ${(m * 100).toFixed(2)}%) despite multiple attempts — this skill may need a different approach or deeper scaffolding.`;
  }

  const top = trajectories[0];
  if (top.delta > 0.1) {
    return `Your mastery of "${top.skillName}" has grown significantly (accuracy up ${(top.delta * 100).toFixed(2)}pp) — your practice is clearly paying off.`;
  }
  if (top.delta < -0.1) {
    return `"${top.skillName}" shows signs of decay (accuracy down ${(Math.abs(top.delta) * 100).toFixed(2)}pp) — a targeted review could help restore it.`;
  }

  const strongest = student.summary.strongest_skill;
  const weakest = student.summary.weakest_skill;
  const sName = nameMap[strongest] ?? `Skill ${strongest}`;
  const wName = nameMap[weakest] ?? `Skill ${weakest}`;
  const sM =
    strongest < student.final_mastery.length
      ? student.final_mastery[strongest]
      : 0;
  const wM =
    weakest < student.final_mastery.length
      ? student.final_mastery[weakest]
      : 0;

  if (sM - wM > 0.3) {
    return `Your strongest skill "${sName}" (${(sM * 100).toFixed(2)}%) far outpaces "${wName}" (${(wM * 100).toFixed(2)}%) — bridging this gap could unlock more advanced topics.`;
  }

  return `Your skills are developing relatively evenly — "${sName}" leads at ${(sM * 100).toFixed(2)}% while "${wName}" at ${(wM * 100).toFixed(2)}% has the most room for growth.`;
}

function buildRecommendedNextStep(
  student: StudentPortfolio,
  nameMap: Record<number, string>
): string {
  if (student.final_mastery.length === 0) {
    return "Select your course and job-posting skills first. Once you do, ARCD will recommend the best next step.";
  }

  if (student.learning_path && student.learning_path.steps.length > 0) {
    const step = student.learning_path.steps[0];
    const gain = step.predicted_mastery_gain;
    return `Your Learning Path recommends focusing on "${step.skill_name}" next — it's in your Zone of Proximal Development with a predicted mastery gain of ${(gain * 100).toFixed(2)}%. Start there for the highest impact.`;
  }

  if (student.review_session) {
    const rs = student.review_session;
    if (rs.pco_skills_detected.length > 0) {
      const pcoId = rs.pco_skills_detected[0];
      const pcoName = nameMap[pcoId] ?? `Skill ${pcoId}`;
      return `Your review queue flagged "${pcoName}" as needing deep review — try the guided slow-thinking exercises to build a stronger foundation in this area.`;
    }
    if (rs.fast_reviews.length > 0) {
      const fr = rs.fast_reviews[0];
      return `A quick review of "${fr.skill_name}" is queued up — it has high urgency and a short session could solidify your understanding.`;
    }
  }

  const weakest = student.summary.weakest_skill;
  const wName = nameMap[weakest] ?? `Skill ${weakest}`;
  const wM =
    weakest < student.final_mastery.length
      ? student.final_mastery[weakest]
      : 0;
  return `Consider spending time on "${wName}" (currently at ${(wM * 100).toFixed(2)}% mastery) — steady practice on your weakest area will yield the biggest overall improvement.`;
}

export function generateInsight(
  student: StudentPortfolio,
  skills: SkillInfo[]
): InsightResponse {
  const nameMap = buildSubSkillNameMap(skills);
  return {
    greeting_summary: buildGreetingSummary(student),
    knowledge_tracing_insight: buildKnowledgeTracingInsight(student, nameMap),
    recommended_next_step: buildRecommendedNextStep(student, nameMap),
  };
}
