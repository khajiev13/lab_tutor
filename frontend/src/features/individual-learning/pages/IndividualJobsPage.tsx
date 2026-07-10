import { ArrowRight, BriefcaseBusiness, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import {
  getIndividualSkillBanks,
  selectInterestedJobs,
  type IndividualGraphJobPosting,
  type IndividualSkillBankJobPosting,
} from '@/features/individual-learning/api';
import {
  type IndividualGraphSession,
  readIndividualGraphSession,
  writeIndividualGraphSession,
} from '@/features/individual-learning/graph-session';
import {
  captureAuthSession,
  captureCurrentAuthSession,
  isStaleAuthSessionError,
  type AuthSessionSnapshot,
} from '@/features/auth/auth-session';
import { useAuthRequestGuard } from '@/features/individual-learning/use-auth-request-guard';

function toSkillBankPosting(
  posting: IndividualGraphJobPosting,
  selectedUrls: Set<string>,
): IndividualSkillBankJobPosting {
  return {
    url: posting.url,
    title: posting.title,
    company: posting.company ?? '',
    site: posting.site,
    search_term: posting.search_term,
    is_interested: selectedUrls.has(posting.url),
    match_score: posting.match_score,
    skill_extraction_status: posting.skill_extraction_status,
    skill_extraction_error: posting.skill_extraction_error,
    skills: (posting.skills ?? []).map((skill) => ({
      name: skill.name,
      category: skill.category,
      description: skill.description,
      is_selected: false,
      coverage: skill.coverage ?? 'unknown',
    })),
  };
}

function buildSelectionSet(postings: IndividualSkillBankJobPosting[], persistedUrls: string[]) {
  const next = new Set(persistedUrls);
  postings.forEach((posting) => {
    if (posting.is_interested) {
      next.add(posting.url);
    }
  });
  return next;
}

function formatMatchScore(score: number) {
  const percentage = score <= 1 ? score * 100 : score;
  return `${Math.round(percentage)}%`;
}

function formatCoverage(coverage: IndividualSkillBankJobPosting['skills'][number]['coverage']) {
  return coverage ? coverage.charAt(0).toUpperCase() + coverage.slice(1) : '';
}

function buildGraphDraftSession(
  session: IndividualGraphSession,
  jobs: IndividualSkillBankJobPosting[],
  selectedUrls: Set<string>,
): IndividualGraphSession {
  const nextUrls = jobs.filter((job) => selectedUrls.has(job.url)).map((job) => job.url);
  const availableSkillNames = new Set(
    jobs
      .filter((job) => selectedUrls.has(job.url))
      .flatMap((job) => job.skills.map((skill) => skill.name)),
  );

  return {
    ...session,
    selectedPostingUrls: nextUrls,
    selectedSkillNames: session.selectedSkillNames.filter((name) =>
      availableSkillNames.has(name),
    ),
  };
}

export default function IndividualJobsPage() {
  const navigate = useNavigate();
  const { assertRequestCurrent, isRequestCurrent } = useAuthRequestGuard();
  const [graphSession] = useState(readIndividualGraphSession);
  const graphInterrupt = graphSession?.jobsInterrupt ?? null;
  const isGraphWorkflow = graphInterrupt !== null;
  const isGraphSelectionActive = isGraphWorkflow && graphSession?.graphStatus === 'interrupted';
  const isCompletedGraphWorkflow = graphSession?.graphStatus === 'completed';
  const initialSelectedUrls = new Set(graphSession?.selectedPostingUrls ?? []);
  const [jobs, setJobs] = useState<IndividualSkillBankJobPosting[]>(() =>
    (graphInterrupt?.candidate_jobs ?? []).map((posting) =>
      toSkillBankPosting(posting, initialSelectedUrls),
    ),
  );
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(initialSelectedUrls);
  const [persistedUrls, setPersistedUrls] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(!isGraphWorkflow);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasIncompleteSkillExtraction = jobs.some(
    (job) => job.skill_extraction_status === 'failed',
  );

  useEffect(() => {
    if (isGraphWorkflow) {
      return;
    }

    let active = true;
    async function loadJobs() {
      let authSession: AuthSessionSnapshot | null = null;
      try {
        authSession = captureCurrentAuthSession();
        const data = await getIndividualSkillBanks();
        if (!active) {
          return;
        }
        assertRequestCurrent(authSession);

        const selection = buildSelectionSet(
          data.market_skill_bank,
          data.interested_posting_urls,
        );
        setJobs(data.market_skill_bank);
        setSelectedUrls(selection);
        setPersistedUrls(new Set(selection));
        setError(null);
      } catch (loadError) {
        if (
          isStaleAuthSessionError(loadError) ||
          (authSession && !isRequestCurrent(authSession))
        ) {
          return;
        }
        console.error(loadError);
        if (active) {
          setError('We could not load your current job matches.');
        }
        toast.error('Failed to load job matches.');
      } finally {
        if (active && authSession && isRequestCurrent(authSession)) {
          setIsLoading(false);
        }
      }
    }

    loadJobs();
    return () => {
      active = false;
    };
  }, [assertRequestCurrent, isGraphWorkflow, isRequestCurrent, loadAttempt]);

  const retryLoadJobs = () => {
    setError(null);
    setIsLoading(true);
    setLoadAttempt((attempt) => attempt + 1);
  };

  useEffect(() => {
    if (!isGraphSelectionActive || !graphSession) {
      return;
    }

    try {
      captureAuthSession(graphSession.ownerUserId);
      writeIndividualGraphSession(buildGraphDraftSession(graphSession, jobs, selectedUrls));
    } catch (draftError) {
      if (!isStaleAuthSessionError(draftError)) {
        throw draftError;
      }
    }
  }, [graphSession, isGraphSelectionActive, jobs, selectedUrls]);

  const handleToggle = (url: string, checked: boolean) => {
    if (isCompletedGraphWorkflow || (!isGraphWorkflow && persistedUrls.has(url))) {
      return;
    }

    setSelectedUrls((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(url);
      } else {
        next.delete(url);
      }
      return next;
    });
  };

  const handleContinue = async () => {
    if (selectedUrls.size === 0) {
      toast.error('Select at least one interested job to continue.');
      return;
    }

    setIsSaving(true);
    let authSession: AuthSessionSnapshot | null = null;
    try {
      authSession = graphSession
        ? captureAuthSession(graphSession.ownerUserId)
        : captureCurrentAuthSession();
      const nextUrls = jobs.filter((job) => selectedUrls.has(job.url)).map((job) => job.url);

      if (isGraphSelectionActive && graphSession) {
        const stored = writeIndividualGraphSession(
          buildGraphDraftSession(graphSession, jobs, selectedUrls),
        );
        if (!stored) {
          toast.warning('Job selection is available for this page session only.', {
            description: 'Avoid reloading until you finish skill selection.',
          });
        }
      } else if (!isCompletedGraphWorkflow) {
        const addedUrls = nextUrls.filter((url) => !persistedUrls.has(url));
        if (addedUrls.length > 0) {
          await selectInterestedJobs(nextUrls);
          assertRequestCurrent(authSession);
        }
      }

      navigate('/individual/skills');
    } catch (saveError) {
      if (
        isStaleAuthSessionError(saveError) ||
        (authSession && !isRequestCurrent(authSession))
      ) {
        return;
      }
      console.error(saveError);
      toast.error('Could not save interested jobs.');
    } finally {
      if (authSession && isRequestCurrent(authSession)) {
        setIsSaving(false);
      }
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Choose job matches</h1>
        <p className="text-sm text-muted-foreground">
          Select the postings whose market skills should shape your individual learning path.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Interested jobs</CardTitle>
            <CardDescription>
              Review source details, match scores, and market-skill coverage before moving to skill
              selection.
            </CardDescription>
          </div>
          <Button
            onClick={handleContinue}
            disabled={isLoading || isSaving || selectedUrls.size === 0}
          >
            {isSaving ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            Continue to skill selection
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="secondary">{selectedUrls.size} selected</Badge>
            <span>{jobs.length} job posting(s) available</span>
            {isGraphSelectionActive ? <Badge variant="outline">Draft selection</Badge> : null}
            {isCompletedGraphWorkflow ? <Badge variant="outline">Selection complete</Badge> : null}
          </div>

          {hasIncompleteSkillExtraction ? (
            <Alert>
              <BriefcaseBusiness className="size-4" />
              <AlertTitle>Some job skills could not be extracted</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-3">
                <span>
                  You can still select these postings. Edit target titles or retry job search if
                  you need a more complete market-skill set.
                </span>
                <Button type="button" size="sm" variant="outline" asChild>
                  <Link to="/individual/profile">Review titles and retry</Link>
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          {isLoading ? (
            <div className="rounded-md border p-8 text-sm text-muted-foreground">
              Loading job matches...
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <BriefcaseBusiness className="size-4" />
              <AlertTitle>Jobs unavailable</AlertTitle>
              <AlertDescription className="flex flex-col items-start gap-3">
                <span>{error}</span>
                <Button type="button" size="sm" variant="outline" onClick={retryLoadJobs}>
                  <RefreshCw className="size-4" />
                  Retry job matches
                </Button>
              </AlertDescription>
            </Alert>
          ) : jobs.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <BriefcaseBusiness className="size-5" />
                </EmptyMedia>
                <EmptyTitle>No job matches yet</EmptyTitle>
                <EmptyDescription>
                  No candidate postings were returned for the approved target titles.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="grid gap-4">
              {jobs.map((job) => {
                const checked = selectedUrls.has(job.url);
                const isLocked =
                  isCompletedGraphWorkflow || (!isGraphWorkflow && persistedUrls.has(job.url));

                return (
                  <Card key={job.url} className="rounded-lg shadow-none">
                    <CardContent className="flex flex-col gap-5 p-5">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="flex min-w-0 items-start gap-3">
                          <Checkbox
                            checked={checked}
                            disabled={isLocked}
                            onCheckedChange={(value) => handleToggle(job.url, value === true)}
                            aria-label={`Mark ${job.title} as interested`}
                          />
                          <div className="min-w-0 space-y-2">
                            <div>
                              <div className="font-medium">{job.title}</div>
                              <div className="text-sm text-muted-foreground">
                                {job.company || 'Unknown company'}
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {job.site ? <Badge variant="outline">{job.site}</Badge> : null}
                              {job.search_term ? (
                                <Badge variant="outline">Search: {job.search_term}</Badge>
                              ) : null}
                              {job.match_score != null ? (
                                <Badge variant="secondary">
                                  Match {formatMatchScore(job.match_score)}
                                </Badge>
                              ) : null}
                              {isLocked ? <Badge variant="secondary">Already saved</Badge> : null}
                              {job.skill_extraction_status === 'failed' ? (
                                <Badge variant="outline">Skill extraction incomplete</Badge>
                              ) : null}
                            </div>
                          </div>
                        </div>

                        <Button variant="outline" size="sm" asChild>
                          <a href={job.url} target="_blank" rel="noreferrer">
                            <ExternalLink className="size-4" />
                            Open posting
                          </a>
                        </Button>
                      </div>

                      <div className="space-y-2">
                        <div className="text-sm font-medium">Market skills and coverage</div>
                        <div className="flex flex-wrap gap-2">
                          {job.skills.length > 0 ? (
                            job.skills.map((skill) => (
                              <div
                                key={`${job.url}-${skill.name}`}
                                className="flex flex-wrap items-center gap-1"
                              >
                                <Badge variant="outline">{skill.name}</Badge>
                                {skill.coverage && skill.coverage !== 'unknown' ? (
                                  <Badge variant="secondary">
                                    {formatCoverage(skill.coverage)}
                                  </Badge>
                                ) : null}
                              </div>
                            ))
                          ) : (
                            <div className="space-y-1 text-sm text-muted-foreground">
                              <div>No market skills were attached to this posting.</div>
                              {job.skill_extraction_status === 'failed' ? (
                                <div>Retry from your profile to try skill extraction again.</div>
                              ) : null}
                            </div>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
