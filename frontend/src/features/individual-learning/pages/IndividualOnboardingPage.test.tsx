import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualOnboardingPage from './IndividualOnboardingPage';
import {
  establishAuthSession,
  invalidateAuthSession,
  resetAuthSessionForTests,
} from '@/features/auth/auth-session';
import { clearIndividualGraphSession } from '@/features/individual-learning/graph-session';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  uploadCv: vi.fn(),
  retryCvExtraction: vi.fn(),
  startIndividualGraph: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/individual/onboarding']}>
      <Routes>
        <Route
          path="/individual/onboarding"
          element={
            <>
              <IndividualOnboardingPage />
              <LocationProbe />
            </>
          }
        />
        <Route
          path="/individual/profile"
          element={
            <>
              <div>Profile step</div>
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe('IndividualOnboardingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    resetAuthSessionForTests();
    establishAuthSession(7);

    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'needs_cv',
      target_titles: [],
      cv_document_id: null,
      extraction_run_id: null,
      active_thread_id: null,
      next_step: 'upload_cv',
      extracted_profile: null,
      pending_interrupt: null,
    });
    vi.mocked(individualLearningApi.uploadCv).mockResolvedValue({
      id: 42,
      user_id: 7,
      original_filename: 'candidate-cv.pdf',
      content_type: 'application/pdf',
      status: 'uploaded',
    });
    vi.mocked(individualLearningApi.retryCvExtraction).mockResolvedValue({
      id: 42,
      user_id: 7,
      original_filename: 'candidate-cv.pdf',
      content_type: 'application/pdf',
      status: 'completed',
    });
    vi.mocked(individualLearningApi.startIndividualGraph).mockResolvedValue({
      thread_id: 'individual-7-cv-42',
      status: 'interrupted',
      interrupt: {
        kind: 'review_profile_and_roles',
        profile: {
          summary: 'Built dashboards for operations teams.',
          target_title_suggestions: ['Data Analyst'],
        },
        target_title_suggestions: ['Data Analyst'],
      },
      target_titles: [],
      selected_posting_urls: [],
      selected_skill_names: [],
    });
  });

  it('uploads a CV, starts the graph, and navigates to profile review', async () => {
    renderPage();

    const input = await screen.findByLabelText(/cv file/i);
    const file = new File(['cv'], 'candidate-cv.pdf', { type: 'application/pdf' });

    expect(input).toHaveAttribute('accept', '.pdf,.docx');

    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /upload cv/i }));

    await waitFor(() => {
      expect(individualLearningApi.uploadCv).toHaveBeenCalledWith(file);
    });
    await waitFor(() => {
      expect(individualLearningApi.startIndividualGraph).toHaveBeenCalledWith(42);
    });

    expect(await screen.findByText('Profile step')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/individual/profile');
    expect(toast.success).toHaveBeenCalled();

    const storedSession = sessionStorage.getItem('individual-learning.graph-session');
    expect(storedSession).toContain('individual-7-cv-42');
    expect(storedSession).not.toContain('candidate-cv.pdf');
    expect(JSON.parse(storedSession ?? '{}')).toMatchObject({ ownerUserId: 7 });
  });

  it('retries onboarding-status network failures inline without resetting the form', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile)
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({
        user_id: 7,
        onboarding_status: 'needs_cv',
        target_titles: [],
        cv_document_id: null,
        extraction_run_id: null,
        active_thread_id: null,
        next_step: 'upload_cv',
        extracted_profile: null,
        pending_interrupt: null,
      });

    renderPage();

    const input = screen.getByLabelText(/cv file/i);
    const file = new File(['cv'], 'candidate-cv.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(await screen.findByRole('button', { name: /retry status/i }));

    await waitFor(() => {
      expect(individualLearningApi.getIndividualProfile).toHaveBeenCalledTimes(2);
    });
    expect((screen.getByLabelText(/cv file/i) as HTMLInputElement).files?.[0]).toBe(file);
    expect(await screen.findByText('needs cv')).toBeInTheDocument();
  });

  it('does not persist a delayed graph start after the authenticated account changes', async () => {
    const graphStart = deferred<Awaited<ReturnType<typeof individualLearningApi.startIndividualGraph>>>();
    vi.mocked(individualLearningApi.startIndividualGraph).mockReturnValue(graphStart.promise);
    renderPage();

    const file = new File(['cv'], 'candidate-cv.pdf', { type: 'application/pdf' });
    fireEvent.change(await screen.findByLabelText(/cv file/i), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /upload cv/i }));
    await waitFor(() => expect(individualLearningApi.startIndividualGraph).toHaveBeenCalledWith(42));

    invalidateAuthSession();
    establishAuthSession(8);
    clearIndividualGraphSession();
    await act(async () => {
      graphStart.resolve({
        thread_id: 'individual-7-cv-42',
        status: 'interrupted',
        interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Private former-user profile' },
          target_title_suggestions: ['Data Analyst'],
        },
        target_titles: [],
        selected_posting_urls: [],
        selected_skill_names: [],
      });
      await graphStart.promise;
    });

    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
    expect(screen.queryByText('Profile step')).not.toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('does not persist a delayed graph start after the onboarding page unmounts', async () => {
    const graphStart = deferred<Awaited<ReturnType<typeof individualLearningApi.startIndividualGraph>>>();
    vi.mocked(individualLearningApi.startIndividualGraph).mockReturnValue(graphStart.promise);
    const view = renderPage();

    const file = new File(['cv'], 'candidate-cv.pdf', { type: 'application/pdf' });
    fireEvent.change(await screen.findByLabelText(/cv file/i), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /upload cv/i }));
    await waitFor(() => expect(individualLearningApi.startIndividualGraph).toHaveBeenCalled());
    view.unmount();

    await act(async () => {
      graphStart.resolve({
        thread_id: 'individual-7-cv-42',
        status: 'interrupted',
        interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Unmounted private profile' },
          target_title_suggestions: [],
        },
        target_titles: [],
        selected_posting_urls: [],
        selected_skill_names: [],
      });
      await graphStart.promise;
    });

    expect(sessionStorage.getItem('individual-learning.graph-session')).toBeNull();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('recovers a failed CV extraction by retrying the existing document', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'error',
      target_titles: [],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: null,
      next_step: 'retry_cv',
      extracted_profile: null,
      pending_interrupt: null,
    });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /retry cv extraction/i }));

    await waitFor(() => {
      expect(individualLearningApi.retryCvExtraction).toHaveBeenCalledWith(42);
      expect(individualLearningApi.startIndividualGraph).toHaveBeenCalledWith(42);
    });
    expect(individualLearningApi.uploadCv).not.toHaveBeenCalled();
    expect(await screen.findByText('Profile step')).toBeInTheDocument();
  });

  it('keeps failed CV recovery retryable when the retry request fails', async () => {
    vi.mocked(individualLearningApi.getIndividualProfile).mockResolvedValue({
      user_id: 7,
      onboarding_status: 'error',
      target_titles: [],
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: null,
      next_step: 'retry_cv',
      extracted_profile: null,
      pending_interrupt: null,
    });
    vi.mocked(individualLearningApi.retryCvExtraction).mockRejectedValue({
      response: { status: 503 },
    });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: /retry cv extraction/i }));

    expect(await screen.findByText(/could not retry cv extraction/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry cv extraction/i })).toBeEnabled();
    expect(individualLearningApi.startIndividualGraph).not.toHaveBeenCalled();
  });
});
