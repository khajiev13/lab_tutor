import { describe, expect, it } from 'vitest';

import {
  computeCoverage,
  computeDepth,
  computeNovelty,
  computeTopicBalance,
  computeSkillRichness,
  computeConceptDensity,
  computeFactors,
  computeComposite,
  rankBooks,
} from './chapter-scoring';

import type {
  ChapterAnalysisSummary,
  ConceptCoverageItem,
  ChapterUniqueConceptItem,
  RecommendationWeights,
  RecommendationFactors,
} from '../types';

// ── Test fixtures ──────────────────────────────────────────────

function makeCoverage(simValues: number[]): ConceptCoverageItem[] {
  return simValues.map((sim, i) => ({
    concept_name: `Concept ${i}`,
    doc_topic: `Topic ${i % 3}`,
    sim_max: sim,
    sim_evidence: sim,
    sim_weighted: sim,
    matched_relevance: 'core',
    best_match: `Match ${i}`,
    course_text_evidence: null,
    book_text_evidence: null,
    book_chapter_title: null,
    book_section_title: null,
  }));
}

function makeUniqueConcepts(
  entries: { sim: number; relevance: 'core' | 'supplementary' | 'tangential' }[],
): ChapterUniqueConceptItem[] {
  return entries.map((e, i) => ({
    name: `BookConcept ${i}`,
    description: 'desc',
    skill_name: 'Mock Skill',
    chapter_title: 'Ch 1',
    section_title: 'Sec 1',
    sim_max: e.sim,
    best_course_match: 'Match',
  }));
}

