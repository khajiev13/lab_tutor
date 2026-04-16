import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, type Mock } from 'vitest';

import StudentLearningPathStudyPage from './StudentLearningPathStudyPage';
import * as studentLearningPathApi from '../api';

vi.mock('../api', () => ({
  getLearningPath: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
  },
}));

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
          name: 'Streaming Basics',
          source: 'book',
          description: 'Understand event streams.',
          skill_type: 'book',
          concepts: [],
          readings: [
            {
              id: 'reading-1',
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
            {
              id: 'reading-pdf',
              title: 'Streaming Whitepaper PDF',
              url: 'https://example.com/streaming.pdf',
              domain: 'example.com',
              snippet: '',
              search_content: '',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'pdf',
              final_score: 0.5,
              concepts_covered: [],
            },
          ],
          videos: [
            {
              id: 'video-1',
              title: 'Streaming Basics Video',
              url: 'https://www.youtube.com/watch?v=stream123',
              domain: 'youtube.com',
              snippet: '',
              search_content: '',
              video_id: 'stream123',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'video',
              final_score: 0.85,
              concepts_covered: [],
            },
            {
              id: 'video-2',
              title: 'Streaming Basics Backup Video',
              url: 'https://www.youtube.com/watch?v=stream456',
              domain: 'youtube.com',
              snippet: '',
              search_content: '',
              video_id: '',
              search_result_url: '',
              search_result_domain: '',
              source_engine: '',
              source_engines: [],
              search_metadata_json: '[]',
              resource_type: 'video',
              final_score: 0.75,
              concepts_covered: [],
            },
          ],
          questions: [],
          is_known: false,
          resource_status: 'loaded',
        },
      ],
    },
    {
      title: 'Locked Systems',
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
          readings: [
            {
              id: 'locked-reading',
              title: 'Locked Reading',
              url: 'https://example.com/locked',
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

function renderStudyPage({
  initialEntries = ['/courses/1/learning-path/study/reading/reading-1'],
  initialIndex,
  routePath = '/courses/:id/learning-path/study/:resourceKind/:resourceId',
}: {
  initialEntries?: Array<string | { pathname: string; state?: unknown }>;
  initialIndex?: number;
  routePath?: string;
} = {}) {
  render(
    <MemoryRouter initialEntries={initialEntries} initialIndex={initialIndex}>
      <Routes>
        <Route path={routePath} element={<StudentLearningPathStudyPage />} />
        <Route path="/courses/:id/learning-path" element={<div>Learning path destination</div>} />
        <Route path="/courses/:id" element={<div>Course destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('StudentLearningPathStudyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (studentLearningPathApi.getLearningPath as Mock).mockResolvedValue(learningPathResponse);
  });

  it('renders the reading iframe and hides the loader after the iframe loads', async () => {
    renderStudyPage();

    await waitFor(() => {
      expect(studentLearningPathApi.getLearningPath).toHaveBeenCalledWith(1);
    });

    expect(screen.getByTestId('study-page-shell')).toHaveClass(
      'h-svh',
      'min-h-svh',
      'p-3',
      'md:p-4',
    );
    expect(screen.getByTestId('study-page-layout')).toHaveClass(
      'flex-1',
      'min-h-0',
      'xl:grid-cols-[minmax(0,1fr)_22rem]',
    );
    expect(screen.getByTestId('resource-viewer-pane')).toHaveClass('h-full', 'min-h-0');

    const iframe = await screen.findByTitle('Streaming Primer');
    expect(iframe).toHaveAttribute('src', 'https://example.com/streaming');
    expect(iframe).toHaveAttribute(
      'sandbox',
      'allow-scripts allow-same-origin allow-popups',
    );
    expect(screen.getByRole('status', { name: /Loading reading/i })).toBeInTheDocument();

    fireEvent.load(iframe);

    await waitFor(() => {
      expect(screen.queryByRole('status', { name: /Loading reading/i })).not.toBeInTheDocument();
    });
  });

  it('renders a YouTube embed for video study routes', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/video/video-1'],
    });

    const iframe = await screen.findByTitle('Streaming Basics Video');
    expect(iframe).toHaveAttribute(
      'src',
      'https://www.youtube.com/embed/stream123?rel=0',
    );
  });

  it('renders a fallback when the video cannot be embedded', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/video/video-2'],
    });

    expect(await screen.findByText('Video unavailable in-app')).toBeInTheDocument();
    expect(
      screen.getByText('This video does not have an embeddable YouTube identifier yet.'),
    ).toBeInTheDocument();
  });

  it('renders the resource agent pane with desktop-only classes', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/video/video-1'],
    });

    expect(await screen.findByText('Resource Agent')).toBeInTheDocument();
    expect(screen.getByTestId('resource-agent-pane')).toHaveClass(
      'hidden',
      'h-full',
      'min-h-0',
      'md:flex',
      'md:flex-col',
    );
  });

  it('close viewer returns to the previous page when navigation history is available', async () => {
    renderStudyPage({
      initialEntries: [
        '/courses/1/learning-path',
        {
          pathname: '/courses/1/learning-path/study/reading/reading-1',
          state: { fromLearningPath: true },
        },
      ],
      initialIndex: 1,
    });

    expect(await screen.findByTitle('Streaming Primer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Close viewer/i }));

    expect(await screen.findByText('Learning path destination')).toBeInTheDocument();
  });

  it('close viewer falls back to the learning-path route when there is no history entry', async () => {
    renderStudyPage();

    expect(await screen.findByTitle('Streaming Primer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Close viewer/i }));

    expect(await screen.findByText('Learning path destination')).toBeInTheDocument();
  });

  it('shows a safe fallback for invalid resource kinds and missing resource ids', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/audio/reading-1'],
    });

    expect(await screen.findByText('Invalid study link')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Return to learning path/i })).toHaveAttribute(
      'href',
      '/courses/1/learning-path',
    );

    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/reading'],
      routePath: '/courses/:id/learning-path/study/:resourceKind/:resourceId?',
    });

    expect(await screen.findAllByText('Invalid study link')).toHaveLength(2);
  });

  it('shows a safe fallback when the requested resource is filtered out', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/reading/reading-pdf'],
    });

    expect(await screen.findByText('Resource not available for study')).toBeInTheDocument();
  });

  it('shows a safe fallback when the requested resource is outside the accessible learning path', async () => {
    renderStudyPage({
      initialEntries: ['/courses/1/learning-path/study/reading/locked-reading'],
    });

    expect(await screen.findByText('Resource not available for study')).toBeInTheDocument();
  });
});
