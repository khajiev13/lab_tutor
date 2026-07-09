import { describe, expect, it, vi } from 'vitest';
import api from '@/services/api';
import {
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
  it('loads the individual profile', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { user_id: 7, onboarding_status: 'needs_cv', target_titles: [] },
    });

    const profile = await getIndividualProfile();

    expect(api.get).toHaveBeenCalledWith('/individual-learning/profile');
    expect(profile.onboarding_status).toBe('needs_cv');
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
