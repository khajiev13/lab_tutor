import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { approveSkillIntegration, skillReviewErrorMessage } from "@/features/market-demand/api";
import { isUsablePostingUrl } from "@/features/market-demand/selection";
import { EvidenceLink } from "@/features/market-demand/components/SkillEvidencePanel";
import type { SkillReview } from "@/features/market-demand/types";

interface Props {
  courseId: number;
  review: SkillReview;
  onReviewChange: (review: SkillReview) => void;
  disabled?: boolean;
}

export function IntegrationReview({courseId, review, onReviewChange, disabled}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0);
  const [incoming, setIncoming] = useState(review);
  const [acknowledged, setAcknowledged] = useState<SkillReview | null>(null);
  if (incoming !== review) {
    setIncoming(review);
    setBusy(false);
    setError(null);
    if (review !== acknowledged) setSuccess(null);
  }
  useEffect(() => {
    generation.current += 1;
    return () => { generation.current += 1; };
  }, [courseId, review]);
  const proposal = review.integration_review;
  if (!proposal) return success ? <p role="status" className="text-xs">{success}</p> : null;
  const ids = proposal.items.map(item => item.candidate_id);
  const missing = proposal.items.filter(item => {
    const candidate = review.candidates.find(value => value.candidate_id === item.candidate_id);
    return candidate?.posting_support !== "supported" || !candidate.qualifying_posting_links.some(isUsablePostingUrl) || !item.qualifying_posting_links.some(isUsablePostingUrl) || !item.evidence_snapshot_ids.length;
  });
  const current = proposal.candidate_revision === review.candidate_revision &&
    proposal.selection_revision === review.selection_revision && !!proposal.review_digest &&
    ids.length === review.selected_candidate_ids.length && ids.every(id => review.selected_candidate_ids.includes(id));
  const canApprove = !!review.run_id && current && ids.length > 0 && !missing.length &&
    (!proposal.omissions.length || proposal.omissions_acknowledged);
  const approve = async () => {
    if (!canApprove || disabled || busy || !review.run_id) return;
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await approveSkillIntegration(courseId, {
        run_id: review.run_id,
        expected_candidate_revision: review.candidate_revision,
        expected_selection_revision: review.selection_revision,
        review_digest: proposal.review_digest,
        approved_candidate_ids: ids,
      });
      if (request !== generation.current) return;
      setAcknowledged(response.review);
      onReviewChange(response.review);
      setSuccess(response.projection_status === "projected" ? "Approval saved; publication projected" : response.projection_status === "error" ? "Approval saved; projection failed" : "Approval saved; publication waiting for projection");
    } catch (cause) {
      if (request === generation.current) setError(skillReviewErrorMessage(cause, "Integration approval failed"));
    } finally {
      if (request === generation.current) setBusy(false);
    }
  };
  return (
    <section className="space-y-3 rounded-lg border p-3 text-sm" aria-label="Final integration review">
      <h3 className="font-semibold">Final integration review</h3>
      <p className="text-xs text-muted-foreground">Review the exact targets and chapter relationships before publishing. Draft changes leave the previous offering available.</p>
      {proposal.items.map(item => (
        <div key={item.candidate_id} className="space-y-1 rounded-md border p-2">
          <p className="font-medium">{item.target.label}</p>
          <p className="text-xs">{item.disposition} · {item.target.source} · {item.target.origin} · target {item.target.identity}</p>
          <p className="text-xs">Chapters: {item.chapters.map(chapter => chapter.title).join(", ") || "No chapter relationship"}</p>
          {item.qualifying_posting_links.map(url => <p key={url} className="text-xs"><EvidenceLink url={url} label="Original job posting"/></p>)}
          {missing.some(value => value.candidate_id === item.candidate_id) && <p className="text-xs text-destructive">Needs supporting job posting</p>}
        </div>
      ))}
      {proposal.omissions.map((omission, index) => <p key={index} className="text-xs">{omission}</p>)}
      {!current && <p className="text-xs text-destructive">Review revisions changed. Confirm the current selection for a new mapping review.</p>}
      {!!proposal.omissions.length && !proposal.omissions_acknowledged && <p className="text-xs text-destructive">Acknowledge the current evidence omissions before approval.</p>}
      {review.approved_references.length > 0 && <div className="text-xs"><p className="font-medium">Previously published offering</p>{review.approved_references.map(item => <p key={item.reference_id}>{item.label}</p>)}</div>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {success && <p role="status">{success}</p>}
      <Button size="sm" disabled={!canApprove || disabled || busy || !!success} onClick={() => void approve()}>{busy ? "Approving…" : "Approve integration"}</Button>
    </section>
  );
}
