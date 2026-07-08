import { BriefcaseBusiness, ExternalLink, Loader2, Save } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import { getIndividualSkillBanks, selectInterestedJobs, type IndividualSkillBankJobPosting } from '../api';

function sameMembers(left: string[], right: string[]) {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((value, index) => value === right[index]);
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

export default function IndividualJobsPage() {
  const [jobs, setJobs] = useState<IndividualSkillBankJobPosting[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [persistedUrls, setPersistedUrls] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadJobs() {
      try {
        const data = await getIndividualSkillBanks();
        if (!active) {
          return;
        }

        const initialSelection = buildSelectionSet(
          data.market_skill_bank,
          data.interested_posting_urls,
        );
        setJobs(data.market_skill_bank);
        setSelectedUrls(initialSelection);
        setPersistedUrls(Array.from(initialSelection).sort());
      } catch (error) {
        console.error(error);
        toast.error('Failed to load job matches.');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    loadJobs();

    return () => {
      active = false;
    };
  }, []);

  const selectedCount = selectedUrls.size;
  const hasChanges = useMemo(() => {
    const next = Array.from(selectedUrls).sort();
    return !sameMembers(next, persistedUrls);
  }, [persistedUrls, selectedUrls]);

  const handleToggle = (url: string, checked: boolean) => {
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

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const orderedUrls = Array.from(selectedUrls);
      const response = await selectInterestedJobs(orderedUrls);
      setPersistedUrls([...orderedUrls].sort());
      toast.success('Interested jobs saved', {
        description: `${response.postings_linked} job posting(s) linked to your profile.`,
      });
    } catch (error) {
      console.error(error);
      toast.error('Could not save interested jobs.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Job matches</h1>
        <p className="text-sm text-muted-foreground">
          Mark the postings that should contribute market skills to your individual path.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Interested jobs</CardTitle>
            <CardDescription>
              Individual learning uses only market skills from the jobs you select here.
            </CardDescription>
          </div>
          <Button onClick={handleSave} disabled={isLoading || isSaving || !hasChanges}>
            {isSaving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            Save interested jobs
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="secondary">{selectedCount} selected</Badge>
            <span>{jobs.length} job posting(s) available</span>
          </div>

          {isLoading ? (
            <div className="rounded-md border p-8 text-sm text-muted-foreground">Loading job matches...</div>
          ) : jobs.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <BriefcaseBusiness className="size-5" />
                </EmptyMedia>
                <EmptyTitle>No job matches yet</EmptyTitle>
                <EmptyDescription>
                  Your backend profile has not surfaced any job postings yet.
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent />
            </Empty>
          ) : (
            <div className="grid gap-4">
              {jobs.map((job) => {
                const checked = selectedUrls.has(job.url);

                return (
                  <Card key={job.url} className="rounded-lg">
                    <CardContent className="flex flex-col gap-4 p-5">
                      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                        <div className="space-y-2">
                          <div className="flex items-center gap-3">
                            <Checkbox
                              checked={checked}
                              onCheckedChange={(value) => handleToggle(job.url, value === true)}
                              aria-label={`Mark ${job.title} as interested`}
                            />
                            <div>
                              <div className="font-medium">{job.title}</div>
                              <div className="text-sm text-muted-foreground">
                                {job.company || 'Unknown company'}
                                {job.site ? ` • ${job.site}` : ''}
                                {job.search_term ? ` • ${job.search_term}` : ''}
                              </div>
                            </div>
                          </div>
                          {job.match_score != null ? (
                            <Badge variant="outline">Match {(job.match_score * 100).toFixed(0)}%</Badge>
                          ) : null}
                        </div>
                        <Button variant="outline" size="sm" asChild>
                          <a href={job.url} target="_blank" rel="noreferrer">
                            <ExternalLink className="size-4" />
                            Open posting
                          </a>
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {job.skills.length > 0 ? (
                          job.skills.map((skill) => (
                            <Badge key={`${job.url}-${skill.name}`} variant="secondary">
                              {skill.name}
                            </Badge>
                          ))
                        ) : (
                          <span className="text-sm text-muted-foreground">No market skills attached yet.</span>
                        )}
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
