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
    const list = screen.getByTestId('course-materials-table');

    expect(upload).toHaveAttribute('data-disabled', 'true');
    expect(list).toHaveAttribute('data-disabled', 'true');

    // Check for locked message
    expect(screen.getByText('File Management Locked')).toBeInTheDocument();
  });

  it('polls for status updates', async () => {
    const inProgressCourse = { ...mockCourse, extraction_status: 'in_progress' };
    const finishedCourse = { ...mockCourse, extraction_status: 'finished' };

    const intervals: Array<{ callback: () => unknown; delay: number | undefined }> = [];
    const setIntervalSpy = vi
      .spyOn(globalThis, 'setInterval')
      .mockImplementation(((callback: (...args: unknown[]) => unknown, delay?: number) => {
        intervals.push({
          callback: callback as unknown as () => unknown,
          delay,
        });
        return 1 as unknown as ReturnType<typeof setInterval>;
      }) as unknown as typeof setInterval);
    const clearIntervalSpy = vi
      .spyOn(globalThis, 'clearInterval')
      .mockImplementation((() => {}) as unknown as typeof clearInterval);

    // Setup mock responses
    const getCourseMock = coursesApi.getCourse as Mock;
    getCourseMock
      .mockResolvedValueOnce(inProgressCourse) // Initial load
      .mockResolvedValueOnce(inProgressCourse) // Poll 1
      .mockResolvedValueOnce(finishedCourse) // Poll 2
      .mockResolvedValue(finishedCourse);

    // Ensure the embeddings polling interval (started after extraction finishes)
    // terminates quickly so fake timers don't keep running.
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

    try {
      expect(await screen.findByText('Extracting Data...')).toBeInTheDocument();
      expect(getCourseMock).toHaveBeenCalledTimes(1);

      // First interval is the extraction polling loop.
      await waitFor(() => {
        expect(intervals.length).toBeGreaterThan(0);
      });
      const pollIntervalMs = 10_000;
      const extractionPoll = intervals.find((i) => i.delay === pollIntervalMs)?.callback;
      expect(extractionPoll).toBeDefined();

      // Poll 1 (still in progress)
      await act(async () => {
        await extractionPoll?.();
      });
      expect(getCourseMock).toHaveBeenCalledTimes(2);

      // Poll 2 (finished)
      await act(async () => {
        await extractionPoll?.();
      });
      expect(getCourseMock).toHaveBeenCalledTimes(3);

      expect(await screen.findByText('Extraction Complete')).toBeInTheDocument();
    } finally {
      setIntervalSpy.mockRestore();
      clearIntervalSpy.mockRestore();
    }
  });
});
