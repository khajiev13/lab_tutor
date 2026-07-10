import {
  getIndividualProfile,
  startIndividualGraph,
  type IndividualNextStep,
  type IndividualProfile,
} from '@/features/individual-learning/api';
import {
  hydrateIndividualGraphSession,
  persistIndividualGraphResponse,
  type IndividualGraphSession,
} from '@/features/individual-learning/graph-session';
import {
  assertAuthSessionCurrent,
  captureAuthSession,
} from '@/features/auth/auth-session';

type RecoveryDraft = Pick<IndividualGraphSession, 'selectedPostingUrls'>;

function normalizeIndividualPathname(pathname: string): string {
  const withoutTrailingSlashes = pathname.replace(/\/+$/, '');
  return (withoutTrailingSlashes || '/').toLowerCase();
}

function throwIfRecoveryWasCancelled(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw new DOMException('Individual workflow recovery was cancelled.', 'AbortError');
  }
}

export function getIndividualRecoveryPath(nextStep: IndividualNextStep): string {
  if (
    nextStep === 'upload_cv' ||
    nextStep === 'wait_for_extraction' ||
    nextStep === 'retry_cv'
  ) {
    return '/individual/onboarding';
  }
  if (nextStep === 'review_profile' || nextStep === 'search_jobs') {
    return '/individual/profile';
  }
  if (nextStep === 'select_jobs_and_skills') {
    return '/individual/jobs';
  }
  return '/individual/learning-path';
}

export function getIndividualRecoveryRedirect(
  nextStep: IndividualNextStep,
  pathname: string,
  session: RecoveryDraft | null,
): string | null {
  const currentPath = normalizeIndividualPathname(pathname);
  const recoveryPath = getIndividualRecoveryPath(nextStep);
  if (currentPath === recoveryPath) {
    return null;
  }

  if (
    nextStep === 'select_jobs_and_skills' &&
    currentPath === '/individual/skills' &&
    (session?.selectedPostingUrls.length ?? 0) > 0
  ) {
    return null;
  }
  return recoveryPath;
}

export type IndividualRecovery = {
  profile: IndividualProfile;
  session: IndividualGraphSession | null;
};

export async function recoverIndividualWorkflow(
  ownerUserId: number,
  signal?: AbortSignal,
): Promise<IndividualRecovery> {
  const authSession = captureAuthSession(ownerUserId);
  const profile = await getIndividualProfile();
  assertAuthSessionCurrent(authSession);
  if (profile.user_id !== ownerUserId) {
    throw new Error('Recovered individual workflow belongs to another user.');
  }

  throwIfRecoveryWasCancelled(signal);
  let session = hydrateIndividualGraphSession(profile);
  if (profile.next_step === 'review_profile' && !profile.pending_interrupt) {
    if (!profile.cv_document_id) {
      throw new Error('Recovered profile review is missing its CV document.');
    }

    const response = await startIndividualGraph(profile.cv_document_id);
    throwIfRecoveryWasCancelled(signal);
    assertAuthSessionCurrent(authSession);
    if (
      response.status !== 'interrupted' ||
      response.interrupt?.kind !== 'review_profile_and_roles'
    ) {
      throw new Error('Recovered profile review did not reach its review checkpoint.');
    }
    session = persistIndividualGraphResponse(response, {
      cvDocumentId: profile.cv_document_id,
      extractionRunId: profile.extraction_run_id ?? undefined,
      ownerUserId,
      authSession,
      nextStep: 'review_profile',
      replace: true,
    }).session;
  }

  const needsSession =
    profile.next_step === 'review_profile' ||
    profile.next_step === 'search_jobs' ||
    profile.next_step === 'select_jobs_and_skills' ||
    profile.next_step === 'learning_path';
  if (needsSession && !session) {
    throw new Error('The recovered workflow state is incomplete.');
  }

  assertAuthSessionCurrent(authSession);
  return { profile, session };
}

export function getErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }
  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}
