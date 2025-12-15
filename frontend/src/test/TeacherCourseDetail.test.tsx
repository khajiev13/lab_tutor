import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import TeacherCourseDetail from '../pages/TeacherCourseDetail';
import { coursesApi } from '../services/api';
import { vi, type Mock } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock APIs
vi.mock('../services/api', () => ({
  coursesApi: {
    getCourse: vi.fn(),
    startExtraction: vi.fn(),
  },
  presentationsApi: {
    upload: vi.fn(),
    list: vi.fn(), // Mocked because PresentationList uses it
  },
}));

// Mock child components to avoid complex rendering
vi.mock('../components/FileUpload', () => ({
  FileUpload: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="file-upload" data-disabled={disabled}>File Upload</div>
  ),
}));

vi.mock('../components/PresentationList', () => ({
  PresentationList: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="presentation-list" data-disabled={disabled}>Presentation List</div>
  ),
}));

const mockCourse = {
  id: 1,
  title: 'Test Course',
  description: 'Test Description',
  teacher_id: 1,
  created_at: '2023-01-01T00:00:00Z',
  extraction_status: 'not_started',
};

describe('TeacherCourseDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderComponent = () => {
    render(
      <MemoryRouter initialEntries={['/courses/1']}>
        <Routes>
          <Route path="/courses/:id" element={<TeacherCourseDetail />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it('renders course details', async () => {
    (coursesApi.getCourse as Mock).mockResolvedValue(mockCourse);
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Course')).toBeInTheDocument();
      expect(screen.getByText('Test Description')).toBeInTheDocument();
      expect(screen.getByText('Ready to Extract')).toBeInTheDocument();
    });
  });

  it('starts extraction when button is clicked', async () => {
    (coursesApi.getCourse as Mock).mockResolvedValue(mockCourse);
    (coursesApi.startExtraction as Mock).mockResolvedValue({ 
      message: 'Started', 
      status: 'in_progress' 
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Start Data Extraction')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start Data Extraction'));

    await waitFor(() => {
      expect(coursesApi.startExtraction).toHaveBeenCalledWith(1);
    });
  });

  it('locks UI when extraction is in progress', async () => {
    const inProgressCourse = { ...mockCourse, extraction_status: 'in_progress' };
    (coursesApi.getCourse as Mock).mockResolvedValue(inProgressCourse);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Extracting Data...')).toBeInTheDocument();
    });

    // Check if child components received disabled prop
    const upload = screen.getByTestId('file-upload');
    const list = screen.getByTestId('presentation-list');

    expect(upload).toHaveAttribute('data-disabled', 'true');
    expect(list).toHaveAttribute('data-disabled', 'true');

    // Check for locked message
    expect(screen.getByText('File Management Locked')).toBeInTheDocument();
  });

  it('polls for status updates', async () => {
    // Only fake setInterval so waitFor (which uses setTimeout) works normally
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    const inProgressCourse = { ...mockCourse, extraction_status: 'in_progress' };
    const finishedCourse = { ...mockCourse, extraction_status: 'finished' };

    // Setup mock responses
    const getCourseMock = coursesApi.getCourse as Mock;
    getCourseMock
      .mockResolvedValueOnce(inProgressCourse) // Initial load
      .mockResolvedValueOnce(inProgressCourse) // Poll 1
      .mockResolvedValueOnce(finishedCourse);  // Poll 2

    renderComponent();

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText('Extracting Data...')).toBeInTheDocument();
    });

    // Advance time for first poll (3s)
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Advance time for second poll (3s)
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });

    // Should be finished now
    await waitFor(() => {
      expect(screen.getByText('Extraction Complete')).toBeInTheDocument();
    });

    vi.useRealTimers();
  });
});
