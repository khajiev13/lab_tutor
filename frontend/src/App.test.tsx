import type { ReactNode } from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { coursesApi } from '@/features/courses/api';
import type { CourseReadiness } from '@/features/courses/types';

const auth = vi.hoisted(() => ({ role: 'student', authenticated: true, loading: false }));

vi.mock('@/features/courses/api', () => ({
  coursesApi: { getReadiness: vi.fn() },
}));

vi.mock('@/features/auth/context/AuthContext', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
  useAuth: () => ({
    user: {
      id: 1,
      first_name: 'Test',
      last_name: 'Student',
      email: 'student@example.com',
      role: auth.role,
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

import { AppShell } from '@/App';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
const routers: ReturnType<typeof createMemoryRouter>[] = [];
afterEach(() => { cleanup(); routers.splice(0).forEach(router => router.dispose()); });

function renderAppAt(pathname: string) {
  const router = createMemoryRouter([{path:'*', element:<AppShell />}], {initialEntries:[pathname]});
  routers.push(router);
  render(<RouterProvider router={router} />);
}

describe('App routing', () => {
  it('protects a market deep link and redirects signed-out users to Login', async () => { auth.authenticated=false; renderAppAt('/courses/1/market-analyst'); expect(await screen.findByText('Login')).toBeInTheDocument(); expect(screen.queryByText('Market Demand')).not.toBeInTheDocument(); });
  it('redirects authenticated users from public routes', async () => { renderAppAt('/login'); expect(await screen.findByText('Dashboard')).toBeInTheDocument(); });
  it('keeps market decisions focused without dashboard chrome', () => { renderAppAt('/courses/1/market-analyst'); expect(screen.getByText('Market Demand')).toBeInTheDocument(); expect(screen.queryByText('Mock Sidebar')).not.toBeInTheDocument(); });
  it('preserves the course overview route', () => { renderAppAt('/courses/1'); expect(screen.getByText('Agent Hub')).toBeInTheDocument(); });
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'student'; auth.authenticated = true; auth.loading = false;
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
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

const initialReadiness: CourseReadiness = {
  course_id: 1,
  publication_status: 'draft',
  availability_status: 'draft',
  can_publish: false,
  blockers: ['Complete the book skill bank.', 'Complete the market skill bank.', 'Review prerequisites.'],
  next_action: { id: 'book', label: 'Complete book skill bank', route: '/courses/1/architect' },
  gates: [
    { id: 'book', label: 'Book skill bank', status: 'ready', route: '/courses/1/architect', detail: 'Complete the book skill bank before publishing.' },
    { id: 'market', label: 'Market skill bank', status: 'locked', route: '/courses/1/market-analyst', detail: 'Complete or waive the market skill bank before publishing.' },
    { id: 'prerequisites', label: 'Prerequisites', status: 'locked', route: '/courses/1/prerequisites', detail: 'Review and approve prerequisites before publishing.' },
    { id: 'publish', label: 'Publish', status: 'locked', route: null, detail: 'Resolve readiness blockers before publishing.' },
  ],
  prerequisite_review: { status: 'not_started', edge_count: 0, isolated_skill_count: 0, last_generated_at: null },
};

describe('Teacher course setup access', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'teacher'; auth.authenticated = true; auth.loading = false;
    vi.mocked(coursesApi.getReadiness).mockResolvedValue(initialReadiness);
  });

  afterEach(cleanup);

  it.each(['market-analyst', 'prerequisites'])('blocks a direct visit to the locked %s step', async (route) => {
    renderAppAt(`/courses/1/${route}`);

    expect(await screen.findByRole('heading', { name: 'Complete the earlier steps first' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Continue to prepare course/i })).toHaveAttribute('href', '/courses/1/architect');
    expect(screen.queryByText('Market Demand')).not.toBeInTheDocument();
    expect(screen.queryByText('Prerequisite Review Page')).not.toBeInTheDocument();
  });

  it.each(['ready', 'complete'] as const)('opens the market workspace when its step is %s', async (status) => {
    vi.mocked(coursesApi.getReadiness).mockResolvedValue({
      ...initialReadiness,
      gates: initialReadiness.gates.map((gate) => gate.id === 'market' ? { ...gate, status } : gate),
    });
    renderAppAt('/courses/1/market-analyst');

    expect(await screen.findByText('Market Demand')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Complete the earlier steps first' })).not.toBeInTheDocument();
  });

  it('keeps later steps closed while readiness is loading', async () => {
    vi.mocked(coursesApi.getReadiness).mockReturnValue(new Promise(() => {}));
    renderAppAt('/courses/1/market-analyst');

    expect(screen.getByRole('status')).toHaveTextContent('Checking course progress');
    expect(screen.queryByText('Market Demand')).not.toBeInTheDocument();
  });

  it('keeps later steps closed after a readiness error and allows retrying', async () => {
    vi.mocked(coursesApi.getReadiness).mockRejectedValueOnce(new Error('Offline'));
    renderAppAt('/courses/1/market-analyst');

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load course progress');
    expect(screen.queryByText('Market Demand')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Complete the earlier steps first' })).toBeInTheDocument());
  });

  it('does not reuse an unlocked step when navigating to a different course', async () => {
    let resolveSecondCourse!: (value: CourseReadiness) => void;
    vi.mocked(coursesApi.getReadiness)
      .mockResolvedValueOnce({
        ...initialReadiness,
        gates: initialReadiness.gates.map((gate) => gate.id === 'market' ? { ...gate, status: 'ready' } : gate),
      })
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecondCourse = resolve; }));
    renderAppAt('/courses/1/market-analyst');
    expect(await screen.findByText('Market Demand')).toBeInTheDocument();

    await act(async () => {
      await routers.at(-1)!.navigate('/courses/2/market-analyst');
    });
    expect(screen.queryByText('Market Demand')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Checking course progress');

    await act(async () => {
      resolveSecondCourse({
        ...initialReadiness,
        course_id: 2,
        next_action: { id: 'book', label: 'Complete book skill bank', route: '/courses/2/architect' },
      });
    });
    expect(screen.getByRole('link', { name: /Continue to prepare course/i })).toHaveAttribute('href', '/courses/2/architect');
  });
});
