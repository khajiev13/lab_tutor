import { zodResolver } from '@hookform/resolvers/zod';
import {
  ArrowDown,
  ArrowUp,
  AlertTriangle,
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { z } from 'zod';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  getIndividualProfile,
  resumeIndividualGraph,
  type IndividualCvProfileExtraction,
  type IndividualProfile,
} from '@/features/individual-learning/api';
import {
  hydrateIndividualGraphSession,
  persistIndividualGraphResponse,
  readIndividualGraphSession,
  writeIndividualGraphSession,
} from '@/features/individual-learning/graph-session';
import {
  getErrorStatus,
  getIndividualRecoveryPath,
  recoverIndividualWorkflow,
} from '@/features/individual-learning/recovery';

const MAX_TARGET_TITLES = 10;

const targetTitlesSchema = z.object({
  targetTitles: z
    .array(
      z.object({
        value: z.string().refine((value) => value.trim().length > 0, 'Enter a target title.'),
      }),
    )
    .min(1, 'Add at least one target title.')
    .max(MAX_TARGET_TITLES, `Choose no more than ${MAX_TARGET_TITLES} target titles.`),
});

type TargetTitlesFormValues = z.infer<typeof targetTitlesSchema>;

function cleanTitles(values: TargetTitlesFormValues['targetTitles']) {
  return Array.from(new Set(values.map(({ value }) => value.trim()).filter(Boolean)));
}

function getInitialTitles(
  savedTitles: string[],
  suggestions: string[],
): TargetTitlesFormValues['targetTitles'] {
  const titles = savedTitles.length > 0 ? savedTitles : suggestions;
  return (titles.length > 0 ? titles : ['']).map((value) => ({ value }));
}

function hasLowConfidence(profile: IndividualCvProfileExtraction) {
  const skillConfidenceIsLow = (profile.skills ?? []).some(
    (skill) => skill.confidence != null && skill.confidence < 0.6,
  );
  const summaryConfidenceIsLow = Object.values(profile.confidence_summary ?? {}).some(
    (confidence) => confidence < 0.6,
  );
  return skillConfidenceIsLow || summaryConfidenceIsLow;
}

