/**
 * Tests for CourseDetailContext — specifically the step-status computation
 * and auto-navigation logic added for the stepper feature.
 */
import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";

import { CourseDetailProvider, useCourseDetail } from "./CourseDetailContext";
import type { Course } from "../types";
import type { BookSelectionSession } from "@/features/book-selection/types";
import type { BookExtractionRun } from "@/features/book-selection/types";

/* ── Mocks ──────────────────────────────────────────────────── */

// Mock the courses API
const mockGetCourse = vi.fn<(id: number) => Promise<Course>>();
const mockGetEmbeddingsStatus = vi.fn().mockResolvedValue(null);

vi.mock("../api", () => ({
  coursesApi: {
    getCourse: (...args: Parameters<typeof mockGetCourse>) => mockGetCourse(...args),
    getEmbeddingsStatus: (...args: unknown[]) => mockGetEmbeddingsStatus(...args),
  },
  streamExtraction: vi.fn(),
}));

// Mock book-selection API
const mockGetLatestSession = vi.fn<(courseId: number) => Promise<BookSelectionSession | null>>();
const mockGetLatestAnalysis = vi.fn<(courseId: number) => Promise<BookExtractionRun | null>>();

vi.mock("@/features/book-selection/api", () => ({
  getLatestSession: (...args: Parameters<typeof mockGetLatestSession>) =>
    mockGetLatestSession(...args),
  getLatestAnalysis: (...args: Parameters<typeof mockGetLatestAnalysis>) =>
    mockGetLatestAnalysis(...args),
}));

// Suppress toast calls
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

/* ── Helpers ────────────────────────────────────────────────── */

function makeCourse(overrides: Partial<Course> = {}): Course {
  return {
    id: 1,
    title: "Test Course",
    teacher_id: 1,
    created_at: "2025-01-01T00:00:00Z",
    extraction_status: "finished",
    ...overrides,
  };
}

function makeSession(overrides: Partial<BookSelectionSession> = {}): BookSelectionSession {
  return {
    id: 1,
    course_id: 1,
    thread_id: "t-1",
    status: "completed",
    course_level: "bachelor",
    weights_json: null,
    progress_scored: 0,
    progress_total: 0,
    error_message: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeRun(overrides: Partial<BookExtractionRun> = {}): BookExtractionRun {
  return {
    id: 1,
    course_id: 1,
    status: "completed",
    error_message: null,
    progress_detail: null,
    embedding_model: null,
    embedding_dims: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  return <CourseDetailProvider courseId={1}>{children}</CourseDetailProvider>;
}

/* ── Tests ──────────────────────────────────────────────────── */

beforeEach(() => {
  vi.clearAllMocks();
  // Default: extraction finished, no session/analysis
  mockGetCourse.mockResolvedValue(makeCourse());
  mockGetLatestSession.mockResolvedValue(null);
  mockGetLatestAnalysis.mockResolvedValue(null);
});

describe("getStepStatus", () => {
  it("returns 'active' for materials when extraction not started", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.getStepStatus(0)).toBe("active");
  });

  it("returns 'active' for materials when extraction in progress", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "in_progress" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.getStepStatus(0)).toBe("active");
  });

  it("returns 'completed' for materials when extraction finished", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.getStepStatus(0)).toBe("completed");
  });

  it("locks all steps after materials when extraction not done", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.getStepStatus(1)).toBe("locked");
    expect(result.current.getStepStatus(2)).toBe("locked");
    expect(result.current.getStepStatus(3)).toBe("locked");
    expect(result.current.getStepStatus(4)).toBe("locked");
  });

  it("unlocks normalization/book-selection as pending after extraction", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Without backend statuses, steps 1-4 should be pending (unlocked)
    expect(result.current.getStepStatus(1)).toBe("pending");
    expect(result.current.getStepStatus(2)).toBe("pending");
  });

  it("marks book-selection 'completed' when session status is completed", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "completed" }));
    mockGetLatestAnalysis.mockResolvedValue(null);

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(2)).toBe("completed"));
  });

  it("marks normalization 'completed' when book-selection is completed (inferred)", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "completed" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(1)).toBe("completed"));
  });

  it("marks book-selection 'active' when session is discovering", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "discovering" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(2)).toBe("active"));
  });

  it("marks book-selection 'active' when session is scoring", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "scoring" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(2)).toBe("active"));
  });

  it("marks book-selection 'active' when session is downloading", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "downloading" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(2)).toBe("active"));
  });

  it("marks analysis 'completed' when run status is completed", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "completed" }));
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "completed" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("completed"));
  });

  it("marks analysis 'completed' when run status is agentic_completed", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "agentic_completed" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("completed"));
  });

  it("marks analysis 'completed' when run status is book_picked", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "book_picked" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("completed"));
  });

  it("marks analysis 'active' when run is extracting", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "extracting" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("active"));
  });

  it("marks analysis 'active' when run is agentic_extracting", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "agentic_extracting" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("active"));
  });

  it("marks analysis 'active' when run is chunking", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "chunking" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("active"));
  });

  it("marks analysis 'active' when run is embedding", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "embedding" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(3)).toBe("active"));
  });

  it("marks visualization 'completed' when analysis is completed", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "completed" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.getStepStatus(4)).toBe("completed"));
  });

  it("marks visualization 'pending' when analysis is not done", async () => {
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "extracting" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    // Visualization stays pending while analysis is still running
    await waitFor(() => expect(result.current.getStepStatus(4)).toBe("pending"));
  });

  it("returns 'locked' for out-of-range indices", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.getStepStatus(5)).toBe("locked");
    expect(result.current.getStepStatus(-1)).toBe("locked");
  });
});

