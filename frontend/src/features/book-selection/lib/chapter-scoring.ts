/**
 * Pure scoring functions for chapter-level book recommendation.
 *
 * No React, no side effects — purely computational.
 * All functions operate on data from ChapterAnalysisSummary.
 */

import type {
  ChapterAnalysisSummary,
  ChapterUniqueConceptItem,
  ConceptCoverageItem,
  BookRecommendationScore,
  RecommendationFactors,
  RecommendationWeights,
} from '../types';

// ── Individual factor computations ─────────────────────────────

/**
 * Coverage: ratio of course concepts with sim_max ≥ threshold.
 * "How much of MY course does this book cover?"
 */
export function computeCoverage(
  courseCoverage: ConceptCoverageItem[],
  coveredThreshold: number,
): number {
  if (courseCoverage.length === 0) return 0;
  let covered = 0;
  for (let i = 0; i < courseCoverage.length; i++) {
    if (courseCoverage[i].sim_max >= coveredThreshold) covered++;
  }
  return covered / courseCoverage.length;
}

/**
 * Depth: mean sim_max for concepts above a minimum threshold.
 * "When the book covers a concept, how deeply?"
 */
export function computeDepth(
  courseCoverage: ConceptCoverageItem[],
  minThreshold: number,
): number {
  let sum = 0;
  let count = 0;
  for (let i = 0; i < courseCoverage.length; i++) {
    if (courseCoverage[i].sim_max >= minThreshold) {
      sum += courseCoverage[i].sim_max;
      count++;
    }
  }
  return count > 0 ? sum / count : 0;
}

/**
 * Novelty: ratio of core book concepts with sim_max < threshold.
 * "How much NEW knowledge does this book introduce?"
 */
export function computeNovelty(
  bookUniqueConcepts: ChapterUniqueConceptItem[],
  novelThreshold: number,
): number {
  const core = bookUniqueConcepts;
  if (core.length === 0) return 0;
  let novel = 0;
  for (let i = 0; i < core.length; i++) {
    if (core[i].sim_max < novelThreshold) novel++;
  }
  return novel / core.length;
}

/**
 * Topic Balance: 1 - coefficient_of_variation(topic_scores).
 * "Does this book cover course topics evenly?"
 */
export function computeTopicBalance(
  topicScores: Record<string, number>,
): number {
  const values = Object.values(topicScores);
  if (values.length <= 1) return 1;

  let sum = 0;
  for (let i = 0; i < values.length; i++) sum += values[i];
  const mean = sum / values.length;
  if (mean === 0) return 0;

  let sqDiffSum = 0;
  for (let i = 0; i < values.length; i++) {
    sqDiffSum += (values[i] - mean) ** 2;
  }
  const std = Math.sqrt(sqDiffSum / values.length);
  const cv = std / mean;

  return Math.max(0, Math.min(1, 1 - cv));
}

/**
 * Skill Richness: ratio of chapters with ≥2 concept-linked skills.
 * "Does this book produce practical, actionable skills?"
 */
export function computeSkillRichness(
  summary: ChapterAnalysisSummary,
): number {
  const chapters = summary.chapter_details;
  if (chapters.length === 0) return 0;
  let rich = 0;
  for (let i = 0; i < chapters.length; i++) {
    const linkedSkills = chapters[i].skills.filter(
      (s) => s.concepts.length >= 2,
    );
    if (linkedSkills.length > 0) rich++;
  }
  return rich / chapters.length;
}

/**
 * Concept Density: mean core concepts per chapter, normalized 0-1.
 * Pass maxDensity from the highest-density book across all summaries.
 */
export function computeConceptDensity(
  summary: ChapterAnalysisSummary,
  maxDensity: number,
): number {
  const chapters = summary.chapter_details;
  if (chapters.length === 0 || maxDensity === 0) return 0;
  let totalCore = 0;
  for (let i = 0; i < chapters.length; i++) totalCore += chapters[i].concept_count;
  const mean = totalCore / chapters.length;
  return Math.min(1, mean / maxDensity);
}

/**
 * Evidence Depth: mean evidence_embedding similarity for concepts above threshold.
 * Strategy ②: deeper semantic match via actual text quotes.
 */
