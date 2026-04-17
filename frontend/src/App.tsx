import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/features/auth/context/AuthContext';
import { Toaster } from '@/components/ui/sonner';
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/layout/AppSidebar"
import { ThemeToggle } from "@/components/ui/theme-toggle"
import Login from '@/features/auth/pages/Login';
import Register from '@/features/auth/pages/Register';
import Dashboard from '@/features/dashboard/pages/Dashboard';
import TeacherCourses from '@/features/courses/pages/TeacherCourses';
import AgentHubPage from '@/features/courses/pages/AgentHubPage';
import ArchitectAgentPage from '@/features/courses/pages/ArchitectAgentPage';
import CurriculumPage from '@/features/curriculum/pages/CurriculumPage';
import MergeReviewPage from '@/features/normalization/pages/MergeReviewPage';
import MarketDemandPage from '@/features/market-demand/pages/MarketDemandPage';
import ChapterQuizPage from '@/features/student-learning-path/pages/ChapterQuizPage';
import StudentLearningPathPage from '@/features/student-learning-path/pages/StudentLearningPathPage';
import StudentLearningPathStudyPage from '@/features/student-learning-path/pages/StudentLearningPathStudyPage';
import Profile from '@/features/auth/pages/Profile';
import { lazy, Suspense } from 'react';
const ArcdAgentShell = lazy(() => import('@/features/arcd-agent/ArcdAgentShell'));

function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <ThemeToggle />
        </header>
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden min-h-0 p-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

// Protected Route component
function ProtectedRoute({
  children,
  withDashboardLayout = true,
}: {
  children: React.ReactNode;
  withDashboardLayout?: boolean;
}) {
  const { isAuthenticated, isLoading, isServerWakingUp } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        {isServerWakingUp && (
          <p className="text-sm text-muted-foreground animate-pulse">
            Server is waking up, hang tight…
          </p>
        )}
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!withDashboardLayout) {
    return <>{children}</>;
  }

  return <DashboardLayout>{children}</DashboardLayout>;
}

// Public Route component (redirects to home if already authenticated)
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, isServerWakingUp } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        {isServerWakingUp && (
          <p className="text-sm text-muted-foreground animate-pulse">
            Server is waking up, hang tight…
          </p>
        )}
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/home" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route
        path="/login"
        element={
          <PublicRoute>
            <Login />
          </PublicRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicRoute>
            <Register />
          </PublicRoute>
        }
      />
      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses"
        element={
          <ProtectedRoute>
            <TeacherCourses />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id"
        element={
          <ProtectedRoute>
            <AgentHubPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/architect"
        element={
          <ProtectedRoute>
            <ArchitectAgentPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/market-analyst"
        element={
          <ProtectedRoute>
            <MarketDemandPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/learning-path"
        element={
          <ProtectedRoute>
            <StudentLearningPathPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/learning-path/study/:resourceKind/:resourceId"
        element={
          <ProtectedRoute withDashboardLayout={false}>
            <StudentLearningPathStudyPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/learning-path/chapters/:chapterIndex/quiz"
        element={
          <ProtectedRoute>
            <ChapterQuizPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/curriculum"
        element={
          <ProtectedRoute>
            <CurriculumPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/courses/:id/reviews/:reviewId"
        element={
          <ProtectedRoute>
            <MergeReviewPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <Profile />
          </ProtectedRoute>
        }
      />
      {/* ARCD Agent — nested sub-routes under each course */}
      <Route
        path="/courses/:id/arcd/*"
        element={
          <ProtectedRoute>
            <Suspense fallback={<div className="flex items-center justify-center h-64"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>}>
              <ArcdAgentShell />
            </Suspense>
          </ProtectedRoute>
        }
      />
      {/* Catch all route - redirect to home or login */}
      <Route path="*" element={<Navigate to="/home" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
        <Toaster richColors position="top-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
