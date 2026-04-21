import { Routes, Route, Navigate, useParams } from "react-router-dom";
import { Component, type ReactNode, type ErrorInfo, useCallback, useState } from "react";
import { DataProvider, useData } from "@/features/arcd-agent/context/DataContext";
import { TwinProvider } from "@/features/arcd-agent/context/TwinContext";
import { TeacherDataProvider } from "@/features/arcd-agent/context/TeacherDataContext";
import { useAuth } from "@/features/auth/context/AuthContext";

// Student pages
import DashboardPage from "@/features/arcd-agent/pages/DashboardPage";
import StudentPage from "@/features/arcd-agent/pages/StudentPage";
import JourneyPage from "@/features/arcd-agent/pages/JourneyPage";
import LearningPathPage from "@/features/arcd-agent/pages/LearningPathPage";
import SchedulePage from "@/features/arcd-agent/pages/SchedulePage";
import QuizLabPage from "@/features/arcd-agent/pages/QuizLabPage";
import ReviewPage from "@/features/arcd-agent/pages/ReviewPage";
import DigitalTwinPage from "@/features/arcd-agent/pages/DigitalTwinPage";

// Teacher pages
import ClassOverviewPage from "@/features/arcd-agent/pages/ClassOverviewPage";
import ClassRosterPage from "@/features/arcd-agent/pages/ClassRosterPage";
import TeacherTwinPage from "@/features/arcd-agent/pages/TeacherTwinPage";
import StudentDrilldownPage from "@/features/arcd-agent/pages/StudentDrilldownPage";

/* ── Error Boundary ─────────────────────────────────────────────────── */

interface EBState { error: Error | null }

class ArcdErrorBoundary extends Component<{ children: ReactNode }, EBState> {
  state: EBState = { error: null };

  static getDerivedStateFromError(error: Error): EBState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ARCD] Render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center min-h-[400px] p-8">
          <div className="max-w-lg w-full space-y-4">
            <h2 className="text-xl font-semibold text-destructive">Something went wrong</h2>
            <p className="text-sm text-muted-foreground">
              An error occurred while rendering this page. Details below:
            </p>
            <pre className="bg-muted rounded-lg p-4 text-xs overflow-auto max-h-64 whitespace-pre-wrap break-words">
              {this.state.error.message}
              {"\n\n"}
              {this.state.error.stack}
            </pre>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 bg-primary text-primary-foreground text-sm rounded-lg hover:bg-primary/90"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── Shared loading / error screens ──────────────────────────────────── */

function LoadingScreen({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

function ErrorScreen({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const [retrying, setRetrying] = useState(false);

  const handleRetry = useCallback(() => {
    if (!onRetry) return;
    setRetrying(true);
    onRetry();
    setTimeout(() => setRetrying(false), 2000);
  }, [onRetry]);

  const errorMap: Record<string, { title: string; hint: string }> = {
    NETWORK_ERROR: {
      title: "Cannot reach the backend",
      hint: "The Lab Tutor server is not responding. Make sure the backend is running and try again.",
    },
    SESSION_EXPIRED: {
      title: "Session expired",
      hint: "Your login session has expired. Please log out and log back in.",
    },
    ACCESS_DENIED: {
      title: "Access denied",
      hint: "You do not have permission to view this page.",
    },
    NEO4J_UNAVAILABLE: {
      title: "Knowledge Graph unavailable",
      hint: "The Neo4j database is not reachable. Check that Neo4j is running and try again.",
    },
  };

  const detail = errorMap[message] ?? { title: "Could not load data", hint: message };

  return (
    <div className="flex items-center justify-center h-64 p-8">
      <div className="text-center space-y-3 max-w-md">
        <h2 className="text-xl font-semibold text-destructive">{detail.title}</h2>
        <p className="text-sm text-muted-foreground">{detail.hint}</p>
        {onRetry && (
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="mt-2 px-4 py-2 bg-primary text-primary-foreground text-sm rounded-lg hover:bg-primary/90 disabled:opacity-50"
          >
            {retrying ? "Retrying…" : "Retry"}
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Student routes ──────────────────────────────────────────────────── */

function StudentRoutes({ courseId }: { courseId: string }) {
  const { loading, error, selectedUid, dataVersion, refreshData } = useData();

  if (loading) return <LoadingScreen label="Loading student portfolio…" />;
  if (error) return <ErrorScreen message={error} onRetry={refreshData} />;

  return (
    <TwinProvider selectedUid={selectedUid} dataVersion={dataVersion} courseId={courseId}>
      <ArcdErrorBoundary>
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="home" element={<DashboardPage />} />
          <Route path="student" element={<StudentPage />} />
          <Route path="journey" element={<JourneyPage />} />
          <Route path="learning-path" element={<LearningPathPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="quiz-lab" element={<QuizLabPage />} />
          <Route path="review" element={<ReviewPage />} />
          <Route path="digital-twin" element={<DigitalTwinPage />} />
          <Route path="*" element={<Navigate to="." replace />} />
        </Routes>
      </ArcdErrorBoundary>
    </TwinProvider>
  );
}

/* ── Teacher routes ──────────────────────────────────────────────────── */

function TeacherRoutes() {
  return (
    <ArcdErrorBoundary>
      <Routes>
        <Route index element={<ClassOverviewPage />} />
        <Route path="overview" element={<ClassOverviewPage />} />
        <Route path="roster" element={<ClassRosterPage />} />
        <Route path="teacher-twin" element={<TeacherTwinPage />} />
        <Route path="student/:studentId" element={<StudentDrilldownPage />} />
        <Route path="*" element={<Navigate to="." replace />} />
      </Routes>
    </ArcdErrorBoundary>
  );
}

/* ── Shell ───────────────────────────────────────────────────────────── */

export default function ArcdAgentShell() {
  const { id } = useParams<{ id: string }>();
  const courseId = id ?? "";
  const { user, isLoading } = useAuth();

  // Wait for auth to resolve before deciding which provider tree to mount.
  // Without this guard, the wrong provider can mount on first render (before
  // the role is known), causing context-mismatch errors after HMR or refresh.
  if (isLoading) {
    return <LoadingScreen label="Authenticating…" />;
  }

  if (user?.role === "teacher") {
    return (
      <TeacherDataProvider courseId={courseId}>
        <TeacherRoutes />
      </TeacherDataProvider>
    );
  }

  return (
    <DataProvider courseId={courseId}>
      <StudentRoutes courseId={courseId} />
    </DataProvider>
  );
}
