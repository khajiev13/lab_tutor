import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { coursesApi } from "@/features/courses/api";
import type { PrerequisiteDraftEdge, PrerequisiteReview } from "@/features/courses/types";
import { AddPrerequisiteEdgeDialog } from "@/features/prerequisite-review/components/AddPrerequisiteEdgeDialog";
import { IsolatedSkillsPanel } from "@/features/prerequisite-review/components/IsolatedSkillsPanel";
import { PrerequisiteEdgeWorklist } from "@/features/prerequisite-review/components/PrerequisiteEdgeWorklist";
import { PrerequisiteGraphPreview } from "@/features/prerequisite-review/components/PrerequisiteGraphPreview";
import { cn } from "@/lib/utils";

const STATUS_LABEL = {
  not_started: "Not started",
  needs_review: "Needs review",
  approved: "Approved",
  stale: "Stale",
} satisfies Record<PrerequisiteReview["status"], string>;

const STATUS_CLASS = {
  not_started: "text-muted-foreground",
  needs_review: "border-amber-200 text-amber-700",
  approved: "border-emerald-200 text-emerald-700",
  stale: "border-rose-200 text-rose-700",
} satisfies Record<PrerequisiteReview["status"], string>;

export function PrerequisiteReviewPage() {
  const { id } = useParams();
  const courseId = Number(id);
  const [review, setReview] = useState<PrerequisiteReview | null>(null);
  const [isolatedReviewed, setIsolatedReviewed] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReview = useCallback(async () => {
    if (!Number.isFinite(courseId)) return;
    setIsLoading(true);
    setError(null);
    try {
      const nextReview = await coursesApi.getPrerequisiteReview(courseId);
      setReview(nextReview);
      setIsolatedReviewed(nextReview.isolated_skills.length === 0);
    } catch {
      setError("Unable to load prerequisite review.");
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    void loadReview();
  }, [loadReview]);

  const cyclePath = useMemo(() => review?.validation.cycle_path.join(" -> ") ?? "", [review]);
  const approvalDisabled =
    !review ||
    !review.validation.is_valid ||
    review.is_rebuilding ||
    (review.isolated_skills.length > 0 && !isolatedReviewed);

  async function saveDraft(nextEdges: PrerequisiteDraftEdge[], nextIsolatedReviewed = false) {
    if (!review) return;

    setIsSaving(true);
    setError(null);
    try {
      const nextReview = await coursesApi.savePrerequisiteReview(courseId, {
        draft_edges: nextEdges,
        isolated_skills_viewed: nextIsolatedReviewed,
      });
      setReview(nextReview);
      setIsolatedReviewed(nextIsolatedReviewed || nextReview.isolated_skills.length === 0);
    } catch {
      setError("Unable to save prerequisite review.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRegenerate() {
    setIsSaving(true);
    setError(null);
    try {
      await coursesApi.regeneratePrerequisites(courseId);
      await loadReview();
    } catch {
      setError("Unable to regenerate prerequisites.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleApprove() {
    setIsSaving(true);
    setError(null);
    try {
      const nextReview = await coursesApi.approvePrerequisiteReview(courseId);
      setReview(nextReview);
      setIsolatedReviewed(nextReview.isolated_skills.length === 0 || isolatedReviewed);
    } catch {
      setError("Unable to approve prerequisite graph.");
    } finally {
      setIsSaving(false);
    }
  }

  if (!Number.isFinite(courseId)) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Invalid course</AlertTitle>
      </Alert>
    );
  }

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading prerequisite review...</div>;
  }

  if (!review) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Prerequisite review unavailable</AlertTitle>
        {error && <AlertDescription>{error}</AlertDescription>}
      </Alert>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <Button variant="ghost" size="sm" asChild className="w-fit">
            <Link to={`/courses/${courseId}`}>
              <ArrowLeft />
              Back to course
            </Link>
          </Button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Prerequisite Review</h1>
            <Badge variant="outline" className={cn(STATUS_CLASS[review.status])}>
              {STATUS_LABEL[review.status]}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={isSaving || review.is_rebuilding}
            onClick={handleRegenerate}
          >
            <RefreshCw />
            Regenerate
          </Button>
          <Button type="button" variant="outline" onClick={() => setDialogOpen(true)}>
            <Plus />
            Add edge
          </Button>
          <Button type="button" disabled={approvalDisabled || isSaving} onClick={handleApprove}>
            Approve graph
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>Action failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!review.validation.is_valid && (
        <Alert variant="destructive">
          <AlertTitle>Validation failed</AlertTitle>
          <AlertDescription>
            {review.validation.errors.map((validationError) => (
              <p key={validationError}>{validationError}</p>
            ))}
            {cyclePath && <p>{cyclePath}</p>}
          </AlertDescription>
        </Alert>
      )}

      {review.is_rebuilding && (
        <Alert>
          <AlertTitle>Rebuilding prerequisite graph</AlertTitle>
        </Alert>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold">Draft edges</h2>
            <span className="text-sm text-muted-foreground">{review.draft_edges.length} edges</span>
          </div>
          <PrerequisiteEdgeWorklist
            edges={review.draft_edges}
            isSaving={isSaving}
            onRemove={(edge) =>
              saveDraft(
                review.draft_edges.filter(
                  (draftEdge) =>
                    draftEdge.prerequisite_name !== edge.prerequisite_name ||
                    draftEdge.dependent_name !== edge.dependent_name,
                ),
              )
            }
          />
        </section>

        <IsolatedSkillsPanel
          isolatedSkills={review.isolated_skills}
          reviewed={isolatedReviewed}
          isSaving={isSaving}
          onMarkReviewed={() => saveDraft(review.draft_edges, true)}
        />
      </div>

      <PrerequisiteGraphPreview skills={review.skills} edges={review.draft_edges} />

      <AddPrerequisiteEdgeDialog
        open={dialogOpen}
        skills={review.skills}
        isSaving={isSaving}
        onOpenChange={setDialogOpen}
        onAdd={(edge) => {
          setDialogOpen(false);
          void saveDraft([...review.draft_edges, edge]);
        }}
      />
    </div>
  );
}

export default PrerequisiteReviewPage;
