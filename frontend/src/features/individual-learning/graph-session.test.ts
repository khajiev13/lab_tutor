import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearIndividualGraphSession,
  clearIndividualGraphSessionForOtherUser,
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
});
