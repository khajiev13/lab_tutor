import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearIndividualGraphSession,
  clearIndividualGraphSessionForOtherUser,
  hydrateIndividualGraphSession,
  persistIndividualGraphResponse,
  readIndividualGraphSession,
  writeIndividualGraphSession,
} from '@/features/individual-learning/graph-session';

const storedSession = {
  ownerUserId: 7,
  threadId: 'older-thread',
  graphStatus: 'interrupted' as const,
  targetTitles: ['Data Analyst'],
  selectedPostingUrls: [],
  selectedSkillNames: [],
};

const recoveredProfile = {
  user_id: 7,
  onboarding_status: 'needs_profile_review' as const,
  target_titles: ['Data Analyst'],
  cv_document_id: 42,
  extraction_run_id: 91,
  active_thread_id: 'opaque-thread-value',
  next_step: 'review_profile' as const,
  extracted_profile: {
    summary: 'Analytics profile',
    skills: [{ name: 'SQL', confidence: 0.82 }],
    confidence_summary: { skills: 0.82 },
  },
  pending_interrupt: {
    kind: 'review_profile_and_roles' as const,
    profile: { summary: 'Analytics profile' },
    target_title_suggestions: ['Data Analyst'],
  },
};

describe('individual graph session', () => {
  beforeEach(() => {
    clearIndividualGraphSession();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps resumable graph metadata without storing CV file data or credentials', () => {
    persistIndividualGraphResponse(
      {
        thread_id: 'individual-7-cv-42',
        status: 'interrupted',
        interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Analytics profile' },
          target_title_suggestions: ['Data Analyst'],
        },
        target_titles: [],
        selected_posting_urls: [],
        selected_skill_names: [],
      },
      { cvDocumentId: 42, ownerUserId: 7 },
    );

    expect(readIndividualGraphSession()).toMatchObject({
      cvDocumentId: 42,
      ownerUserId: 7,
      threadId: 'individual-7-cv-42',
      graphStatus: 'interrupted',
      targetTitles: [],
      reviewInterrupt: { kind: 'review_profile_and_roles' },
    });

    const raw = sessionStorage.getItem('individual-learning.graph-session') ?? '';
    expect(raw).not.toContain('candidate-cv.pdf');
    expect(raw).not.toMatch(/token|authorization|password/i);
  });

  it('keeps an in-memory navigation handoff when session storage is unavailable', () => {
    vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
      getItem: () => null,
      setItem: () => {
        throw new Error('storage unavailable');
      },
      removeItem: () => undefined,
    } as unknown as Storage);

    const result = persistIndividualGraphResponse(
      {
        thread_id: 'individual-7-cv-42',
        status: 'interrupted',
        interrupt: {
          kind: 'review_profile_and_roles',
          profile: { summary: 'Analytics profile' },
          target_title_suggestions: ['Data Analyst'],
        },
        target_titles: [],
        selected_posting_urls: [],
        selected_skill_names: [],
      },
      { cvDocumentId: 42, ownerUserId: 7 },
    );

    expect(result.stored).toBe(false);
    expect(readIndividualGraphSession()).toMatchObject({
      ownerUserId: 7,
      threadId: 'individual-7-cv-42',
    });
  });

  it('does not let an older stored session overwrite a newer in-memory session after setItem fails', () => {
    vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
      getItem: () => JSON.stringify(storedSession),
      setItem: () => {
        throw new Error('storage unavailable');
      },
      removeItem: () => undefined,
    } as unknown as Storage);

    expect(
      writeIndividualGraphSession({
        ...storedSession,
        threadId: 'newer-thread',
        targetTitles: ['Analytics Engineer'],
      }),
    ).toBe(false);

    expect(readIndividualGraphSession()).toMatchObject({
      threadId: 'newer-thread',
      targetTitles: ['Analytics Engineer'],
    });
  });

  it('does not resurrect a cleared prior-owner session after removeItem fails', () => {
    vi.spyOn(window, 'sessionStorage', 'get').mockReturnValue({
      getItem: () => JSON.stringify(storedSession),
      setItem: () => undefined,
      removeItem: () => {
        throw new Error('storage unavailable');
      },
    } as unknown as Storage);

    clearIndividualGraphSessionForOtherUser(8);

    expect(readIndividualGraphSession()).toBeNull();
  });

  it('hydrates a review interrupt into empty storage without interpreting the opaque thread id', () => {
    const session = hydrateIndividualGraphSession(recoveredProfile);

    expect(session).toMatchObject({
      ownerUserId: 7,
      cvDocumentId: 42,
      extractionRunId: 91,
      threadId: 'opaque-thread-value',
      nextStep: 'review_profile',
      graphStatus: 'interrupted',
      reviewInterrupt: { kind: 'review_profile_and_roles' },
      extractedProfile: { confidence_summary: { skills: 0.82 } },
    });
  });

  it('hydrates recovered job candidates after storage is lost', () => {
    const session = hydrateIndividualGraphSession({
      ...recoveredProfile,
      onboarding_status: 'needs_skill_selection',
      next_step: 'select_jobs_and_skills',
      pending_interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [
          {
            url: 'https://example.test/jobs/data-analyst',
            title: 'Data Analyst',
            skills: [{ name: 'SQL' }],
          },
        ],
        skill_bank: [{ name: 'SQL' }],
      },
    });

    expect(session?.jobsInterrupt?.candidate_jobs).toEqual([
      expect.objectContaining({ title: 'Data Analyst' }),
    ]);
  });

  it('replaces drafts from a stale extraction attempt', () => {
    writeIndividualGraphSession({
      ...storedSession,
      threadId: 'opaque-thread-value',
      extractionRunId: 90,
      selectedPostingUrls: ['https://example.test/jobs/stale'],
      selectedSkillNames: ['Stale skill'],
    });

    const session = hydrateIndividualGraphSession(recoveredProfile);

    expect(session).toMatchObject({
      extractionRunId: 91,
      selectedPostingUrls: [],
      selectedSkillNames: [],
    });
  });

  it('preserves drafts only when owner, thread, and extraction attempt all match', () => {
    writeIndividualGraphSession({
      ...storedSession,
      threadId: 'opaque-thread-value',
      extractionRunId: 91,
      targetTitles: ['Draft Analytics Engineer'],
      selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
      selectedSkillNames: ['SQL'],
    });

    const session = hydrateIndividualGraphSession({
      ...recoveredProfile,
      onboarding_status: 'needs_skill_selection',
      next_step: 'select_jobs_and_skills',
      pending_interrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [
          { url: 'https://example.test/jobs/data-analyst', title: 'Data Analyst' },
        ],
        skill_bank: [{ name: 'SQL' }],
      },
    });

    expect(session).toMatchObject({
      targetTitles: ['Draft Analytics Engineer'],
      selectedPostingUrls: ['https://example.test/jobs/data-analyst'],
      selectedSkillNames: ['SQL'],
      jobsInterrupt: { kind: 'choose_jobs_and_skills' },
    });
  });

  it('turns completed recovery into safe read-only state without a synthetic interrupt', () => {
    writeIndividualGraphSession({
      ...storedSession,
      threadId: 'opaque-thread-value',
      extractionRunId: 91,
      jobsInterrupt: {
        kind: 'choose_jobs_and_skills',
        candidate_jobs: [],
        skill_bank: [],
      },
      selectedSkillNames: ['Draft skill'],
    });

    const session = hydrateIndividualGraphSession({
      ...recoveredProfile,
      onboarding_status: 'ready',
      next_step: 'learning_path',
      pending_interrupt: null,
    });

    expect(session).toMatchObject({
      graphStatus: 'completed',
      nextStep: 'learning_path',
      reviewInterrupt: null,
      jobsInterrupt: null,
      selectedPostingUrls: [],
      selectedSkillNames: [],
    });
  });

  it('fails closed and clears stale state for malformed recovery data', () => {
    writeIndividualGraphSession(storedSession);

    const session = hydrateIndividualGraphSession({
      ...recoveredProfile,
      pending_interrupt: { kind: 'choose_jobs_and_skills', candidate_jobs: 'invalid' },
    });

    expect(session).toBeNull();
    expect(readIndividualGraphSession()).toBeNull();
  });

  it('fails closed when skill-selection recovery is missing its real pending interrupt', () => {
    const session = hydrateIndividualGraphSession({
      ...recoveredProfile,
      onboarding_status: 'needs_skill_selection',
      next_step: 'select_jobs_and_skills',
      pending_interrupt: null,
    });

    expect(session).toBeNull();
  });
});
