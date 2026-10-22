import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import { CourseDetailProvider, useCourseDetail } from "@/features/courses/context/CourseDetailContext";
import { coursesApi } from "@/features/courses/api";
import { getLatestAnalysis, getLatestSession, getCourseSelectedBooks } from "@/features/book-selection/api";
import { getChapterPlan } from "@/features/curriculum-planning/api";
import type { Course } from "@/features/courses/types";
import type { BookExtractionRun, BookSelectionSession, CourseSelectedBook, ExtractionRunStatus } from "@/features/book-selection/types";

vi.mock("@/features/courses/api", () => ({
  coursesApi: { getCourse: vi.fn(), getEmbeddingsStatus: vi.fn(), getMaterialsReadiness: vi.fn() },
  streamExtraction: vi.fn(),
}));
vi.mock("@/features/book-selection/api", () => ({
  getLatestSession: vi.fn(), getLatestAnalysis: vi.fn(), getCourseSelectedBooks: vi.fn(),
}));
vi.mock("@/features/curriculum-planning/api", () => ({ getChapterPlan: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const course: Course = {
  id: 1, title: "Test course", description: null, level: "bachelor", teacher_id: 1,
  created_at: "2026-01-01T00:00:00Z", extraction_status: "finished",
  publication_status: "draft", market_gate_status: "not_started",
};
const emptyPlan = { course_id: 1, chapters: [], unassigned_documents: [], all_documents: [] };
const chapterPlan = { ...emptyPlan, chapters: [{ number: 1, title: "Introduction", description: "", learning_objectives: [], prerequisites: [], assigned_documents: ["doc-1"] }] };
const session: BookSelectionSession = {
  id: 1, course_id: 1, thread_id: "t-1", status: "completed", course_level: "bachelor",
  weights_json: null, progress_scored: 2, progress_total: 2, error_message: null,
  created_at: course.created_at, updated_at: course.created_at,
};
const book: CourseSelectedBook = {
  id: 1, course_id: 1, source_book_id: 1, title: "Course book", authors: null,
  publisher: null, year: null, status: "downloaded", blob_path: "books/course.pdf", blob_url: null,
  error_message: null, created_at: course.created_at, updated_at: course.created_at,
};
function run(status: ExtractionRunStatus): BookExtractionRun {
  return { id: 1, course_id: 1, status, error_message: null, progress_detail: null,
    embedding_model: null, embedding_dims: null, created_at: course.created_at, updated_at: course.created_at };
}
function wrapper({ children }: { children: ReactNode }) {
  return <CourseDetailProvider courseId={1}>{children}</CourseDetailProvider>;
}
async function load() {
  const hook = renderHook(() => useCourseDetail(), { wrapper });
  await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
  await waitFor(() => expect(hook.result.current.stepStatusesLoading).toBe(false));
  return hook;
}
function readyBooks() {
  vi.mocked(getLatestSession).mockResolvedValue(session);
  vi.mocked(getCourseSelectedBooks).mockResolvedValue([book]);
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(coursesApi.getCourse).mockResolvedValue(course);
  vi.mocked(coursesApi.getMaterialsReadiness).mockImplementation(async (id) => {
    const ready = (await coursesApi.getCourse(id)).extraction_status === "finished";
    return { ready, status: ready ? "ready" : "processing", message: ready ? "Ready." : "Processing.", total_files: 1, processed_files: ready ? 1 : 0 };
  });
  vi.mocked(getLatestSession).mockResolvedValue(null);
  vi.mocked(getLatestAnalysis).mockResolvedValue(null);
  vi.mocked(getCourseSelectedBooks).mockResolvedValue([]);
  vi.mocked(getChapterPlan).mockResolvedValue(chapterPlan);
});
afterEach(() => vi.useRealTimers());

describe("preparation dependencies", () => {
  it.each(["not_started", "in_progress", "failed"] as const)("locks later workspaces while material extraction is %s", async (extraction_status) => {
    vi.mocked(coursesApi.getCourse).mockResolvedValue({ ...course, extraction_status });
    const { result } = await load();
    for (const index of [1, 2, 3, 4, 5]) expect(result.current.canNavigateToStep(index)).toBe(false);
    expect(result.current.activeStep).toBe(0);
  });

  it("requires chapters after materials while normalization stays optional", async () => {
    vi.mocked(getChapterPlan).mockResolvedValue(emptyPlan);
    const { result } = await load();
    expect(result.current.activeStep).toBe(2);
    expect(result.current.nextPreparationStep).toBe(2);
    expect(result.current.canNavigateToStep(3)).toBe(false);
    expect(result.current.canNavigateToStep(1)).toBe(true);
    expect(result.current.canNavigateToStep(2)).toBe(true);
    expect(result.current.getStepStatus(4)).toBe("locked");
    expect(result.current.getStepStatus(5)).toBe("locked");
  });

  it.each(["discovering", "scoring", "awaiting_review", "downloading"] as const)("keeps analysis locked while book selection is %s", async (status) => {
    readyBooks();
    vi.mocked(getLatestSession).mockResolvedValue({ ...session, status });
    const { result } = await load();
    expect(result.current.getStepStatus(4)).toBe("locked");
    act(() => result.current.setActiveStep(4));
    expect(result.current.activeStep).toBe(3);
    act(() => result.current.goToNext());
    expect(result.current.activeStep).toBe(3);
  });

  it.each([
    { status: "failed", blob_path: null },
    { status: "downloading", blob_path: null },
    { status: "downloaded", blob_path: null },
  ] as const)("does not unlock analysis for an unusable book: $status / $blob_path", async (overrides) => {
    readyBooks();
    vi.mocked(getCourseSelectedBooks).mockResolvedValue([{ ...book, ...overrides }]);
    const { result } = await load();
    expect(result.current.getStepStatus(3)).not.toBe("completed");
    expect(result.current.getStepStatus(4)).toBe("locked");
    expect(result.current.nextPreparationStep).toBe(3);
  });

  it("unlocks analysis for completed selection with a usable downloaded book", async () => {
    readyBooks();
    const { result } = await load();
    expect(result.current.getStepStatus(3)).toBe("completed");
    expect(result.current.getStepStatus(4)).toBe("pending");
    expect(result.current.activeStep).toBe(4);
    expect(result.current.getStepStatus(1)).toBe("pending");
  });

  it("accepts a directly uploaded book without a discovery session", async () => {
    vi.mocked(getCourseSelectedBooks).mockResolvedValue([{ ...book, status: "uploaded" }]);
    const { result } = await load();
    expect(result.current.activeStep).toBe(4);
    expect(result.current.getStepStatus(3)).toBe("completed");
  });

  it.each(["pending", "extracting", "chapter_extracted", "chunking", "embedding", "scoring", "agentic_extracting", "failed"] as const)("keeps results locked while analysis is %s", async (status) => {
    readyBooks();
    vi.mocked(getLatestAnalysis).mockResolvedValue(run(status));
    const { result } = await load();
    expect(result.current.activeStep).toBe(4);
    expect(result.current.getStepStatus(5)).toBe("locked");
    act(() => result.current.setActiveStep(5));
    expect(result.current.activeStep).toBe(4);
  });

  it.each(["completed", "agentic_completed", "book_picked", "curriculum_built"] as const)("opens results after %s without claiming the teacher reviewed them", async (status) => {
    readyBooks();
    vi.mocked(getLatestAnalysis).mockResolvedValue(run(status));
    const { result } = await load();
    expect(result.current.activeStep).toBe(5);
    expect(result.current.getStepStatus(4)).toBe("completed");
    expect(result.current.getStepStatus(5)).toBe("pending");
  });

  it("respects Skip Books without sending teachers into an empty analysis workspace", async () => {
    vi.mocked(getLatestSession).mockResolvedValue({ ...session, progress_total: 0, progress_scored: 0 });
    const { result } = await load();
    expect(result.current.booksSkipped).toBe(true);
    expect(result.current.nextPreparationStep).toBeNull();
    expect(result.current.activeStep).toBe(3);
    expect(result.current.getStepStatus(3)).toBe("completed");
    expect(result.current.getStepStatus(4)).toBe("locked");
    expect(result.current.getStepStatus(5)).toBe("locked");
  });

  it("does not use stale analysis results after the books are removed", async () => {
    vi.mocked(getLatestAnalysis).mockResolvedValue(run("completed"));
    const { result } = await load();
    expect(result.current.nextPreparationStep).toBe(3);
    expect(result.current.canNavigateToStep(5)).toBe(false);
  });
});

describe("live progress and navigation", () => {
  it("keeps dependent steps closed until their status has loaded", async () => {
    vi.mocked(getLatestSession).mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useCourseDetail(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.stepStatusesLoading).toBe(true);
    expect(result.current.canNavigateToStep(3)).toBe(false);
    expect(result.current.canNavigateToStep(4)).toBe(false);
    expect(result.current.canNavigateToStep(5)).toBe(false);
  });

  it("fails closed on a status error, then unlocks after a successful retry", async () => {
    vi.mocked(getLatestSession).mockRejectedValueOnce(new Error("Network unavailable"));
    const { result } = await load();
    expect(result.current.stepStatusesError).toBe(true);
    expect(result.current.getStepStatus(4)).toBe("locked");
    readyBooks();
    act(() => result.current.refreshStepStatuses());
    await waitFor(() => expect(result.current.getStepStatus(4)).toBe("pending"));
    expect(result.current.stepStatusesError).toBe(false);
  });

  it("updates completed books without reloading and leaves the teacher on their current workspace", async () => {
    const { result } = await load();
    expect(result.current.activeStep).toBe(3);
    readyBooks();
    act(() => result.current.refreshStepStatuses());
    await waitFor(() => expect(result.current.getStepStatus(4)).toBe("pending"));
    expect(result.current.activeStep).toBe(3);
    act(() => result.current.goToNext());
    expect(result.current.activeStep).toBe(4);
  });

  it("removes access to an open results workspace if its prerequisites become incomplete", async () => {
    readyBooks();
    vi.mocked(getLatestAnalysis).mockResolvedValue(run("completed"));
    const { result } = await load();
    expect(result.current.activeStep).toBe(5);
    vi.mocked(getCourseSelectedBooks).mockResolvedValue([]);
    act(() => result.current.refreshStepStatuses());
    await waitFor(() => expect(result.current.activeStep).toBe(3));
    expect(result.current.getStepStatus(5)).toBe("locked");
  });

  it("continues from materials through chapters and then books", async () => {
    const { result } = await load();
    await act(async () => result.current.setActiveStep(0));
    await act(async () => result.current.goToNext());
    expect(result.current.activeStep).toBe(2);
    await act(async () => result.current.goToNext());
    expect(result.current.activeStep).toBe(3);
  });

  it("keeps completed steps and optional tools available to revisit", async () => {
    readyBooks();
    const { result } = await load();
    for (const index of [0, 1, 2, 3]) {
      await act(async () => result.current.setActiveStep(index));
      expect(result.current.activeStep).toBe(index);
    }
    expect(result.current.getStepStatus(-1)).toBe("locked");
    expect(result.current.getStepStatus(6)).toBe("locked");
  });

  it("polls completion while the Prepare course page is open", async () => {
    vi.useFakeTimers();
    const { result, unmount } = renderHook(() => useCourseDetail(), {
      wrapper: ({ children }: { children: ReactNode }) => <CourseDetailProvider courseId={1} pollStepStatuses>{children}</CourseDetailProvider>,
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.getStepStatus(4)).toBe("locked");
    readyBooks();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(result.current.getStepStatus(4)).toBe("pending");
    unmount();
  });
});


describe("deployed material readiness", () => {
  it("does not replace a teacher's navigation when initial progress finishes loading", async () => {
    let finishLoading!: (value: BookSelectionSession | null) => void;
    vi.mocked(getLatestSession).mockReturnValue(new Promise((resolve) => { finishLoading = resolve; }));
    const {result} = renderHook(() => useCourseDetail(), {wrapper});
    await waitFor(() => expect(result.current.materialsReady).toBe(true));
    act(() => result.current.setActiveStep(0));
    await act(async () => finishLoading(null));
    expect(result.current.activeStep).toBe(0);
    expect(result.current.nextPreparationStep).toBe(3);
  });
  it("does not call teacher-only readiness for student views", async () => {
    const { result } = renderHook(() => useCourseDetail(), {wrapper: ({children}) => <CourseDetailProvider courseId={1} checkMaterials={false}>{children}</CourseDetailProvider>});
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(coursesApi.getMaterialsReadiness).not.toHaveBeenCalled();
  });
  it("keeps later steps locked when newly uploaded files are still processing", async () => {
    vi.mocked(coursesApi.getMaterialsReadiness).mockResolvedValue({ready:false,status:"processing",message:"Processing new files.",total_files:2,processed_files:1});
    const {result} = await load();
    expect(result.current.activeStep).toBe(0);
    expect(result.current.nextPreparationStep).toBe(0);
    expect(result.current.getStepStatus(0)).toBe("active");
    expect(result.current.canNavigateToStep(3)).toBe(false);
    expect(result.current.canNavigateToStep(4)).toBe(false);
  });
  it("preserves explicit materials deep links after book selection", async () => {
    readyBooks();
    const {result} = renderHook(() => useCourseDetail(), {wrapper: ({children}) => <CourseDetailProvider courseId={1} initialStep="materials">{children}</CourseDetailProvider>});
    await waitFor(() => expect(result.current.bookSessionStatus).toBe("completed"));
    expect(result.current.activeStep).toBe(0);
  });
  it("unlocks after fresh readiness and closes again if readiness cannot be checked", async () => {
    vi.useFakeTimers();
    vi.mocked(coursesApi.getMaterialsReadiness)
      .mockResolvedValueOnce({ready:false,status:"processing",message:"Processing.",total_files:2,processed_files:1})
      .mockResolvedValueOnce({ready:true,status:"ready",message:"Ready.",total_files:2,processed_files:2})
      .mockRejectedValue(new Error("Unavailable"));
    const {result} = renderHook(() => useCourseDetail(), {wrapper});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.canNavigateToStep(3)).toBe(false);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(result.current.canNavigateToStep(3)).toBe(true);
    act(() => result.current.setActiveStep(3));
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(result.current.canNavigateToStep(3)).toBe(false);
    expect(result.current.activeStep).toBe(0);
  });
  it("uses fresh readiness when ingestion finishes after loading the page", async () => {
    vi.useFakeTimers();
    vi.mocked(coursesApi.getCourse).mockResolvedValue({...course, extraction_status:"not_started"});
    vi.mocked(coursesApi.getMaterialsReadiness)
      .mockResolvedValueOnce({ready:false,status:"processing",message:"Processing.",total_files:1,processed_files:0})
      .mockResolvedValue({ready:true,status:"ready",message:"Ready.",total_files:1,processed_files:1});
    const {result} = renderHook(() => useCourseDetail(), {wrapper});
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.canNavigateToStep(3)).toBe(false);
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(result.current.canNavigateToStep(3)).toBe(true);
  });
});


it("does not let Skip Books bypass missing chapters", async () => {
  vi.mocked(getChapterPlan).mockResolvedValue(emptyPlan);
  vi.mocked(getLatestSession).mockResolvedValue({ ...session, progress_total: 0, progress_scored: 0 });
  const { result } = await load();
  expect(result.current.booksSkipped).toBe(true);
  expect(result.current.activeStep).toBe(2);
  expect(result.current.nextPreparationStep).toBe(2);
});

it("reports an unavailable chapter plan separately and retries without depending on book services", async () => {
  vi.mocked(getChapterPlan).mockRejectedValueOnce(new Error("Chapter service unavailable"));
  vi.mocked(getLatestSession).mockRejectedValue(new Error("Book service unavailable"));
  const { result } = await load();
  expect(result.current.chapterPlanError).toBe(true);
  expect(result.current.chapterPlanLoading).toBe(false);
  expect(result.current.canNavigateToStep(3)).toBe(false);
  act(() => result.current.refreshChapterPlan());
  await waitFor(() => expect(result.current.hasChapters).toBe(true));
  expect(result.current.chapterPlanError).toBe(false);
  expect(result.current.stepStatusesError).toBe(true);
});

it("retains an explicit chapter deep link while initial readiness loads", async () => {
  const { result } = renderHook(() => useCourseDetail(), { wrapper: ({children}) =>
    <CourseDetailProvider courseId={1} initialStep="build-chapters">{children}</CourseDetailProvider> });
  await waitFor(() => expect(result.current.materialsReady).toBe(true));
  await waitFor(() => expect(result.current.stepStatusesLoading).toBe(false));
  expect(result.current.activeStep).toBe(2);
});


it("does not reuse the previous course's chapter readiness while the next course loads", async () => {
  let courseId = 1;
  const hook = renderHook(() => useCourseDetail(), {wrapper: ({children}) =>
    <CourseDetailProvider courseId={courseId}>{children}</CourseDetailProvider>});
  await waitFor(() => expect(hook.result.current.hasChapters).toBe(true));
  let resolvePlan!: (plan: typeof emptyPlan) => void;
  vi.mocked(getChapterPlan).mockImplementation(() => new Promise(resolve => { resolvePlan = resolve; }));
  courseId = 2;
  hook.rerender();
  await waitFor(() => expect(coursesApi.getMaterialsReadiness).toHaveBeenCalledWith(2));
  await waitFor(() => expect(hook.result.current.materialsReady).toBe(true));
  expect(hook.result.current.chapterPlanLoading).toBe(true);
  expect(hook.result.current.canNavigateToStep(3)).toBe(false);
  await act(async () => resolvePlan({...emptyPlan, course_id: 2}));
  expect(hook.result.current.chapterPlanLoading).toBe(false);
  expect(hook.result.current.hasChapters).toBe(false);
  expect(hook.result.current.nextPreparationStep).toBe(2);
});
