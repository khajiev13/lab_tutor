import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, type Mock } from 'vitest';

import { coursesApi } from '@/features/courses/api';
import CurriculumPage from '@/features/curriculum/pages/CurriculumPage';

vi.mock('@/features/courses/api', () => ({
  coursesApi: {
    getCourse: vi.fn(),
    getSkillBanks: vi.fn(),
    getStudentInsights: vi.fn(),
    getStudentInsightDetail: vi.fn(),
    updateSkillSelectionRange: vi.fn(),
  },
}));

vi.mock('@/features/curriculum/components/StudentInsightSidebarCard', () => ({
  StudentInsightSidebarCard: ({
    overview,
    selectedStudentId,
    onSelectStudent,
    detail,
  }: {
    overview: {
      students: Array<{ id: number; full_name: string }>;
    };
    selectedStudentId: string | null;
    onSelectStudent: (value: string) => void;
    detail: {
      student: {
        email: string;
      };
    } | null;
  }) => (
    <div>
      <p>Student drill-down mock</p>
      <p>Selected student id: {selectedStudentId ?? 'none'}</p>
      {detail && <p>{detail.student.email}</p>}
      {overview.students.map((student) => (
        <button key={student.id} onClick={() => onSelectStudent(String(student.id))}>
          Pick {student.full_name}
        </button>
      ))}
    </div>
  ),
}));

const courseResponse = {
  id: 2,
  title: 'Data Systems Lab',
  description: 'Transcript-driven systems course',
  teacher_id: 7,
  created_at: '2026-04-20T00:00:00Z',
  extraction_status: 'finished',
};

const teacherSkillBanks = {
  course_chapters: [
    {
      chapter_index: 1,
      title: 'Foundations',
      description: 'Intro chapter',
      learning_objectives: ['Explain distributed systems'],
      documents: [{ topic: 'Lecture 1', source_filename: 'lecture-1.pdf' }],
    },
  ],
  book_skill_bank: [
    {
      book_id: 'book-1',
      title: 'Distributed Systems',
      authors: 'T. Author',
      chapters: [
        {
          chapter_id: 'chapter-1',
          title: 'Foundations',
          chapter_index: 1,
          skills: [{ name: 'Batch Processing', description: 'Learn batch systems.' }],
        },
      ],
    },
  ],
  market_skill_bank: [
    {
      title: 'Platform Engineer',
      company: 'Acme',
      site: 'LinkedIn',
      url: 'https://jobs.example/platform',
      search_term: 'platform engineer',
      skills: [
        {
          name: 'Kafka',
          category: 'data',
          status: 'gap',
          priority: 'high',
          demand_pct: 83,
        },
      ],
    },
  ],
  selection_range: {
    min_skills: 20,
    max_skills: 35,
    is_default: true,
  },
};

const studentInsightsOverview = {
  summary: {
    students_with_selections: 2,
    students_with_learning_paths: 2,
    avg_selected_skill_count: 1.5,
    top_selected_skills: [{ name: 'Kafka', student_count: 2 }],
    top_interested_postings: [
      {
        url: 'https://jobs.example/platform',
        title: 'Platform Engineer',
        company: 'Acme',
        student_count: 2,
      },
    ],
  },
  students: [
    {
      id: 11,
      full_name: 'Dana Demostudent',
      email: 'dana@example.com',
      selected_skill_count: 2,
      interested_posting_count: 1,
      has_learning_path: true,
    },
    {
      id: 12,
      full_name: 'Alex Example',
      email: 'alex@example.com',
      selected_skill_count: 1,
      interested_posting_count: 0,
      has_learning_path: true,
    },
  ],
};