function ProfileList({
  title,
  items,
}: {
  title: string;
  items: string[] | undefined;
}) {
  if (!items?.length) {
    return null;
  }

  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">{title}</div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <Badge key={`${title}-${item}`} variant="outline">
            {item}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function ExtractedProfile({ profile }: { profile: IndividualCvProfileExtraction }) {
  const hasSupportingDetails = [
    profile.projects,
    profile.education,
    profile.certifications,
    profile.tools,
    profile.languages,
    profile.industries,
    profile.seniority_signals,
  ].some((items) => items?.length);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="size-5" />
            Extracted profile
          </CardTitle>
          <CardDescription>Review the information extracted from your latest CV.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-6 text-muted-foreground">
            {profile.summary || 'No profile summary was extracted.'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>CV skills</CardTitle>
          <CardDescription>
            These describe your current experience. They are evidence only and are not selectable
            learning targets.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {profile.skills?.length ? (
            profile.skills.map((skill, index) => (
              <div key={`${skill.name}-${index}`} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{skill.name}</span>
                  {skill.category ? <Badge variant="outline">{skill.category}</Badge> : null}
                  {skill.confidence != null ? (
                    <Badge variant="secondary">
                      {Math.round(Math.max(0, Math.min(1, skill.confidence)) * 100)}% confidence
                    </Badge>
                  ) : null}
                </div>
                {skill.evidence ? (
                  <p className="mt-2 text-sm text-muted-foreground">{skill.evidence}</p>
                ) : null}
              </div>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No CV skills were extracted.</p>
          )}
        </CardContent>
      </Card>

      {profile.experience?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BriefcaseBusiness className="size-5" />
              Experience
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {profile.experience.map((experience, index) => (
              <div key={`${experience.title ?? 'experience'}-${index}`} className="rounded-lg border p-4">
                <div className="font-medium">{experience.title || 'Untitled role'}</div>
                <div className="text-sm text-muted-foreground">
                  {[experience.organization, experience.start_date, experience.end_date]
                    .filter(Boolean)
                    .join(' • ')}
                </div>
                {experience.summary ? (
                  <p className="mt-2 text-sm text-muted-foreground">{experience.summary}</p>
                ) : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {hasSupportingDetails ? (
        <Card>
          <CardHeader>
            <CardTitle>Additional details</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-5 md:grid-cols-2">
            <ProfileList title="Projects" items={profile.projects} />
            <ProfileList title="Education" items={profile.education} />
            <ProfileList title="Certifications" items={profile.certifications} />
            <ProfileList title="Tools" items={profile.tools} />
            <ProfileList title="Languages" items={profile.languages} />
            <ProfileList title="Industries" items={profile.industries} />
            <ProfileList title="Seniority signals" items={profile.seniority_signals} />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

export default function IndividualProfilePage() {
  const navigate = useNavigate();
  const [graphSession, setGraphSession] = useState(readIndividualGraphSession);
  const [profile, setProfile] = useState<IndividualProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [isRetryingJobs, setIsRetryingJobs] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const reviewInterrupt = graphSession?.reviewInterrupt ?? null;
  const hasAdvancedToJobs = graphSession?.jobsInterrupt != null;
  const nextStep = profile?.next_step ?? graphSession?.nextStep;
  const needsJobSearchRetry = nextStep === 'search_jobs';
  const hasCompletedWorkflow = nextStep === 'learning_path' || graphSession?.graphStatus === 'completed';
  const extractedProfile =
    reviewInterrupt?.profile ?? graphSession?.extractedProfile ?? profile?.extracted_profile ?? null;
  const suggestions = useMemo(() => {
    const values = [
      ...(reviewInterrupt?.target_title_suggestions ?? []),
      ...(reviewInterrupt?.profile.target_title_suggestions ?? []),
      ...(extractedProfile?.target_title_suggestions ?? []),
    ];
    return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
  }, [extractedProfile, reviewInterrupt]);

  const form = useForm<TargetTitlesFormValues>({
    resolver: zodResolver(targetTitlesSchema),
    defaultValues: {
      targetTitles: getInitialTitles(graphSession?.targetTitles ?? [], suggestions),
    },
  });
  const { getFieldState, reset: resetForm } = form;
  const titleFields = useFieldArray({ control: form.control, name: 'targetTitles' });

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        const data = await getIndividualProfile();
        if (!active) {
          return;
        }
        const recoveredSession = hydrateIndividualGraphSession(data);
        setProfile(data);
        setGraphSession(recoveredSession);
        setProfileError(null);

        if (!getFieldState('targetTitles').isDirty) {
          const recoveredSuggestions =
            data.pending_interrupt?.kind === 'review_profile_and_roles'
              ? data.pending_interrupt.target_title_suggestions
              : data.extracted_profile?.target_title_suggestions ?? [];
          resetForm({
            targetTitles: getInitialTitles(
              recoveredSession?.targetTitles ?? data.target_titles,
              recoveredSuggestions,
            ),
          });
        }
      } catch (error) {
        console.error(error);
        if (active) {
          setProfileError('We could not load your current profile status.');
        }
      } finally {
        if (active) {
          setIsLoadingProfile(false);
        }
      }
    }

    loadProfile();
    return () => {
      active = false;
    };
  }, [getFieldState, resetForm]);

  const addSuggestion = (suggestion: string) => {
    const current = cleanTitles(form.getValues('targetTitles'));
    if (titleFields.fields.length >= MAX_TARGET_TITLES || current.includes(suggestion)) {
      return;
    }
    titleFields.append({ value: suggestion });
  };

  const recoverConflict = async () => {
    const ownerUserId = profile?.user_id ?? graphSession?.ownerUserId;
    if (!ownerUserId) {
      throw new Error('The current individual workflow has no owner.');
    }
    const recovery = await recoverIndividualWorkflow(ownerUserId);
    setProfile(recovery.profile);
    setGraphSession(recovery.session);
    navigate(getIndividualRecoveryPath(recovery.profile.next_step));
  };

  const resumeProfile = async (threadId: string, targetTitles: string[]) => {
    setActionError(null);
    try {
      const response = await resumeIndividualGraph(threadId, {
        approved: true,
        target_titles: targetTitles,
      });
      const persisted = persistIndividualGraphResponse(response);
      setGraphSession(persisted.session);
      if (!persisted.stored) {
        toast.warning('Job review state is available for this page session only.', {
          description: 'Avoid reloading until you finish job and skill selection.',
        });
      }
      toast.success('Profile approved', {
        description: 'Review the job matches generated from your target titles.',
      });
      navigate('/individual/jobs');
    } catch (error) {
      if (getErrorStatus(error) === 409) {
        try {
          await recoverConflict();
          return;
        } catch (recoveryError) {
          console.error(recoveryError);
          setActionError('The workflow changed, but its latest state could not be loaded.');
          return;
        }
      }
      console.error(error);
      setActionError('Job search did not complete. Your target titles are still available.');
      toast.error('Could not approve your profile.');
    }
  };

  const onSubmit = form.handleSubmit(async ({ targetTitles }) => {
    if (!graphSession?.reviewInterrupt) {
      toast.error('Upload a CV again to start a resumable review.');
      return;
    }

    const editedTitles = cleanTitles(targetTitles);
    const draftSession = { ...graphSession, targetTitles: editedTitles };
    writeIndividualGraphSession(draftSession);
    setGraphSession(draftSession);
    await resumeProfile(graphSession.threadId, editedTitles);
  });

  const retryJobSearch = async () => {
    if (!profile?.active_thread_id || profile.target_titles.length === 0) {
      setActionError('The durable job-search state is incomplete. Refresh recovery and try again.');
      return;
    }
    setIsRetryingJobs(true);
    await resumeProfile(profile.active_thread_id, profile.target_titles);
    setIsRetryingJobs(false);
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Review your CV profile</h1>
        <p className="text-sm text-muted-foreground">
          Confirm the extracted evidence and edit the target roles used for job matching.
        </p>
      </div>

      {profileError ? (
        <Alert variant="destructive">
          <FileText className="size-4" />
          <AlertTitle>Profile status unavailable</AlertTitle>
          <AlertDescription>{profileError}</AlertDescription>
        </Alert>
      ) : null}

      {extractedProfile && hasLowConfidence(extractedProfile) ? (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>Low-confidence extraction</AlertTitle>
          <AlertDescription>
            Some extracted details have low confidence. Review the CV evidence carefully before continuing.
          </AlertDescription>
        </Alert>
      ) : null}

      {!extractedProfile ? (
        <Alert>
          <FileText className="size-4" />
          <AlertTitle>No active CV review</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {isLoadingProfile
                ? 'Checking your profile status...'
                : profile?.onboarding_status === 'needs_cv'
                  ? 'Upload a CV to begin profile review.'
                  : 'This browser tab does not have the resumable graph session for your latest CV.'}
            </span>
            <Button asChild size="sm" variant="outline">
              <Link to="/individual/onboarding">Upload CV</Link>
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1.35fr_0.9fr]">
          <ExtractedProfile profile={extractedProfile} />

          {hasAdvancedToJobs || hasCompletedWorkflow ? (
            <Card className="h-fit xl:sticky xl:top-6">
              <CardHeader>
                <CardTitle>Profile review complete</CardTitle>
                <CardDescription>
                  This graph session has already advanced to job and skill selection.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {(profile?.target_titles ?? graphSession?.targetTitles ?? []).map((title) => (
                    <Badge key={title} variant="outline">
                      {title}
                    </Badge>
                  ))}
                </div>
                <Button asChild className="w-full">
                  <Link to="/individual/jobs">
                    <BriefcaseBusiness className="size-4" />
                    Continue to job matches
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ) : needsJobSearchRetry ? (
            <Card className="h-fit xl:sticky xl:top-6">
              <CardHeader>
                <CardTitle>Retry job search</CardTitle>
                <CardDescription>
                  Your reviewed profile and target titles are saved. Retry the failed provider step without re-approving the CV.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {(profile?.target_titles ?? []).map((title) => (
                    <Badge key={title} variant="outline">{title}</Badge>
                  ))}
                </div>
                {actionError ? (
                  <Alert variant="destructive">
                    <AlertTriangle className="size-4" />
                    <AlertTitle>Job search unavailable</AlertTitle>
                    <AlertDescription>{actionError}</AlertDescription>
                  </Alert>
                ) : null}
                <Button type="button" className="w-full" onClick={retryJobSearch} disabled={isRetryingJobs}>
                  {isRetryingJobs ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                  Retry job search
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card className="h-fit xl:sticky xl:top-6">
              <CardHeader>
                <CardTitle>Target job titles</CardTitle>
                <CardDescription>
                  Accept, remove, reorder, or add titles before generating job matches.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {actionError ? (
                  <Alert variant="destructive">
                    <AlertTriangle className="size-4" />
                    <AlertTitle>Job search unavailable</AlertTitle>
                    <AlertDescription>{actionError}</AlertDescription>
                  </Alert>
                ) : null}
                {suggestions.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Suggestions from your CV</div>
                    <div className="flex flex-wrap gap-2">
                      {suggestions.map((suggestion) => (
                        <Button
                          key={suggestion}
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => addSuggestion(suggestion)}
                          disabled={titleFields.fields.length >= MAX_TARGET_TITLES}
                        >
                          <Plus className="size-3.5" />
                          {suggestion}
                        </Button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <Form {...form}>
                  <form onSubmit={onSubmit} className="space-y-4">
                    <div className="space-y-3">
                      {titleFields.fields.map((field, index) => (
                        <FormField
                          key={field.id}
                          control={form.control}
                          name={`targetTitles.${index}.value`}
                          render={({ field: inputField }) => (
                            <FormItem>
                              <FormLabel className="sr-only">Target title {index + 1}</FormLabel>
                              <div className="flex items-start gap-2">
                                <FormControl>
                                  <Input {...inputField} placeholder="e.g. Data Analyst" />
                                </FormControl>
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="outline"
                                  aria-label={`Move target title ${index + 1} up`}
                                  disabled={index === 0}
                                  onClick={() => titleFields.move(index, index - 1)}
                                >
                                  <ArrowUp className="size-4" />
                                </Button>
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="outline"
                                  aria-label={`Move target title ${index + 1} down`}
                                  disabled={index === titleFields.fields.length - 1}
                                  onClick={() => titleFields.move(index, index + 1)}
                                >
                                  <ArrowDown className="size-4" />
                                </Button>
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  aria-label={`Remove target title ${index + 1}`}
                                  disabled={titleFields.fields.length === 1}
                                  onClick={() => titleFields.remove(index)}
                                >
                                  <Trash2 className="size-4" />
                                </Button>
                              </div>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      ))}
                    </div>

                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => titleFields.append({ value: '' })}
                      disabled={titleFields.fields.length >= MAX_TARGET_TITLES}
                    >
                      <Plus className="size-4" />
                      Add another title
                    </Button>

                    <Button
                      type="submit"
                      className="w-full"
                      disabled={form.formState.isSubmitting}
                    >
                      {form.formState.isSubmitting ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="size-4" />
                      )}
                      Approve profile and find jobs
                    </Button>
                  </form>
                </Form>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </main>
  );
}