function makeSummary(
  overrides: Partial<ChapterAnalysisSummary> = {},
): ChapterAnalysisSummary {
  return {
    id: 1,
    run_id: 1,
    selected_book_id: 1,
    book_title: 'Test Book',
    total_core_concepts: 3,
    total_supplementary_concepts: 2,
    total_skills: 1,
    total_chapters: 2,
    s_final_name: 0.7,
    s_final_evidence: 0.7,
    s_final_weighted: 0.7,
    s_chapter_lecture: 0.5,
    novel_count_default: 1,
    overlap_count_default: 1,
    covered_count_default: 1,
    chapter_details: [
      {
        chapter_title: 'Ch 1',
        chapter_index: 0,
        chapter_summary: 'Summary',
        concept_count: 3,
        skill_count: 1,
        skills: [
          { name: 'SQL', description: 'Write SQL', concepts: [{ name: 'A', description: '', sim_max: 0.8, best_course_match: 'A' }, { name: 'B', description: '', sim_max: 0.8, best_course_match: 'B' }] },
        ],
      },
      {
        chapter_title: 'Ch 2',
        chapter_index: 1,
        chapter_summary: null,
        concept_count: 2,
        skill_count: 0,
        skills: [],
      },
    ],
    course_coverage: makeCoverage([0.9, 0.6, 0.3]),
    book_unique_concepts: makeUniqueConcepts([
      { sim: 0.2, relevance: 'core' },
      { sim: 0.7, relevance: 'core' },
      { sim: 0.1, relevance: 'supplementary' },
    ]),
    topic_scores: { 'Topic 0': 0.9, 'Topic 1': 0.6, 'Topic 2': 0.3 },
    sim_distribution: [{ bucket_start: 0, bucket_end: 0.1, count: 1 }],
    created_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

const DEFAULT_WEIGHTS: RecommendationWeights = {
  coverage: 0.3,
  depth: 0.2,
  novelty: 0.15,
  balance: 0.15,
  skillRichness: 0.1,
  density: 0.1,
  evidenceDepth: 0,
  chapterAlignment: 0,
  relevanceQuality: 0,
};

// ── computeCoverage ────────────────────────────────────────────

describe('computeCoverage', () => {
  it('returns 0 for empty list', () => {
    expect(computeCoverage([], 0.55)).toBe(0);
  });

  it('returns 1 when all concepts are covered', () => {
    const coverage = makeCoverage([0.9, 0.8, 0.7]);
    expect(computeCoverage(coverage, 0.55)).toBe(1);
  });

  it('returns 0 when no concepts are covered', () => {
    const coverage = makeCoverage([0.1, 0.2, 0.3]);
    expect(computeCoverage(coverage, 0.55)).toBe(0);
  });

  it('returns correct ratio for mixed values', () => {
    const coverage = makeCoverage([0.9, 0.6, 0.3]);
    // 2 of 3 >= 0.55
    expect(computeCoverage(coverage, 0.55)).toBeCloseTo(2 / 3);
  });

  it('threshold adjustment changes result', () => {
    const coverage = makeCoverage([0.5, 0.5, 0.5]);
    expect(computeCoverage(coverage, 0.6)).toBe(0);
    expect(computeCoverage(coverage, 0.4)).toBe(1);
  });
});

// ── computeDepth ───────────────────────────────────────────────

describe('computeDepth', () => {
  it('returns 0 for empty list', () => {
    expect(computeDepth([], 0.3)).toBe(0);
  });

  it('computes mean of values above threshold', () => {
    const coverage = makeCoverage([0.9, 0.8, 0.2, 0.1]);
    // Only 0.9 and 0.8 are >= 0.5 → mean = 0.85
    expect(computeDepth(coverage, 0.5)).toBeCloseTo(0.85);
  });

  it('returns 0 when nothing above threshold', () => {
    const coverage = makeCoverage([0.1, 0.2]);
    expect(computeDepth(coverage, 0.5)).toBe(0);
  });
});

// ── computeNovelty ─────────────────────────────────────────────

describe('computeNovelty', () => {
  it('returns 0 for empty list', () => {
    expect(computeNovelty([], 0.35)).toBe(0);
  });

  it('returns correct ratio for mixed similarities', () => {
    const concepts = makeUniqueConcepts([
      { sim: 0.1, relevance: 'core' },
      { sim: 0.9, relevance: 'supplementary' },
      { sim: 0.1, relevance: 'tangential' },
    ]);
    // 2 out of 3 concepts have sim < 0.35
    expect(computeNovelty(concepts, 0.35)).toBeCloseTo(2 / 3);
  });

  it('returns correct ratio for all items', () => {
    const concepts = makeUniqueConcepts([
      { sim: 0.1, relevance: 'core' },
      { sim: 0.7, relevance: 'core' },
      { sim: 0.2, relevance: 'core' },
    ]);
    // 2 of 3 concepts have sim < 0.35
    expect(computeNovelty(concepts, 0.35)).toBeCloseTo(2 / 3);
  });
});

// ── computeTopicBalance ────────────────────────────────────────

describe('computeTopicBalance', () => {
  it('returns 1 when all topics are equal', () => {
    expect(computeTopicBalance({ A: 0.5, B: 0.5, C: 0.5 })).toBe(1);
  });

  it('returns 1 for single topic', () => {
    expect(computeTopicBalance({ A: 0.5 })).toBe(1);
  });

  it('returns value between 0 and 1 for varied topics', () => {
    const result = computeTopicBalance({ A: 0.9, B: 0.1 });
    expect(result).toBeGreaterThan(0);
    expect(result).toBeLessThan(1);
  });

  it('returns 0 when mean is 0', () => {
    expect(computeTopicBalance({ A: 0, B: 0 })).toBe(0);
  });
});

// ── computeSkillRichness ───────────────────────────────────────

describe('computeSkillRichness', () => {
  it('returns 0 for no chapters', () => {
    const s = makeSummary({ chapter_details: [] });
    expect(computeSkillRichness(s)).toBe(0);
  });

  it('counts chapters with skills that have ≥2 linked concepts', () => {
    const s = makeSummary();
    // Ch 1 has 1 skill with 2 concept_names → rich; Ch 2 has 0 skills → not rich
    expect(computeSkillRichness(s)).toBeCloseTo(0.5);
  });

  it('returns 1 when all chapters have rich skills', () => {
    const s = makeSummary({
      chapter_details: [
        {
          chapter_title: 'Ch 1',
          chapter_index: 0,
          chapter_summary: null,
          concept_count: 2,
          skill_count: 1,
          skills: [
            { name: 'S1', description: 'd', concepts: [{ name: 'A', description: '', sim_max: 0.8, best_course_match: 'A' }, { name: 'B', description: '', sim_max: 0.8, best_course_match: 'B' }] },
          ],
        },
      ],
    });
    expect(computeSkillRichness(s)).toBe(1);
  });
});

// ── computeConceptDensity ──────────────────────────────────────

describe('computeConceptDensity', () => {
  it('returns 0 for no chapters', () => {
    const s = makeSummary({ chapter_details: [] });
    expect(computeConceptDensity(s, 5)).toBe(0);
  });

  it('returns 0 when maxDensity is 0', () => {
    const s = makeSummary();
    expect(computeConceptDensity(s, 0)).toBe(0);
  });

  it('returns correct normalized density', () => {
    const s = makeSummary();
    // Ch 1: concept_count=3, Ch 2: concept_count=2 → mean=2.5
    // maxDensity=3 → 2.5/3 = 0.833333333
    expect(computeConceptDensity(s, 3)).toBeCloseTo(2.5 / 3);
  });

  it('caps at 1', () => {
    const s = makeSummary();
    // mean=1.5, maxDensity=1 → min(1, 1.5) = 1
    expect(computeConceptDensity(s, 1)).toBe(1);
  });
});

// ── computeComposite ───────────────────────────────────────────

describe('computeComposite', () => {
  it('computes weighted sum correctly', () => {
    const factors: RecommendationFactors = {
      coverage: 1,
      depth: 1,
      novelty: 1,
      balance: 1,
      skillRichness: 1,
      density: 1,
      evidenceDepth: 1,
      chapterAlignment: 1,
      relevanceQuality: 1,
    };
    const sum =
      DEFAULT_WEIGHTS.coverage +
      DEFAULT_WEIGHTS.depth +
      DEFAULT_WEIGHTS.novelty +
      DEFAULT_WEIGHTS.balance +
      DEFAULT_WEIGHTS.skillRichness +
      DEFAULT_WEIGHTS.density +
      DEFAULT_WEIGHTS.evidenceDepth +
      DEFAULT_WEIGHTS.chapterAlignment +
      DEFAULT_WEIGHTS.relevanceQuality;
    expect(computeComposite(factors, DEFAULT_WEIGHTS)).toBeCloseTo(sum);
  });

  it('returns 0 when all factors are 0', () => {
    const factors: RecommendationFactors = {
      coverage: 0,
      depth: 0,
      novelty: 0,
      balance: 0,
      skillRichness: 0,
      density: 0,
      evidenceDepth: 0,
      chapterAlignment: 0,
      relevanceQuality: 0,
    };
    expect(computeComposite(factors, DEFAULT_WEIGHTS)).toBe(0);
  });
});

// ── computeFactors ─────────────────────────────────────────────

describe('computeFactors', () => {
  it('returns all 6 factors between 0 and 1', () => {
    const s = makeSummary();
    const factors = computeFactors(s, 0.55, 0.35, 3);
    for (const [, value] of Object.entries(factors)) {
      expect(value).toBeGreaterThanOrEqual(0);
      expect(value).toBeLessThanOrEqual(1);
    }
  });
});

// ── rankBooks ──────────────────────────────────────────────────

describe('rankBooks', () => {
  it('returns empty array for no summaries', () => {
    expect(rankBooks([], DEFAULT_WEIGHTS, 0.55, 0.35)).toEqual([]);
  });

  it('returns sorted scores, highest first', () => {
    const s1 = makeSummary({ selected_book_id: 1, book_title: 'Book A' });
    const s2 = makeSummary({
      selected_book_id: 2,
      book_title: 'Book B',
      // Higher coverage → should rank higher
      course_coverage: makeCoverage([0.99, 0.99, 0.99]),
    });

    const scores = rankBooks([s1, s2], DEFAULT_WEIGHTS, 0.55, 0.35);

    expect(scores).toHaveLength(2);
    expect(scores[0].composite).toBeGreaterThanOrEqual(scores[1].composite);
  });

  it('each score has correct structure', () => {
    const s = makeSummary();
    const scores = rankBooks([s], DEFAULT_WEIGHTS, 0.55, 0.35);

    expect(scores).toHaveLength(1);
    expect(scores[0]).toHaveProperty('bookId');
    expect(scores[0]).toHaveProperty('bookTitle');
    expect(scores[0]).toHaveProperty('factors');
    expect(scores[0]).toHaveProperty('composite');
  });

  it('changing weights changes ranking', () => {
    const s1 = makeSummary({
      selected_book_id: 1,
      book_title: 'High Coverage',
      course_coverage: makeCoverage([0.99, 0.99, 0.99]),
      book_unique_concepts: makeUniqueConcepts([
        { sim: 0.9, relevance: 'core' },
      ]),
    });
    const s2 = makeSummary({
      selected_book_id: 2,
      book_title: 'High Novelty',
      course_coverage: makeCoverage([0.3, 0.3, 0.3]),
      book_unique_concepts: makeUniqueConcepts([
        { sim: 0.05, relevance: 'core' },
        { sim: 0.05, relevance: 'core' },
        { sim: 0.05, relevance: 'core' },
      ]),
    });

    // Coverage-heavy weights
    const coverageWeights: RecommendationWeights = {
      coverage: 0.9,
      depth: 0.02,
      novelty: 0.02,
      balance: 0.02,
      skillRichness: 0.02,
      density: 0.02,
      evidenceDepth: 0,
      chapterAlignment: 0,
      relevanceQuality: 0,
    };
    const scoresA = rankBooks([s1, s2], coverageWeights, 0.55, 0.35);
    expect(scoresA[0].bookTitle).toBe('High Coverage');

    // Novelty-heavy weights
    const noveltyWeights: RecommendationWeights = {
      coverage: 0.02,
      depth: 0.02,
      novelty: 0.9,
      balance: 0.02,
      skillRichness: 0.02,
      density: 0.02,
      evidenceDepth: 0,
      chapterAlignment: 0,
      relevanceQuality: 0,
    };
    const scoresB = rankBooks([s1, s2], noveltyWeights, 0.55, 0.35);
    expect(scoresB[0].bookTitle).toBe('High Novelty');
  });
});
