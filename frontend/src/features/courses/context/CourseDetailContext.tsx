/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { coursesApi, streamExtraction } from "@/features/courses/api";
import type {
  ExtractionProgressEvent,
} from "@/features/courses/api";
import type {
  Course,
  CourseEmbeddingStatusResponse,
} from "@/features/courses/types";
import type { StepStatus } from "@/components/ui/stepper";
import { getLatestSession, getLatestAnalysis, getCourseSelectedBooks } from "@/features/book-selection/api";
import type { SessionStatus, ExtractionRunStatus } from "@/features/book-selection/types";
import { getChapterPlan } from "@/features/curriculum-planning/api";

import { useCourseMaterialsReadiness } from "@/features/courses/hooks/useCourseMaterialsReadiness";

/* ── Step definitions ───────────────────────────────────────── */

export const COURSE_STEPS = [
  "materials",
  "normalization",
  "build-chapters",
  "book-selection",
  "analysis",
  "visualization",
] as const;

export type CourseStep = (typeof COURSE_STEPS)[number];

/* ── Context shape ──────────────────────────────────────────── */

interface ExtractionProgressInfo {
  total: number;
  processed: number;
  failed: number;
  terminal: number;
  value: number;
  allTerminal: boolean;
}

interface CourseDetailContextValue {
  /* Course data */
  course: Course | null;
  courseId: number;
  isLoading: boolean;
  refreshCourse: () => Promise<void>;

  /* Extraction */
  isExtracting: boolean;
  startExtraction: () => Promise<void>;
  extractionProgress: ExtractionProgressInfo | null;
  onProgressChange: (stats: ExtractionProgressInfo) => void;

  /* Materials */
  presentationCount: number;
  onFilesChange: (files: string[]) => void;
  refreshTrigger: number;
  triggerRefresh: () => void;
  materialsReady: boolean;
  materialsMessage: string;

  /* Embedding */
  embeddingStatus: CourseEmbeddingStatusResponse | null;

  /* Step-completion signals */
  bookSessionStatus: SessionStatus | null;
  analysisRunStatus: ExtractionRunStatus | null;
  hasChapters: boolean;
  chapterPlanLoading: boolean;
  chapterPlanError: boolean;
  refreshChapterPlan: () => void;
  setHasChapters: (val: boolean) => void;
  booksSkipped: boolean;
  stepStatusesLoading: boolean;
  stepStatusesError: boolean;
  refreshStepStatuses: () => void;
  nextPreparationStep: number | null;

  /* Stepper navigation */
  activeStep: number;
  setActiveStep: (step: number) => void;
  goToNext: () => void;
  canNavigateToStep: (index: number) => boolean;
  getStepStatus: (index: number) => StepStatus;
}

const CourseDetailContext = createContext<CourseDetailContextValue | null>(null);

/* ── Hook ───────────────────────────────────────────────────── */

export function useCourseDetail() {
  const ctx = useContext(CourseDetailContext);
  if (!ctx)
    throw new Error(
      "useCourseDetail must be used within <CourseDetailProvider>"
    );
  return ctx;
}

/* ── Provider ───────────────────────────────────────────────── */

const POLL_INTERVAL_MS = 10_000;

interface CourseDetailProviderProps {
  courseId: number;
  pollStepStatuses?: boolean;
  initialStep?: CourseStep;
  checkMaterials?: boolean;
  children: React.ReactNode;
}

