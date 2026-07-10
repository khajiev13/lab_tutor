import { z } from 'zod';
import {
  type IndividualNextStep,
  type IndividualGraphJobsInterrupt,
  type IndividualGraphResponse,
  type IndividualGraphReviewInterrupt,
} from '@/features/individual-learning/api';

export const INDIVIDUAL_GRAPH_SESSION_KEY = 'individual-learning.graph-session';

const optionalText = z.string().nullable().optional();

const cvProfileSchema = z.object({
  summary: optionalText,
  skills: z
    .array(
      z.object({
        name: z.string(),
        category: optionalText,
        evidence: optionalText,
        confidence: z.number().nullable().optional(),
      }),
    )
    .optional(),
  experience: z
    .array(
      z.object({
        title: optionalText,
        organization: optionalText,
        start_date: optionalText,
        end_date: optionalText,
        summary: optionalText,
      }),
    )
    .optional(),
  projects: z.array(z.string()).optional(),
  education: z.array(z.string()).optional(),
  certifications: z.array(z.string()).optional(),
  tools: z.array(z.string()).optional(),
  languages: z.array(z.string()).optional(),
  industries: z.array(z.string()).optional(),
  seniority_signals: z.array(z.string()).optional(),
  target_title_suggestions: z.array(z.string()).optional(),
  confidence_summary: z.record(z.string(), z.number()).optional(),
});

const reviewInterruptSchema = z.object({
  kind: z.literal('review_profile_and_roles'),
  profile: cvProfileSchema,
  target_title_suggestions: z.array(z.string()),
});

const graphSkillSchema = z.object({
  name: z.string(),
  category: optionalText,
  description: optionalText,
  coverage: z.enum(['covered', 'gap', 'partial', 'unknown']).optional(),
});

const jobsInterruptSchema = z.object({
  kind: z.literal('choose_jobs_and_skills'),
  candidate_jobs: z.array(
    z.object({
      url: z.string(),
      title: z.string(),
      company: optionalText,
      site: optionalText,
      search_term: optionalText,
      country: optionalText,
      location: optionalText,
      description: optionalText,
      match_score: z.number().nullable().optional(),
      skills: z.array(graphSkillSchema).optional(),
    }),
  ),
  skill_bank: z.array(graphSkillSchema),
});

const nextStepSchema = z.enum([
  'upload_cv',
  'wait_for_extraction',
  'review_profile',
  'search_jobs',
  'select_jobs_and_skills',
  'learning_path',
  'retry_cv',
]);

const individualGraphSessionSchema = z.object({
  cvDocumentId: z.number().int().positive().optional(),
  extractionRunId: z.number().int().positive().optional(),
  ownerUserId: z.number().int().positive(),
  threadId: z.string().min(1),
  nextStep: nextStepSchema.optional(),
  graphStatus: z.enum(['interrupted', 'completed']).default('interrupted'),
  extractedProfile: cvProfileSchema.nullable().optional(),
  reviewInterrupt: reviewInterruptSchema.nullable().optional(),
  jobsInterrupt: jobsInterruptSchema.nullable().optional(),
  targetTitles: z.array(z.string()),
  selectedPostingUrls: z.array(z.string()),
  selectedSkillNames: z.array(z.string()),
});

const recoveryProfileSchema = z.object({
  user_id: z.number().int().positive(),
  onboarding_status: z.enum([
    'needs_cv',
    'extracting',
    'needs_profile_review',
    'needs_jobs',
    'needs_skill_selection',
    'ready',
    'error',
  ]),
  target_titles: z.array(z.string()),
  cv_document_id: z.number().int().positive().nullable(),
  extraction_run_id: z.number().int().positive().nullable(),
  active_thread_id: z.string().min(1).nullable(),
  next_step: nextStepSchema,
  extracted_profile: cvProfileSchema.nullable(),
  pending_interrupt: z
    .discriminatedUnion('kind', [reviewInterruptSchema, jobsInterruptSchema])
    .nullable(),
});

export type IndividualGraphSession = z.infer<typeof individualGraphSessionSchema>;

export type PersistIndividualGraphResponseResult = {
  session: IndividualGraphSession;
  stored: boolean;
};

let inMemorySession: IndividualGraphSession | null = null;
let inMemorySessionIsAuthoritative = false;

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function readIndividualGraphSession(): IndividualGraphSession | null {
  if (inMemorySessionIsAuthoritative) {
    return inMemorySession;
  }

  const storage = getSessionStorage();
  if (!storage) {
    return inMemorySession;
  }

  try {
    const raw = storage.getItem(INDIVIDUAL_GRAPH_SESSION_KEY);
    if (!raw) {
      return inMemorySession;
    }

    const result = individualGraphSessionSchema.safeParse(JSON.parse(raw));
    if (!result.success) {
      inMemorySession = null;
      try {
        storage.removeItem(INDIVIDUAL_GRAPH_SESSION_KEY);
      } catch {
        inMemorySessionIsAuthoritative = true;
      }
      return null;
    }

    inMemorySession = result.data;
    return result.data;
  } catch {
    return inMemorySession;
  }
}

export function writeIndividualGraphSession(session: IndividualGraphSession): boolean {
  const storage = getSessionStorage();
  const result = individualGraphSessionSchema.safeParse(session);
  if (!result.success) {
    return false;
  }

  inMemorySession = result.data;
  if (!storage) {
    inMemorySessionIsAuthoritative = true;
    return false;
  }

  try {
    storage.setItem(INDIVIDUAL_GRAPH_SESSION_KEY, JSON.stringify(result.data));
    inMemorySessionIsAuthoritative = false;
    return true;
  } catch {
    inMemorySessionIsAuthoritative = true;
    return false;
  }
}

