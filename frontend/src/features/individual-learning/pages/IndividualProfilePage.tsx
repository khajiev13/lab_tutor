import { zodResolver } from '@hookform/resolvers/zod';
import {
  ArrowDown,
  ArrowUp,
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  Loader2,
  Plus,
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
  persistIndividualGraphResponse,
  readIndividualGraphSession,
} from '@/features/individual-learning/graph-session';

const targetTitlesSchema = z.object({
  targetTitles: z
    .array(
      z.object({
        value: z.string().refine((value) => value.trim().length > 0, 'Enter a target title.'),
      }),
    )
    .min(1, 'Add at least one target title.')
    .max(10, 'Choose no more than 10 target titles.'),
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
  const [graphSession] = useState(readIndividualGraphSession);
  const [profile, setProfile] = useState<IndividualProfile | null>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const reviewInterrupt = graphSession?.reviewInterrupt ?? null;
  const hasAdvancedToJobs = graphSession?.jobsInterrupt != null;
  const suggestions = useMemo(() => {
    const values = [
      ...(reviewInterrupt?.target_title_suggestions ?? []),
      ...(reviewInterrupt?.profile.target_title_suggestions ?? []),
    ];
    return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
  }, [reviewInterrupt]);

  const form = useForm<TargetTitlesFormValues>({
    resolver: zodResolver(targetTitlesSchema),
    defaultValues: {
      targetTitles: getInitialTitles(graphSession?.targetTitles ?? [], suggestions),
    },
  });
  const titleFields = useFieldArray({ control: form.control, name: 'targetTitles' });

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        const data = await getIndividualProfile();
        if (!active) {
          return;
        }
        setProfile(data);
        setProfileError(null);

        if (!reviewInterrupt && data.target_titles.length > 0) {
          form.reset({ targetTitles: getInitialTitles(data.target_titles, []) });
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
  }, [form, reviewInterrupt]);

  const addSuggestion = (suggestion: string) => {
    const current = cleanTitles(form.getValues('targetTitles'));
    if (current.includes(suggestion)) {
      return;
    }
    titleFields.append({ value: suggestion });
  };

  const onSubmit = form.handleSubmit(async ({ targetTitles }) => {
    if (!graphSession) {
      toast.error('Upload a CV again to start a resumable review.');
      return;
    }

    const editedTitles = cleanTitles(targetTitles);
    try {
      const response = await resumeIndividualGraph(graphSession.threadId, {
        approved: true,
        target_titles: editedTitles,
      });
      const { stored } = persistIndividualGraphResponse(response);
      if (!stored) {
        toast.warning('Job review state is available for this page session only.', {
          description: 'Avoid reloading until you finish job and skill selection.',
        });
      }
      toast.success('Profile approved', {
        description: 'Review the job matches generated from your target titles.',
      });
      navigate('/individual/jobs');
    } catch (error) {
      console.error(error);
      toast.error('Could not approve your profile.');
    }
  });

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

      {!reviewInterrupt ? (
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
          <ExtractedProfile profile={reviewInterrupt.profile} />

          {hasAdvancedToJobs ? (
            <Card className="h-fit xl:sticky xl:top-6">
              <CardHeader>
                <CardTitle>Profile review complete</CardTitle>
                <CardDescription>
                  This graph session has already advanced to job and skill selection.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  {graphSession.targetTitles.map((title) => (
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
          ) : (
            <Card className="h-fit xl:sticky xl:top-6">
              <CardHeader>
                <CardTitle>Target job titles</CardTitle>
                <CardDescription>
                  Accept, remove, reorder, or add titles before generating job matches.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
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
                      disabled={titleFields.fields.length >= 10}
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