export function CourseDetailProvider({
  courseId,
  pollStepStatuses = false,
  initialStep,
  checkMaterials = true,
  children,
}: CourseDetailProviderProps) {
  /* ── State ─────────────────────────────────────────────────── */
  const [course, setCourse] = useState<Course | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const materials = useCourseMaterialsReadiness(courseId, refreshTrigger, checkMaterials);
  const [isExtracting, setIsExtracting] = useState(false);
  const [presentationCount, setPresentationCount] = useState(0);
  const [activeStep, setActiveStepRaw] = useState(initialStep ? COURSE_STEPS.indexOf(initialStep) : 0);
  const hasAutoNavigated = useRef(initialStep !== undefined);
  const [embeddingStatus, setEmbeddingStatus] =
    useState<CourseEmbeddingStatusResponse | null>(null);
  const [extractionProgress, setExtractionProgress] =
    useState<ExtractionProgressInfo | null>(null);

  /* Step-completion signals from backend */
  const [bookSessionStatus, setBookSessionStatus] = useState<SessionStatus | null>(null);
  const [analysisRunStatus, setAnalysisRunStatus] = useState<ExtractionRunStatus | null>(null);
  const [hasChapters, setHasChapters] = useState(false);
  const [stepStatusesFetched, setStepStatusesFetched] = useState(false);
  const [bookStatusesError, setBookStatusesError] = useState(false);
  const [chapterPlanFetched, setChapterPlanFetched] = useState(false);
  const [chapterPlanCourseId, setChapterPlanCourseId] = useState<number | null>(null);
  const [chapterPlanError, setChapterPlanError] = useState(false);
  const [chapterRefresh, setChapterRefresh] = useState(0);
  const [statusRefresh, setStatusRefresh] = useState(0);
  const [booksReady, setBooksReady] = useState(false);
  const [booksSkipped, setBooksSkipped] = useState(false);

  const refreshChapterPlan = useCallback(() => {
    setChapterPlanFetched(false);
    setChapterPlanError(false);
    setChapterRefresh((value) => value + 1);
  }, []);

  const refreshStepStatuses = useCallback(() => {
    setStepStatusesFetched(false);
    setBookStatusesError(false);
    setStatusRefresh((value) => value + 1);
    refreshChapterPlan();
  }, [refreshChapterPlan]);

  /* ── Fetch course ──────────────────────────────────────────── */

  const refreshCourse = useCallback(async () => {
    try {
      const data = await coursesApi.getCourse(courseId);
      setCourse(data);
    } catch (error) {
      toast.error("Failed to fetch course details");
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refreshCourse();
  }, [refreshCourse]);

  /* ── SSE extraction stream ──────────────────────────────────── */

  const sseAbortRef = useRef<AbortController | null>(null);

  const connectExtractionStream = useCallback(
    (cId: number) => {
      // Abort any existing connection
      sseAbortRef.current?.abort();
      const controller = new AbortController();
      sseAbortRef.current = controller;

      streamExtraction({
        courseId: cId,
        signal: controller.signal,
        onProgress: (event: ExtractionProgressEvent) => {
          setExtractionProgress({
            total: event.total,
            processed: event.processed,
            failed: event.failed,
            terminal: event.terminal,
            value: event.value,
            allTerminal: event.total > 0 && event.terminal >= event.total,
          });
        },
        onComplete: (event) => {
          setExtractionProgress({
            total: event.total,
            processed: event.processed,
            failed: event.failed,
            terminal: event.terminal,
            value: event.value,
            allTerminal: true,
          });
          setCourse((prev) =>
            prev ? { ...prev, extraction_status: event.status } : null
          );
          if (event.status === "finished") {
            toast.success("Data extraction completed successfully!");
          } else if (event.status === "failed") {
            toast.error("Data extraction failed.");
          }
          sseAbortRef.current = null;
        },
        onError: (err) => {
          console.error("Extraction SSE error:", err);
          // Fallback: re-fetch course to get the latest status
          coursesApi.getCourse(cId).then(setCourse).catch(console.error);
          sseAbortRef.current = null;
        },
      });
    },
    []
  );

  // Auto-connect SSE on page load if extraction is already in progress
  useEffect(() => {
    if (course?.extraction_status !== "in_progress") return;
    // Only connect if no existing SSE connection
    if (sseAbortRef.current) return;
    connectExtractionStream(courseId);
  }, [course?.extraction_status, courseId, connectExtractionStream]);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => {
      sseAbortRef.current?.abort();
    };
  }, []);

  /* ── Derived ───────────────────────────────────────────────── */

  const materialsReady = materials.ready;
  const extractionDone = materialsReady || course?.extraction_status === "finished";

  const chapterPlanLoading = extractionDone && (!chapterPlanFetched || chapterPlanCourseId !== courseId);
  const stepStatusesError = bookStatusesError || chapterPlanError;

  // Chapter readiness must not depend on book discovery or analysis services.
  useEffect(() => {
    if (!extractionDone) {
      setHasChapters(false);
      setChapterPlanFetched(false);
      setChapterPlanError(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function fetchPlan() {
      try {
        const plan = await getChapterPlan(courseId);
        if (cancelled) return;
        setHasChapters(plan.chapters.length > 0);
        setChapterPlanError(false);
      } catch {
        if (!cancelled) setChapterPlanError(true);
      } finally {
        if (!cancelled) {
          setChapterPlanFetched(true);
          setChapterPlanCourseId(courseId);
          if (pollStepStatuses) timer = setTimeout(fetchPlan, 5_000);
        }
      }
    }
    void fetchPlan();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [extractionDone, courseId, pollStepStatuses, chapterRefresh]);

  /* ── Fetch step-completion statuses from backend ─────────── */

  useEffect(() => {
    if (!extractionDone) {
      setStepStatusesFetched(false);
      setBookStatusesError(false);
      setBooksReady(false);
      setBooksSkipped(false);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function fetchStatuses() {
      try {
        const [session, analysis, books] = await Promise.all([
          getLatestSession(courseId),
          getLatestAnalysis(courseId),
          getCourseSelectedBooks(courseId),
        ]);
        if (cancelled) return;
        setBookSessionStatus(session?.status ?? null);
        setAnalysisRunStatus(analysis?.status ?? null);
        setBooksReady(
          (!session || session.status === "completed") &&
          books.some((book) =>
            ["downloaded", "uploaded"].includes(book.status) && Boolean(book.blob_path)
          )
        );
        setBooksSkipped(session?.status === "completed" && session.progress_total === 0 && books.length === 0);
        setBookStatusesError(false);
      } catch (error) {
        if (cancelled) return;
        setBookStatusesError(true);
        console.error("Failed to fetch step statuses", error);
      } finally {
        if (!cancelled) {
          setStepStatusesFetched(true);
          if (pollStepStatuses) timer = setTimeout(fetchStatuses, 5_000);
        }
      }
    }

    fetchStatuses();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [extractionDone, courseId, pollStepStatuses, statusRefresh]);

  /* ── Embedding polling (only on materials step) ────────────── */

  useEffect(() => {
    if (
      course?.extraction_status !== "finished" ||
      activeStep !== 0
    ) {
      setEmbeddingStatus(null);
      return;
    }

    const fetchEmbeddings = async () => {
      try {
        const status = await coursesApi.getEmbeddingsStatus(courseId);
        setEmbeddingStatus(status);
      } catch (error) {
        console.error("Embeddings status polling failed", error);
      }
    };

    fetchEmbeddings();
    const intervalId = setInterval(fetchEmbeddings, POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [course?.extraction_status, activeStep, courseId]);

  /* ── Actions ───────────────────────────────────────────────── */

  const startExtraction = useCallback(async () => {
    if (!course) return;
    setIsExtracting(true);
    try {
      // Optimistic UI update — SSE will set real status
      setCourse((prev) =>
        prev ? { ...prev, extraction_status: "in_progress" } : null
      );
      connectExtractionStream(course.id);
      toast.success("Extraction started");
    } catch {
      toast.error("Failed to start extraction");
    } finally {
      setIsExtracting(false);
    }
  }, [course, connectExtractionStream]);

  const onProgressChange = useCallback(
    (stats: ExtractionProgressInfo) => {
      setExtractionProgress((prev) => {
        if (!prev) return stats;
        const same =
          prev.total === stats.total &&
          prev.processed === stats.processed &&
          prev.failed === stats.failed &&
          prev.terminal === stats.terminal &&
          prev.value === stats.value &&
          prev.allTerminal === stats.allTerminal;
        return same ? prev : stats;
      });
    },
    []
  );

  const onFilesChange = useCallback((files: string[]) => {
    setPresentationCount(files.length);
  }, []);

  const triggerRefresh = useCallback(() => {
    setRefreshTrigger((n) => n + 1);
  }, []);

  /* ── Step status computation ───────────────────────────────── */

  const getStepStatus = useCallback(
    (index: number): StepStatus => {
      if (index > 0 && !materialsReady) return "locked";
      if (index >= 3 && (!hasChapters || chapterPlanLoading || chapterPlanError)) return "locked";
      const ACTIVE_SESSION: SessionStatus[] = ["discovering", "scoring", "downloading"];
      const ACTIVE_ANALYSIS: ExtractionRunStatus[] = [
        "pending",
        "agentic_extracting",
        "extracting",
        "chapter_extracted",
        "chunking",
        "embedding",
        "scoring",
      ];
      const DONE_ANALYSIS: ExtractionRunStatus[] = [
        "completed",
        "agentic_completed",
        "book_picked",
        "curriculum_built",
      ];

      switch (index) {
        case 0: // Materials
          if (course?.extraction_status === "in_progress") return "active";
          if (materialsReady) return "completed";
          return "active"; // always accessible as first step
        case 1: // Normalization — optional, unlocked once extraction done
          if (!extractionDone) return "locked";
          return "pending";
        case 2: // Chapter planning is required before books and curriculum mapping
          if (!extractionDone) return "locked";
          if (hasChapters) return "completed";
          return "pending";
        case 3: // Book Selection
          if (!extractionDone || !stepStatusesFetched || stepStatusesError) return "locked";
          if (booksReady || booksSkipped)
            return "completed";
          if (bookSessionStatus && ACTIVE_SESSION.includes(bookSessionStatus))
            return "active";
          return "pending";
        case 4: // Analysis
          if (!extractionDone || !stepStatusesFetched || stepStatusesError || !booksReady) return "locked";
          if (analysisRunStatus && DONE_ANALYSIS.includes(analysisRunStatus))
            return "completed";
          if (analysisRunStatus && ACTIVE_ANALYSIS.includes(analysisRunStatus))
            return "active";
          return "pending";
        case 5: // Results are available after analysis; viewing is not a persisted completion.
          if (!extractionDone || !stepStatusesFetched || stepStatusesError || !booksReady) return "locked";
          return analysisRunStatus && DONE_ANALYSIS.includes(analysisRunStatus)
            ? "pending"
            : "locked";
        default:
          return "locked";
      }
    },
    [course?.extraction_status, extractionDone, materialsReady, bookSessionStatus, analysisRunStatus, hasChapters, chapterPlanLoading, chapterPlanError, stepStatusesFetched, stepStatusesError, booksReady, booksSkipped]
  );

  const canNavigateToStep = useCallback(
    (index: number): boolean => {
      const status = getStepStatus(index);
      return status !== "locked";
    },
    [getStepStatus]
  );

  const setActiveStep = useCallback(
    (step: number) => {
      if (canNavigateToStep(step)) {
        hasAutoNavigated.current = true;
        setActiveStepRaw(step);
      }
    },
    [canNavigateToStep]
  );

  const goToNext = useCallback(() => {
    setActiveStep(activeStep < 2 ? 2 : activeStep + 1);
  }, [activeStep, setActiveStep]);

  const stepStatusesLoading = extractionDone && (!stepStatusesFetched || chapterPlanLoading);
  const nextPreparationStep = !materialsReady ? 0
    : !hasChapters ? 2
    : booksSkipped ? null
    : !booksReady ? 3
    : getStepStatus(4) === "completed" ? 5 : 4;

  // Choose the next required step once. Later completion updates the guidance
  // without moving a teacher away from work they are reviewing.
  useEffect(() => {
    if (hasAutoNavigated.current || isLoading || !course || stepStatusesLoading || stepStatusesError || (extractionDone && !materialsReady)) return;
    setActiveStepRaw(nextPreparationStep ?? 3);
    hasAutoNavigated.current = true;
  }, [isLoading, course, stepStatusesLoading, stepStatusesError, nextPreparationStep, extractionDone, materialsReady]);

  useEffect(() => {
    if (isLoading || !materialsReady || stepStatusesLoading || stepStatusesError) return;
    if (canNavigateToStep(activeStep)) return;
    const target = nextPreparationStep ?? 3;
    setActiveStepRaw(canNavigateToStep(target) ? target : 0);
  }, [activeStep, canNavigateToStep, nextPreparationStep, isLoading, materialsReady, stepStatusesLoading, stepStatusesError]);

  /* ── Context value (stable ref) ────────────────────────────── */

  const value = useMemo<CourseDetailContextValue>(
    () => ({
      course,
      courseId,
      isLoading,
      refreshCourse,
      isExtracting,
      startExtraction,
      extractionProgress,
      onProgressChange,
      presentationCount,
      onFilesChange,
      refreshTrigger,
      triggerRefresh,
      materialsReady,
      materialsMessage: materials.message,
      embeddingStatus,
      bookSessionStatus,
      analysisRunStatus,
      hasChapters,
      chapterPlanLoading,
      chapterPlanError,
      refreshChapterPlan,
      setHasChapters,
      booksSkipped,
      stepStatusesLoading,
      stepStatusesError,
      refreshStepStatuses,
      nextPreparationStep,
      activeStep: materialsReady ? activeStep : 0,
      setActiveStep,
      goToNext,
      canNavigateToStep,
      getStepStatus,
    }),
    [
      course,
      courseId,
      isLoading,
      refreshCourse,
      isExtracting,
      startExtraction,
      extractionProgress,
      onProgressChange,
      presentationCount,
      onFilesChange,
      refreshTrigger,
      triggerRefresh,
      materialsReady,
      materials.message,
      embeddingStatus,
      bookSessionStatus,
      analysisRunStatus,
      hasChapters,
      chapterPlanLoading,
      chapterPlanError,
      refreshChapterPlan,
      booksSkipped,
      stepStatusesLoading,
      stepStatusesError,
      refreshStepStatuses,
      nextPreparationStep,
      activeStep,
      setActiveStep,
      goToNext,
      canNavigateToStep,
      getStepStatus,
    ]
  );

  return (
    <CourseDetailContext.Provider value={value}>
      {children}
    </CourseDetailContext.Provider>
  );
}