export function computeEvidenceDepth(
  courseCoverage: ConceptCoverageItem[],
  minThreshold: number,
): number {
  let sum = 0;
  let count = 0;
  for (let i = 0; i < courseCoverage.length; i++) {
    if (courseCoverage[i].sim_max >= minThreshold) {
      sum += courseCoverage[i].sim_evidence ?? courseCoverage[i].sim_max;
      count++;
    }
  }
  return count > 0 ? sum / count : 0;
}

/**
 * Chapter-Lecture Alignment: how well book chapters map to course lectures.
 * Strategy ③: pre-computed on backend as s_chapter_lecture.
 */
export function computeChapterAlignment(
  summary: ChapterAnalysisSummary,
): number {
  return summary.s_chapter_lecture ?? 0;
}

/**
 * Relevance Quality: ratio of covered concepts matched to core book concepts
 * vs supplementary, weighted by relevance. Strategy ⑤.
 */
export function computeRelevanceQuality(
  courseCoverage: ConceptCoverageItem[],
  coveredThreshold: number,
): number {
  const covered = courseCoverage.filter((c) => c.sim_max >= coveredThreshold);
  if (covered.length === 0) return 0;
  let coreMatches = 0;
  for (const c of covered) {
    if (c.matched_relevance === 'core') coreMatches++;
  }
  return coreMatches / covered.length;
}

// ── Composite scoring ──────────────────────────────────────────

/** Compute all 9 factors for one book summary. */
export function computeFactors(
  summary: ChapterAnalysisSummary,
  coveredThreshold: number,
  novelThreshold: number,
  maxDensity: number,
): RecommendationFactors {
  return {
    coverage: computeCoverage(summary.course_coverage, coveredThreshold),
    depth: computeDepth(summary.course_coverage, novelThreshold),
    novelty: computeNovelty(summary.book_unique_concepts, novelThreshold),
    balance: computeTopicBalance(summary.topic_scores),
    skillRichness: computeSkillRichness(summary),
    density: computeConceptDensity(summary, maxDensity),
    evidenceDepth: computeEvidenceDepth(summary.course_coverage, novelThreshold),
    chapterAlignment: computeChapterAlignment(summary),
    relevanceQuality: computeRelevanceQuality(summary.course_coverage, coveredThreshold),
  };
}

/** Weighted composite score from factors and weights. */
export function computeComposite(
  factors: RecommendationFactors,
  weights: RecommendationWeights,
): number {
  return (
    factors.coverage * weights.coverage +
    factors.depth * weights.depth +
    factors.novelty * weights.novelty +
    factors.balance * weights.balance +
    factors.skillRichness * weights.skillRichness +
    factors.density * weights.density +
    factors.evidenceDepth * weights.evidenceDepth +
    factors.chapterAlignment * weights.chapterAlignment +
    factors.relevanceQuality * weights.relevanceQuality
  );
}

/** Compute max average core concepts per chapter across all summaries. */
function computeMaxDensity(summaries: ChapterAnalysisSummary[]): number {
  let max = 0;
  for (const s of summaries) {
    if (s.chapter_details.length === 0) continue;
    let totalCore = 0;
    for (const ch of s.chapter_details) totalCore += ch.concept_count;
    const mean = totalCore / s.chapter_details.length;
    if (mean > max) max = mean;
  }
  return max || 1;
}

/**
 * Rank all books by composite score.
 * Returns sorted BookRecommendationScore[] (highest first).
 */
export function rankBooks(
  summaries: ChapterAnalysisSummary[],
  weights: RecommendationWeights,
  coveredThreshold: number,
  novelThreshold: number,
): BookRecommendationScore[] {
  const maxDensity = computeMaxDensity(summaries);

  const scores: BookRecommendationScore[] = summaries.map((s) => {
    const factors = computeFactors(s, coveredThreshold, novelThreshold, maxDensity);
    return {
      bookId: s.selected_book_id,
      bookTitle: s.book_title,
      factors,
      composite: computeComposite(factors, weights),
    };
  });

  scores.sort((a, b) => b.composite - a.composite);
  return scores;
}
