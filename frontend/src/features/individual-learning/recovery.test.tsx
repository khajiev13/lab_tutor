import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '@/features/auth/context/AuthContext';
import * as individualLearningApi from '@/features/individual-learning/api';
import {
  getIndividualRecoveryRedirect,
} from '@/features/individual-learning/recovery';
import { IndividualRecoveryGate } from '@/features/individual-learning/IndividualRecoveryGate';
import {
  clearIndividualGraphSession,
  readIndividualGraphSession,
} from '@/features/individual-learning/graph-session';

vi.mock('@/features/auth/context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  startIndividualGraph: vi.fn(),
}));

const reviewRecovery = {
  user_id: 7,
  onboarding_status: 'needs_profile_review' as const,
  target_titles: ['Data Analyst'],
  cv_document_id: 42,
  extraction_run_id: 91,
  active_thread_id: 'opaque-thread-value',
  next_step: 'review_profile' as const,
  extracted_profile: {
    summary: 'Analytics profile',
    confidence_summary: { skills: 0.82 },
  },
  pending_interrupt: {
    kind: 'review_profile_and_roles' as const,
    profile: { summary: 'Analytics profile' },
    target_title_suggestions: ['Data Analyst'],
  },
};

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function GateHarness({ pathname }: { pathname: string }) {
  return (
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route
          path="/individual/*"
          element={
            <IndividualRecoveryGate>
              <div>Protected individual page</div>
              <LocationProbe />
            </IndividualRecoveryGate>
          }
        />
        <Route
          path="/home"
          element={
            <>
              <div>Home page</div>
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

function renderGate(pathname: string) {
  return render(<GateHarness pathname={pathname} />);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe('individual recovery routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearIndividualGraphSession();
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 7,
        first_name: 'Indy',
        last_name: 'Learner',
        email: 'indy@example.test',
        role: 'individual',
        created_at: '2026-07-10T00:00:00Z',
      },
      isAuthenticated: true,
      isLoading: false,
      isServerWakingUp: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    });
  });

  it('maps only unsafe downstream routes to the durable recovery step', () => {
    expect(getIndividualRecoveryRedirect('upload_cv', '/individual/profile', null)).toBe(
      '/individual/onboarding',
    );
    expect(getIndividualRecoveryRedirect('review_profile', '/individual/jobs', null)).toBe(
      '/individual/profile',
    );
    expect(getIndividualRecoveryRedirect('review_profile', '/individual/jobs/', null)).toBe(
      '/individual/profile',
    );
    expect(getIndividualRecoveryRedirect('review_profile', '/INDIVIDUAL/JOBS', null)).toBe(
      '/individual/profile',
    );
    expect(
      getIndividualRecoveryRedirect('select_jobs_and_skills', '/individual/skills', {
        selectedPostingUrls: [],
      }),
    ).toBe('/individual/jobs');
    expect(
      getIndividualRecoveryRedirect('select_jobs_and_skills', '/individual/skills', {
        selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
      }),
    ).toBeNull();
    expect(
      getIndividualRecoveryRedirect('learning_path', '/individual/profile', null),
    ).toBeNull();
  });

  it('starts a missing review checkpoint before rendering the profile route', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      ...reviewRecovery,
      pending_interrupt: null,
    });
    vi.mocked(individualLearningApi.startIndividualGraph).mockResolvedValue({
      thread_id: 'opaque-thread-value',
      status: 'interrupted',
      interrupt: reviewRecovery.pending_interrupt,
      target_titles: ['Data Analyst'],
      selected_posting_urls: [],
      selected_skill_names: [],
    });

    renderGate('/individual/profile');

    expect(screen.getByText(/recovering your individual learning progress/i)).toBeInTheDocument();
    expect(await screen.findByText('Protected individual page')).toBeInTheDocument();
    expect(individualLearningApi.startIndividualGraph).toHaveBeenCalledWith(42);
    expect(readIndividualGraphSession()).toMatchObject({
      extractionRunId: 91,
      threadId: 'opaque-thread-value',
      reviewInterrupt: { kind: 'review_profile_and_roles' },
    });
  });

  it('redirects an unsafe route to the recovered step', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue(reviewRecovery);

    renderGate('/individual/skills');

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent('/individual/profile');
    });
  });

  it('shows a retryable recovery error without rendering the page early', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile)
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce({
        ...reviewRecovery,
        onboarding_status: 'needs_cv',
        cv_document_id: null,
        extraction_run_id: null,
        active_thread_id: null,
        next_step: 'upload_cv',
        extracted_profile: null,
        pending_interrupt: null,
      });

    renderGate('/individual/onboarding');

    expect(await screen.findByText(/^Could not recover your progress$/)).toBeInTheDocument();
    expect(screen.queryByText('Protected individual page')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /retry recovery/i }));

    expect(await screen.findByText('Protected individual page')).toBeInTheDocument();
    expect(individualLearningApi.getIndividualProfile).toHaveBeenCalledTimes(2);
  });

  it('routes non-individual users home without loading private recovery data', async () => {
    vi.mocked(useAuth).mockReturnValue({
      ...vi.mocked(useAuth).mock.results[0]?.value,
      user: {
        id: 9,
        first_name: 'Teacher',
        last_name: 'User',
        email: 'teacher@example.test',
        role: 'teacher',
        created_at: '2026-07-10T00:00:00Z',
      },
    });

    renderGate('/individual/profile');

    expect(await screen.findByText('Home page')).toBeInTheDocument();
    expect(individualLearningApi.getIndividualProfile).not.toHaveBeenCalled();
  });

  it('does not hydrate a stale recovery response after logout', async () => {
    const profileRequest = deferred<typeof reviewRecovery>();
    vi.mocked(individualLearningApi.getIndividualProfile).mockReturnValue(profileRequest.promise);
    const view = renderGate('/individual/profile');

    vi.mocked(useAuth).mockReturnValue({
      ...vi.mocked(useAuth).mock.results[0]?.value,
      user: null,
      isAuthenticated: false,
    });
    view.rerender(<GateHarness pathname="/individual/profile" />);

    await act(async () => {
      profileRequest.resolve(reviewRecovery);
      await profileRequest.promise;
    });

    expect(await screen.findByText('Home page')).toBeInTheDocument();
    expect(readIndividualGraphSession()).toBeNull();
  });

  it('does not persist a stale checkpoint response after an account switch', async () => {
    const oldCheckpointRequest = deferred<Awaited<ReturnType<typeof individualLearningApi.startIndividualGraph>>>();
    const newProfileRequest = deferred<typeof reviewRecovery>();
    vi.mocked(individualLearningApi.getIndividualProfile)
      .mockResolvedValueOnce({ ...reviewRecovery, pending_interrupt: null })
      .mockReturnValueOnce(newProfileRequest.promise);
    vi.mocked(individualLearningApi.startIndividualGraph).mockReturnValue(
      oldCheckpointRequest.promise,
    );
    const view = renderGate('/individual/profile');

    await waitFor(() => {
      expect(individualLearningApi.startIndividualGraph).toHaveBeenCalledWith(42);
    });

    vi.mocked(useAuth).mockReturnValue({
      ...vi.mocked(useAuth).mock.results[0]?.value,
      user: {
        id: 8,
        first_name: 'New',
        last_name: 'Learner',
        email: 'new-learner@example.test',
        role: 'individual',
        created_at: '2026-07-10T00:00:00Z',
      },
    });
    clearIndividualGraphSession();
    view.rerender(<GateHarness pathname="/individual/profile" />);

    await act(async () => {
      oldCheckpointRequest.resolve({
        thread_id: 'stale-thread-value',
        status: 'interrupted',
        interrupt: reviewRecovery.pending_interrupt,
        target_titles: ['Data Analyst'],
        selected_posting_urls: [],
        selected_skill_names: [],
      });
      await oldCheckpointRequest.promise;
    });

    expect(readIndividualGraphSession()).toBeNull();
    view.unmount();
  });
});
