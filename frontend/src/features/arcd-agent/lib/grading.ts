/**
 * Shared grading logic (Coursera-style) and formatting for the dashboard.
 * Use everywhere we show mastery/accuracy so values are consistent.
 *
 * KG hierarchy: CHAPTER (domain) → SKILL → CONCEPT
 * The mastery vector is indexed by skill position (mastery[i] = mastery of skills[i]).
 */
import type { SkillInfo, TimelineEntry } from "@/features/arcd-agent/lib/types";

export interface ConceptStat {
  correct: number;
  total: number;
}

/** Build per-concept and per-skill stats from timeline. Keys: concept id (number) and skill_id (number). */
export function buildConceptStats(
  timeline: TimelineEntry[]
): Map<number | string, ConceptStat> {
  const byConcept = new Map<number, ConceptStat>();
  const bySkill = new Map<number, ConceptStat>();
  for (const e of timeline) {
    if (e.concept_id >= 0) {
      const prev = byConcept.get(e.concept_id) ?? { correct: 0, total: 0 };
      byConcept.set(e.concept_id, {
        correct: prev.correct + e.response,
        total: prev.total + 1,
      });
    }
    if (e.skill_id >= 0) {
      const prev = bySkill.get(e.skill_id) ?? { correct: 0, total: 0 };
      bySkill.set(e.skill_id, {
        correct: prev.correct + e.response,
        total: prev.total + 1,
      });
    }
  }
  const out = new Map<number | string, ConceptStat>();
  for (const [k, v] of byConcept) out.set(k, v);
  for (const [k, v] of bySkill) out.set(k, v);
  return out;
}

/**
 * Resolve concept key for lookup (timeline uses numeric concept_id; hierarchy may use number or string id).
 * For string ids like "Tag-103" or "Tag-103 (Reading...)" (EdNet-style), parses the number so stats match.
 */
export function getConceptLookupKey(c: { id: number | string; numeric_id?: number }): number | string {
  if (c.numeric_id !== undefined) return c.numeric_id;
  if (typeof c.id === "number") return c.id;
  const s = String(c.id);
  const match = s.match(/^Tag-(\d+)/);
  if (match) return parseInt(match[1], 10);
  return c.id;
}

function conceptKey(c: { id: number | string; numeric_id?: number }): number | string {
  return getConceptLookupKey(c);
}

/**
 * Coursera-style grade for a skill: average of its concept grades.
 * Each concept = correct/attempted (0–1), not attempted = 0.
 */
export function getCourseraSkillGrade(
  skill: SkillInfo,
  conceptStats: Map<number | string, ConceptStat>
): number {
  const concepts = skill.concepts ?? [];
  if (concepts.length === 0) {
    // Fall back to the skill-level stat if no concepts are attached.
    const stat = conceptStats.get(skill.id);
    return stat && stat.total > 0 ? stat.correct / stat.total : 0;
  }
  let sum = 0;
  for (const c of concepts) {
    const key = conceptKey(c);
    const stat = conceptStats.get(key);
    if (stat && stat.total > 0) sum += stat.correct / stat.total;
  }
  return sum / concepts.length;
}

// Backward-compat alias (was used for sub-skill-level grading).
export const getCourseraSubSkillGrade = (
  _subSkill: { id: number; name: string; concepts?: { id: number | string; numeric_id?: number }[] },
  conceptStats: Map<number | string, ConceptStat>
): number => {
  const concepts = _subSkill.concepts ?? [];
  if (concepts.length === 0) return 0;
  let sum = 0;
  for (const c of concepts) {
    const key = conceptKey(c);
    const stat = conceptStats.get(key);
    if (stat && stat.total > 0) sum += stat.correct / stat.total;
  }
  return sum / concepts.length;
};

/**
 * Coursera-style grade for a chapter (= a SkillInfo row):
 * average of concept grades across the skill.
 */
export function getCourseraChapterGrade(
  chapter: SkillInfo,
  conceptStats: Map<number | string, ConceptStat>
): number {
  return getCourseraSkillGrade(chapter, conceptStats);
}

/**
 * Per-skill: total correct and total questions from concept-level stats.
 */
