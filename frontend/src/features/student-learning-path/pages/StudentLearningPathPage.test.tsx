import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi, type Mock } from 'vitest';
import { toast } from 'sonner';
import { careerSkill, postingUrl, referenceA, referenceB, referencePending, referenceWithdrawn, task9Banks } from '@/features/curriculum/__tests__/task9-fixtures';

import StudentLearningPathPage from '@/features/student-learning-path/pages/StudentLearningPathPage';
import * as studentLearningPathApi from '@/features/student-learning-path/api';
import { buildPrerequisiteIndex, collectStudentSkills } from '@/features/student-learning-path/selection';

vi.mock('@/features/student-learning-path/api', () => ({
  getSkillBanks: vi.fn(),
  getLearningPath: vi.fn(),
  getChapterQuiz: vi.fn(),
  submitChapterQuiz: vi.fn(),
  buildLearningPath: vi.fn(),
  streamBuildProgress: vi.fn(),
  trackResourceOpen: vi.fn(),
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

const openWindowSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

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

const permissiveUnlockedSkillBanksWithoutPrerequisites = {
  ...permissiveUnlockedSkillBanks,
  prerequisite_edges: [],
};

const permissiveUnlockedSkillBanksWithPostingOwnedDrafts = {
  ...permissiveUnlockedSkillBanksWithoutPrerequisites,
  market_skill_bank: [
    {
      ...permissiveUnlockedSkillBanksWithoutPrerequisites.market_skill_bank[0],
      skills: [
        {
          name: 'Build microservices using Spring Boot',
          description: 'Build resilient backend services.',
          category: 'backend',
          peer_count: 73,
        },
        {
          name: 'Design and optimize caching solutions',
          description: 'Tune application caching layers.',
          category: 'backend',
          peer_count: 73,
        },
        {
          name: 'Develop and deploy cloud-based solutions',
          description: 'Ship services to cloud infrastructure.',
          category: 'cloud',
          peer_count: 67,
        },
      ],
    },
  ],
  peer_selection_counts: {
    'Build microservices using Spring Boot': 73,
    'Design and optimize caching solutions': 73,
    'Develop and deploy cloud-based solutions': 67,
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

const gatingLearningPathResponse = {
  course_id: 1,
  course_title: 'Data Systems',
  total_selected_skills: 3,
  skills_with_resources: 3,
  chapters: [
    {
      title: 'Foundations',
      chapter_index: 1,
      description: null,
      quiz_status: 'quiz_required',
      easy_question_count: 1,
      answered_count: 0,
      correct_count: 0,
      selected_skills: [
        {
          name: 'Batch Processing',
          source: 'book',
          description: 'Process large datasets reliably.',
          skill_type: 'book',
          concepts: [],
          readings: [],
          videos: [],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
    {
      title: 'Streaming Systems',
      chapter_index: 2,
      description: null,
      quiz_status: 'locked',
      easy_question_count: 1,
      answered_count: 0,
      correct_count: 0,
      selected_skills: [
        {
          name: 'Kafka',
          source: 'market',
          description: 'Stream events across services.',
          skill_type: 'market',
          concepts: [],
          readings: [],
          videos: [],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
    {
      title: 'Batch Review',
      chapter_index: 3,
      description: null,
      quiz_status: 'completed',
      easy_question_count: 1,
      answered_count: 1,
      correct_count: 1,
      selected_skills: [
        {
          name: 'Batch Processing',
          source: 'book',
          description: 'Process large datasets reliably.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              id: 'reading-3',
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
          is_known: true,
          resource_status: 'loaded',
        },
      ],
    },
  ],
};

const learningPathResponse = {
  course_id: 1,
  course_title: 'Data Systems',
  total_selected_skills: 2,
  skills_with_resources: 2,
  chapters: [
    {
      title: 'Foundations',
      chapter_index: 1,
      description: null,
      quiz_status: 'learning',
      easy_question_count: 2,
      answered_count: 1,
      correct_count: 1,
      selected_skills: [
        {
          name: 'Batch Processing',
          source: 'book',
          description: 'Process large datasets reliably.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              id: 'reading-1',
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
          videos: [
            {
              id: 'video-1',
              title: 'Batch Systems Video',
              url: 'https://www.youtube.com/watch?v=batch123',
              domain: 'youtube.com',
              snippet: '',
              search_content: '',
              video_id: 'batch123',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'video',
              final_score: 0.85,
              concepts_covered: [],
            },
          ],
          questions: [],
          is_known: true,
          resource_status: 'loaded',
        },
        {
          name: 'Streaming Basics',
          source: 'book',
          description: 'Understand event streams.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              id: 'reading-2',
              title: 'Streaming Primer',
              url: 'https://example.com/streaming',
              domain: 'example.com',
              snippet: '',
              search_content: '',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'article',
              final_score: 0.8,
              concepts_covered: [],
            },
          ],
          videos: [],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
  ],
};

const partialProgressLearningPathResponse = {
  ...learningPathResponse,
  total_selected_skills: 3,
  chapters: [
    ...learningPathResponse.chapters,
    {
      title: 'Streaming Systems',
      chapter_index: 2,
      description: null,
      quiz_status: 'locked',
      easy_question_count: 1,
      answered_count: 0,
      correct_count: 0,
      selected_skills: [
        {
          name: 'Kafka',
          source: 'market',
          description: 'Stream events across services.',
          skill_type: 'market',
          concepts: [],
          readings: [],
          videos: [],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
  ],
};

const learningPathResponseWithEmptyChapter = {
  ...learningPathResponse,
  chapters: [
    ...learningPathResponse.chapters,
    {
      title: 'Optimization',
      chapter_index: 2,
      description: null,
      quiz_status: 'locked',
      easy_question_count: 0,
      answered_count: 0,
      correct_count: 0,
      selected_skills: [],
    },
  ],
};

const transparentChapterLearningPathResponse = {
  course_id: 1,
  course_title: 'Data Systems',
  total_selected_skills: 1,
  skills_with_resources: 1,
  chapters: [
    {
      title: 'Foundations',
      chapter_index: 1,
      description: null,
      quiz_status: 'completed',
      easy_question_count: 1,
      answered_count: 1,
      correct_count: 1,
      selected_skills: [
        {
          name: 'Batch Processing',
          source: 'book',
          description: 'Process large datasets reliably.',
          skill_type: 'book',
          concepts: [],
          readings: [],
          videos: [],
          questions: [],
          is_known: true,
          resource_status: 'loaded',
        },
      ],
    },
    {
      title: 'No Quiz Yet',
      chapter_index: 2,
      description: null,
      quiz_status: 'learning',
      easy_question_count: 0,
      answered_count: 0,
      correct_count: 0,
      selected_skills: [
        {
          name: 'Fresh Skill',
          source: 'book',
          description: 'Waiting on generated questions.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              id: 'reading-4',
              title: 'Fresh Skill Guide',
              url: 'https://example.com/fresh-skill',
              domain: 'example.com',
              snippet: '',
              search_content: '',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'article',
              final_score: 0.7,
              concepts_covered: [],
            },
          ],
          videos: [],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
  ],
};

const emptyLearningPathResponse = {
  course_id: 1,
  course_title: 'Data Systems',
  total_selected_skills: 1,
  skills_with_resources: 0,
  chapters: [],
};

function renderPage() {
  function LocationDisplay() {
    const location = useLocation();
    return <div data-testid="pathname">{location.pathname}</div>;
  }

  render(
    <MemoryRouter initialEntries={['/courses/1/learning-path']}>
      <LocationDisplay />
      <Routes>
        <Route path="/courses/:id/learning-path" element={<StudentLearningPathPage />} />
        <Route
          path="/courses/:id/learning-path/study/:resourceKind/:resourceId"
          element={<div>Study route destination</div>}
        />
        <Route path="/courses/:id" element={<div>Course Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('StudentLearningPathPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    openWindowSpy.mockClear();
    (studentLearningPathApi.streamBuildProgress as Mock).mockReturnValue(() => {});
    (studentLearningPathApi.trackResourceOpen as Mock).mockResolvedValue(undefined);
  });

  it('shows only selection UI for unlocked students and does not load the path', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(unlockedSkillBanks);

    renderPage();

    expect(await screen.findByText('Book Skill Banks')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Build My Learning Path/i })).toBeInTheDocument();
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

  it('stages job posting skills locally and only sends them during build', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(
      permissiveUnlockedSkillBanksWithoutPrerequisites,
    );
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({
      run_id: 'run-1',
      status: 'started',
    });

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Select all skills/i }));

    expect(await screen.findByText('1 of 1-35 skills selected')).toBeInTheDocument();
    expect(await screen.findByText('Selected in draft')).toBeInTheDocument();
    expect(studentLearningPathApi.selectJobPostings).not.toHaveBeenCalled();
    expect(studentLearningPathApi.deselectJobPosting).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [
        { name: 'Kafka', source: 'market' },
      ]);
    });
  });

  it('clears every staged posting skill when a draft posting selection is removed', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(
      permissiveUnlockedSkillBanksWithPostingOwnedDrafts,
    );

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Design and optimize caching solutions/i }));
    fireEvent.click(screen.getByRole('button', { name: /Develop and deploy cloud-based solutions/i }));
    expect(await screen.findByText('2 of 1-35 skills selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Select all skills/i }));
    expect(await screen.findByText('3 of 1-35 skills selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Remove draft selection/i }));

    expect(await screen.findByText('0 of 1-35 skills selected')).toBeInTheDocument();
    expect(screen.getByText('Not selected')).toBeInTheDocument();
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

    fireEvent.click(await screen.findByRole('button', { name: /1 prerequisite/i }));
    expect(await screen.findByText('Prerequisite chain')).toBeInTheDocument();
    expect(screen.getByText('Must learn first')).toBeInTheDocument();
    expect(screen.getByText('Batch concepts should come before streaming concepts.')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Kafka/i }));
    fireEvent.click(screen.getByRole('button', { name: /Build My Learning Path/i }));

    expect(await screen.findByText('Review prerequisites')).toBeInTheDocument();
    expect(screen.queryByText('Why this popped up')).not.toBeInTheDocument();
    expect(screen.getByText('Skill connection')).toBeInTheDocument();
    expect(screen.getByText('Recommended first')).toBeInTheDocument();
    expect(screen.getByText('It supports these selected skills')).toBeInTheDocument();
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

  it('reloads into chapter learning mode after build completion', async () => {
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
      expect(screen.queryByRole('button', { name: /Build My Learning Path/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Build Learning Path/i })).not.toBeInTheDocument();
    });
  });

  it('hides the hero build button after a locked learning path loads', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);

    renderPage();

    expect(await screen.findByText('Chapter 1: Foundations')).toBeInTheDocument();
    expect(screen.getByText('Your saved learning path is ready to study.')).toBeInTheDocument();
    expect(
      screen.queryByText('Your saved learning path is ready to study and rebuild when needed.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Build My Learning Path/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Build Learning Path/i })).not.toBeInTheDocument();
  });

  it('keeps a recovery build button when skills are locked but the learning path is empty', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(emptyLearningPathResponse);
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({
      run_id: 'run-1',
      status: 'started',
    });

    renderPage();

    expect(
      await screen.findByText(
        'Your skill choices are locked in. Build the learning path to finish loading your study surface.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Your skills are already fixed. Build the learning path to finish loading your study surface.',
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Build Learning Path/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, []);
    });
  });

  it('renders chapter gating and known-skill collapse', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(gatingLearningPathResponse);

    renderPage();

    expect(await screen.findByText('Chapter 1: Foundations')).toBeInTheDocument();
    expect(screen.getByText('Quiz required')).toBeInTheDocument();
    expect(screen.getByText('Locked')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Start chapter - take quiz/i })).toHaveAttribute(
      'href',
      '/courses/1/learning-path/chapters/1/quiz',
    );
    expect(screen.getByText('1/1 correct')).toBeInTheDocument();
    expect(screen.queryByText('Batch Systems Guide')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Show Answer/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Batch Processing/i }));
    expect(await screen.findByText('Batch Systems Guide')).toBeInTheDocument();
    expect(screen.getByText('Known · Review anyway')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Retake diagnostic/i })).toHaveAttribute(
      'href',
      '/courses/1/learning-path/chapters/3/quiz',
    );
  });

  it('clicking a video row navigates to the study route and calls trackResourceOpen once', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Batch Processing/i }));
    fireEvent.click(screen.getByRole('button', { name: /Open Batch Systems Video in viewer/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.trackResourceOpen).toHaveBeenCalledTimes(1);
      expect(studentLearningPathApi.trackResourceOpen).toHaveBeenCalledWith(1, {
        resource_type: 'video',
        url: 'https://www.youtube.com/watch?v=batch123',
      });
    });

    expect(await screen.findByText('Study route destination')).toBeInTheDocument();
    expect(screen.getByTestId('pathname')).toHaveTextContent(
      '/courses/1/learning-path/study/video/video-1',
    );
    expect(screen.queryByText('Resource Agent')).not.toBeInTheDocument();
  });

  it('clicking a reading row navigates to the study route and calls trackResourceOpen once', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);

    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /Open Streaming Primer in viewer/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.trackResourceOpen).toHaveBeenCalledWith(1, {
        resource_type: 'reading',
        url: 'https://example.com/streaming',
      });
    });

    expect(await screen.findByText('Study route destination')).toBeInTheDocument();
    expect(screen.getByTestId('pathname')).toHaveTextContent(
      '/courses/1/learning-path/study/reading/reading-2',
    );
    expect(screen.queryByText('Resource Agent')).not.toBeInTheDocument();
  });

  it('opens the secondary source link externally without opening the viewer', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);

    renderPage();

    fireEvent.click(await screen.findByRole('link', { name: /Open source for Streaming Primer/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.trackResourceOpen).toHaveBeenCalledTimes(1);
      expect(studentLearningPathApi.trackResourceOpen).toHaveBeenCalledWith(1, {
        resource_type: 'reading',
        url: 'https://example.com/streaming',
      });
    });

    expect(openWindowSpy).toHaveBeenCalledWith(
      'https://example.com/streaming',
      '_blank',
      'noopener,noreferrer',
    );
    expect(screen.getByTestId('pathname')).toHaveTextContent('/courses/1/learning-path');
    expect(screen.queryByText('Resource Agent')).not.toBeInTheDocument();
    expect(screen.getByText('Chapter 1: Foundations')).toBeInTheDocument();
  });

  it('shows partial current-chapter access while keeping the next chapter locked', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(
      partialProgressLearningPathResponse,
    );

    renderPage();

    expect(await screen.findByText('Chapter 1: Foundations')).toBeInTheDocument();
    expect(screen.getByText('Learning')).toBeInTheDocument();
    expect(screen.getByText('1/2 correct')).toBeInTheDocument();
    expect(screen.getByText('Streaming Primer')).toBeInTheDocument();
    expect(screen.getByText('Chapter 2: Streaming Systems')).toBeInTheDocument();
    expect(screen.getByText('Chapter 2 stays locked until every question in the previous chapter is answered correctly.')).toBeInTheDocument();
  });

  it('renders chapters that currently have no selected skills', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(
      learningPathResponseWithEmptyChapter,
    );

    renderPage();

    expect(await screen.findByText('Chapter 2: Optimization')).toBeInTheDocument();
    expect(screen.getByText('No selected skills in this chapter yet.')).toBeInTheDocument();
    expect(screen.getByText('No selected skills')).toBeInTheDocument();
  });

  it('hides quiz actions and progress for transparent zero-question chapters', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(lockedSkillBanks);
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(
      transparentChapterLearningPathResponse,
    );

    renderPage();

    expect(await screen.findByText('Chapter 2: No Quiz Yet')).toBeInTheDocument();
    expect(screen.getByText('Fresh Skill Guide')).toBeInTheDocument();
    expect(screen.queryByText('0/0 correct')).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: /Retake diagnostic/i })).toHaveLength(1);
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

