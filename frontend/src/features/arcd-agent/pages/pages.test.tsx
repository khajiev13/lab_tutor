/**
 * Smoke tests for teacher-twin pages.
 *
 * Strategy: mock the context hooks and API functions so pages render
 * without needing real network or store.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// ── Mock context hooks ─────────────────────────────────────────────────────

const mockTeacherCtx = {
  courseId: 1,
  loading: false,
  error: '',
  skillDifficulty: {
    course_id: 1,
    skills: [
      { skill_name: 'algebra', student_count: 5, avg_mastery: 0.6, perceived_difficulty: 0.4 },
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

describe('TeacherTwinPage', () => {
  it('renders without crashing', async () => {
    render(
      <MemoryRouter initialEntries={['/teacher/1/twin']}>
        <Routes>
          <Route path="/teacher/:courseId/twin" element={<TeacherTwinPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(document.body).toBeTruthy();
    });
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
