/**
 * Smoke tests for teacher-twin pages.
 *
 * Strategy: mock the context hooks and API functions so pages render
 * without needing real network or store.
 */

import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ── Mock context hooks ─────────────────────────────────────────────────────

const mockTeacherCtx = {
  courseId: 1,
  loading: false,
  error: '',
  skillDifficulty: {
    course_id: 1,
    skills: [
      {
        skill_name: 'algebra',
        student_count: 5,
        avg_mastery: 0.6,
        perceived_difficulty: 0.4,
        prereq_count: 2,
        downstream_count: 3,
        pco_risk_ratio: 0.2,
      },
    ],
    total_skills: 1,
  },
  skillPopularity: {
    course_id: 1,
    all_skills: [],
    most_popular: [],
    least_popular: [],
    total_students: 3,
  },
  classMastery: {
    course_id: 1,
    students: [
      {
        user_id: 10,
        full_name: 'Alice Student',
        email: 'alice@test.com',
        selected_skill_count: 2,
        avg_mastery: 0.7,
        mastered_count: 1,
        struggling_count: 0,
        pco_count: 0,
        at_risk: false,
      },
    ],
    class_avg_mastery: 0.7,
    at_risk_count: 0,
    total_students: 1,
  },
  studentGroups: { course_id: 1, groups: [], ungrouped_students: [], total_groups: 0 },
  lastUpdated: new Date(),
  refresh: vi.fn(),
};

vi.mock('@/features/arcd-agent/context/TeacherDataContext', () => ({
  useTeacherData: () => mockTeacherCtx,
  TeacherDataProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/features/arcd-agent/api/teacher-twin', () => ({
  fetchStudentPortfolio: vi.fn().mockResolvedValue({
    user_id: 10,
    course_id: 1,
    skills: [],
    mastered_count: 0,
    struggling_count: 0,
    in_progress_count: 0,
    overall_mastery: 0,
    learning_path: [],
    next_recommended_skill: null,
  }),
  fetchStudentTwin: vi.fn().mockResolvedValue(null),
  fetchStudentPortfolioForTeacher: vi.fn().mockResolvedValue({}),
  fetchStudentTwinForTeacher: vi.fn().mockResolvedValue({}),
  simulateSkills: vi.fn().mockResolvedValue({}),
  runWhatIf: vi.fn().mockResolvedValue({}),
}));

// Stub recharts to avoid SVG rendering issues in jsdom
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children?: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  BarChart: ({ children }: { children?: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Line: () => null,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  ReferenceLine: () => null,
  Cell: () => null,
  RadarChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Radar: () => null,
  PolarGrid: () => null,
  PolarAngleAxis: () => null,
  PolarRadiusAxis: () => null,
}));

// Stub TwinViewerTab
vi.mock('@/features/arcd-agent/components/twin-viewer-tab', () => ({
  TwinViewerTab: () => <div data-testid="twin-viewer-tab">twin-viewer</div>,
}));

// ── ClassOverviewPage ──────────────────────────────────────────────────────

import ClassOverviewPage from './ClassOverviewPage';

describe('ClassOverviewPage', () => {
  it('renders without crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/overview']}>
        <Routes>
          <Route path="/teacher/:courseId/overview" element={<ClassOverviewPage />} />
        </Routes>
      </MemoryRouter>,
    );
    // Should show some content from the mock data
    await waitFor(() => {
      expect(document.body).toBeTruthy();
    });
  });

  it('shows class average mastery', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/overview']}>
        <Routes>
          <Route path="/teacher/:courseId/overview" element={<ClassOverviewPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      // 70% class avg
      expect(document.body.textContent).toContain('70');
    });
  });
});

// ── ClassRosterPage ────────────────────────────────────────────────────────

import ClassRosterPage from './ClassRosterPage';

describe('ClassRosterPage', () => {
  it('renders without crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/roster']}>
        <Routes>
          <Route path="/teacher/:courseId/roster" element={<ClassRosterPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(document.body).toBeTruthy();
    });
  });

  it('displays student name from mock data', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/roster']}>
        <Routes>
          <Route path="/teacher/:courseId/roster" element={<ClassRosterPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(document.body.textContent).toContain('Alice Student');
    });
  });
});