export function clearIndividualGraphSession(): void {
  inMemorySession = null;
  const storage = getSessionStorage();
  if (!storage) {
    inMemorySessionIsAuthoritative = true;
    return;
  }

  try {
    storage.removeItem(INDIVIDUAL_GRAPH_SESSION_KEY);
    inMemorySessionIsAuthoritative = false;
  } catch {
    inMemorySessionIsAuthoritative = true;
  }
}

export function clearIndividualGraphSessionForOtherUser(userId: number): void {
  const session = readIndividualGraphSession();
  if (session && session.ownerUserId !== userId) {
    clearIndividualGraphSession();
  }
}

function recoveryPhaseIsConsistent(
  nextStep: IndividualNextStep,
  interrupt: IndividualGraphReviewInterrupt | IndividualGraphJobsInterrupt | null,
) {
  if (nextStep === 'review_profile') {
    return !interrupt || interrupt.kind === 'review_profile_and_roles';
  }
  if (nextStep === 'select_jobs_and_skills') {
    return interrupt?.kind === 'choose_jobs_and_skills';
  }
  return interrupt === null;
}

export function hydrateIndividualGraphSession(recovery: unknown): IndividualGraphSession | null {
  const result = recoveryProfileSchema.safeParse(recovery);
  if (!result.success) {
    clearIndividualGraphSession();
    return null;
  }

  const profile = result.data;
  if (
    !recoveryPhaseIsConsistent(profile.next_step, profile.pending_interrupt) ||
    profile.next_step === 'upload_cv' ||
    profile.next_step === 'wait_for_extraction' ||
    profile.next_step === 'retry_cv' ||
    !profile.cv_document_id ||
    !profile.extraction_run_id ||
    !profile.active_thread_id
  ) {
    clearIndividualGraphSession();
    return null;
  }

  const current = readIndividualGraphSession();
  const sameAttempt =
    current?.ownerUserId === profile.user_id &&
    current.threadId === profile.active_thread_id &&
    current.extractionRunId === profile.extraction_run_id;
  const isCompleted = profile.next_step === 'learning_path';
  const preserveDrafts = sameAttempt && !isCompleted;
  const interrupt = profile.pending_interrupt;
  const session: IndividualGraphSession = {
    cvDocumentId: profile.cv_document_id,
    extractionRunId: profile.extraction_run_id,
    ownerUserId: profile.user_id,
    threadId: profile.active_thread_id,
    nextStep: profile.next_step,
    graphStatus: isCompleted ? 'completed' : 'interrupted',
    extractedProfile: profile.extracted_profile,
    reviewInterrupt:
      interrupt?.kind === 'review_profile_and_roles' ? interrupt : null,
    jobsInterrupt: interrupt?.kind === 'choose_jobs_and_skills' ? interrupt : null,
    targetTitles: preserveDrafts ? current.targetTitles : profile.target_titles,
    selectedPostingUrls: preserveDrafts ? current.selectedPostingUrls : [],
    selectedSkillNames: preserveDrafts ? current.selectedSkillNames : [],
  };

  writeIndividualGraphSession(session);
  return session;
}

export function persistIndividualGraphResponse(
  response: IndividualGraphResponse,
  options: {
    cvDocumentId?: number;
    extractionRunId?: number;
    ownerUserId?: number;
    nextStep?: IndividualNextStep;
    replace?: boolean;
  } = {},
): PersistIndividualGraphResponseResult {
  const current = options.replace ? null : readIndividualGraphSession();
  const ownerUserId = options.ownerUserId ?? current?.ownerUserId;
  if (!ownerUserId) {
    throw new Error('An authenticated user is required to persist an individual graph session.');
  }
  const interrupt = response.interrupt;
  const reviewInterrupt =
    interrupt?.kind === 'review_profile_and_roles'
      ? (interrupt as IndividualGraphReviewInterrupt)
      : current?.reviewInterrupt ?? null;
  const jobsInterrupt =
    interrupt?.kind === 'choose_jobs_and_skills'
      ? (interrupt as IndividualGraphJobsInterrupt)
      : current?.jobsInterrupt ?? null;

  const next: IndividualGraphSession = {
    cvDocumentId: options.cvDocumentId ?? current?.cvDocumentId,
    extractionRunId: options.extractionRunId ?? current?.extractionRunId,
    ownerUserId,
    threadId: response.thread_id,
    nextStep:
      options.nextStep ??
      (response.status === 'completed'
        ? 'learning_path'
        : interrupt?.kind === 'review_profile_and_roles'
          ? 'review_profile'
          : interrupt?.kind === 'choose_jobs_and_skills'
            ? 'select_jobs_and_skills'
            : current?.nextStep),
    graphStatus: response.status,
    extractedProfile:
      interrupt?.kind === 'review_profile_and_roles'
        ? (interrupt as IndividualGraphReviewInterrupt).profile
        : current?.extractedProfile ?? null,
    reviewInterrupt,
    jobsInterrupt,
    targetTitles: response.target_titles,
    selectedPostingUrls: response.selected_posting_urls,
    selectedSkillNames: response.selected_skill_names,
  };

  return {
    session: next,
    stored: writeIndividualGraphSession(next),
  };
}
