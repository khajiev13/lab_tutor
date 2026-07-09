import { render, screen } from '@testing-library/react';
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
});
