import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualProfilePage from './IndividualProfilePage';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  resumeIndividualGraph: vi.fn(),
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

describe('IndividualProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        reviewInterrupt: {
          kind: 'review_profile_and_roles',
          profile: {
            summary: 'Built dashboards for operations teams.',
            skills: [
              {
                name: 'SQL',
                evidence: 'Automated weekly reporting queries.',
                confidence: 0.92,
              },
            ],
            experience: [
              {
                title: 'Operations Analyst',
                organization: 'ExampleCo',
                summary: 'Owned dashboard delivery.',
              },
            ],
          },
          target_title_suggestions: ['Data Analyst'],
        },
        jobsInterrupt: null,
        targetTitles: [],
        selectedPostingUrls: [],
        selectedSkillNames: [],
      }),
    );

    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_profile_review',
      target_titles: [],
    });
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockResolvedValue({
      thread_id: 'individual-7-cv-42',
      status: 'interrupted',
      interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [
          {
            url: 'https://example.test/jobs/data-analyst',
            title: 'Data Analyst',
            company: 'ExampleCo',
            skills: [{ name: 'Query relational databases using SQL' }],
          },
        ],
        skill_bank: [{ name: 'Query relational databases using SQL' }],
      },
      target_titles: ['Data Analyst'],
      selected_posting_urls: [],
      selected_skill_names: [],
    });
  });

  it('renders extracted CV data and resumes with approved target titles', async () => {
    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route
            path="/individual/profile"
            element={
              <>
                <IndividualProfilePage />
                <LocationProbe />
              </>
            }
          />
          <Route
            path="/individual/jobs"
            element={
              <>
                <div>Job selection step</div>
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Built dashboards for operations teams.')).toBeInTheDocument();
    expect(screen.getByText('SQL')).toBeInTheDocument();
    expect(screen.getByText('Automated weekly reporting queries.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Data Analyst')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /approve profile and find jobs/i }));

    await waitFor(() => {
      expect(individualLearningApi.resumeIndividualGraph).toHaveBeenCalledWith(
        'individual-7-cv-42',
        { approved: true, target_titles: ['Data Analyst'] },
      );
    });
    expect(await screen.findByText('Job selection step')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/individual/jobs');
  });

  it('does not submit profile approval after the graph has advanced to job selection', async () => {
    const storedSession = JSON.parse(
      sessionStorage.getItem('individual-learning.graph-session') ?? '{}',
    );
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        ...storedSession,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [],
          skill_bank: [],
        },
        targetTitles: ['Data Analyst'],
      }),
    );

    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route path="/individual/profile" element={<IndividualProfilePage />} />
          <Route path="/individual/jobs" element={<div>Job selection step</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Profile review complete')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /approve profile and find jobs/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: /continue to job matches/i }));

    expect(await screen.findByText('Job selection step')).toBeInTheDocument();
    expect(individualLearningApi.resumeIndividualGraph).not.toHaveBeenCalled();
  });

  it('does not append a suggested title after reaching the 10-title limit', async () => {
    const storedSession = JSON.parse(
      sessionStorage.getItem('individual-learning.graph-session') ?? '{}',
    );
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        ...storedSession,
        reviewInterrupt: {
          ...storedSession.reviewInterrupt,
          target_title_suggestions: ['Analytics Engineer'],
        },
        targetTitles: Array.from({ length: 10 }, (_, index) => `Target role ${index + 1}`),
      }),
    );

    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route path="/individual/profile" element={<IndividualProfilePage />} />
        </Routes>
      </MemoryRouter>,
    );

    const suggestion = await screen.findByRole('button', { name: /analytics engineer/i });
    expect(suggestion).toBeDisabled();

    fireEvent.click(suggestion);

    expect(screen.getAllByRole('textbox')).toHaveLength(10);
  });
});