const danaDetail = {
  student: {
    id: 11,
    full_name: 'Dana Demostudent',
    email: 'dana@example.com',
  },
  skill_banks: {
    book_skill_banks: [
      {
        book_id: 'book-1',
        title: 'Distributed Systems',
        authors: 'T. Author',
        chapters: [
          {
            chapter_id: 'chapter-1',
            title: 'Foundations',
            chapter_index: 1,
            skills: [
              {
                name: 'Batch Processing',
                description: 'Learn batch systems.',
                is_selected: false,
                peer_count: 2,
              },
            ],
          },
        ],
      },
    ],
    market_skill_bank: [
      {
        title: 'Platform Engineer',
        company: 'Acme',
        site: 'LinkedIn',
        url: 'https://jobs.example/platform',
        search_term: 'platform engineer',
        is_interested: true,
        skills: [
          {
            name: 'Kafka',
            description: 'Event streaming',
            category: 'data',
            is_selected: true,
            peer_count: 3,
          },
        ],
      },
    ],
    selected_skill_names: ['Kafka'],
    interested_posting_urls: ['https://jobs.example/platform'],
    peer_selection_counts: { Kafka: 3 },
    selection_range: {
      min_skills: 20,
      max_skills: 35,
      is_default: true,
    },
    prerequisite_edges: [],
  },
  learning_path_summary: {
    has_learning_path: true,
    total_selected_skills: 2,
    skills_with_resources: 1,
    chapter_status_counts: {
      locked: 0,
      quiz_required: 1,
      learning: 0,
      completed: 1,
    },
  },
};

const alexDetail = {
  student: {
    id: 12,
    full_name: 'Alex Example',
    email: 'alex@example.com',
  },
  skill_banks: {
    book_skill_banks: [
      {
        book_id: 'book-1',
        title: 'Distributed Systems',
        authors: 'T. Author',
        chapters: [
          {
            chapter_id: 'chapter-1',
            title: 'Foundations',
            chapter_index: 1,
            skills: [
              {
                name: 'Batch Processing',
                description: 'Learn batch systems.',
                is_selected: true,
                peer_count: 2,
              },
            ],
          },
        ],
      },
    ],
    market_skill_bank: [
      {
        title: 'Platform Engineer',
        company: 'Acme',
        site: 'LinkedIn',
        url: 'https://jobs.example/platform',
        search_term: 'platform engineer',
        is_interested: false,
        skills: [
          {
            name: 'Kafka',
            description: 'Event streaming',
            category: 'data',
            is_selected: false,
            peer_count: 3,
          },
        ],
      },
    ],
    selected_skill_names: ['Batch Processing'],
    interested_posting_urls: [],
    peer_selection_counts: { 'Batch Processing': 2, Kafka: 3 },
    selection_range: {
      min_skills: 20,
      max_skills: 35,
      is_default: true,
    },
    prerequisite_edges: [],
  },
  learning_path_summary: {
    has_learning_path: true,
    total_selected_skills: 1,
    skills_with_resources: 1,
    chapter_status_counts: {
      locked: 1,
      quiz_required: 0,
      learning: 0,
      completed: 1,
    },
  },
};

