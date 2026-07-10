import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '@/services/api';
import {
  buildIndividualLearningPath,
  getIndividualProfile,
  resumeIndividualGraph,
  startIndividualGraph,
} from '@/features/individual-learning/api';

vi.mock('@/services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('individual learning api', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads the individual profile', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        user_id: 7,
        onboarding_status: 'needs_profile_review',
        target_titles: ['Data Analyst'],
        cv_document_id: 42,
        extraction_run_id: 91,
        active_thread_id: 'opaque-thread-value',
        next_step: 'review_profile',
        extracted_profile: {
          summary: 'Analytics profile',
          confidence_summary: { skills: 0.82 },
        },
        pending_interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Analytics profile' },
          target_title_suggestions: ['Data Analyst'],
        },
      },
    });

    const profile = await getIndividualProfile();

    expect(api.get).toHaveBeenCalledWith('/individual-learning/profile');
    expect(profile).toMatchObject({
      cv_document_id: 42,
      extraction_run_id: 91,
      active_thread_id: 'opaque-thread-value',
      next_step: 'review_profile',
      extracted_profile: { confidence_summary: { skills: 0.82 } },
      pending_interrupt: { kind: 'review_profile_and_roles' },
    });
  });

  it('returns the durable learning run id from a build', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { status: 'completed', run_id: 'learning-run-4' },
    });

    const result = await buildIndividualLearningPath(['SQL']);

    expect(result).toEqual({ status: 'completed', run_id: 'learning-run-4' });
  });

  it('starts and resumes an individual graph with the backend contract', async () => {
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        data: {
          thread_id: 'individual-7-cv-42',
          status: 'interrupted',
          interrupt: { kind: 'review_profile_and_roles' },
          target_titles: [],
          selected_posting_urls: [],
          selected_skill_names: [],
        },
      })
      .mockResolvedValueOnce({
        data: {
          thread_id: 'individual-7-cv-42',
          status: 'interrupted',
          interrupt: { kind: 'choose_jobs_and_skills' },
          target_titles: ['Data Analyst'],
          selected_posting_urls: [],
          selected_skill_names: [],
        },
      });

    await startIndividualGraph(42);
    await resumeIndividualGraph('individual-7-cv-42', {
      approved: true,
      target_titles: ['Data Analyst'],
    });

    expect(api.post).toHaveBeenNthCalledWith(1, '/individual-learning/graph/start', {
      cv_document_id: 42,
    });
    expect(api.post).toHaveBeenNthCalledWith(2, '/individual-learning/graph/resume', {
      thread_id: 'individual-7-cv-42',
      payload: {
        approved: true,
        target_titles: ['Data Analyst'],
      },
    });
  });
});
