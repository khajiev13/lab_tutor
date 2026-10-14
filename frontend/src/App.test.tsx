import type { ReactNode } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({authenticated:true,loading:false}));
vi.mock('@/features/auth/context/AuthContext', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useAuth: () => ({
    user: {
      id: 1,
      first_name: 'Test',
      last_name: 'Student',
      email: 'student@example.com',
      role: 'student',
      created_at: '2026-04-15T00:00:00Z',
    },
    isAuthenticated: auth.authenticated,
    isLoading: auth.loading,
    isServerWakingUp: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  }),
}));

vi.mock('@/components/ui/sonner', () => ({
  Toaster: () => null,
}));

vi.mock('@/components/ui/sidebar', () => ({
  SidebarProvider: ({ children }: { children: ReactNode }) => (
    <div data-testid="dashboard-layout">{children}</div>
  ),
  SidebarInset: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SidebarTrigger: () => <button type="button">Open sidebar</button>,
}));

vi.mock('@/components/layout/AppSidebar', () => ({
  AppSidebar: () => <aside>Mock Sidebar</aside>,
}));

vi.mock('@/components/ui/theme-toggle', () => ({
  ThemeToggle: () => <button type="button" aria-label="Toggle theme">Toggle theme</button>,
}));

vi.mock('@/features/auth/pages/Login', () => ({ default: () => <div>Login</div> }));
vi.mock('@/features/auth/pages/Register', () => ({ default: () => <div>Register</div> }));
vi.mock('@/features/dashboard/pages/Dashboard', () => ({ default: () => <div>Dashboard</div> }));
vi.mock('@/features/courses/pages/TeacherCourses', () => ({ default: () => <div>Teacher Courses</div> }));
vi.mock('@/features/courses/pages/AgentHubPage', () => ({ default: () => <div>Agent Hub</div> }));
vi.mock('@/features/courses/pages/ArchitectAgentPage', () => ({
  default: () => <div>Architect Agent</div>,
}));
vi.mock('@/features/curriculum/pages/CurriculumPage', () => ({ default: () => <div>Curriculum</div> }));
vi.mock('@/features/normalization/pages/MergeReviewPage', () => ({
  default: () => <div>Merge Review</div>,
}));
vi.mock('@/features/market-demand/pages/MarketDemandPage', () => ({
  default: () => <div>Market Demand</div>,
}));
vi.mock('@/features/prerequisite-review/pages/PrerequisiteReviewPage', () => ({
  default: () => <div>Prerequisite Review Page</div>,
}));
vi.mock('@/features/student-learning-path/pages/ChapterQuizPage', () => ({
  default: () => <div>Chapter Quiz</div>,
}));
vi.mock('@/features/student-learning-path/pages/StudentLearningPathPage', () => ({
  default: () => <div>Learning Path Page</div>,
}));
vi.mock('@/features/student-learning-path/pages/StudentLearningPathStudyPage', () => ({
  default: () => <div>Study Page</div>,
}));
vi.mock('@/features/auth/pages/Profile', () => ({ default: () => <div>Profile</div> }));

import {AppShell} from './App';
import {createMemoryRouter, RouterProvider} from 'react-router-dom';
const routers: ReturnType<typeof createMemoryRouter>[] = [];

function renderAppAt(pathname: string) {
  const router=createMemoryRouter([{path:'*',element:<AppShell/>}],{initialEntries:[pathname]}); routers.push(router);
  render(<RouterProvider router={router}/>);
}

describe('App routing', () => {
  it('protects a market deep link and redirects signed-out users to Login', async () => {auth.authenticated=false; renderAppAt('/courses/1/market-analyst'); expect(await screen.findByText('Login')).toBeInTheDocument(); expect(screen.queryByText('Market Demand')).not.toBeInTheDocument();});
  it('redirects authenticated users from public routes', async () => {renderAppAt('/login'); expect(await screen.findByText('Dashboard')).toBeInTheDocument();});
  it('keeps the protected market decision focused without dashboard chrome', () => {renderAppAt('/courses/1/market-analyst'); expect(screen.getByText('Market Demand')).toBeInTheDocument(); expect(screen.queryByText('Mock Sidebar')).not.toBeInTheDocument();});
  it('preserves the agents hub route', () => {renderAppAt('/courses/1'); expect(screen.getByText('Agent Hub')).toBeInTheDocument();});
  beforeEach(() => {
    auth.authenticated=true; auth.loading=false;
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup(); routers.splice(0).forEach(router => router.dispose());
  });

  it('keeps dashboard chrome on the learning-path route', () => {
    renderAppAt('/courses/1/learning-path');

    expect(screen.getByText('Learning Path Page')).toBeInTheDocument();
    expect(screen.getByText('Mock Sidebar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Toggle theme/i })).toBeInTheDocument();
  });

  it('keeps dashboard chrome on the prerequisite review route', () => {
    renderAppAt('/courses/1/prerequisites');

    expect(screen.getByText('Prerequisite Review Page')).toBeInTheDocument();
    expect(screen.getByText('Mock Sidebar')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Toggle theme/i })).toBeInTheDocument();
  });

  it('renders the study route without dashboard chrome', () => {
    renderAppAt('/courses/1/learning-path/study/reading/reading-1');

    expect(screen.getByText('Study Page')).toBeInTheDocument();
    expect(screen.queryByText('Mock Sidebar')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Toggle theme/i })).not.toBeInTheDocument();
  });
});
