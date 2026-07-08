import { ArrowRight, CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
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
import { cn } from '@/lib/utils';
import {
  buildIndividualLearningPath,
  deselectIndividualSkills,
  getIndividualSkillBanks,
  selectIndividualSkills,
  type IndividualSkillBankJobPosting,
  type IndividualSkillBankSkill,
} from '../api';

type SkillSummary = {
  name: string;
  description?: string | null;
  category?: string | null;
  coverage?: IndividualSkillBankSkill['coverage'];
  postingCount: number;
};

function buildInterestedPostingUrls(postings: IndividualSkillBankJobPosting[], persistedUrls: string[]) {
  const next = new Set(persistedUrls);

  postings.forEach((posting) => {
    if (posting.is_interested) {
      next.add(posting.url);
    }
  });

  return next;
}

function buildMarketSkillSummaries(
  postings: IndividualSkillBankJobPosting[],
  interestedUrls: Set<string>,
) {
  const summaries = new Map<string, SkillSummary>();

  postings.forEach((posting) => {
    if (!interestedUrls.has(posting.url)) {
      return;
    }

    posting.skills.forEach((skill) => {
      const current = summaries.get(skill.name);
      if (current) {
        current.postingCount += 1;
        if (!current.description && skill.description) {
          current.description = skill.description;
        }
        if (!current.category && skill.category) {
          current.category = skill.category;
        }
        if ((!current.coverage || current.coverage === 'unknown') && skill.coverage) {
          current.coverage = skill.coverage;
        }
        return;
      }

      summaries.set(skill.name, {
        name: skill.name,
        description: skill.description,
        category: skill.category,
        coverage: skill.coverage,
        postingCount: 1,
      });
    });
  });

  return Array.from(summaries.values()).sort((left, right) => left.name.localeCompare(right.name));
}

export default function IndividualSkillsPage() {
  const navigate = useNavigate();
  const [postings, setPostings] = useState<IndividualSkillBankJobPosting[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const [persistedSkills, setPersistedSkills] = useState<Set<string>>(new Set());
  const [interestedUrls, setInterestedUrls] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);

  useEffect(() => {
    let active = true;

    async function loadSkillBanks() {
      try {
        const data = await getIndividualSkillBanks();
        if (!active) {
          return;
        }

        const nextInterestedUrls = buildInterestedPostingUrls(
          data.market_skill_bank,
          data.interested_posting_urls,
        );
        const nextSelectedSkills = new Set(data.selected_skill_names);

        setPostings(data.market_skill_bank);
        setInterestedUrls(nextInterestedUrls);
        setSelectedSkills(nextSelectedSkills);
        setPersistedSkills(nextSelectedSkills);
      } catch (error) {
        console.error(error);
        toast.error('Failed to load market skills.');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    loadSkillBanks();

    return () => {
      active = false;
    };
  }, []);

  const availableSkills = useMemo(
    () => buildMarketSkillSummaries(postings, interestedUrls),
    [interestedUrls, postings],
  );

  const hasSelectionChanges = useMemo(() => {
    if (selectedSkills.size !== persistedSkills.size) {
      return true;
    }

    return Array.from(selectedSkills).some((skillName) => !persistedSkills.has(skillName));
  }, [persistedSkills, selectedSkills]);

  const toggleSkill = (skillName: string, checked: boolean) => {
    setSelectedSkills((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(skillName);
      } else {
        next.delete(skillName);
      }
      return next;
    });
  };

  const persistSelection = async () => {
    const selected = Array.from(selectedSkills);
    const added = selected.filter((skillName) => !persistedSkills.has(skillName));
    const removed = Array.from(persistedSkills).filter((skillName) => !selectedSkills.has(skillName));

    if (added.length === 0 && removed.length === 0) {
      return;
    }

    if (added.length > 0) {
      await selectIndividualSkills(added);
    }

    if (removed.length > 0) {
      await deselectIndividualSkills(removed);
    }

    setPersistedSkills(new Set(selected));
  };

  const handleSaveSelection = async () => {
    setIsSaving(true);
    try {
      await persistSelection();
      toast.success('Skill selection saved.');
    } catch (error) {
      console.error(error);
      toast.error('Could not save your selected skills.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleBuild = async () => {
    if (selectedSkills.size === 0) {
      toast.error('Select at least one market skill before building.');
      return;
    }

    setIsBuilding(true);
    try {
      await persistSelection();
      const response = await buildIndividualLearningPath(Array.from(selectedSkills));
      toast.success('Learning path built', {
        description: `Backend status: ${response.status}.`,
      });
      navigate('/individual/learning-path');
    } catch (error) {
      console.error(error);
      toast.error('Learning path build failed.');
    } finally {
      setIsBuilding(false);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Skill selection</h1>
        <p className="text-sm text-muted-foreground">
          Choose from market skills attached to your interested jobs, then build the path
          synchronously.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Selected skills</CardTitle>
            <CardDescription>
              CV skills are intentionally not selectable in this flow.
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={handleSaveSelection} disabled={isLoading || isSaving || !hasSelectionChanges}>
              {isSaving ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
              Save selection
            </Button>
            <Button onClick={handleBuild} disabled={isLoading || isBuilding || selectedSkills.size === 0}>
              {isBuilding ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
              Build learning path
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <Badge variant="secondary">{selectedSkills.size} selected</Badge>
            <Badge variant="outline">{interestedUrls.size} interested job(s)</Badge>
            <Badge variant="outline">{availableSkills.length} available market skill(s)</Badge>
          </div>

          {isLoading ? (
            <div className="rounded-md border p-8 text-sm text-muted-foreground">Loading skill bank...</div>
          ) : availableSkills.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <ArrowRight className="size-5" />
                </EmptyMedia>
                <EmptyTitle>No selectable skills yet</EmptyTitle>
                <EmptyDescription>
                  Pick interested jobs first so market skills can appear here.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {availableSkills.map((skill) => {
                const checked = selectedSkills.has(skill.name);

                return (
                  <Card key={skill.name} className={cn('rounded-lg', checked && 'border-primary')}>
                    <CardContent className="flex h-full flex-col gap-4 p-5">
                      <div className="flex items-start gap-3">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(value) => toggleSkill(skill.name, value === true)}
                          aria-label={`Select ${skill.name}`}
                        />
                        <div className="space-y-2">
                          <div className="font-medium">{skill.name}</div>
                          <div className="flex flex-wrap gap-2">
                            {skill.category ? <Badge variant="outline">{skill.category}</Badge> : null}
                            <Badge variant="secondary">{skill.postingCount} posting(s)</Badge>
                            {skill.coverage ? (
                              <Badge variant="outline" className="capitalize">
                                {skill.coverage}
                              </Badge>
                            ) : null}
                          </div>
                        </div>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {skill.description ?? 'No description was returned for this market skill.'}
                      </p>
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