describe("canNavigateToStep", () => {
  it("allows navigating to unlocked steps", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Step 0 is completed (extraction done), so navigable
    expect(result.current.canNavigateToStep(0)).toBe(true);
    // Steps 1-4 are pending (extraction done), so navigable
    expect(result.current.canNavigateToStep(1)).toBe(true);
    expect(result.current.canNavigateToStep(2)).toBe(true);
  });

  it("blocks navigating to locked steps", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.canNavigateToStep(0)).toBe(true); // always accessible
    expect(result.current.canNavigateToStep(1)).toBe(false);
    expect(result.current.canNavigateToStep(2)).toBe(false);
  });
});

describe("auto-navigation", () => {
  it("auto-navigates to the step after the furthest completed one", async () => {
    // All steps through analysis completed
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "completed" }));
    mockGetLatestAnalysis.mockResolvedValue(makeRun({ status: "completed" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    // Should auto-navigate to visualization (step 4) — last step, all completed
    await waitFor(() => expect(result.current.activeStep).toBe(4));
  });

  it("auto-navigates to an active step if one exists", async () => {
    // Extraction in progress → step 0 is active
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "in_progress" }));
    mockGetLatestSession.mockResolvedValue(null);
    mockGetLatestAnalysis.mockResolvedValue(null);

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.activeStep).toBe(0);
  });

  it("stays on step 0 when extraction not started", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    // Step 0 is active (first step), so it should stay there
    expect(result.current.activeStep).toBe(0);
  });

  it("navigates past materials to next pending step when only extraction done", async () => {
    // Extraction done, no session/analysis
    mockGetLatestSession.mockResolvedValue(null);
    mockGetLatestAnalysis.mockResolvedValue(null);

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    // Step 0 is completed, step 1 is pending → should land on step 1
    await waitFor(() => expect(result.current.activeStep).toBe(1));
  });

  it("navigates to analysis step when book-selection is completed", async () => {
    mockGetLatestSession.mockResolvedValue(makeSession({ status: "completed" }));
    mockGetLatestAnalysis.mockResolvedValue(null);

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    // Steps 0-2 completed, step 3 pending → should land on step 3
    await waitFor(() => expect(result.current.activeStep).toBe(3));
  });
});

describe("step status fetch effect", () => {
  it("calls getLatestSession and getLatestAnalysis when extraction is done", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetLatestSession).toHaveBeenCalledWith(1);
    expect(mockGetLatestAnalysis).toHaveBeenCalledWith(1);
  });

  it("does NOT call getLatestSession/getLatestAnalysis when extraction not done", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockGetLatestSession).not.toHaveBeenCalled();
    expect(mockGetLatestAnalysis).not.toHaveBeenCalled();
  });

  it("handles API errors gracefully without crashing", async () => {
    mockGetLatestSession.mockRejectedValue(new Error("network fail"));
    mockGetLatestAnalysis.mockRejectedValue(new Error("network fail"));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    // Should still load without crashing — steps fall back to pending
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.getStepStatus(2)).toBe("pending");
    expect(result.current.getStepStatus(3)).toBe("pending");
  });
});

describe("manual navigation", () => {
  it("setActiveStep updates the active step", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.setActiveStep(2));
    expect(result.current.activeStep).toBe(2);
  });

  it("setActiveStep does not navigate to locked steps", async () => {
    mockGetCourse.mockResolvedValue(makeCourse({ extraction_status: "not_started" }));

    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    act(() => result.current.setActiveStep(3));
    // Should remain on 0 since step 3 is locked
    expect(result.current.activeStep).toBe(0);
  });

  it("goToNext advances by one step", async () => {
    const { result } = renderHook(() => useCourseDetail(), { wrapper });

    // Wait for auto-navigation to settle
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Set to step 2 first
    act(() => result.current.setActiveStep(2));
    expect(result.current.activeStep).toBe(2);

    act(() => result.current.goToNext());
    expect(result.current.activeStep).toBe(3);
  });
});