export function getSkillConceptStats(
  skill: SkillInfo,
  conceptStats: Map<number | string, ConceptStat>
): { correct: number; total: number; attemptedConcepts: number } {
  const concepts = skill.concepts ?? [];
  let correct = 0;
  let total = 0;
  let attempted = 0;
  for (const c of concepts) {
    const stat = conceptStats.get(conceptKey(c));
    if (stat) {
      correct += stat.correct;
      total += stat.total;
      attempted += 1;
    }
  }
  // Also count direct skill-level interactions.
  if (concepts.length === 0) {
    const stat = conceptStats.get(skill.id);
    if (stat) {
      correct += stat.correct;
      total += stat.total;
    }
  }
  return { correct, total, attemptedConcepts: attempted };
}

// Backward-compat alias.
export const getSubSkillCorrectTotal = (
  subSkill: { id: number; name: string; concepts?: { id: number | string; numeric_id?: number }[] },
  conceptStats: Map<number | string, ConceptStat>
): { correct: number; total: number; attemptedConcepts: number } => {
  const concepts = subSkill.concepts ?? [];
  let correct = 0;
  let total = 0;
  let attempted = 0;
  for (const c of concepts) {
    const stat = conceptStats.get(conceptKey(c));
    if (stat) {
      correct += stat.correct;
      total += stat.total;
      attempted += 1;
    }
  }
  return { correct, total, attemptedConcepts: attempted };
};

/** Format percentage with exact decimals (default 2). */
export function formatPct(value: number, decimals = 2): string {
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Format percentage from 0–100 with exact decimals. */
export function formatPct100(value: number, decimals = 2): string {
  return `${Number(value.toFixed(decimals))}%`;
}

/** Find skill by id (= index in skills array). */
export function getSkillById(skills: SkillInfo[], skillId: number): SkillInfo | undefined {
  return skills.find((s) => s.id === skillId);
}

// Backward-compat alias.
export const getSubSkillById = getSkillById;

/**
 * Compute the 60/20/20 weighted final grade.
 * When no modality data exists (quiz-only), pass videoCov = 0, readingCov = 0
 * and the weight collapses to quiz-only (0.60 / 0.60 = 1.0 effective).
 * Caller should pass videoCov/readingCov as 0–1 coverage fractions.
 */
export function computeWeightedFinalGrade(
  quizGrade: number,
  videoCov: number,
  readingCov: number,
): number {
  return 0.6 * quizGrade + 0.2 * videoCov + 0.2 * readingCov;
}

/**
 * Retention Gap = Base Mastery − Decayed (current) Mastery.
 * Positive value means the student has forgotten since their peak.
 * Returns 0 when base is not available.
 */
export function computeRetentionGap(
  baseMastery: number | undefined,
  decayedMastery: number,
): number {
  if (baseMastery === undefined) return 0;
  return Math.max(0, baseMastery - decayedMastery);
}

/**
 * Build the set of skill IDs (= skill indices) that the student has actually attempted.
 * A skill counts as "attempted" when its skill_id appears in the timeline.
 */
export function buildAttemptedSkillIds(
  timeline: TimelineEntry[],
  skills?: SkillInfo[],
  conceptStats?: Map<number | string, ConceptStat>,
): Set<number> {
  const ids = new Set<number>();
  for (const e of timeline) {
    if (e.skill_id >= 0) ids.add(e.skill_id);
  }
  if (skills && conceptStats) {
    for (const skill of skills) {
      if (ids.has(skill.id)) continue;
      for (const c of skill.concepts ?? []) {
        if (conceptStats.has(c.id) || conceptStats.has(getConceptLookupKey(c))) {
          ids.add(skill.id);
          break;
        }
      }
    }
  }
  return ids;
}

/**
 * Skill mastery from the mastery vector.
 * skillIds are skill indices (= skill.id values).
 * Unstarted skills contribute 0 to the numerator.
 */
export function skillMasteryFromFinal(
  skillIds: number[],
  finalMastery: number[],
  attemptedSkillIds: Set<number>,
): number {
  if (skillIds.length === 0) return 0;
  const sum = skillIds.reduce((acc, id) => {
    if (!attemptedSkillIds.has(id)) return acc;
    return acc + (id >= 0 && id < finalMastery.length ? finalMastery[id] : 0);
  }, 0);
  return sum / skillIds.length;
}

// Backward-compat aliases.
export const getCourseraDomainGrade = getCourseraChapterGrade;
export const chapterMasteryFromFinal = skillMasteryFromFinal;
export const domainMasteryFromFinal = skillMasteryFromFinal;
