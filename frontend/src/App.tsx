import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from '@/features/auth/context/AuthContext';
import { Toaster } from '@/components/ui/sonner';
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/layout/AppSidebar"
import Login from '@/features/auth/pages/Login';
import Register from '@/features/auth/pages/Register';
import Dashboard from '@/features/dashboard/pages/Dashboard';
import TeacherCourses from '@/features/courses/pages/TeacherCourses';
import AgentHubPage from '@/features/courses/pages/AgentHubPage';
import ArchitectAgentPage from '@/features/courses/pages/ArchitectAgentPage';
import CourseGraphPage from '@/features/graph/pages/CourseGraphPage';
import MergeReviewPage from '@/features/normalization/pages/MergeReviewPage';
import MarketDemandPage from '@/features/market-demand/pages/MarketDemandPage';
import Profile from '@/features/auth/pages/Profile';

function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
        </header>
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden min-h-0 p-6">
          {children}
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}

// Protected Route component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
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

  return (
    <DashboardLayout>
      {children}
    </DashboardLayout>
  );
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
        path="/courses/:id/graph"
        element={
          <ProtectedRoute>
            <CourseGraphPage />
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
