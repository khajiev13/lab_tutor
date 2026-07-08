import { describe, expect, it, vi } from 'vitest';
import api from '@/services/api';
import { getIndividualProfile } from '@/features/individual-learning/api';

vi.mock('@/services/api', () => ({
  default: {
    get: vi.fn(),
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
});
