import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Loader2, RefreshCw, Search, ShieldCheck, ThumbsDown, ThumbsUp } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

import {
  applyNormalizationReview,
  getNormalizationReview,
  updateNormalizationReviewDecisions,
  type MergeProposalDecision,
  type MergeProposal,
  type NormalizationReview,
} from '@/features/normalization/api';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

import { MergeProposalCard } from '../components/MergeProposalCard';

type Filter = 'all' | 'pending' | 'approved' | 'rejected';

function normalize(s: string): string {
  return s.trim().toLowerCase();
}

export default function MergeReviewPage() {
  const { id, reviewId } = useParams<{ id: string; reviewId: string }>();
  const navigate = useNavigate();
  const courseId = Number(id);
  
  const [isLoading, setIsLoading] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [review, setReview] = useState<NormalizationReview | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmApplyOpen, setConfirmApplyOpen] = useState(false);

  const loadReview = useCallback(async () => {
    if (!reviewId) return;
    setIsLoading(true);
    try {
      const data = await getNormalizationReview(courseId, reviewId);
      setReview(data);
      setSelectedId((prev) => prev ?? (data.proposals[0]?.id ?? null));
    } catch (e) {
      // After successful Apply, backend deletes the staged review rows -> GET returns 404.
      if (axios.isAxiosError(e) && e.response?.status === 404) {
        toast.message('Review no longer exists (already applied or replaced)');
        navigate(`/courses/${courseId}`);
        return;
      }
      toast.error('Failed to load review');
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  }, [courseId, reviewId, navigate]);

  useEffect(() => {
    void loadReview();
  }, [loadReview]);

  const proposals = useMemo(() => review?.proposals ?? [], [review]);

  const filteredProposals = useMemo(() => {
    const q = normalize(search);
    return proposals.filter((p: MergeProposal) => {
      if (filter !== 'all' && p.decision !== filter) return false;
      if (!q) return true;
      const hay = `${p.concept_a} ${p.concept_b} ${p.canonical} ${p.r}`.toLowerCase();
      return hay.includes(q);
    });
  }, [proposals, search, filter]);

  const selected = useMemo(() => {
    return proposals.find((p: MergeProposal) => p.id === selectedId) ?? null;
  }, [proposals, selectedId]);

  const decisionCounts = useMemo(() => {
    const counts = { pending: 0, approved: 0, rejected: 0 };
    for (const p of proposals) {
      counts[p.decision] += 1;
    }
    return counts;
  }, [proposals]);

  const updateDecision = useCallback(
    async (proposalId: string, decision: MergeProposalDecision) => {
      if (!review || !reviewId) return;

      // Optimistic UI
      setReview({
        ...review,
        proposals: review.proposals.map((p) =>
          p.id === proposalId ? { ...p, decision } : p
        ),
      });

      try {
        await updateNormalizationReviewDecisions(courseId, reviewId, [
          { proposal_id: proposalId, decision },
        ]);
      } catch (e) {
        toast.error('Failed to update decision');
        console.error(e);
        // Reload to re-sync.
        void loadReview();
      }
    },
    [courseId, reviewId, review, loadReview]
  );

  const bulkApprovePending = useCallback(async () => {
    if (!review) return;
    const pending = review.proposals.filter((p) => p.decision === 'pending' && !p.applied);
    if (pending.length === 0) return;

    // Optimistic UI
    setReview({
      ...review,
      proposals: review.proposals.map((p) =>
        p.decision === 'pending' && !p.applied ? { ...p, decision: 'approved' } : p
      ),
    });

    try {
      await updateNormalizationReviewDecisions(
        courseId,
        reviewId!,
        pending.map((p) => ({ proposal_id: p.id, decision: 'approved' }))
      );
      toast.success(`Approved ${pending.length} merges`);
    } catch (e) {
      toast.error('Failed to bulk approve');
      console.error(e);
      void loadReview();
    }
  }, [courseId, reviewId, review, loadReview]);

  const applyApproved = useCallback(async () => {
    if (!reviewId || isApplying) return;
    setConfirmApplyOpen(false);
    try {
      setIsApplying(true);
      const res = await applyNormalizationReview(courseId, reviewId);
      if (res.failed > 0) {
        toast.error(`Apply finished with ${res.failed} failures`);
        if (res.errors?.length) {
          console.error('Apply errors:', res.errors);
        }
        void loadReview();
      } else {
        toast.success(`Applied ${res.applied} merges (${res.skipped} skipped)`);
        // Review rows are deleted in backend on success -> go back to course.
        navigate(`/courses/${courseId}`);
      }
    } catch (e) {
      toast.error('Failed to apply merges');
      console.error(e);
    } finally {
      setIsApplying(false);
    }
  }, [courseId, reviewId, loadReview, navigate, isApplying]);

  const definitionBlock = useCallback(
    (conceptName: string) => {
      const defs = review?.definitions?.[conceptName] ?? [];
      if (defs.length === 0) {
        return <div className="text-sm text-muted-foreground">No definitions found.</div>;
      }
      return (
        <ScrollArea className="h-[240px] pr-3">
          <div className="space-y-3">
            {defs.slice(0, 12).map((d: string, idx: number) => (
              <div
                key={`${conceptName}-${idx}`}
                className="text-sm text-muted-foreground whitespace-pre-wrap break-words"
              >
                <span className="mr-2 text-muted-foreground/70 tabular-nums">{idx + 1}.</span>
                {d}
              </div>
            ))}
            {defs.length > 12 && (
              <div className="text-xs text-muted-foreground">+ {defs.length - 12} more…</div>
            )}
          </div>
        </ScrollArea>
      );
    },
    [review?.definitions]
  );

  const hasApproved = proposals.some((p) => p.decision === 'approved' && !p.applied);

  return (
    <div className="min-h-screen flex flex-col">
      <div className="border-b bg-background">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                className="pl-0 hover:bg-transparent hover:text-primary"
                onClick={() => navigate(`/courses/${courseId}`)}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
              <div>
                <h1 className="flex items-center gap-2 text-2xl font-semibold">
                  <ShieldCheck className="h-6 w-6 text-primary" />
                  Review suggested concept merges
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                  Scan the queue, approve/reject merges, then apply approved merges to Neo4j.
                </p>
              </div>
            </div>

            <Button
              variant="secondary"
              onClick={() => void loadReview()}
              disabled={isLoading}
              title="Refresh"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              <span className="ml-2 hidden sm:inline">Refresh</span>
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 container mx-auto px-6 py-6">
        <div className="grid h-[calc(100vh-200px)] lg:grid-cols-[420px_1fr] gap-6">
          {/* Left: queue */}
          <div className="border-r flex min-h-0 flex-col">
            <div className="px-4 pt-4 pb-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">Pending {decisionCounts.pending}</Badge>
                <Badge variant="default">Approved {decisionCounts.approved}</Badge>
                <Badge variant="destructive">Rejected {decisionCounts.rejected}</Badge>
                {isLoading && (
                  <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Loading…
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    className="pl-8"
                    placeholder="Search merges…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <Button
                  variant="secondary"
                  onClick={() => void bulkApprovePending()}
                  disabled={isLoading}
                  title="Approve all pending merges"
                >
                  <ThumbsUp className="mr-2 h-4 w-4" />
                  <span className="hidden sm:inline">Approve pending</span>
                  <span className="sm:hidden">Approve</span>
                </Button>
              </div>

              <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)}>
                <TabsList className="w-full grid grid-cols-4">
                  <TabsTrigger value="all">All</TabsTrigger>
                  <TabsTrigger value="pending">Pending</TabsTrigger>
                  <TabsTrigger value="approved">Approved</TabsTrigger>
                  <TabsTrigger value="rejected">Rejected</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            <Separator />

            <ScrollArea className="flex-1 min-h-0 px-4 py-3">
              <div className="space-y-2">
                {filteredProposals.length === 0 ? (
                  <div className="text-sm text-muted-foreground">No merges match your filters.</div>
                ) : (
                  filteredProposals.map((p: MergeProposal) => (
                    <MergeProposalCard
                      key={p.id}
                      proposal={p}
                      isSelected={p.id === selectedId}
                      onSelect={() => setSelectedId(p.id)}
                    />
                  ))
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Right: details */}
          <div className="min-h-0">
            <ScrollArea className="h-full">
              <div className="p-4 space-y-4">
                <Card>
                  <CardHeader className="py-3">
                    <CardTitle className="text-base">Selected merge</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {!selected ? (
                      <div className="text-sm text-muted-foreground">
                        Select a merge from the left to review.
                      </div>
                    ) : (
                      <>
                        <div className="flex items-start justify-between gap-3">
                          <div className="text-sm leading-6">
                            <span className="font-medium">{selected.canonical}</span>
                            <span className="ml-2 text-xs text-muted-foreground">
                              ({selected.variants.length} variants)
                            </span>
                          </div>
                          <Badge
                            variant={
                              selected.decision === 'approved'
                                ? 'default'
                                : selected.decision === 'rejected'
                                  ? 'destructive'
                                  : 'secondary'
                            }
                          >
                            {selected.decision}
                          </Badge>
                        </div>

                        <div className="text-sm text-muted-foreground whitespace-pre-wrap break-words">
                          {selected.r}
                        </div>

                        <div className="flex flex-wrap gap-2">
                          {selected.variants.map((v: string) => (
                            <Badge key={v} variant="outline">
                              {v}
                            </Badge>
                          ))}
                        </div>

                        <Separator />

                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            onClick={() => void updateDecision(selected.id, 'approved')}
                            disabled={selected.applied || isLoading}
                          >
                            <Check className="mr-2 h-4 w-4" />
                            Approve
                          </Button>
                          <Button
                            variant="destructive"
                            onClick={() => void updateDecision(selected.id, 'rejected')}
                            disabled={selected.applied || isLoading}
                          >
                            <ThumbsDown className="mr-2 h-4 w-4" />
                            Reject
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => void updateDecision(selected.id, 'pending')}
                            disabled={selected.applied || isLoading}
                          >
                            Reset
                          </Button>
                          {selected.applied && (
                            <span className="text-xs text-green-700 dark:text-green-400">
                              Applied
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="py-3">
                    <CardTitle className="text-base">Evidence</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {!selected ? (
                      <div className="text-sm text-muted-foreground">Select a merge to see evidence.</div>
                    ) : (
                      <>
                        <EvidenceTabs
                          key={`${selected.canonical}|${selected.variants.join('|')}`}
                          canonical={selected.canonical}
                          variants={selected.variants}
                          render={definitionBlock}
                        />
                      </>
                    )}
                  </CardContent>
                </Card>

                <div className="flex items-center justify-end gap-2 pb-2">
                  <Button
                    onClick={() => setConfirmApplyOpen(true)}
                    disabled={!hasApproved || isLoading || isApplying}
                    title={!hasApproved ? 'Approve at least one merge to apply' : 'Apply approved merges'}
                  >
                    {isApplying ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Applying…
                      </>
                    ) : (
                      'Apply approved merges'
                    )}
                  </Button>
                </div>
              </div>
            </ScrollArea>
          </div>
        </div>
      </div>

      <AlertDialog open={confirmApplyOpen} onOpenChange={setConfirmApplyOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Apply approved merges?</AlertDialogTitle>
            <AlertDialogDescription>
              This will merge concept nodes in Neo4j (destructive). Duplicate relationships will be merged.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void applyApproved()} disabled={isApplying}>
              {isApplying ? 'Applying…' : 'Apply'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function EvidenceTabs({
  canonical,
  variants,
  render,
}: {
  canonical: string;
  variants: string[];
  render: (name: string) => ReactNode;
}) {
  const variantOptions = useMemo(() => {
    const uniq = Array.from(new Set(variants.filter(Boolean)));
    // Prefer showing a non-canonical variant by default if present.
    const nonCanonical = uniq.filter((v) => v !== canonical);
    return { uniq, nonCanonical };
  }, [variants, canonical]);

  const defaultVariant = variantOptions.nonCanonical[0] ?? canonical;
  const [activeVariant, setActiveVariant] = useState<string>(defaultVariant);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground">Variant</div>
          <div className="flex flex-wrap gap-2">
            {variantOptions.uniq.slice(0, 8).map((v) => (
              <Button
                key={v}
                type="button"
                variant={v === activeVariant ? 'default' : 'secondary'}
                className="justify-start truncate"
                onClick={() => setActiveVariant(v)}
              >
                {v}
              </Button>
            ))}
            {variantOptions.uniq.length > 8 ? (
              <span className="text-xs text-muted-foreground self-center">
                +{variantOptions.uniq.length - 8} more…
              </span>
            ) : null}
          </div>
          <div className="text-xs text-muted-foreground">
            Click a variant to inspect its definitions.
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground">Canonical</div>
          <Badge variant="outline" className="justify-start">
            {canonical}
          </Badge>
          <div className="text-xs text-muted-foreground">
            Compare the selected variant against the canonical concept.
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <div className="text-sm font-medium">{activeVariant}</div>
          {render(activeVariant)}
        </div>
        <div className="space-y-2">
          <div className="text-sm font-medium">{canonical}</div>
          {render(canonical)}
        </div>
      </div>
    </div>
  );
}

