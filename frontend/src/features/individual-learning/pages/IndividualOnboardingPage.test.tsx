import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import * as individualLearningApi from '@/features/individual-learning/api';
import IndividualOnboardingPage from './IndividualOnboardingPage';

vi.mock('@/features/individual-learning/api', () => ({
  getIndividualProfile: vi.fn(),
  uploadCv: vi.fn(),
  startIndividualGraph: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
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

describe('IndividualOnboardingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();

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
});
