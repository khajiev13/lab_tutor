import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, type Mock } from 'vitest';
import { toast } from 'sonner';

import StudentLearningPathPage from './StudentLearningPathPage';
import * as studentLearningPathApi from '../api';

vi.mock('../api', () => ({
  getSkillBanks: vi.fn(),
  getLearningPath: vi.fn(),
  buildLearningPath: vi.fn(),
  streamBuildProgress: vi.fn(),
  selectSkills: vi.fn(),
  deselectSkills: vi.fn(),
  selectJobPostings: vi.fn(),
  deselectJobPosting: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    warning: vi.fn(),
    success: vi.fn(),
  },
}));

const unlockedSkillBanks = {
  book_skill_banks: [
    {
      book_id: 'book-1',
      title: 'Designing Data Systems',
      authors: 'Alex Example',
      chapters: [
        {
          chapter_id: 'chapter-1',
          title: 'Foundations',
          chapter_index: 1,
          skills: [
            {
              name: 'Batch Processing',
              description: 'Process large datasets reliably.',
              peer_count: 2,
            },
          ],
        },
      ],
    },
  ],
  market_skill_bank: [
    {
      url: 'https://jobs.example/backend',
      title: 'Backend Engineer',
      company: 'Acme',
      site: 'LinkedIn',
      search_term: 'backend engineer',
      is_interested: false,
      skills: [
        {
          name: 'Kafka',
          description: 'Stream events across services.',
          category: 'data_processing',
          peer_count: 1,
        },
      ],
    },
  ],
  selected_skill_names: [],
  interested_posting_urls: [],
  peer_selection_counts: {
    'Batch Processing': 2,
    Kafka: 1,
  },
  selection_range: {
    min_skills: 20,
    max_skills: 35,
    is_default: true,
  },
  prerequisite_edges: [
    {
      prerequisite_name: 'Batch Processing',
      dependent_name: 'Kafka',
      confidence: 'high',
      reasoning: 'Batch concepts should come before streaming concepts.',
    },
  ],
};

const lockedSkillBanks = {
  ...unlockedSkillBanks,
  selected_skill_names: ['Batch Processing'],
};

const permissiveUnlockedSkillBanks = {
  ...unlockedSkillBanks,
  selection_range: {
    min_skills: 1,
    max_skills: 35,
    is_default: false,
  },
};

const permissiveLockedSkillBanks = {
  ...lockedSkillBanks,
  selection_range: {
    min_skills: 1,
    max_skills: 35,
    is_default: false,
  },
};

const learningPathResponse = {
  course_id: 1,
  course_title: 'Data Systems',
  total_selected_skills: 1,
  skills_with_resources: 1,
  chapters: [
    {
      title: 'Foundations',
      chapter_index: 1,
      description: null,
      selected_skills: [
        {
          name: 'Batch Processing',
          source: 'book',
          description: 'Process large datasets reliably.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              title: 'Batch Systems Guide',
              url: 'https://example.com/reading',
              domain: 'example.com',
              snippet: '',
              search_content: '',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'article',
              final_score: 0.9,
              concepts_covered: [],
            },
          ],
          videos: [],
          questions: [],
          resource_status: 'loaded',
        },
      ],
    },
  ],
};

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/courses/1/learning-path']}>
      <Routes>
        <Route path="/courses/:id/learning-path" element={<StudentLearningPathPage />} />
        <Route path="/courses/:id" element={<div>Course Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('StudentLearningPathPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (studentLearningPathApi.streamBuildProgress as Mock).mockReturnValue(() => {});
  });

  it('shows only selection UI for unlocked students and does not load the path', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(unlockedSkillBanks);

    renderPage();

    expect(await screen.findByText('Book Skill Banks')).toBeInTheDocument();
    expect(studentLearningPathApi.getLearningPath).not.toHaveBeenCalled();
    expect(screen.queryByText(/No learning path yet/i)).not.toBeInTheDocument();
  });

  it('keeps draft selections local while choosing skills', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(unlockedSkillBanks);

    renderPage();

    const skillChip = await screen.findByRole('button', { name: /Batch Processing/i });
    fireEvent.click(skillChip);

    expect(await screen.findByText('1 of 20-35 skills selected')).toBeInTheDocument();
    expect(studentLearningPathApi.selectSkills).not.toHaveBeenCalled();
    expect(studentLearningPathApi.deselectSkills).not.toHaveBeenCalled();
    expect(studentLearningPathApi.selectJobPostings).not.toHaveBeenCalled();
  });

  it('sends staged selections only when build is clicked', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(permissiveUnlockedSkillBanks);
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({
      run_id: 'run-1',
      status: 'started',
    });

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Batch Processing/i }));
    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [
        { name: 'Batch Processing', source: 'book' },
      ]);
    });
  });

  it('blocks build with a range-aware warning when the draft count is outside the course range', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(unlockedSkillBanks);

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Batch Processing/i }));
    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    await waitFor(() => {
      expect(toast.warning).toHaveBeenCalledWith(
        'Select between 20 and 35 skills before building.',
      );
    });
    expect(studentLearningPathApi.buildLearningPath).not.toHaveBeenCalled();
  });

  it('shows prerequisite guidance while browsing and before build', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(permissiveUnlockedSkillBanks);
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({
      run_id: 'run-1',
      status: 'started',
    });

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Requires 1/i }));
    expect(await screen.findByText('Direct prerequisites')).toBeInTheDocument();
    expect(screen.getByText('Batch concepts should come before streaming concepts.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Kafka/i }));
    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    expect(await screen.findByText('Review prerequisites')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue build/i })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /I already know this/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Continue build/i })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole('button', { name: /Continue build/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [
        { name: 'Kafka', source: 'market' },
      ]);
    });
  });

  it('reloads into locked study mode after build completion', async () => {
    (studentLearningPathApi.getSkillBanks as Mock)
      .mockResolvedValueOnce(permissiveUnlockedSkillBanks)
      .mockResolvedValueOnce(permissiveLockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({
      run_id: 'run-1',
      status: 'started',
    });
    (studentLearningPathApi.streamBuildProgress as Mock).mockImplementation(
      (_courseId, _runId, onEvent, onComplete) => {
        onEvent({
          type: 'skill_progress',
          skill_name: 'Batch Processing',
          phase: 'done',
          detail: 'Done',
          skills_completed: 1,
          total_skills: 1,
        });
        void onComplete();
        return () => {};
      },
    );

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Batch Processing/i }));
    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.getLearningPath).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByText('Chapter 1: Foundations')).toBeInTheDocument();
      expect(screen.queryByText('Book Skill Banks')).not.toBeInTheDocument();
    });
  });

  it('shows only study mode for locked students and opens the first chapter', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);

    renderPage();

    expect(await screen.findByText('Chapter 1: Foundations')).toBeInTheDocument();
    expect(screen.queryByText('Book Skill Banks')).not.toBeInTheDocument();
    expect(screen.getByText('Reading Resources')).toBeInTheDocument();
  });

  it('redirects back to the course page when skill banks return 403', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockRejectedValue({
      response: { status: 403 },
    });

    renderPage();

    expect(await screen.findByText('Course Page')).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('Join the course before opening the learning path.');
  });
});
