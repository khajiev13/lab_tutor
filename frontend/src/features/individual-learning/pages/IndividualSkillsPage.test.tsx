import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualSkillsPage from './IndividualSkillsPage';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  getIndividualSkillBanks: vi.fn(),
  selectIndividualSkills: vi.fn(),
  deselectIndividualSkills: vi.fn(),
  buildIndividualLearningPath: vi.fn(),
  resumeIndividualGraph: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const skillBanksResponse = {
  market_skill_bank: [
    {
      url: 'https://example.test/jobs/data-analyst',
      title: 'Data Analyst',
      company: 'ExampleCo',
      is_interested: true,
      site: 'LinkedIn',
      search_term: 'data analyst',
      skills: [
        {
          name: 'Query relational databases using SQL',
          is_selected: false,
          coverage: 'gap' as const,
        },
        {
          name: 'Build stakeholder dashboards',
          is_selected: false,
          coverage: 'gap' as const,
        },
      ],
    },
    {
      url: 'https://example.test/jobs/bi-analyst',
      title: 'BI Analyst',
      company: 'Insight Labs',
      is_interested: true,
      site: 'Indeed',
      search_term: 'bi analyst',
      skills: [
        {
          name: 'Build stakeholder dashboards',
          is_selected: false,
          coverage: 'gap' as const,
        },
        {
          name: 'Analyze cohorts in spreadsheets',
          is_selected: false,
          coverage: 'covered' as const,
        },
      ],
    },
  ],
  selected_skill_names: [],
  interested_posting_urls: [
    'https://example.test/jobs/data-analyst',
    'https://example.test/jobs/bi-analyst',
  ],
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/individual/skills']}>
      <Routes>
        <Route
          path="/individual/skills"
          element={
            <>
              <IndividualSkillsPage />
              <LocationProbe />
            </>
          }
        />
        <Route
          path="/individual/learning-path"
          element={
            <>
              <div>Learning path route</div>
              <LocationProbe />
            </>
          }
        />
        <Route path="/individual/jobs" element={<div>Recovered job selection</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('IndividualSkillsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(individualLearningApi.getIndividualSkillBanks).mockResolvedValue(skillBanksResponse);
    vi.mocked(individualLearningApi.selectIndividualSkills).mockResolvedValue({ selected: 3 });
    vi.mocked(individualLearningApi.deselectIndividualSkills).mockResolvedValue({ deselected: 0 });
    vi.mocked(individualLearningApi.buildIndividualLearningPath).mockResolvedValue({
      status: 'completed',
      run_id: 'learning-run-4',
    });
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockResolvedValue({
      thread_id: 'individual-7-cv-42',
      status: 'completed',
      interrupt: null,
      target_titles: ['Data Analyst'],
      selected_posting_urls: ['https://example.test/jobs/data-analyst'],
      selected_skill_names: [
        'Query relational databases using SQL',
        'Build stakeholder dashboards',
      ],
    });
  });

  it('renders market skills grouped by job posting', async () => {
    renderPage();

    expect(await screen.findByText('Data Analyst')).toBeInTheDocument();
    expect(await screen.findByText('Query relational databases using SQL')).toBeInTheDocument();
    expect(await screen.findByText('BI Analyst')).toBeInTheDocument();
  });

  it('selects all market skills and builds the learning path', async () => {
    renderPage();

    await screen.findByText('Data Analyst');

    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));
    fireEvent.click(screen.getByRole('button', { name: /build learning path/i }));

    await waitFor(() => {
      expect(individualLearningApi.selectIndividualSkills).toHaveBeenCalledTimes(1);
    });
    const [selectedSkillNames] = vi.mocked(individualLearningApi.selectIndividualSkills).mock.calls[0];
    expect(selectedSkillNames).toEqual(
      expect.arrayContaining([
        'Query relational databases using SQL',
        'Build stakeholder dashboards',
        'Analyze cohorts in spreadsheets',
      ]),
    );
    expect(selectedSkillNames).toHaveLength(3);

    const [builtSkillNames] = vi.mocked(individualLearningApi.buildIndividualLearningPath).mock.calls[0];
    expect(builtSkillNames).toEqual(expect.arrayContaining(selectedSkillNames));

    expect(await screen.findByText('Learning path route')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/individual/learning-path');
  });

  it('resumes the active graph with selected jobs and market skills before building', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
          skill_bank: skillBanksResponse.market_skill_bank[0].skills,
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
        selectedSkillNames: [],
      }),
    );

    renderPage();

    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));
    fireEvent.click(screen.getByRole('button', { name: /build learning path/i }));

    await waitFor(() => {
      expect(individualLearningApi.resumeIndividualGraph).toHaveBeenCalledWith(
        'individual-7-cv-42',
        {
          selected_posting_urls: ['https://example.test/jobs/data-analyst'],
          selected_skill_names: expect.arrayContaining([
            'Query relational databases using SQL',
            'Build stakeholder dashboards',
          ]),
        },
      );
    });
    expect(individualLearningApi.buildIndividualLearningPath).toHaveBeenCalled();
  });

  it('restores an interrupted skill draft after the page remounts', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        extractionRunId: 91,
        ownerUserId: 7,
        threadId: 'opaque-selection-thread',
        nextStep: 'select_jobs_and_skills',
        graphStatus: 'interrupted',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
          skill_bank: skillBanksResponse.market_skill_bank[0].skills,
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
        selectedSkillNames: [],
      }),
    );

    const firstRender = renderPage();

    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));

    await waitFor(() => {
      expect(
        JSON.parse(sessionStorage.getItem('individual-learning.graph-session') ?? '{}')
          .selectedSkillNames,
      ).toEqual([
        'Query relational databases using SQL',
        'Build stakeholder dashboards',
      ]);
    });

    firstRender.unmount();
    renderPage();

    expect(await screen.findByText('2 selected')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /remove query relational databases using sql/i }),
    ).toBeInTheDocument();
  });

  it('does not resume a graph that already completed before retrying a build', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        graphStatus: 'completed',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
          skill_bank: skillBanksResponse.market_skill_bank[0].skills,
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
        selectedSkillNames: [],
      }),
    );

    renderPage();

    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));
    fireEvent.click(screen.getByRole('button', { name: /build learning path/i }));

    await waitFor(() => {
      expect(individualLearningApi.buildIndividualLearningPath).toHaveBeenCalled();
    });
    expect(individualLearningApi.resumeIndividualGraph).not.toHaveBeenCalled();
  });

  it('restores a completed graph REST selection after remounting the page', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        ownerUserId: 7,
        threadId: 'individual-7-cv-42',
        graphStatus: 'completed',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
          skill_bank: skillBanksResponse.market_skill_bank[0].skills,
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
        selectedSkillNames: [],
      }),
    );

    const firstRender = renderPage();

    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));
    fireEvent.click(screen.getByRole('button', { name: /build learning path/i }));

    expect(await screen.findByText('Learning path route')).toBeInTheDocument();
    firstRender.unmount();

    renderPage();

    expect(await screen.findByText('2 selected')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /remove query relational databases using sql/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /remove build stakeholder dashboards/i }),
    ).toBeInTheDocument();
  });

  it('recovers a 409 resume conflict and never builds with stale skill selections', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        extractionRunId: 91,
        ownerUserId: 7,
        threadId: 'opaque-selection-thread',
        nextStep: 'select_jobs_and_skills',
        graphStatus: 'interrupted',
        reviewInterrupt: null,
        jobsInterrupt: {
          kind: 'choose_jobs_and_skills',
          candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
          skill_bank: skillBanksResponse.market_skill_bank[0].skills,
        },
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
        selectedSkillNames: [],
      }),
    );
    vi.mocked(individualLearningApi.resumeIndividualGraph).mockRejectedValue({
      response: { status: 409 },
    });
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_skill_selection',
      target_titles: ['Data Analyst'],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'opaque-selection-thread',
      next_step: 'select_jobs_and_skills',
      extracted_profile: { summary: 'Analytics profile' },
      pending_interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [skillBanksResponse.market_skill_bank[0]],
        skill_bank: skillBanksResponse.market_skill_bank[0].skills,
      },
    });

    renderPage();

    await screen.findByText('Data Analyst');
    fireEvent.click(screen.getByRole('button', { name: /select all market skills/i }));
    fireEvent.click(screen.getByRole('button', { name: /build learning path/i }));

    expect(await screen.findByText('Recovered job selection')).toBeInTheDocument();
    expect(individualLearningApi.buildIndividualLearningPath).not.toHaveBeenCalled();
    expect(
      JSON.parse(sessionStorage.getItem('individual-learning.graph-session') ?? '{}')
        .selectedSkillNames,
    ).toEqual([
      'Query relational databases using SQL',
      'Build stakeholder dashboards',
    ]);
  });

  it('uses durable skill-bank selections for completed recovery without resuming the graph', async () => {
    sessionStorage.setItem(
      'individual-learning.graph-session',
      JSON.stringify({
        cvDocumentId: 42,
        extractionRunId: 91,
        ownerUserId: 7,
        threadId: 'opaque-completed-thread',
        nextStep: 'learning_path',
        graphStatus: 'completed',
        extractedProfile: { summary: 'Analytics profile' },
        reviewInterrupt: null,
        jobsInterrupt: null,
        targetTitles: ['Data Analyst'],
        selectedPostingUrls: [],
        selectedSkillNames: [],
      }),
    );
    vi.mocked(individualLearningApi.getIndividualSkillBanks).mockResolvedValue({
      ...skillBanksResponse,
      selected_skill_names: ['Query relational databases using SQL'],
    });

    renderPage();

    expect(
      await screen.findByRole('button', { name: /remove query relational databases using sql/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /select all market skills/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /build learning path/i })).toBeDisabled();
    expect(individualLearningApi.resumeIndividualGraph).not.toHaveBeenCalled();
  });
});
