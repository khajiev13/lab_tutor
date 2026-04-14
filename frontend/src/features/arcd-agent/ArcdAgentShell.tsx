import { Routes, Route, Navigate, useParams } from "react-router-dom";
import { Component, type ReactNode, type ErrorInfo } from "react";
import { DataProvider, useData } from "@/features/arcd-agent/context/DataContext";
import { TwinProvider } from "@/features/arcd-agent/context/TwinContext";
import { DatasetSwitcher } from "@/features/arcd-agent/components/DatasetSwitcher";
import { HeaderStudentPicker } from "@/features/arcd-agent/components/HeaderStudentPicker";

import DashboardPage from "@/features/arcd-agent/pages/DashboardPage";
import StudentPage from "@/features/arcd-agent/pages/StudentPage";
import JourneyPage from "@/features/arcd-agent/pages/JourneyPage";
import LearningPathPage from "@/features/arcd-agent/pages/LearningPathPage";
import SchedulePage from "@/features/arcd-agent/pages/SchedulePage";
import QuizLabPage from "@/features/arcd-agent/pages/QuizLabPage";
import ReviewPage from "@/features/arcd-agent/pages/ReviewPage";
import DigitalTwinPage from "@/features/arcd-agent/pages/DigitalTwinPage";

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

/* ── Screens ─────────────────────────────────────────────────────────── */

function LoadingScreen() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      <p className="text-sm text-muted-foreground">Loading student portfolio…</p>
    </div>
  );
}

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-64 p-8">
      <div className="text-center space-y-3 max-w-md">
        <h2 className="text-xl font-semibold text-destructive">
          Could not load portfolio data
        </h2>
        <p className="text-sm text-muted-foreground">
          Make sure the backend is running and you are enrolled in this course
          with skills selected.
        </p>
        <p className="text-xs text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}

function ArcdRoutes({ courseId }: { courseId: string }) {
  const { loading, error, selectedUid, dataVersion, dataSource } = useData();

  if (loading) return <LoadingScreen />;
  if (error) return <ErrorScreen message={error} />;

  return (
    <TwinProvider selectedUid={selectedUid} dataVersion={dataVersion} courseId={courseId}>
      {dataSource === "api" ? (
        <div className="flex items-center gap-2 mb-4 pb-3 border-b">
          <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
            Live data
          </span>
        </div>
      ) : (
        <div className="flex items-center gap-3 mb-4 pb-3 border-b">
          <DatasetSwitcher />
          <HeaderStudentPicker />
        </div>
      )}

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

export default function ArcdAgentShell() {
  const { id } = useParams<{ id: string }>();
  const courseId = id ?? "";

  return (
    <DataProvider courseId={courseId}>
      <ArcdRoutes courseId={courseId} />
    </DataProvider>
  );
}
