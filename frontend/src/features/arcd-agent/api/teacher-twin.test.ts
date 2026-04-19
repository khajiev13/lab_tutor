/**
 * Tests for src/features/arcd-agent/api/teacher-twin.ts
 *
 * All exported API functions are covered:
 *  - fetchSkillDifficulty
 *  - fetchSkillPopularity
 *  - fetchClassMastery
 *  - fetchStudentGroups
 *  - runWhatIf
 *  - simulateSkill
 *  - simulateSkills
 *  - fetchStudentPortfolio / fetchStudentPortfolioForTeacher
 *  - fetchStudentTwin / fetchStudentTwinForTeacher
 */

import { describe, it, expect, afterEach, vi } from 'vitest';

import {
  fetchSkillDifficulty,
  fetchSkillPopularity,
  fetchClassMastery,
  fetchStudentGroups,
  runWhatIf,
  simulateSkill,
  simulateSkills,
  fetchStudentPortfolio,
  fetchStudentTwin,
  fetchStudentPortfolioForTeacher,
  fetchStudentTwinForTeacher,
} from '../api/teacher-twin';
import { mockFetch, mockFetchError, mockFetchHttpError } from '../../../test/fetchMock';

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── fetchSkillDifficulty ────────────────────────────────────────────────────

describe('fetchSkillDifficulty', () => {
  it('resolves with server response', async () => {
    const payload = { course_id: 1, skills: [], total_skills: 0 };
    mockFetch({ json: payload });
    const result = await fetchSkillDifficulty(1);
    expect(result).toEqual(payload);
  });

  it('calls the correct URL', async () => {
    mockFetch({ json: {} });
    await fetchSkillDifficulty(42).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/42/skill-difficulty');
  });

  it('throws on HTTP error', async () => {
    mockFetchHttpError(401, 'Unauthorized');
    await expect(fetchSkillDifficulty(1)).rejects.toThrow('HTTP 401');
  });

  it('throws on network error', async () => {
    mockFetchError('Network error');
    await expect(fetchSkillDifficulty(1)).rejects.toThrow('Network error');
  });
});

// ── fetchSkillPopularity ────────────────────────────────────────────────────

describe('fetchSkillPopularity', () => {
  it('resolves with server response', async () => {
    const payload = {
      course_id: 1,
      all_skills: [],
      most_popular: [],
      least_popular: [],
      total_students: 0,
    };
    mockFetch({ json: payload });
    const result = await fetchSkillPopularity(1);
    expect(result.course_id).toBe(1);
  });

  it('calls the correct URL', async () => {
    mockFetch({ json: {} });
    await fetchSkillPopularity(7).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/7/skill-popularity');
  });
});

// ── fetchClassMastery ───────────────────────────────────────────────────────

describe('fetchClassMastery', () => {
  it('resolves with server response', async () => {
    const payload = {
      course_id: 2,
      students: [],
      class_avg_mastery: 0,
      at_risk_count: 0,
      total_students: 0,
    };
    mockFetch({ json: payload });
    const result = await fetchClassMastery(2);
    expect(result.total_students).toBe(0);
  });

  it('calls the correct URL', async () => {
    mockFetch({ json: {} });
    await fetchClassMastery(5).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/5/class-mastery');
  });
});

// ── fetchStudentGroups ──────────────────────────────────────────────────────

describe('fetchStudentGroups', () => {
  it('resolves with server response', async () => {
    const payload = {
      course_id: 3,
      groups: [],
      ungrouped_students: [],
      total_groups: 0,
    };
    mockFetch({ json: payload });
    const result = await fetchStudentGroups(3);
    expect(result.total_groups).toBe(0);
  });
});

// ── runWhatIf ──────────────────────────────────────────────────────────────

describe('runWhatIf', () => {
  it('sends POST with body and resolves', async () => {
    const payload = {
      mode: 'automatic',
      course_id: 1,
      simulated_path: [],
      pco_analysis: [],
      recommendations: [],
      skill_impacts: [],
      summary: 'ok',
      llm_recommendation: null,
    };
    mockFetch({ json: payload });
    const result = await runWhatIf(1, { mode: 'automatic', delta: 0.2 });
    expect(result.mode).toBe('automatic');
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
  });
});

// ── simulateSkill ──────────────────────────────────────────────────────────

describe('simulateSkill', () => {
  it('sends POST to correct URL', async () => {
    const payload = {
      skill_name: 'algebra',
      simulated_mastery: 0.5,
      perceived_difficulty: 0.5,
      avg_class_mastery: 0.5,
      student_count: 5,
      question: 'Solve for x',
      options: ['1', '2', '3', '4'],
      correct_index: 0,
      explanation: 'x=1',
    };
    mockFetch({ json: payload });
    const result = await simulateSkill(1, { skill_name: 'algebra' });
    expect(result.skill_name).toBe('algebra');
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/simulate-skill');
  });
});

// ── simulateSkills ─────────────────────────────────────────────────────────

describe('simulateSkills', () => {
  it('sends POST to correct URL', async () => {
    const payload = {
      mode: 'manual',
      course_id: 1,
      auto_selected_skills: [],
      skill_results: [],
      coherence: {
        overall_score: 0,
        label: 'Low',
        pairs: [],
        teaching_order: [],
        clusters: [],
        common_students: 0,
      },
      llm_insights: null,
    };
    mockFetch({ json: payload });
    const result = await simulateSkills(1, { skills: [{ skill_name: 'algebra' }] });
    expect(result.mode).toBe('manual');
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/simulate-skills');
  });
});

// ── fetchStudentPortfolio / fetchStudentTwin ────────────────────────────────

describe('fetchStudentPortfolio', () => {
  it('calls correct URL', async () => {
    mockFetch({ json: {} });
    await fetchStudentPortfolio(1, 10).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/student/10/portfolio');
  });
});

describe('fetchStudentTwin', () => {
  it('calls correct URL', async () => {
    mockFetch({ json: {} });
    await fetchStudentTwin(1, 10).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/student/10/twin');
  });
});

describe('fetchStudentPortfolioForTeacher', () => {
  it('calls correct URL', async () => {
    mockFetch({ json: {} });
    await fetchStudentPortfolioForTeacher(1, 10).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/student/10/portfolio');
  });
});

describe('fetchStudentTwinForTeacher', () => {
  it('calls correct URL', async () => {
    mockFetch({ json: {} });
    await fetchStudentTwinForTeacher(1, 10).catch(() => {});
    const callUrl = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(callUrl).toContain('/teacher-twin/1/student/10/twin');
  });
});

// ── Auth header injection ──────────────────────────────────────────────────

describe('authHeaders', () => {
  it('includes Authorization header when token present', async () => {
    localStorage.setItem('access_token', 'test-token');
    mockFetch({ json: {} });
    await fetchSkillDifficulty(1).catch(() => {});
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const headers = fetchMock.mock.calls[0][1]?.headers ?? {};
    expect(JSON.stringify(headers)).toContain('test-token');
    localStorage.removeItem('access_token');
  });

  it('omits Authorization header when no token', async () => {
    localStorage.removeItem('access_token');
    mockFetch({ json: {} });
    await fetchSkillDifficulty(1).catch(() => {});
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>;
    const headers = fetchMock.mock.calls[0][1]?.headers ?? {};
    expect(JSON.stringify(headers)).not.toContain('Bearer');
  });
});
