import { describe, expect, it } from 'vitest';

import {
  parseScores,
  reclassify,
  DEFAULT_NOVEL_THRESHOLD,
  DEFAULT_COVERED_THRESHOLD,
  DEFAULT_RECOMMENDATION_WEIGHTS,
  DEFAULT_WEIGHTS,
} from '../types';

// ── parseScores ────────────────────────────────────────────────

describe('parseScores', () => {
  it('returns null for null input', () => {
    expect(parseScores(null)).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseScores('')).toBeNull();
  });

  it('returns null for invalid JSON', () => {
    expect(parseScores('not json')).toBeNull();
  });

  it('returns null when C_topic is missing', () => {
    expect(parseScores(JSON.stringify({ C_struc: 5 }))).toBeNull();
  });

  it('returns null when C_topic is not a number', () => {
    expect(parseScores(JSON.stringify({ C_topic: 'high' }))).toBeNull();
  });

  it('parses valid scores JSON', () => {
    const scores = {
      C_topic: 8,
      C_topic_rationale: 'Good coverage',
      C_struc: 7,
      C_struc_rationale: 'Well structured',
      C_scope: 6,
      C_scope_rationale: 'Appropriate level',
      C_pub: 8,
      C_pub_rationale: 'Reputable publisher',
      C_auth: 7,
      C_auth_rationale: 'Expert author',
      C_time: 9,
      C_time_rationale: 'Recent edition',
      C_prac: 6,
      C_prac_rationale: 'Good exercises',
      S_final: 7.5,
      S_final_with_prac: 7.2,
    };
    const result = parseScores(JSON.stringify(scores));
    expect(result).not.toBeNull();
    expect(result!.C_topic).toBe(8);
    expect(result!.S_final).toBe(7.5);
  });
});

// ── reclassify ─────────────────────────────────────────────────

describe('reclassify', () => {
  const items = [
    { name: 'A', sim_max: 0.1 },
    { name: 'B', sim_max: 0.4 },
    { name: 'C', sim_max: 0.7 },
    { name: 'D', sim_max: 0.55 },
  ];

  it('classifies items into tiers', () => {
    const result = reclassify(items, 0.35, 0.55);
    expect(result[0].tier).toBe('novel');     // 0.1 < 0.35
    expect(result[1].tier).toBe('overlap');   // 0.4 >= 0.35 && < 0.55
    expect(result[2].tier).toBe('covered');   // 0.7 >= 0.55
    expect(result[3].tier).toBe('covered');   // 0.55 >= 0.55
  });

  it('preserves original properties', () => {
    const result = reclassify(items, 0.35, 0.55);
    expect(result[0].name).toBe('A');
    expect(result[0].sim_max).toBe(0.1);
  });

  it('returns empty array for empty input', () => {
    expect(reclassify([], 0.35, 0.55)).toEqual([]);
  });

  it('all novel when covered threshold is very high', () => {
    const result = reclassify(items, 0.99, 1.0);
    for (const item of result) {
      expect(item.tier).toBe('novel');
    }
  });

  it('all covered when novel threshold is very low', () => {
    const result = reclassify(items, 0.0, 0.0);
    for (const item of result) {
      expect(item.tier).toBe('covered');
    }
  });
});

// ── Default constants ──────────────────────────────────────────

describe('default constants', () => {
  it('DEFAULT_NOVEL_THRESHOLD is 0.35', () => {
    expect(DEFAULT_NOVEL_THRESHOLD).toBe(0.35);
  });

  it('DEFAULT_COVERED_THRESHOLD is 0.55', () => {
    expect(DEFAULT_COVERED_THRESHOLD).toBe(0.55);
  });

  it('DEFAULT_WEIGHTS sums to 1', () => {
    const w = DEFAULT_WEIGHTS;
    const sum = w.C_topic + w.C_struc + w.C_scope + w.C_pub + w.C_auth + w.C_time;
    expect(sum).toBeCloseTo(1.0);
  });

  it('DEFAULT_RECOMMENDATION_WEIGHTS sums to 1', () => {
    const w = DEFAULT_RECOMMENDATION_WEIGHTS;
    const sum =
      w.coverage + w.depth + w.novelty + w.balance +
      w.skillRichness + w.density + w.evidenceDepth +
      w.chapterAlignment + w.relevanceQuality;
    expect(sum).toBeCloseTo(1.0);
  });
});