function renderCurriculumPage() {
  return render(
    <MemoryRouter initialEntries={['/courses/2/curriculum']}>
      <Routes>
        <Route path="/courses/:id/curriculum" element={<CurriculumPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CurriculumPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (coursesApi.getCourse as Mock).mockResolvedValue(courseResponse);
    (coursesApi.updateSkillSelectionRange as Mock).mockResolvedValue(teacherSkillBanks.selection_range);
  });

  it('renders a course-first shell with transcript-first stats', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue(teacherSkillBanks);
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    expect(await screen.findByRole('heading', { name: 'Data Systems Lab' })).toBeInTheDocument();
    expect(screen.getByText('Course Chapters')).toBeInTheDocument();
    expect(screen.getByText('Transcript Files')).toBeInTheDocument();
    expect(screen.getAllByText('Book Skills').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Market Skills').length).toBeGreaterThan(0);
    expect(screen.getByText('Job Postings')).toBeInTheDocument();
    expect(screen.queryByText('Gaps')).not.toBeInTheDocument();
  });

  it('renders the student activity overview and auto-selects the first active student', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue(teacherSkillBanks);
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    expect(await screen.findByText('Student Activity')).toBeInTheDocument();
    expect(await screen.findByText('dana@example.com')).toBeInTheDocument();
    await waitFor(() => {
      expect(coursesApi.getStudentInsightDetail).toHaveBeenCalledWith(2, 11);
    });
  });

  it('switches overlay badges when the teacher picks a different student', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue(teacherSkillBanks);
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockImplementation((_courseId: number, studentId: number) =>
      studentId === 11 ? Promise.resolve(danaDetail) : Promise.resolve(alexDetail),
    );

    renderCurriculumPage();

    expect(await screen.findByText('dana@example.com')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Pick Alex Example' }));

    await waitFor(() => {
      expect(coursesApi.getStudentInsightDetail).toHaveBeenCalledWith(2, 12);
    });
    expect(await screen.findByText('alex@example.com')).toBeInTheDocument();
    expect(screen.queryByText('dana@example.com')).not.toBeInTheDocument();
  });

  it('shows teacher market data without legacy gap labels', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue(teacherSkillBanks);
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    fireEvent.click(await screen.findByRole('tab', { name: /Market Skills/i }));

    expect(await screen.findByText('Platform Engineer')).toBeInTheDocument();
    expect(screen.getByText('Kafka')).toBeInTheDocument();
    expect(screen.queryByText('Gap')).not.toBeInTheDocument();
    expect(screen.queryByText('New Topic')).not.toBeInTheDocument();
    expect(screen.queryByText('Covered')).not.toBeInTheDocument();
  });

  it('keeps the stat cards aligned with the visible market overlay', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue({
      ...teacherSkillBanks,
      market_skill_bank: [],
    });
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    expect(await screen.findByText('dana@example.com')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Market Skills/i }));
    expect(await screen.findByText('Platform Engineer')).toBeInTheDocument();

    const marketSkillsLabel = screen
      .getAllByText('Market Skills')
      .find((element) => element.tagName === 'P');
    const marketSkillsStat = marketSkillsLabel?.parentElement;
    const jobPostingsStat = screen.getByText('Job Postings').parentElement;

    expect(marketSkillsLabel).toBeDefined();
    expect(marketSkillsStat).not.toBeNull();
    expect(jobPostingsStat).not.toBeNull();

    expect(within(marketSkillsStat as HTMLElement).getByText('1')).toBeInTheDocument();
    expect(within(jobPostingsStat as HTMLElement).getByText('1')).toBeInTheDocument();
  });

  it('shows section warnings without falling into the full-page empty state when skill banks fail', async () => {
    (coursesApi.getSkillBanks as Mock).mockRejectedValue(new Error('neo4j down'));
    (coursesApi.getStudentInsights as Mock).mockResolvedValue(studentInsightsOverview);
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    expect(await screen.findByText('Student Activity')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Transcripts/i }));
    expect(await screen.findByText('Transcript bank unavailable')).toBeInTheDocument();
    expect(screen.queryByText('No course chapters built yet')).not.toBeInTheDocument();
  });

  it('shows the full empty state only when skill banks load as empty', async () => {
    (coursesApi.getSkillBanks as Mock).mockResolvedValue({
      course_chapters: [],
      book_skill_bank: [],
      market_skill_bank: [],
      selection_range: {
        min_skills: 20,
        max_skills: 35,
        is_default: true,
      },
    });
    (coursesApi.getStudentInsights as Mock).mockResolvedValue({
      summary: {
        students_with_selections: 0,
        students_with_learning_paths: 0,
        avg_selected_skill_count: 0,
        top_selected_skills: [],
        top_interested_postings: [],
      },
      students: [],
    });
    (coursesApi.getStudentInsightDetail as Mock).mockResolvedValue(danaDetail);

    renderCurriculumPage();

    expect(await screen.findByText('No course chapters built yet')).toBeInTheDocument();
    expect(screen.getByText('Student Activity')).toBeInTheDocument();
    expect(coursesApi.getStudentInsightDetail).not.toHaveBeenCalled();
  });
});
