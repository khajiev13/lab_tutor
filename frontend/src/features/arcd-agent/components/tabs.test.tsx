/**
 * Smoke tests for arcd-agent tab components.
 *
 * Each test verifies the component mounts without throwing.
 * Contexts and APIs are mocked to isolate rendering from network.
 */

import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ── Stub fetch to avoid network calls ────────────────────────────────────

vi.stubGlobal(
  'fetch',
  vi.fn().mockResolvedValue({
    ok: false,
    status: 503,
    text: () => Promise.resolve('unavailable'),
    json: () => Promise.resolve({}),
  }),
);

// ── Shared mock data ──────────────────────────────────────────────────────

import type { StudentPortfolio } from '@/features/arcd-agent/lib/types';

const mockStudent: StudentPortfolio = {
  uid: 'u-1',
  name: 'Test Student',
  skills: [
    {
      id: 1,
      name: 'algebra',
      mastery: 0.7,
      status: 'at',
      path_position: 1,
      sub_skills: [],
      session_type: 'guided_learning',
      rationale: '',
    } as StudentPortfolio['skills'][0],
  ],
  schedule: [],
  timeline: [],
  final_mastery: [],
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
} as unknown as StudentPortfolio;

const mockSkills: Parameters<typeof import('@/features/arcd-agent/components/pathgen-tab').PathGenTab>[0]['skills'] = [];

// ── Mock TwinContext ───────────────────────────────────────────────────────

vi.mock('recharts', () => ({
  LineChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  ComposedChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  Line: () => null,
  Bar: () => null,
  Area: () => null,
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
  AreaChart: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
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

// ── Mock DataContext ───────────────────────────────────────────────────────

vi.mock('@/features/arcd-agent/context/DataContext', () => ({
  useData: () => ({
    student: mockStudent,
    skills: [],
    activeDatasetId: 'course',
    currentDataset: null,
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

// ── ReviewChatTab (chat-tab) ──────────────────────────────────────────────

import { ReviewChatTab } from './chat-tab';

describe('ReviewChatTab', () => {
  it('renders without crashing', () => {
    render(
      <ReviewChatTab
        student={mockStudent}
        datasetId="course"
      />,
    );
    expect(document.body).toBeTruthy();
  });
});

// ── PathGenTab ─────────────────────────────────────────────────────────────

import { PathGenTab } from './pathgen-tab';

describe('PathGenTab', () => {
  it('renders with empty path', () => {
    render(
      <PathGenTab
        student={{ ...mockStudent, skills: [] } as unknown as StudentPortfolio}
        skills={mockSkills}
        datasetId="course"
      />,
    );
    expect(document.body).toBeTruthy();
  });
});

// ── JourneyMapTab ──────────────────────────────────────────────────────────

import { JourneyMapTab } from './journey-map-tab';

describe('JourneyMapTab', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <JourneyMapTab
          student={mockStudent}
          skills={mockSkills}
          datasetId="course"
        />
      </MemoryRouter>,
    );
    expect(document.body).toBeTruthy();
  });
});

// ── TwinViewerTab ──────────────────────────────────────────────────────────

import { TwinViewerTab } from './twin-viewer-tab';

describe('TwinViewerTab', () => {
  it('renders without crashing', () => {
    render(
      <TwinViewerTab
        student={mockStudent}
        skills={mockSkills}
        datasetId="course"
      />,
    );
    expect(document.body).toBeTruthy();
  });
});

// ── ScheduleTab ───────────────────────────────────────────────────────────

import { ScheduleTab } from './schedule-tab';

describe('ScheduleTab', () => {
  it('renders without crashing', () => {
    render(
      <ScheduleTab
        student={mockStudent}
        skills={mockSkills}
      />,
    );
    expect(document.body).toBeTruthy();
  });
});

// ── UnifiedTab ────────────────────────────────────────────────────────────

import { UnifiedTab } from './unified-tab';

describe('UnifiedTab', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <UnifiedTab
          student={mockStudent}
          skills={mockSkills}
        />
      </MemoryRouter>,
    );
    expect(document.body).toBeTruthy();
  });
});
