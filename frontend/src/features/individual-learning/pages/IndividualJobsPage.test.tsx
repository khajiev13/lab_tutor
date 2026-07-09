import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualJobsPage from './IndividualJobsPage';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualSkillBanks: vi.fn(),
  selectInterestedJobs: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

describe('IndividualJobsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        graphStatus: 'interrupted',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [
            {
              url: 'https://example.test/jobs/data-analyst',
              title: 'Data Analyst',
              company: 'ExampleCo',
              site: 'LinkedIn',
              search_term: 'analytics',
              match_score: 0.84,
              skills: [
                { name: 'Query relational databases using SQL', coverage: 'gap' },
              ],
            },
          ],
          skill_bank: [{ name: 'Query relational databases using SQL' }],
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: [],
        selectedSkillNames: [],
      }),
    );
  });

  it('renders interrupt job cards and carries interested jobs to skill selection', async () => {
    render(
      <MemoryRouter initialEntries={['/individual/jobs']}>
        <Routes>
          <Route
            path="/individual/jobs"
            element={
              <>
                <IndividualJobsPage />
                <LocationProbe />
              </>
            }
          />
          <Route
            path="/individual/skills"
            element={
              <>
                <div>Skill selection step</div>
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Data Analyst')).toBeInTheDocument();
    expect(screen.getByText(/ExampleCo/)).toBeInTheDocument();
    expect(screen.getByText(/LinkedIn/)).toBeInTheDocument();
    expect(screen.getByText(/analytics/)).toBeInTheDocument();
    expect(screen.getByText('Match 84%')).toBeInTheDocument();
    expect(screen.getByText('Query relational databases using SQL')).toBeInTheDocument();
    expect(screen.getByText('Gap')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: /mark data analyst as interested/i }));
    fireEvent.click(screen.getByRole('button', { name: /continue to skill selection/i }));

    expect(await screen.findByText('Skill selection step')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/individual/skills');
    expect(JSON.parse(sessionStorage.getItem('individual-learning.graph-session') ?? '{}')).toMatchObject({
      selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
    });
    expect(individualLearningApi.getIndividualSkillBanks).not.toHaveBeenCalled();
  });

  it('persists graph job drafts before the user leaves the page', async () => {
    const firstRender = render(
      <MemoryRouter>
        <IndividualJobsPage />
      </MemoryRouter>,
    );

    fireEvent.click(
      await screen.findByRole('checkbox', { name: /mark data analyst as interested/i }),
    );

    await waitFor(() => {
      expect(
        JSON.parse(sessionStorage.getItem('individual-learning.graph-session') ?? '{}'),
      ).toMatchObject({
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
      });
    });

    firstRender.unmount();
    render(
      <MemoryRouter>
        <IndividualJobsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('checkbox', { name: /mark data analyst as interested/i }),
    ).toBeChecked();
  });

  it('keeps completed graph job selection read-only on re-entry', async () => {
    const session = JSON.parse(
      sessionStorage.getItem('individual-learning.graph-session') ?? '{}',
    );
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        ...session,
        graphStatus: 'completed',
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
      }),
    );

    render(
      <MemoryRouter>
        <IndividualJobsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('checkbox', { name: /mark data analyst as interested/i }),
    ).toBeDisabled();
    expect(screen.getByText('Selection complete')).toBeInTheDocument();
  });
});
