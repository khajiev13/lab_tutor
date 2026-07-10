import {
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import {
  buildIndividualLearningPath,
  deselectIndividualSkills,
  getIndividualSkillBanks,
  resumeIndividualGraph,
  selectIndividualSkills,
  type IndividualGraphJobPosting,
  type IndividualSkillBankJobPosting,
  type IndividualSkillBankSkill,
} from '@/features/individual-learning/api';
import {
  persistIndividualGraphResponse,
  readIndividualGraphSession,
  writeIndividualGraphSession,
} from '@/features/individual-learning/graph-session';
import {
  getErrorStatus,
  getIndividualRecoveryPath,
  recoverIndividualWorkflow,
} from '@/features/individual-learning/recovery';
import {
  captureAuthSession,
  captureCurrentAuthSession,
  isStaleAuthSessionError,
  type AuthSessionSnapshot,
} from '@/features/auth/auth-session';
import { useAuthRequestGuard } from '@/features/individual-learning/use-auth-request-guard';

const MAX_SELECTED_SKILLS = 20;

function toSkillBankPosting(
  posting: IndividualGraphJobPosting,
  selectedSkillNames: Set<string>,
): IndividualSkillBankJobPosting {
  return {
    url: posting.url,
    title: posting.title,
    company: posting.company ?? '',
    site: posting.site,
    search_term: posting.search_term,
    is_interested: true,
    match_score: posting.match_score,
    skill_extraction_status: posting.skill_extraction_status,
    skill_extraction_error: posting.skill_extraction_error,
    skills: (posting.skills ?? []).map((skill) => ({
      name: skill.name,
      description: skill.description,
      category: skill.category,
      is_selected: selectedSkillNames.has(skill.name),
      coverage: skill.coverage ?? 'unknown',
    })),
  };
}

function buildInterestedPostingUrls(postings: IndividualSkillBankJobPosting[], persistedUrls: string[]) {
  const next = new Set(persistedUrls);
  postings.forEach((posting) => {
    if (posting.is_interested) {
      next.add(posting.url);
    }
  });
  return next;
}

function getUniqueSkillNames(postings: IndividualSkillBankJobPosting[]) {
  return Array.from(
    new Set(postings.flatMap((posting) => posting.skills.map((skill) => skill.name))),
  );
}

function SkillChip({
  skill,
  selected,
  disabled,
  onToggle,
}: {
  skill: IndividualSkillBankSkill;
  selected: boolean;
  disabled?: boolean;
  onToggle: () => void;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={selected ? 'default' : 'outline'}
      className="h-auto min-h-9 rounded-full px-3 py-1.5"
      onClick={onToggle}
      disabled={disabled}
      aria-label={`${selected ? 'Remove' : 'Select'} ${skill.name}`}
      title={skill.description ?? undefined}
    >
      {selected ? <CheckCircle2 className="size-3.5" /> : null}
      <span>{skill.name}</span>
      {skill.coverage && skill.coverage !== 'unknown' ? (
        <Badge
          variant={selected ? 'secondary' : 'outline'}
          className="ml-1 capitalize"
        >
          {skill.coverage}
        </Badge>
      ) : null}
    </Button>
  );
}

export default function IndividualSkillsPage() {
  const navigate = useNavigate();
  const { assertRequestCurrent, isRequestCurrent } = useAuthRequestGuard();
  const [graphSession, setGraphSession] = useState(readIndividualGraphSession);
  const graphInterrupt = graphSession?.jobsInterrupt ?? null;
  const isGraphWorkflow = graphInterrupt !== null;
  const graphSelectedSkills = new Set(graphSession?.selectedSkillNames ?? []);
  const [postings, setPostings] = useState<IndividualSkillBankJobPosting[]>(() =>
    (graphInterrupt?.candidate_jobs ?? []).map((posting) =>
      toSkillBankPosting(posting, graphSelectedSkills),
    ),
  );
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(graphSelectedSkills);
  const [persistedSkills, setPersistedSkills] = useState<Set<string>>(graphSelectedSkills);
  const [interestedUrls, setInterestedUrls] = useState<Set<string>>(
    new Set(graphSession?.selectedPostingUrls ?? []),
  );
  const [isLoading, setIsLoading] = useState(!isGraphWorkflow);
  const [isBuilding, setIsBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);

  useEffect(() => {
    if (isGraphWorkflow) {
      return;
    }

    let active = true;
    async function loadSkillBanks() {
      let authSession: AuthSessionSnapshot | null = null;
      try {
        authSession = captureCurrentAuthSession();
        const data = await getIndividualSkillBanks();
        if (!active) {
          return;
        }
        assertRequestCurrent(authSession);

        const nextInterestedUrls = buildInterestedPostingUrls(
          data.market_skill_bank,
          data.interested_posting_urls,
        );
        const availableNames = new Set(getUniqueSkillNames(data.market_skill_bank));
        const nextSelectedSkills = new Set(
          data.selected_skill_names.filter((name) => availableNames.has(name)),
        );

        setPostings(data.market_skill_bank);
        setInterestedUrls(nextInterestedUrls);
        setSelectedSkills(nextSelectedSkills);
        setPersistedSkills(new Set(nextSelectedSkills));
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
          setError('We could not load market skills for your interested jobs.');
        }
        toast.error('Failed to load market skills.');
      } finally {
        if (active && authSession && isRequestCurrent(authSession)) {
          setIsLoading(false);
        }
      }
    }

    loadSkillBanks();
    return () => {
      active = false;
    };
  }, [assertRequestCurrent, isGraphWorkflow, isRequestCurrent]);

  const interestedPostings = useMemo(
    () => postings.filter((posting) => interestedUrls.has(posting.url)),
    [interestedUrls, postings],
  );
  const availableSkillNames = useMemo(
    () => getUniqueSkillNames(interestedPostings),
    [interestedPostings],
  );

  useEffect(() => {
    if (!isGraphWorkflow || graphSession?.graphStatus !== 'interrupted') {
      return;
    }

    try {
      captureAuthSession(graphSession.ownerUserId);
      writeIndividualGraphSession({
        ...graphSession,
        selectedSkillNames: availableSkillNames.filter((name) => selectedSkills.has(name)),
      });
    } catch (error) {
      if (!isStaleAuthSessionError(error)) {
        throw error;
      }
    }
  }, [availableSkillNames, graphSession, isGraphWorkflow, selectedSkills]);

  const allSkillsSelected =
    availableSkillNames.length > 0 &&
    availableSkillNames.every((skillName) => selectedSkills.has(skillName));

  const toggleSkill = (skillName: string) => {
    setSelectedSkills((current) => {
      const next = new Set(current);
      if (next.has(skillName)) {
        next.delete(skillName);
      } else {
        next.add(skillName);
      }
      return next;
    });
  };

  const togglePostingSkills = (posting: IndividualSkillBankJobPosting) => {
    const postingSkillNames = posting.skills.map((skill) => skill.name);
    const everySelected = postingSkillNames.every((name) => selectedSkills.has(name));
    setSelectedSkills((current) => {
      const next = new Set(current);
      postingSkillNames.forEach((name) => {
        if (everySelected) {
          next.delete(name);
        } else {
          next.add(name);
        }
      });
      return next;
    });
  };

  const toggleAllSkills = () => {
    setSelectedSkills((current) => {
      const next = new Set(current);
      availableSkillNames.forEach((name) => {
        if (allSkillsSelected) {
          next.delete(name);
        } else {
          next.add(name);
        }
      });
      return next;
    });
  };

  const handleBuild = async () => {
    if (selectedSkills.size === 0 || selectedSkills.size > MAX_SELECTED_SKILLS) {
      toast.error(`Select between 1 and ${MAX_SELECTED_SKILLS} market skills before building.`);
      return;
    }

    const orderedSelection = availableSkillNames.filter((name) => selectedSkills.has(name));
    const added = orderedSelection.filter((name) => !persistedSkills.has(name));
    const removed = Array.from(persistedSkills).filter((name) => !selectedSkills.has(name));

    setIsBuilding(true);
    setBuildError(null);
    let authSession: AuthSessionSnapshot | null = null;
    try {
      authSession = graphSession
        ? captureAuthSession(graphSession.ownerUserId)
        : captureCurrentAuthSession();
      if (
        isGraphWorkflow &&
        graphSession &&
        graphSession.graphStatus === 'interrupted'
      ) {
        const graphResponse = await resumeIndividualGraph(graphSession.threadId, {
          selected_posting_urls: Array.from(interestedUrls),
          selected_skill_names: orderedSelection,
        });
        assertRequestCurrent(authSession);
        if (graphResponse.status !== 'completed') {
          throw new Error('The individual learning graph did not complete skill selection.');
        }
        const persistedGraph = persistIndividualGraphResponse(graphResponse, {
          ownerUserId: graphSession.ownerUserId,
          authSession,
          expectedThreadId: graphSession.threadId,
        });
        setGraphSession(persistedGraph.session);
        if (!persistedGraph.stored) {
          toast.warning('Completed graph state is available for this page session only.');
        }

        if (removed.length > 0) {
          await deselectIndividualSkills(removed);
          assertRequestCurrent(authSession);
        }
      } else {
        if (added.length > 0) {
          await selectIndividualSkills(added);
          assertRequestCurrent(authSession);
        }
        if (removed.length > 0) {
          await deselectIndividualSkills(removed);
          assertRequestCurrent(authSession);
        }

        if (isGraphWorkflow && graphSession?.graphStatus === 'completed') {
          const reconciledSession = {
            ...graphSession,
            selectedSkillNames: orderedSelection,
          };
          const stored = writeIndividualGraphSession(reconciledSession);
          setGraphSession(reconciledSession);
          if (!stored) {
            toast.warning('Updated skill selection is available for this page session only.');
          }
        }
      }

      const response = await buildIndividualLearningPath(orderedSelection);
      assertRequestCurrent(authSession);
      setPersistedSkills(new Set(orderedSelection));
      if (response.status === 'failed') {
        const failureMessage = response.error ?? 'No learning resources could be generated.';
        setBuildError(failureMessage);
        toast.error('Learning path build failed.', {
          description: failureMessage,
        });
        return;
      }
      if (response.status === 'partial') {
        toast.warning('Learning path partially built', {
          description:
            response.error ?? 'Some selected skills do not have learning resources yet.',
        });
        navigate('/individual/learning-path');
        return;
      }
      toast.success('Learning path built');
      navigate('/individual/learning-path');
    } catch (buildError) {
      if (
        isStaleAuthSessionError(buildError) ||
        (authSession && !isRequestCurrent(authSession))
      ) {
        return;
      }
      if (getErrorStatus(buildError) === 409 && graphSession) {
        try {
          const recovery = await recoverIndividualWorkflow(graphSession.ownerUserId);
          setGraphSession(recovery.session);
          navigate(getIndividualRecoveryPath(recovery.profile.next_step));
          return;
        } catch (recoveryError) {
          console.error(recoveryError);
          toast.error('Workflow changed and could not be recovered.');
          return;
        }
      }
      console.error(buildError);
      setBuildError('The learning path could not be built. Your skill selection is still saved.');
      toast.error('Learning path build failed.');
    } finally {
      if (authSession && isRequestCurrent(authSession)) {
        setIsBuilding(false);
      }
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Select market skills</h1>
        <p className="text-sm text-muted-foreground">
          Stage skills from interested job postings, then persist the final market-skill selection
          when you build.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle>Job-posting skill bank</CardTitle>
            <CardDescription>
              CV skills remain profile evidence and are not selectable learning targets.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="outline"
              onClick={toggleAllSkills}
              disabled={isLoading || availableSkillNames.length === 0}
            >
              <CheckCircle2 className="size-4" />
              {allSkillsSelected ? 'Clear all market skills' : 'Select all market skills'}
            </Button>
            <Button
              onClick={handleBuild}
              disabled={
                isLoading ||
                isBuilding ||
                selectedSkills.size === 0 ||
                selectedSkills.size > MAX_SELECTED_SKILLS
              }
            >
              {isBuilding ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              Build learning path
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <Badge variant="secondary">{selectedSkills.size} selected</Badge>
            <Badge variant="outline">{interestedPostings.length} interested job(s)</Badge>
            <Badge variant="outline">{availableSkillNames.length} available market skill(s)</Badge>
            <span>Choose 1-{MAX_SELECTED_SKILLS} skills.</span>
          </div>

          {buildError ? (
            <Alert variant="destructive">
              <ArrowRight className="size-4" />
              <AlertTitle>Learning path build failed</AlertTitle>
              <AlertDescription>
                {buildError} Retry the build when you are ready; your selected skills remain here.
              </AlertDescription>
            </Alert>
          ) : null}

          {isLoading ? (
            <div className="rounded-md border p-8 text-sm text-muted-foreground">
              Loading skill bank...
            </div>
          ) : error ? (
            <Alert variant="destructive">
              <ArrowRight className="size-4" />
              <AlertTitle>Skills unavailable</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : interestedPostings.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <BriefcaseBusiness className="size-5" />
                </EmptyMedia>
                <EmptyTitle>No interested job skills yet</EmptyTitle>
                <EmptyDescription>
                  Return to job matches and select at least one posting first.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <Accordion
              type="multiple"
              defaultValue={[`job-${interestedPostings[0]?.url}`]}
              className="space-y-3"
            >
              {interestedPostings.map((posting) => {
                const postingSkillNames = posting.skills.map((skill) => skill.name);
                const everyPostingSkillSelected =
                  postingSkillNames.length > 0 &&
                  postingSkillNames.every((name) => selectedSkills.has(name));

                return (
                  <AccordionItem
                    key={posting.url}
                    value={`job-${posting.url}`}
                    className="overflow-hidden rounded-xl border px-4"
                  >
                    <div className="flex flex-col gap-3 py-4 lg:flex-row lg:items-start">
                      <AccordionTrigger className="min-w-0 flex-1 gap-3 py-0 hover:no-underline">
                        <div className="min-w-0 space-y-2 text-left">
                          <div>
                            <div className="font-medium">{posting.title}</div>
                            <div className="text-sm text-muted-foreground">
                              {posting.company || 'Unknown company'}
                              {posting.site ? ` • ${posting.site}` : ''}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline">{posting.skills.length} skills</Badge>
                            {posting.search_term ? (
                              <Badge variant="outline">Search: {posting.search_term}</Badge>
                            ) : null}
                          </div>
                        </div>
                      </AccordionTrigger>
                      <Button
                        type="button"
                        size="sm"
                        variant={everyPostingSkillSelected ? 'default' : 'outline'}
                        onClick={() => togglePostingSkills(posting)}
                        disabled={posting.skills.length === 0}
                        aria-label={`${
                          everyPostingSkillSelected ? 'Clear' : 'Select all'
                        } skills for ${posting.title}`}
                      >
                        <Sparkles className="size-3.5" />
                        {everyPostingSkillSelected ? 'Clear posting skills' : 'Select posting skills'}
                      </Button>
                    </div>
                    <AccordionContent className="space-y-4 border-t pt-4">
                      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>Fine-tune the draft with individual market-skill chips.</span>
                        <a
                          href={posting.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex shrink-0 items-center gap-1 hover:text-foreground"
                        >
                          View posting
                          <ExternalLink className="size-3" />
                        </a>
                      </div>
                      {posting.skills.length > 0 ? (
                        <div className="flex flex-wrap gap-2 pb-2">
                          {posting.skills.map((skill) => (
                            <SkillChip
                              key={`${posting.url}-${skill.name}`}
                              skill={skill}
                              selected={selectedSkills.has(skill.name)}
                              onToggle={() => toggleSkill(skill.name)}
                            />
                          ))}
                        </div>
                      ) : (
                        <p className="pb-2 text-sm text-muted-foreground">
                          No market skills are linked to this posting yet.
                        </p>
                      )}
                    </AccordionContent>
                  </AccordionItem>
                );
              })}
            </Accordion>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
