import { useEffect } from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import TeacherCourseDetail from '../features/courses/pages/TeacherCourseDetail';
import { coursesApi, presentationsApi, streamExtraction } from '../features/courses/api';
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
    getEmbeddingsStatus: vi.fn(),
    getEnrollment: vi.fn(),
    join: vi.fn(),
    leave: vi.fn(),
  },
  presentationsApi: {
    upload: vi.fn(),
    list: vi.fn(),
    listStatuses: vi.fn(),
  },
  streamExtraction: vi.fn(),
}));

// Mock child components to avoid complex rendering
vi.mock('../components/FileUpload', () => ({
  FileUpload: ({ disabled }: { disabled: boolean }) => (
    <div data-testid="file-upload" data-disabled={disabled}>File Upload</div>
  ),
}));

vi.mock('../components/CourseMaterialsTable', () => ({
  CourseMaterialsTable: ({
    disabled,
    onFilesChange,
  }: {
    disabled: boolean;
    onFilesChange?: (files: string[]) => void;
  }) => {
    // Simulate the table being loaded and informing the parent.
    useEffect(() => {
      onFilesChange?.(mockPresentationFiles);
    }, [onFilesChange]);
    return (
      <div data-testid="course-materials-table" data-disabled={disabled}>
        Course Materials Table
      </div>
    );
  },
}));

vi.mock('../features/book-selection', () => ({
  BookSelectionDashboard: ({ courseId }: { courseId: number }) => (
    <div data-testid="book-selection-dashboard" data-course-id={courseId}>Book Selection</div>
  ),
  BookAnalysisTab: ({ courseId }: { courseId: number }) => (
    <div data-testid="book-analysis-tab" data-course-id={courseId}>Book Analysis</div>
  ),
  BookVisualizationTab: ({ courseId }: { courseId: number }) => (
    <div data-testid="book-visualization-tab" data-course-id={courseId}>Book Visualization</div>
  ),
}));

vi.mock('../features/book-selection/api', () => ({
  getLatestSession: vi.fn().mockResolvedValue(null),
  getLatestAnalysis: vi.fn().mockResolvedValue(null),
}));

vi.mock('../features/normalization/components/NormalizationDashboard', () => ({
  NormalizationDashboard: ({
    courseId,
    disabled,
  }: {
    courseId: number;
    disabled?: boolean;
  }) => (
    <div data-testid="normalization-dashboard" data-course-id={courseId} data-disabled={disabled}>
      Normalization Dashboard
    </div>
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
    mockPresentationFiles = [];
    (presentationsApi.listStatuses as Mock).mockResolvedValue([]);
    (coursesApi.getEmbeddingsStatus as Mock).mockResolvedValue({
      course_id: 1,
      extraction_status: 'finished',
      embedding_status: 'not_started',
      embedding_started_at: null,
      embedding_finished_at: null,
      embedding_last_error: null,
      files: [],
    });
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
    (streamExtraction as Mock).mockImplementation(() => {});
    mockPresentationFiles = ['lecture1.pdf'];

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Start Data Extraction')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start Data Extraction'));

    await waitFor(() => {
      expect(streamExtraction).toHaveBeenCalledWith(
        expect.objectContaining({ courseId: 1 })
      );
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
    // SSE auto-connects when status is in_progress
    (streamExtraction as Mock).mockImplementation(() => {});

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Extracting Data...')).toBeInTheDocument();
    });

    // Check if child components received disabled prop
    const upload = screen.getByTestId('file-upload');
    const list = screen.getByTestId('course-materials-table');

    expect(upload).toHaveAttribute('data-disabled', 'true');
    expect(list).toHaveAttribute('data-disabled', 'true');

    // Check for locked message
    expect(screen.getByText('File Management Locked')).toBeInTheDocument();
  });

  it('calls getEmbeddingsStatus when on materials tab with finished extraction', async () => {
    const finishedCourse = { ...mockCourse, extraction_status: 'finished' };
    (coursesApi.getCourse as Mock).mockResolvedValue(finishedCourse);

    renderComponent();

    await waitFor(() => {
      expect(coursesApi.getEmbeddingsStatus).toHaveBeenCalledWith(1);
    });
  });

  it('does not call getEmbeddingsStatus after switching away from materials tab', async () => {
    const finishedCourse = { ...mockCourse, extraction_status: 'finished' };
    (coursesApi.getCourse as Mock).mockResolvedValue(finishedCourse);

    renderComponent();

    // Wait for the initial call on the default materials tab
    await waitFor(() => {
      expect(coursesApi.getEmbeddingsStatus).toHaveBeenCalledTimes(1);
    });

    // Switch to a different step (Normalization = step 2)
    fireEvent.click(screen.getByRole('button', { name: /go to step 2/i }));

    // Wait a tick to let any React effects settle
    await act(async () => {});

    // No additional calls should have been made
    expect(coursesApi.getEmbeddingsStatus).toHaveBeenCalledTimes(1);
  });

  it('receives SSE complete event and updates UI', async () => {
    const inProgressCourse = { ...mockCourse, extraction_status: 'in_progress' };

    // Capture the onComplete callback when streamExtraction is called
    let capturedOnComplete: ((event: unknown) => void) | undefined;
    (streamExtraction as Mock).mockImplementation(({ onComplete }) => {
      capturedOnComplete = onComplete;
    });

    const getCourseMock = coursesApi.getCourse as Mock;
    getCourseMock.mockResolvedValue(inProgressCourse);

    (coursesApi.getEmbeddingsStatus as Mock).mockResolvedValue({
      course_id: 1,
      extraction_status: 'finished',
      embedding_status: 'completed',
      embedding_started_at: null,
      embedding_finished_at: null,
      embedding_last_error: null,
      files: [],
    });

    renderComponent();

    expect(await screen.findByText('Extracting Data...')).toBeInTheDocument();

    // SSE should have been connected automatically
    await waitFor(() => {
      expect(streamExtraction).toHaveBeenCalled();
    });
    expect(capturedOnComplete).toBeDefined();

    // Simulate the SSE complete event
    await act(async () => {
      capturedOnComplete?.({
        total: 38,
        processed: 38,
        failed: 0,
        terminal: 38,
        value: 100,
        status: 'finished',
        files: [],
      });
    });

    expect(await screen.findByText('Extraction Complete')).toBeInTheDocument();
  });
});
