import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { toast } from "sonner";

import { coursesApi } from "../api";
import type {
  Course,
  CourseEmbeddingStatusResponse,
} from "../types";
import type { StepStatus } from "@/components/ui/stepper";
import { getLatestSession, getLatestAnalysis } from "@/features/book-selection/api";
import type { SessionStatus, ExtractionRunStatus } from "@/features/book-selection/types";

/* ── Step definitions ───────────────────────────────────────── */

export const COURSE_STEPS = [
  "materials",
  "normalization",
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

  /* Embedding */
  embeddingStatus: CourseEmbeddingStatusResponse | null;

  /* Step-completion signals */
  bookSessionStatus: SessionStatus | null;
  analysisRunStatus: ExtractionRunStatus | null;

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
  children: React.ReactNode;
}

export function CourseDetailProvider({
  courseId,
  children,
}: CourseDetailProviderProps) {
  /* ── State ─────────────────────────────────────────────────── */
  const [course, setCourse] = useState<Course | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isExtracting, setIsExtracting] = useState(false);
  const [presentationCount, setPresentationCount] = useState(0);
  const [activeStep, setActiveStepRaw] = useState(0);
  const [embeddingStatus, setEmbeddingStatus] =
    useState<CourseEmbeddingStatusResponse | null>(null);
  const [extractionProgress, setExtractionProgress] =
    useState<ExtractionProgressInfo | null>(null);

  /* Step-completion signals from backend */
  const [bookSessionStatus, setBookSessionStatus] = useState<SessionStatus | null>(null);
  const [analysisRunStatus, setAnalysisRunStatus] = useState<ExtractionRunStatus | null>(null);
  const [stepStatusesFetched, setStepStatusesFetched] = useState(false);

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

  /* ── Extraction polling ────────────────────────────────────── */

  useEffect(() => {
    if (course?.extraction_status !== "in_progress") return;

    const intervalId = setInterval(async () => {
      try {
        const updated = await coursesApi.getCourse(courseId);
        setCourse(updated);
        if (updated.extraction_status !== "in_progress") {
          clearInterval(intervalId);
          if (updated.extraction_status === "finished") {
            toast.success("Data extraction completed successfully!");
          } else if (updated.extraction_status === "failed") {
            toast.error("Data extraction failed.");
          }
        }
      } catch (error) {
        console.error("Polling failed", error);
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(intervalId);
  }, [course?.extraction_status, courseId]);

  /* ── Derived ───────────────────────────────────────────────── */

  const extractionDone = course?.extraction_status === "finished";

  /* ── Fetch step-completion statuses from backend ─────────── */

  useEffect(() => {
    if (!extractionDone) return;

    let cancelled = false;

    async function fetchStatuses() {
      try {
        const [session, analysis] = await Promise.all([
          getLatestSession(courseId),
          getLatestAnalysis(courseId),
        ]);
        if (cancelled) return;
        if (session) setBookSessionStatus(session.status);
        if (analysis) setAnalysisRunStatus(analysis.status);
      } catch (error) {
        console.error("Failed to fetch step statuses", error);
      } finally {
        if (!cancelled) setStepStatusesFetched(true);
      }
    }

    fetchStatuses();
    return () => { cancelled = true; };
  }, [extractionDone, courseId]);

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
      const response = await coursesApi.startExtraction(course.id);
      toast.success(response.message);
      setCourse((prev) =>
        prev ? { ...prev, extraction_status: response.status } : null
      );
    } catch {
      toast.error("Failed to start extraction");
    } finally {
      setIsExtracting(false);
    }
  }, [course]);

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
      const ACTIVE_SESSION: SessionStatus[] = ["discovering", "scoring", "downloading"];
      const DONE_SESSION: SessionStatus[] = ["completed"];
      const ACTIVE_ANALYSIS: ExtractionRunStatus[] = [
        "agentic_extracting",
        "extracting",
        "chunking",
        "embedding",
        "scoring",
      ];
      const DONE_ANALYSIS: ExtractionRunStatus[] = [
        "completed",
        "agentic_completed",
        "book_picked",
      ];

      switch (index) {
        case 0: // Materials
          if (course?.extraction_status === "in_progress") return "active";
          if (extractionDone) return "completed";
          return "active"; // always accessible as first step
        case 1: // Normalization — optional, unlocked once extraction done
          if (!extractionDone) return "locked";
          // No persistent backend status — mark completed if later steps are done
          if (bookSessionStatus && DONE_SESSION.includes(bookSessionStatus))
            return "completed";
          return "pending";
        case 2: // Book Selection
          if (!extractionDone) return "locked";
          if (bookSessionStatus && DONE_SESSION.includes(bookSessionStatus))
            return "completed";
          if (bookSessionStatus && ACTIVE_SESSION.includes(bookSessionStatus))
            return "active";
          return "pending";
        case 3: // Analysis
          if (!extractionDone) return "locked";
          if (analysisRunStatus && DONE_ANALYSIS.includes(analysisRunStatus))
            return "completed";
          if (analysisRunStatus && ACTIVE_ANALYSIS.includes(analysisRunStatus))
            return "active";
          return "pending";
        case 4: // Visualization
          if (!extractionDone) return "locked";
          if (analysisRunStatus && DONE_ANALYSIS.includes(analysisRunStatus))
            return "completed";
          return "pending";
        default:
          return "locked";
      }
    },
    [course?.extraction_status, extractionDone, bookSessionStatus, analysisRunStatus]
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
        setActiveStepRaw(step);
      }
    },
    [canNavigateToStep]
  );

  const goToNext = useCallback(() => {
    setActiveStep(activeStep + 1);
  }, [activeStep, setActiveStep]);

  /* ── Auto-navigate to the furthest meaningful step on load ── */

  const [hasAutoNavigated, setHasAutoNavigated] = useState(false);

  useEffect(() => {
    if (hasAutoNavigated || isLoading || !course) return;
    // Wait until backend statuses have been fetched (or extraction isn't done)
    if (extractionDone && !stepStatusesFetched) return;

    // Find the furthest completed step, then go one past it (the current work)
    let furthestCompleted = -1;
    for (let i = COURSE_STEPS.length - 1; i >= 0; i--) {
      if (getStepStatus(i) === "completed") {
        furthestCompleted = i;
        break;
      }
    }

    // Also check for an active step
    let activeIdx = -1;
    for (let i = 0; i < COURSE_STEPS.length; i++) {
      if (getStepStatus(i) === "active") {
        activeIdx = i;
        break;
      }
    }

    if (activeIdx >= 0) {
      setActiveStepRaw(activeIdx);
    } else if (furthestCompleted >= 0) {
      // If everything is completed, land on the last step; otherwise go one past
      const target = Math.min(furthestCompleted + 1, COURSE_STEPS.length - 1);
      setActiveStepRaw(target);
    }

    setHasAutoNavigated(true);
  }, [
    hasAutoNavigated,
    isLoading,
    course,
    extractionDone,
    stepStatusesFetched,
    getStepStatus,
  ]);

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
      embeddingStatus,
      bookSessionStatus,
      analysisRunStatus,
      activeStep,
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
      embeddingStatus,
      bookSessionStatus,
      analysisRunStatus,
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