// ── StudentDrilldownPage ───────────────────────────────────────────────────

import StudentDrilldownPage from './StudentDrilldownPage';

describe('StudentDrilldownPage', () => {
  it('renders without crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/student/10']}>
        <Routes>
          <Route path="/teacher/:courseId/student/:studentId" element={<StudentDrilldownPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(document.body).toBeTruthy();
    });
  });
});

// ── TeacherTwinPage ────────────────────────────────────────────────────────

import TeacherTwinPage from './TeacherTwinPage';
import { runWhatIf, simulateSkills } from '@/features/arcd-agent/api/teacher-twin';
import { resetTeacherTwinSimulationTasks } from '@/features/arcd-agent/state/teacherTwinSimulationStore';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderTeacherTwinPage() {
  return render(
    <MemoryRouter initialEntries={['/teacher/1/twin']}>
      <Routes>
        <Route path="/teacher/:courseId/twin" element={<TeacherTwinPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  resetTeacherTwinSimulationTasks();
  vi.clearAllMocks();
  vi.mocked(simulateSkills).mockResolvedValue({} as never);
  vi.mocked(runWhatIf).mockResolvedValue({} as never);
});

afterEach(() => {
  resetTeacherTwinSimulationTasks();
});

describe('TeacherTwinPage', () => {
  it('renders without crashing', async () => {
    renderTeacherTwinPage();
    await waitFor(() => {
      expect(document.body).toBeTruthy();
    });
  });

  it('labels automatic what-if controls as teacher hints', async () => {
    const user = userEvent.setup();
    vi.mocked(runWhatIf).mockResolvedValue({
      mode: 'automatic',
      course_id: 1,
      simulated_path: ['algebra'],
      pco_analysis: [],
      recommendations: ['Teach algebra toward 78% mastery - broad support'],
      skill_impacts: [],
      summary: 'Automatic what-if finished.',
      llm_recommendation: null,
      automatic_criteria: {
        intervention_intensity: 0.7,
        focus: 'broad_support',
        max_skills: 3,
        llm_decision_summary: 'The LLM used teacher hints and made the final decision.',
      },
    } as never);

    renderTeacherTwinPage();
    await user.click(screen.getByRole('tab', { name: /what-if/i }));

    expect(screen.getByText(/teacher hints only/i)).toBeInTheDocument();
    expect(screen.getByText(/llm-led automatic planning/i)).toBeInTheDocument();
    expect(screen.getByText(/planning focus hint/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /run what-if analysis/i }));

    await waitFor(() => {
      expect(vi.mocked(runWhatIf)).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          mode: 'automatic',
          preferences: expect.objectContaining({
            intervention_intensity: expect.any(Number),
            focus: expect.any(String),
            max_skills: expect.any(Number),
          }),
        }),
      );
    });
  });

  it('keeps manual what-if teacher controlled', async () => {
    const user = userEvent.setup();
    renderTeacherTwinPage();

    await user.click(screen.getByRole('tab', { name: /what-if/i }));
    await user.click(screen.getByRole('button', { name: /^manual$/i }));

    expect(screen.getByText(/set a target mastery for each skill/i)).toBeInTheDocument();
    expect(screen.getByText(/show top results/i)).toBeInTheDocument();
  });

  it('keeps skill simulation running after the page remounts', async () => {
    const user = userEvent.setup();
    const pending = deferred<Record<string, unknown>>();
    vi.mocked(simulateSkills).mockImplementation(() => pending.promise as never);

    const firstPage = renderTeacherTwinPage();

    await user.click(screen.getByRole('tab', { name: /skill simulator/i }));
    await user.click(screen.getByRole('button', { name: /run automatic analysis/i }));

    expect(screen.getByRole('button', { name: /simulating/i })).toBeInTheDocument();

    firstPage.unmount();
    renderTeacherTwinPage();

    try {
      await user.click(screen.getByRole('tab', { name: /skill simulator/i }));
      expect(screen.getByRole('button', { name: /simulating/i })).toBeInTheDocument();
    } finally {
      await act(async () => {
        pending.resolve({
          mode: 'automatic',
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
        });
        await pending.promise;
      });
      await waitFor(() => expect(vi.mocked(simulateSkills)).toHaveBeenCalledTimes(1));
    }
  });

  it('keeps what-if simulation running after the page remounts', async () => {
    const user = userEvent.setup();
    const pending = deferred<Record<string, unknown>>();
    vi.mocked(runWhatIf).mockImplementation(() => pending.promise as never);

    const firstPage = renderTeacherTwinPage();

    await user.click(screen.getByRole('tab', { name: /what-if/i }));
    await user.click(screen.getByRole('button', { name: /run what-if analysis/i }));

    expect(screen.getByRole('button', { name: /running simulation/i })).toBeInTheDocument();

    firstPage.unmount();
    renderTeacherTwinPage();

    try {
      await user.click(screen.getByRole('tab', { name: /what-if/i }));
      expect(screen.getByRole('button', { name: /running simulation/i })).toBeInTheDocument();
    } finally {
      await act(async () => {
        pending.resolve({
          mode: 'automatic',
          course_id: 1,
          simulated_path: [],
          pco_analysis: [],
          recommendations: [],
          skill_impacts: [],
          summary: 'done',
          llm_recommendation: null,
        });
        await pending.promise;
      });
      await waitFor(() => expect(vi.mocked(runWhatIf)).toHaveBeenCalledTimes(1));
    }
  });

  it('explains learning curve tiers and individualized averaging', async () => {
    const user = userEvent.setup();
    renderTeacherTwinPage();

    await user.click(screen.getByRole('tab', { name: /students learning curve/i }));

    expect(screen.getByText(/each group line is the average of student-specific projected curves/i)).toBeInTheDocument();
    expect(screen.getByText(/students still needing core-skill support/i)).toBeInTheDocument();
  });
});

