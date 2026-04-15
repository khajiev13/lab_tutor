import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, type Mock } from 'vitest';

import ChapterQuizPage from './ChapterQuizPage';
import * as studentLearningPathApi from '../api';

vi.mock('../api', () => ({
  getChapterQuiz: vi.fn(),
  submitChapterQuiz: vi.fn(),
}));

const quizResponse = {
  course_id: 'course-1',
  chapter_index: 1,
  chapter_title: 'Foundations',
  questions: [
    {
      id: 'q-1',
      skill_name: 'Batch Processing',
      text: 'What is batching?',
      options: ['One', 'Two', 'Three', 'Four'],
    },
    {
      id: 'q-2',
      skill_name: 'Streaming Basics',
      text: 'What is a stream?',
      options: ['Alpha', 'Beta', 'Gamma', 'Delta'],
    },
  ],
  previous_answers: {},
};

const retakeQuizResponse = {
  ...quizResponse,
  previous_answers: {
    'q-1': {
      selected_option: 'B',
      answered_right: true,
      answered_at: '2026-04-14T08:00:00Z',
    },
  },
};

function renderPage(initialEntry = '/courses/1/learning-path/chapters/1/quiz') {
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/courses/:id/learning-path/chapters/:chapterIndex/quiz" element={<ChapterQuizPage />} />
        <Route path="/courses/:id/learning-path" element={<div>Learning path destination</div>} />
        <Route path="/courses/:id" element={<div>Course page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ChapterQuizPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with unanswered progress and a disabled submit button', async () => {
    (studentLearningPathApi.getChapterQuiz as Mock).mockResolvedValue(quizResponse);

    renderPage();

    expect(await screen.findByText('Foundations')).toBeInTheDocument();
    expect(screen.getByText('0/2 answered')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Submit quiz/i })).toBeDisabled();

    fireEvent.click(screen.getByRole('radio', { name: /A\. One/i }));

    await waitFor(() => {
      expect(screen.getByText('1/2 answered')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Submit quiz/i })).toBeDisabled();
  });

  it('submits answers and shows the summary dialog', async () => {
    (studentLearningPathApi.getChapterQuiz as Mock).mockResolvedValue(quizResponse);
    (studentLearningPathApi.submitChapterQuiz as Mock).mockResolvedValue({
      chapter_index: 1,
      results: [
        {
          question_id: 'q-1',
          skill_name: 'Batch Processing',
          selected_option: 'A',
          answered_right: true,
          correct_option: 'A',
        },
        {
          question_id: 'q-2',
          skill_name: 'Streaming Basics',
          selected_option: 'B',
          answered_right: false,
          correct_option: 'C',
        },
      ],
      skills_known: ['Batch Processing'],
    });

    renderPage();

    expect(await screen.findByText('Foundations')).toBeInTheDocument();
    expect(screen.queryByText(/Correct answer/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: /A\. One/i }));
    fireEvent.click(screen.getByRole('radio', { name: /B\. Beta/i }));
    fireEvent.click(screen.getByRole('button', { name: /Submit quiz/i }));

    await waitFor(() => {
      expect(studentLearningPathApi.submitChapterQuiz).toHaveBeenCalledWith(1, 1, [
        { question_id: 'q-1', selected_option: 'A' },
        { question_id: 'q-2', selected_option: 'B' },
      ]);
    });

    expect(await screen.findByText('Quiz submitted')).toBeInTheDocument();
    expect(screen.getByText('Known skills')).toBeInTheDocument();
    expect(screen.getAllByText('Batch Processing').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /Continue to learning/i }));
    expect(await screen.findByText('Learning path destination')).toBeInTheDocument();
  });

  it('prefills previous answers on retake', async () => {
    (studentLearningPathApi.getChapterQuiz as Mock).mockResolvedValue(retakeQuizResponse);

    renderPage();

    expect(await screen.findByText('Retake available')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /B\. Two/i })).toHaveAttribute('data-state', 'checked');
    expect(screen.getByText('1/2 answered')).toBeInTheDocument();
  });
});
