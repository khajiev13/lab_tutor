import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import * as individualLearningApi from '@/features/individual-learning/api';
import { clearIndividualGraphSession } from '@/features/individual-learning/graph-session';
import IndividualProfilePage from './IndividualProfilePage';
import {
  establishAuthSession,
  invalidateAuthSession,
  resetAuthSessionForTests,
} from '@/features/auth/auth-session';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  resumeIndividualGraph: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

describe('IndividualProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearIndividualGraphSession();
    sessionStorage.clear();
    resetAuthSessionForTests();
    establishAuthSession(7);
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        extractionRunId: 91,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        nextStep: 'review_profile',
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
      target_titles: ['Data Analyst'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'individual-7-cv-42',
      next_step: 'review_profile',
      extracted_profile: {
        summary: 'Built dashboards for operations teams.',
        skills: [
          {
            name: 'SQL',
            evidence: 'Automated weekly reporting queries.',
            confidence: 0.92,
          },
        ],
        confidence_summary: { skills: 0.92 },
      },
      pending_interrupt: {
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
        },
        target_title_suggestions: ['Data Analyst'],
      },
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
    expect(screen.getByText('92% confidence')).toBeInTheDocument();
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
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_skill_selection',
      target_titles: ['Data Analyst'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'individual-7-cv-42',
      next_step: 'select_jobs_and_skills',
      extracted_profile: storedSession.reviewInterrupt.profile,
      pending_interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [],
        skill_bank: [],
      },
    });

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

  it('renders a recovered profile without session storage and warns on low confidence', async () => {
    sessionStorage.clear();
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_profile_review',
      target_titles: ['Analytics Engineer'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'opaque-thread-value',
      next_step: 'review_profile',
      extracted_profile: {
        summary: 'Recovered analytics profile',
        skills: [{ name: 'Python', confidence: 0.55 }],
        confidence_summary: { experience: 0.58 },
      },
      pending_interrupt: {
        kind: 'review_profile_and_roles',
        profile: {
          summary: 'Recovered analytics profile',
          skills: [{ name: 'Python', confidence: 0.55 }],
          confidence_summary: { experience: 0.58 },
        },
        target_title_suggestions: ['Analytics Engineer'],
      },
    });

    render(
      <MemoryRouter>
        <IndividualProfilePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Recovered analytics profile')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('55% confidence')).toBeInTheDocument();
    expect(screen.getByText(/some extracted details have low confidence/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('Analytics Engineer')).toBeInTheDocument();
  });

  it('presents zero, null, and absent provider confidence as unavailable without a low warning', async () => {
    sessionStorage.clear();
    const unknownConfidenceProfile = {
      summary: 'Forward-deployed AI engineering profile',
      skills: [
        { name: 'RAG', confidence: 0 },
        { name: 'LangGraph', confidence: null },
        { name: 'Neo4j' },
      ],
      confidence_summary: { skills: 0, experience: 0 },
    };
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_profile_review',
      target_titles: ['AI Engineer'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'opaque-thread-value',
      next_step: 'review_profile',
      extracted_profile: unknownConfidenceProfile,
      pending_interrupt: {
        kind: 'review_profile_and_roles',
        profile: unknownConfidenceProfile,
        target_title_suggestions: ['AI Engineer'],
      },
    });

    render(
      <MemoryRouter>
        <IndividualProfilePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Forward-deployed AI engineering profile')).toBeInTheDocument();
    expect(screen.getAllByText('Confidence unavailable')).toHaveLength(3);
    expect(screen.queryByText('0% confidence')).not.toBeInTheDocument();
    expect(screen.queryByText(/some extracted details have low confidence/i)).not.toBeInTheDocument();
  });

  it('retries durable job search with the active opaque thread and durable titles', async () => {
    sessionStorage.clear();
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_jobs',
      target_titles: ['Backend Engineer'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'opaque-search-thread',
      next_step: 'search_jobs',
      extracted_profile: { summary: 'Backend profile', confidence_summary: { skills: 0.9 } },
      pending_interrupt: null,
    });
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockResolvedValue({
      thread_id: 'opaque-search-thread',
      status: 'interrupted',
      interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [
          { url: 'https://example.test/backend', title: 'Backend Engineer' },
        ],
        skill_bank: [{ name: 'Docker' }],
      },
      target_titles: ['Backend Engineer'],
      selected_posting_urls: [],
      selected_skill_names: [],
    });

    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route path="/individual/profile" element={<IndividualProfilePage />} />
          <Route path="/individual/jobs" element={<div>Recovered job matches</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: /retry job search/i }));

    await waitFor(() => {
      expect(individualLearningApi.resumeIndividualGraph).toHaveBeenCalledWith(
        'opaque-search-thread',
        { approved: true, target_titles: ['Backend Engineer'] },
      );
    });
    expect(await screen.findByText('Recovered job matches')).toBeInTheDocument();
  });

  it('recovers a 409 profile resume without losing the target-title draft', async () => {
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockRejectedValue({
      response: { status: 409 },
    });
    vi.mocked(individualLearningApi.getIndividualProfile)
      .mockResolvedValueOnce({
        user_id: 7,
        onboarding_status: 'needs_profile_review',
        target_titles: ['Data Analyst'],
        cv_document_id: 42,
        extraction_run_id: 91,
        active_thread_id: 'individual-7-cv-42',
        next_step: 'review_profile',
        extracted_profile: { summary: 'Analytics profile' },
        pending_interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Analytics profile' },
          target_title_suggestions: ['Data Analyst'],
        },
      })
      .mockResolvedValueOnce({
        user_id: 7,
        onboarding_status: 'needs_skill_selection',
        target_titles: ['Analytics Engineer'],
        cv_document_id: 42,
        extraction_run_id: 91,
        active_thread_id: 'individual-7-cv-42',
        next_step: 'select_jobs_and_skills',
        extracted_profile: { summary: 'Analytics profile' },
        pending_interrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [
            { url: 'https://example.test/analytics', title: 'Analytics Engineer' },
          ],
          skill_bank: [{ name: 'Data modeling' }],
        },
      });

    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route path="/individual/profile" element={<IndividualProfilePage />} />
          <Route path="/individual/jobs" element={<div>Recovered after conflict</div>} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText('Analytics profile');
    const title = screen.getByDisplayValue('Data Analyst');
    fireEvent.change(title, { target: { value: 'Analytics Engineer' } });
    fireEvent.click(screen.getByRole('button', { name: /approve profile and find jobs/i }));

    expect(await screen.findByText('Recovered after conflict')).toBeInTheDocument();
    expect(individualLearningApi.resumeIndividualGraph).toHaveBeenCalledWith(
      'individual-7-cv-42',
      { approved: true, target_titles: ['Analytics Engineer'] },
    );
    expect(individualLearningApi.getIndividualProfile).toHaveBeenCalledTimes(2);
    expect(JSON.parse(sessionStorage.getItem('individual-learning.graph-session') ?? '{}')).toMatchObject({
      targetTitles: ['Analytics Engineer'],
      jobsInterrupt: { kind: 'choose_jobs_and_skills' },
    });
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('does not persist or navigate when profile approval resolves after logout', async () => {
    let resolveResume!: (
      value: Awaited<ReturnType<typeof individualLearningApi.resumeIndividualGraph>>,
    ) => void;
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockReturnValue(
      new Promise((resolve) => {
        resolveResume = resolve;
      }),
    );

    render(
      <MemoryRouter initialEntries={['/individual/profile']}>
        <Routes>
          <Route path="/individual/profile" element={<><IndividualProfilePage /><LocationProbe /></>} />
          <Route path="/individual/jobs" element={<div>Former user jobs</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByText('Built dashboards for operations teams.');
    fireEvent.click(screen.getByRole('button', { name: /approve profile and find jobs/i }));
    await waitFor(() => expect(individualLearningApi.resumeIndividualGraph).toHaveBeenCalled());

    invalidateAuthSession();
    clearIndividualGraphSession();
    resolveResume({
      thread_id: 'individual-7-cv-42',
      status: 'interrupted',
      interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [],
        skill_bank: [],
      },
      target_titles: ['Data Analyst'],
      selected_posting_urls: [],
      selected_skill_names: [],
    });

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/individual/profile'));
    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
    expect(screen.queryByText('Former user jobs')).not.toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