describe('Task9 stable reference student flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (studentLearningPathApi.streamBuildProgress as Mock).mockReturnValue(() => {});
    (studentLearningPathApi.buildLearningPath as Mock).mockResolvedValue({run_id: 'run-9', status: 'started'});
  });

  it('selects distinct same-label references and builds each ID once across career/book/posting views', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(task9Banks());
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
    expect(screen.getByRole('checkbox', {name: 'Select Batch Processing · Streaming'})).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Select Batch Processing · Streaming'}));
    expect(screen.getByText('2 of 1-35 skills selected')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    await waitFor(() => expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [], [referenceA, referenceB]));
  });

  it('filters posting bulk selection by eligibility using unfiltered members and preserves covered-book identity', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(task9Banks());
    renderPage();
    await screen.findByText('Book Skill Banks');
    fireEvent.change(screen.getByPlaceholderText(/Search books/i), {target: {value: 'Batch'}});
    fireEvent.click(screen.getByRole('button', {name: /Select all.*skills/i}));
    expect(screen.getByText('2 of 1-35 skills selected')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    await waitFor(() => expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [], [referenceA, referenceB]));
  });

  it('cannot select pending or withdrawn references through career or posting chips', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(task9Banks());
    renderPage();
    expect(await screen.findByRole('checkbox', {name: 'Select Pending skill · Foundations'})).toBeDisabled();
    expect(screen.getByRole('checkbox', {name: 'Select Withdrawn skill · Foundations'})).toBeDisabled();
    expect(screen.getByRole('button', {name: /^Pending skill/})).toBeDisabled();
    expect(screen.getByRole('button', {name: /^Withdrawn skill/})).toBeDisabled();
    expect(screen.getByText('0 of 1-35 skills selected')).toBeInTheDocument();
  });

  it('keeps an individual reference exclusion when another posting is selected', async () => {
    const banks = task9Banks();
    banks.market_skill_bank.push({...banks.market_skill_bank[0]!, url: 'https://hh.uz/vacancy/102', title: 'Second posting'});
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(banks);
    renderPage();
    const selectButtons = await screen.findAllByRole('button', {name: /Select all.*skills/i});
    fireEvent.click(selectButtons[0]!);
    fireEvent.click(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
    fireEvent.click(selectButtons[1]!);
    expect(screen.getByText('1 of 1-35 skills selected')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    await waitFor(() => expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [], [referenceB]));
  });

  it('preserves an unavailable draft after a typed build rejection and requires explicit removal', async () => {
    const banks = task9Banks();
    const withdrawn = task9Banks();
    withdrawn.career_skill_bank[0] = careerSkill(referenceA, {available_for_new_selection: false, availability_reason: 'Offering withdrawn'});
    withdrawn.book_skill_banks[0]!.chapters[0]!.skills[0] = {...withdrawn.career_skill_bank[0], name: 'Batch Processing'};
    withdrawn.market_skill_bank[0]!.skills[0] = {...withdrawn.career_skill_bank[0], name: 'Batch Processing'};
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValueOnce(banks).mockResolvedValue(withdrawn);
    (studentLearningPathApi.buildLearningPath as Mock).mockRejectedValue({response: {status: 409, data: {detail: {
      code: 'skill_unavailable', message: 'Offering withdrawn', skill_reference_ids: [referenceA], skill_names: [],
    }}}});
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    await waitFor(() => expect(studentLearningPathApi.getSkillBanks).toHaveBeenCalledTimes(2));
    expect(toast.error).toHaveBeenCalledWith('Offering withdrawn');
    expect(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'})).toBeChecked();
    expect(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'})).toBeEnabled();
    expect(screen.getByRole('button', {name: /Build My Learning Path/i})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
    expect(screen.getByText('0 of 1-35 skills selected')).toBeInTheDocument();
  });

  it('recovers saved reference-only selections after withdrawal with a bodyless build', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue({...task9Banks(), selected_skill_reference_ids: [referenceWithdrawn]});
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(emptyLearningPathResponse);
    renderPage();
    fireEvent.click(await screen.findByRole('button', {name: /Build Learning Path/i}));
    await waitFor(() => expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, []));
    expect(screen.queryByText('Book Skill Banks')).not.toBeInTheDocument();
  });

  it.each(['unchanged', 'failed'] as const)('keeps a reconciliation barrier after an unidentified typed rejection and %s bank refresh', async (refresh) => {
    const banks = task9Banks();
    const rejection = {response: {status: 409, data: {detail: {
      code: 'ambiguous_skill_name', message: 'Selection identity needs reconciliation', skill_reference_ids: [], skill_names: [],
    }}}};
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValueOnce(banks);
    if (refresh === 'failed') (studentLearningPathApi.getSkillBanks as Mock).mockRejectedValue(new Error('Refresh unavailable'));
    else (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue(banks);
    (studentLearningPathApi.buildLearningPath as Mock).mockRejectedValueOnce(rejection);

    try {
      renderPage();
      fireEvent.click(await screen.findByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
      fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
      await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Selection identity needs reconciliation'));
      expect(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'})).toBeChecked();
      const buildButton = screen.getByRole('button', {name: /Build My Learning Path/i});
      expect(buildButton).toBeDisabled();
      expect(screen.getByText('Review unavailable draft selections before building.')).toBeInTheDocument();
      fireEvent.click(buildButton);
      expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByRole('button', {name: /Remove unavailable selection/i}));
      expect(screen.getByText('0 of 1-35 skills selected')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('checkbox', {name: 'Select Batch Processing · Foundations'}));
      expect(screen.getByRole('button', {name: /Build My Learning Path/i})).toBeEnabled();
      expect(consoleError).toHaveBeenCalledWith(rejection);
    } finally {
      consoleError.mockRestore();
    }
  });

  it('shows ambiguous dependent identity and prevents automatic prerequisite addition for a name-only edge', async () => {
    const banks = task9Banks();
    banks.career_skill_bank[2] = careerSkill(referencePending, {label: 'Data foundations'});
    const prerequisiteEdges: studentLearningPathApi.PrerequisiteEdge[] = [{
      prerequisite_name: 'Data foundations', dependent_name: 'Batch Processing',
      prerequisite_skill_reference_id: referencePending,
      confidence: 'high', reasoning: 'Legacy name-only dependent edge',
    }];
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue({...banks, prerequisite_edges: prerequisiteEdges});
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Select Batch Processing · Streaming'}));
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    expect(await screen.findByText('Review prerequisites')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Add to learning path/i})).toBeDisabled();
    expect(screen.getByText(/dependent identity.*ambiguous/i)).toBeInTheDocument();
    expect(screen.getByText('1 of 1-35 skills selected')).toBeInTheDocument();
    expect(studentLearningPathApi.buildLearningPath).not.toHaveBeenCalled();
    const index = buildPrerequisiteIndex(prerequisiteEdges, collectStudentSkills(banks));
    expect(index.get(`reference:${referenceB}`)?.[0]?.dependent_key).toBe('ambiguous:Batch Processing');
  });

  it('resolves prerequisites by reference and prevents adding the unavailable same-label target', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue({...task9Banks(), prerequisite_edges: [{
      prerequisite_name: 'Batch Processing', dependent_name: 'Batch Processing',
      prerequisite_skill_reference_id: referencePending, dependent_skill_reference_id: referenceB,
      confidence: 'high', reasoning: 'Reference-specific foundation',
    }]});
    renderPage();
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Select Batch Processing · Streaming'}));
    fireEvent.click(screen.getByRole('button', {name: /Build My Learning Path/i}));
    expect(await screen.findByText('Review prerequisites')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /Add to learning path/i})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: /I already know this/i}));
    fireEvent.click(screen.getByRole('button', {name: /Continue build/i}));
    await waitFor(() => expect(studentLearningPathApi.buildLearningPath).toHaveBeenCalledWith(1, [], [referenceB]));
    expect(studentLearningPathApi.submitChapterQuiz).not.toHaveBeenCalled();
  });

  it('exposes supporting job links in saved learning content without changing quiz mastery or resources', async () => {
    (studentLearningPathApi.getSkillBanks as Mock).mockResolvedValue({...task9Banks(), selected_skill_reference_ids: [referenceA]});
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue({...learningPathResponse, chapters: [
      {...learningPathResponse.chapters[0], selected_skills: [{...learningPathResponse.chapters[0]!.selected_skills[0], ...careerSkill(), name: 'Batch Processing', is_known: true}]},
    ]});
    renderPage();
    expect(await screen.findByRole('link', {name: /Supporting job posting/i})).toHaveAttribute('href', postingUrl);
    fireEvent.click(screen.getByRole('button', {name: /Batch Processing/i}));
    expect(screen.getByText('Known · Review anyway')).toBeInTheDocument();
    expect(screen.getByText('Batch Systems Guide')).toBeInTheDocument();
  });
});