// ── StudentPage & JourneyPage ─────────────────────────────────────────────

const mockStudentData = {
  uid: 'u-1',
  name: 'Alice',
  skills: [],
  schedule: [],
  timeline: [],
  final_mastery: [],
  learning_path: [],
  summary: {
    total_interactions: 0,
    accuracy: 0,
    first_timestamp: '',
    last_timestamp: '',
    active_days: 0,
    avg_mastery: 0,
    strongest_skill: 0,
    weakest_skill: 0,
    skills_touched: 0,
  },
  review_summary: null,
};

const mockCurrentDataset = {
  id: 'course',
  label: 'Course',
  students: [mockStudentData],
  model_info: null,
};

vi.mock('@/features/arcd-agent/context/DataContext', () => ({
  useData: () => ({
    student: mockStudentData,
    skills: [],
    activeDatasetId: 'course',
    currentDataset: mockCurrentDataset,
    loading: false,
    error: '',
    portfolioData: null,
    setActiveDatasetId: vi.fn(),
    selectedUid: 'u-1',
    setSelectedUid: vi.fn(),
    dataVersion: 0,
    bumpVersion: vi.fn(),
    refreshData: vi.fn(),
  }),
}));

vi.mock('@/features/arcd-agent/context/TwinContext', () => ({
  useTwin: () => ({
    twinData: null,
    twinLoading: false,
    twinError: null,
    twinMatched: false,
    twinSource: null,
    checkReplan: () => false,
  }),
}));

vi.mock('@/features/arcd-agent/components/unified-tab', () => ({
  UnifiedTab: () => <div data-testid="unified-tab">unified</div>,
}));

vi.mock('@/features/arcd-agent/components/journey-map-tab', () => ({
  JourneyMapTab: () => <div data-testid="journey-map-tab">journey</div>,
}));

import StudentPage from './StudentPage';
import JourneyPage from './JourneyPage';

describe('StudentPage', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <StudentPage />
      </MemoryRouter>,
    );
    expect(document.body).toBeTruthy();
  });

  it('renders unified tab', () => {
    render(
      <MemoryRouter>
        <StudentPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('unified-tab')).toBeTruthy();
  });
});

describe('JourneyPage', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <JourneyPage />
      </MemoryRouter>,
    );
    expect(document.body).toBeTruthy();
  });

  it('renders journey-map-tab', () => {
    render(
      <MemoryRouter>
        <JourneyPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId('journey-map-tab')).toBeTruthy();
  });
});
