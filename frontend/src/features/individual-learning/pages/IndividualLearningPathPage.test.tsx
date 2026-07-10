import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualLearningPathPage from './IndividualLearningPathPage';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualLearningPath: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
  },
}));

describe('IndividualLearningPathPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders top-level skill sections with loaded and pending content states', async () => {
    vi.mocked(individualLearningApi.getIndividualLearningPath).mockResolvedValue({
      user_id: 7,
      total_selected_skills: 2,
      skills_with_resources: 1,
      build_status: 'completed',
      build_run_id: 'learning-run-4',
      build_error: null,
      selected_skills: [
        {
          name: 'Query relational databases using SQL',
          description: 'Work confidently with analytics queries.',
          source: 'market',
          readings: [
            {
              id: 'reading-1',
              title: 'SQL for Analysts',
              url: 'https://example.test/sql',
              domain: 'example.test',
            },
          ],
          videos: [
            {
              id: 'video-1',
              title: 'SQL walkthrough',
              url: 'https://example.test/sql-video',
              domain: 'example.test',
            },
          ],
          questions: [
            {
              id: 'question-1',
              text: 'Which clause filters grouped rows?',
              difficulty: 'medium',
              options: ['WHERE', 'HAVING', 'SELECT'],
            },
          ],
        },
        {
          name: 'Build stakeholder dashboards',
          description: 'Translate metrics into decisions.',
          source: 'market',
          readings: [],
          videos: [],
          questions: [],
        },
      ],
    });

    render(
      <MemoryRouter>
        <IndividualLearningPathPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Query relational databases using SQL')).toBeInTheDocument();
    expect(screen.getByText('SQL for Analysts')).toBeInTheDocument();
    expect(screen.getByText('SQL walkthrough')).toBeInTheDocument();
    expect(screen.getByText('Which clause filters grouped rows?')).toBeInTheDocument();
    expect(screen.getByText('Build stakeholder dashboards')).toBeInTheDocument();
    expect(screen.getByText(/content is still being assembled for this skill/i)).toBeInTheDocument();
  });

  it('retries a failed learning-path load inline', async () => {
    vi.mocked(individualLearningApi.getIndividualLearningPath)
      .mockRejectedValueOnce({ response: { status: 502 } })
      .mockResolvedValueOnce({
        user_id: 7,
        total_selected_skills: 1,
        skills_with_resources: 0,
        build_status: 'completed',
        build_run_id: 'learning-run-5',
        build_error: null,
        selected_skills: [
          {
            name: 'Recovered SQL',
            readings: [],
            videos: [],
            questions: [],
          },
        ],
      });

    render(
      <MemoryRouter>
        <IndividualLearningPathPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /retry learning path/i }));

    expect(await screen.findByText('Recovered SQL')).toBeInTheDocument();
    expect(individualLearningApi.getIndividualLearningPath).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['partial', 'Learning path partially built', 'Some providers were unavailable.'],
    ['failed', 'Learning path build failed', 'No learning resources could be generated.'],
  ] as const)('renders %s build guidance with its durable run metadata', async (
    buildStatus,
    title,
    buildError,
  ) => {
    vi.mocked(individualLearningApi.getIndividualLearningPath).mockResolvedValue({
      user_id: 7,
      total_selected_skills: 1,
      skills_with_resources: buildStatus === 'partial' ? 1 : 0,
      build_status: buildStatus,
      build_run_id: 'learning-run-status',
      build_error: buildError,
      selected_skills: buildStatus === 'partial'
        ? [{ name: 'SQL', readings: [], videos: [], questions: [] }]
        : [],
    });

    render(
      <MemoryRouter>
        <IndividualLearningPathPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(buildError)).toBeInTheDocument();
    expect(screen.getByText(/learning-run-status/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /return to skill selection/i })).toHaveAttribute(
      'href',
      '/individual/skills',
    );
  });
});
