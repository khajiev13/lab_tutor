/**
 * Tests for TeacherDataContext, DataContext, and TwinContext.
 *
 * Strategy:
 *  - Module-mock the API functions so no real fetch calls happen.
 *  - Render a small helper component that reads from the context.
 *  - Assert the context values/state transitions.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ── TeacherDataContext ─────────────────────────────────────────────────────

vi.mock('@/features/arcd-agent/api/teacher-twin', () => ({
  fetchSkillDifficulty: vi.fn(),
  fetchSkillPopularity: vi.fn(),
  fetchClassMastery: vi.fn(),
  fetchStudentGroups: vi.fn(),
}));

import {
  TeacherDataProvider,
  useTeacherData,
} from './TeacherDataContext';
import {
  fetchSkillDifficulty,
  fetchSkillPopularity,
  fetchClassMastery,
  fetchStudentGroups,
} from '@/features/arcd-agent/api/teacher-twin';

const mockDiff = { course_id: 1, skills: [], total_skills: 0 };
const mockPop = {
  course_id: 1,
  all_skills: [],
  most_popular: [],
  least_popular: [],
  total_students: 0,
};
const mockMastery = {
  course_id: 1,
  students: [],
  class_avg_mastery: 0,
  at_risk_count: 0,
  total_students: 0,
};
const mockGroups = {
  course_id: 1,
  groups: [],
  ungrouped_students: [],
  total_groups: 0,
};

function TeacherConsumer() {
  const ctx = useTeacherData();
  if (ctx.loading) return <div data-testid="loading">loading</div>;
  if (ctx.error) return <div data-testid="error">{ctx.error}</div>;
  return (
    <div>
      <div data-testid="course-id">{ctx.courseId}</div>
      <div data-testid="skills-count">{ctx.skillDifficulty?.total_skills ?? -1}</div>
    </div>
  );
}

describe('TeacherDataContext', () => {
  beforeEach(() => {
    vi.mocked(fetchSkillDifficulty).mockResolvedValue(mockDiff);
    vi.mocked(fetchSkillPopularity).mockResolvedValue(mockPop);
    vi.mocked(fetchClassMastery).mockResolvedValue(mockMastery);
    vi.mocked(fetchStudentGroups).mockResolvedValue(mockGroups);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders children and populates skill difficulty', async () => {
    render(
      <TeacherDataProvider courseId="1">
        <TeacherConsumer />
      </TeacherDataProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('skills-count').textContent).toBe('0');
    });
  });

  it('shows error state for courseId=0', async () => {
    render(
      <TeacherDataProvider courseId="0">
        <TeacherConsumer />
      </TeacherDataProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('error')).toBeTruthy();
    });
  });

  it('calls all four API functions on mount', async () => {
    render(
      <TeacherDataProvider courseId="3">
        <TeacherConsumer />
      </TeacherDataProvider>,
    );
    await waitFor(() => {
      expect(fetchSkillDifficulty).toHaveBeenCalledWith(3);
      expect(fetchSkillPopularity).toHaveBeenCalledWith(3);
      expect(fetchClassMastery).toHaveBeenCalledWith(3);
      expect(fetchStudentGroups).toHaveBeenCalledWith(3);
    });
  });

  it('throws when used outside provider', () => {
    // Suppress the expected error boundary console.error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<TeacherConsumer />)).toThrow();
    spy.mockRestore();
  });
});

// ── DataContext ────────────────────────────────────────────────────────────

vi.mock('@/features/arcd-agent/context/DataContext', async (importOriginal) => {
  const mod = await importOriginal<typeof import('./DataContext')>();
  return mod;
});

import { DataProvider, useData } from './DataContext';
import { mockFetch } from '@/test/fetchMock';

function DataConsumer() {
  const ctx = useData();
  if (ctx.loading) return <div data-testid="data-loading">loading</div>;
  if (ctx.error) return <div data-testid="data-error">{ctx.error}</div>;
  return (
    <div>
      <div data-testid="portfolio-datasets">
        {ctx.portfolioData?.datasets?.length ?? -1}
      </div>
    </div>
  );
}

describe('DataContext', () => {
  afterEach(() => {
    // clearAllMocks resets call history but does NOT remove the localStorage
    // stub installed by setup.ts — unlike unstubAllGlobals which would.
    vi.clearAllMocks();
  });

  it('fetches portfolio on mount and populates datasets', async () => {
    const payload = {
      generated_at: '2026-01-01T00:00:00',
      datasets: [
        { id: 'course', name: 'Course', model_info: {}, skills: [], students: [] },
      ],
    };
    mockFetch({ json: payload });
    render(
      <DataProvider courseId="1">
        <DataConsumer />
      </DataProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('portfolio-datasets').textContent).toBe('1');
    });
  });

  it('shows error state when fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('Network error')),
    );
    render(
      <DataProvider courseId="1">
        <DataConsumer />
      </DataProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('data-error')).toBeTruthy();
    });
  });
});

// ── TwinContext ────────────────────────────────────────────────────────────

import { TwinProvider, useTwin } from './TwinContext';

function TwinConsumer() {
  const ctx = useTwin();
  if (ctx.twinLoading) return <div data-testid="twin-loading">loading</div>;
  return (
    <div>
      <div data-testid="twin-source">{ctx.twinSource ?? 'none'}</div>
      <div data-testid="twin-error">{ctx.twinError ?? ''}</div>
      <div data-testid="twin-matched">{ctx.twinMatched ? 'yes' : 'no'}</div>
    </div>
  );
}

describe('TwinContext', () => {
  afterEach(() => {
    // clearAllMocks resets call history but does NOT remove the localStorage
    // stub installed by setup.ts — unlike unstubAllGlobals which would.
    vi.clearAllMocks();
  });

  it('provides default null state when no uid given', async () => {
    render(
      <TwinProvider selectedUid="" dataVersion={0}>
        <TwinConsumer />
      </TwinProvider>,
    );
    // No uid → should not fetch, source is none
    await waitFor(() => {
      expect(screen.getByTestId('twin-source').textContent).toBe('none');
    });
  });

  it('provides twin data after successful fetch', async () => {
    const payload = {
      student_id: 'u-1',
      generated_at: '2026-01-01T00:00:00Z',
      dataset: 'course-1',
      current_twin: {
        skill_mastery: [],
        trajectory: [],
        learning_velocity: 0,
        risk_level: 'low',
        recommendations: [],
      },
      snapshot_history: [],
      risk_forecast: {},
      scenario_comparison: {},
      twin_confidence: {},
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(payload),
      }),
    );
    render(
      <TwinProvider selectedUid="u-1" dataVersion={0} courseId="1">
        <TwinConsumer />
      </TwinProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('twin-source').textContent).toBe('api');
    });
  });

  it('sets twinError when fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: () => Promise.resolve('Service unavailable'),
      }),
    );
    render(
      <TwinProvider selectedUid="u-1" dataVersion={0} courseId="1">
        <TwinConsumer />
      </TwinProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('twin-error').textContent).not.toBe('');
    });
  });

  it('checkReplan returns false for no large deviations', () => {
    let capturedCtx: ReturnType<typeof useTwin> | null = null;
    function Extractor() {
      // eslint-disable-next-line react-hooks/rules-of-hooks
      const twinCtx = useTwin();
      capturedCtx = twinCtx;
      return null;
    }
    render(
      <TwinProvider selectedUid="" dataVersion={0}>
        <Extractor />
      </TwinProvider>,
    );
    expect(capturedCtx!.checkReplan([{ delta: 0.01 }])).toBe(false);
  });
});
