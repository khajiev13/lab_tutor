import { useEffect } from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import TeacherCourseDetail from '../features/courses/pages/TeacherCourseDetail';
import { coursesApi, presentationsApi } from '../features/courses/api';
import { vi, type Mock } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

let mockPresentationFiles: string[] = [];

// Mock Auth Context
vi.mock('../features/auth/context/AuthContext', () => ({
  useAuth: () => ({
    user: { role: 'teacher', id: 1, email: 'teacher@test.com' },
    isAuthenticated: true,
  }),
}));

// Mock APIs
vi.mock('../features/courses/api', () => ({
  coursesApi: {
    getCourse: vi.fn(),
    startExtraction: vi.fn(),
    getEnrollment: vi.fn(),
    join: vi.fn(),
    leave: vi.fn(),
  },
  presentationsApi: {
    upload: vi.fn(),
    list: vi.fn(),
    listStatuses: vi.fn(),
  },
}));

// Mock child components to avoid complex rendering
vi.mock('../components/FileUpload', () => ({
  FileUpload: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="file-upload" data-disabled={disabled}>File Upload</div>
  ),
}));

vi.mock('../components/PresentationList', () => ({
  PresentationList: ({ disabled, onFilesChange }: { disabled: boolean; onFilesChange?: (files: string[]) => void }) => {
    // Simulate the list being loaded and informing the parent.
    useEffect(() => {
      onFilesChange?.(mockPresentationFiles);
    }, [onFilesChange]);
    return (
      <div data-testid="presentation-list" data-disabled={disabled}>Presentation List</div>
    );
  },
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
    mockPresentationFiles = [];
    (presentationsApi.listStatuses as Mock).mockResolvedValue([]);
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
    mockPresentationFiles = ['lecture1.pdf'];

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Start Data Extraction')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start Data Extraction'));

    await waitFor(() => {
      expect(coursesApi.startExtraction).toHaveBeenCalledWith(1);
    });
  });

  it('does not show extraction button when no files uploaded', async () => {
    (coursesApi.getCourse as Mock).mockResolvedValue(mockCourse);
    mockPresentationFiles = [];

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Test Course')).toBeInTheDocument();
    });

    expect(screen.queryByText('Start Data Extraction')).not.toBeInTheDocument();
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

    // Advance time for first poll (1.5s)
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    // Advance time for second poll (1.5s)
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });

    // Should be finished now
    await waitFor(() => {
      expect(screen.getByText('Extraction Complete')).toBeInTheDocument();
    });

    vi.useRealTimers();
  });
});
