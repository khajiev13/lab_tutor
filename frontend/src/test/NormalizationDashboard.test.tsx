import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, type Mock } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { NormalizationDashboard } from '../features/normalization/components/NormalizationDashboard';
import {
  applyNormalizationReview,
  getNormalizationReview,
  listCourseConcepts,
  updateNormalizationReviewDecisions,
} from '../features/normalization/api';
import { startNormalizationStream } from '../services/normalization';

vi.mock('../features/normalization/api', () => ({
  listCourseConcepts: vi.fn(),
  getNormalizationReview: vi.fn(),
  updateNormalizationReviewDecisions: vi.fn(),
  applyNormalizationReview: vi.fn(),
}));

vi.mock('../services/normalization', () => ({
  startNormalizationStream: vi.fn(),
}));

describe('NormalizationDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => (key === 'access_token' ? 'test-token' : null)),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0,
    });
  });

  it('loads concept bank and starts streaming on click', async () => {
    (listCourseConcepts as Mock).mockResolvedValue(['a', 'b']);
    (startNormalizationStream as Mock).mockImplementation(
      async ({ onEvent }: { onEvent: (evt: unknown) => void }) => {
      onEvent({
        type: 'update',
        iteration: 0,
        phase: 'generation',
        agent_activity: 'Generating',
        requires_review: false,
        review_id: null,
        concepts_count: 2,
        merges_found: 1,
        relationships_found: 0,
        latest_merges: [
          {
            concept_a: 'a',
            concept_b: 'b',
            canonical: 'a',
            variants: ['a', 'b'],
            r: 'same',
          },
        ],
        latest_relationships: [],
        total_merges: 1,
        total_relationships: 0,
      });
      }
    );

    render(
      <MemoryRouter>
        <NormalizationDashboard courseId={1} />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Concept normalization')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start'));

    await waitFor(() => {
      expect(startNormalizationStream).toHaveBeenCalled();
      expect(screen.getByText(/Agent is working/)).toBeInTheDocument();
    });
  });

  it('shows review required CTA on completion and opens review dialog', async () => {
    (listCourseConcepts as Mock).mockResolvedValue(['a', 'b']);
    (getNormalizationReview as Mock).mockResolvedValue({
      id: 'normrev_x',
      course_id: 1,
      status: 'pending',
      created_by_user_id: 1,
      created_at: '',
      proposals: [],
      definitions: {},
    });
    (updateNormalizationReviewDecisions as Mock).mockResolvedValue({ review_id: 'normrev_x', updated: 0 });
    (applyNormalizationReview as Mock).mockResolvedValue({
      review_id: 'normrev_x',
      total_approved: 0,
      applied: 0,
      skipped: 0,
      failed: 0,
      errors: [],
    });

    (startNormalizationStream as Mock).mockImplementation(
      async ({ onEvent }: { onEvent: (evt: unknown) => void }) => {
        onEvent({
          type: 'complete',
          iteration: 2,
          phase: 'complete',
          agent_activity: 'done',
          requires_review: true,
          review_id: 'normrev_x',
          concepts_count: 2,
          merges_found: 0,
          relationships_found: 0,
          latest_merges: [],
          latest_relationships: [],
          total_merges: 1,
          total_relationships: 0,
        });
      }
    );

    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<NormalizationDashboard courseId={1} />} />
          <Route path="/courses/1/reviews/normrev_x" element={<div>Review page</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Concept normalization')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Start'));

    await waitFor(() => {
      expect(screen.getByText('Agent needs your feedback')).toBeInTheDocument();
      expect(screen.getByText('Review merges')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Review merges'));

    await waitFor(() => {
      expect(screen.getByText('Review page')).toBeInTheDocument();
    });
  });
});


