import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '@/services/api';
import { buildLearningPath, deselectSkills, selectSkills } from '@/features/student-learning-path/api';

vi.mock('@/services/api', () => ({ default: { post: vi.fn(), delete: vi.fn() } }));

describe('reference selection request compatibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.post).mockResolvedValue({data: {}});
    vi.mocked(api.delete).mockResolvedValue({data: {}});
  });

  it('sends reference IDs without a client source on direct select and deselect', async () => {
    await selectSkills(1, {skill_reference_ids: ['reference-1']});
    await deselectSkills(1, {skill_reference_ids: ['reference-1']});
    expect(api.post).toHaveBeenCalledWith('/student-learning-path/1/select-skills', {skill_reference_ids: ['reference-1']});
    expect(api.delete).toHaveBeenCalledWith('/student-learning-path/1/deselect-skills', {data: {skill_reference_ids: ['reference-1']}});
  });

  it('serializes a mixed build without repeating reference-backed skills by name', async () => {
    await buildLearningPath(1, [{name: 'Legacy skill', source: 'book'}], ['reference-1']);
    expect(api.post).toHaveBeenCalledWith('/student-learning-path/1/build', {
      selected_skills: [{name: 'Legacy skill', source: 'book'}], skill_reference_ids: ['reference-1'],
    });
  });

  it('retains old name/source selection and bodyless recovery', async () => {
    await selectSkills(1, ['Kafka'], 'market');
    await deselectSkills(1, ['Kafka']);
    await buildLearningPath(1);
    expect(api.post).toHaveBeenCalledWith('/student-learning-path/1/select-skills', {skill_names: ['Kafka'], source: 'market'});
    expect(api.delete).toHaveBeenCalledWith('/student-learning-path/1/deselect-skills', {data: {skill_names: ['Kafka']}});
    expect(api.post).toHaveBeenCalledWith('/student-learning-path/1/build', undefined);
  });
});
