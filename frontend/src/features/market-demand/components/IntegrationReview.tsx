import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { approveSkillIntegration, prepareSkillWithdrawal, skillReviewErrorMessage } from "@/features/market-demand/api";
import { isUsablePostingUrl } from "@/features/market-demand/selection";
import { EvidenceLink } from "@/features/market-demand/components/SkillEvidencePanel";
import type { SkillReview } from "@/features/market-demand/types";

interface Props {
  courseId: number;
  review: SkillReview;
  onReviewChange: (review: SkillReview) => void;
  disabled?: boolean;
  publicationDisabled?: boolean;
}

export function IntegrationReview({courseId, review, onReviewChange, disabled, publicationDisabled}: Props) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const flight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const generation = useRef(0);
  const [incoming, setIncoming] = useState(review);
  const [acknowledged, setAcknowledged] = useState<SkillReview | null>(null);
  if (incoming !== review) {
    setIncoming(review);
    setBusy(false);
    flight.current = false;
    setError(null);
    if (review !== acknowledged) setSuccess(null);
  }
  useEffect(() => {
    generation.current += 1;
    return () => { generation.current += 1; };
  }, [courseId, review]);
  const proposal = review.integration_review;
  const hasOffering = !!review.run_id && review.approved_references.length > 0;
  const withdrawal = proposal?.withdrawal === true;
  const ids = proposal?.items.map(item => item.candidate_id) ?? [];
  const missing = proposal?.items.filter(item => {
    const candidate = review.candidates.find(value => value.candidate_id === item.candidate_id);
    return candidate?.posting_support !== "supported" || !candidate.qualifying_posting_links.some(isUsablePostingUrl) || !item.qualifying_posting_links.some(isUsablePostingUrl) || !item.evidence_snapshot_ids.length;
  }) ?? [];
  const current = !!proposal && proposal.candidate_revision === review.candidate_revision &&
    proposal.selection_revision === review.selection_revision && !!proposal.review_digest &&
    (withdrawal ? ids.length === 0 : new Set(ids).size === ids.length && ids.length === review.selected_candidate_ids.length && ids.every(id => review.selected_candidate_ids.includes(id)));
  const canApprove = !!review.run_id && !!proposal && current && (withdrawal ? hasOffering : !publicationDisabled && ids.length > 0 && !missing.length &&
    (!proposal.omissions.length || proposal.omissions_acknowledged));
  const prepare = async () => {
    if (!hasOffering || disabled || busy || !review.run_id) return;
    flight.current = true;
    const request = ++generation.current;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await prepareSkillWithdrawal(courseId, {
        run_id: review.run_id,
        expected_candidate_revision: review.candidate_revision,
        expected_selection_revision: review.selection_revision,
      });
      if (request !== generation.current) return;
      setAcknowledged(response);
      onReviewChange(response);
    } catch (cause) {
      if (request === generation.current) setError(skillReviewErrorMessage(cause, "Withdrawal preparation failed"));
    } finally {
      if (request === generation.current) {flight.current = false; setBusy(false);}
    }
  };
  const approve = async () => {
    if (flight.current || !canApprove || disabled || busy || !review.run_id || !proposal) return;
    flight.current = true;
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
      setSuccess(withdrawal
        ? response.projection_status === "projected" ? "Withdrawal saved; removal projected" : response.projection_status === "error" ? "Withdrawal saved; projection failed" : "Withdrawal saved; removal waiting for projection"
        : response.projection_status === "projected" ? "Approval saved; publication projected" : response.projection_status === "error" ? "Approval saved; projection failed" : "Approval saved; publication waiting for projection");
    } catch (cause) {
      if (request === generation.current) setError(skillReviewErrorMessage(cause, withdrawal ? "Withdrawal approval failed" : "Integration approval failed"));
    } finally {
      if (request === generation.current) {flight.current = false; setBusy(false);}
    }
  };
  if (!proposal && !hasOffering) return success ? <p role="status" className="text-xs">{success}</p> : null;
  return (
    <section className="space-y-2 text-sm" aria-label="Final integration review">
      {proposal && <p>Do these skills fit the proposed chapters?</p>}
      {hasOffering && <details className="text-xs"><summary>Published offering and withdrawal</summary>
        <p className="text-xs text-muted-foreground">Withdrawal stops this analysis's offering from authorizing new selections. Saved learning paths and resources are preserved. Other approvals can keep a skill available.</p>
        <Button size="sm" variant="outline" disabled={disabled || busy} onClick={() => void prepare()}>Prepare withdrawal</Button>
        {review.approved_references.map(item=><p key={item.reference_id}>{item.label}</p>)}
      </details>}
      {proposal && <>
      <p className="text-xs text-muted-foreground">{withdrawal ? "Review withdrawal of the current offering before confirming removal." : "Review the exact targets and chapter relationships before publishing. Draft changes leave the previous offering available."}</p>
      <ul aria-label="Curriculum targets" className="space-y-1">{proposal.items.slice(0,5).map((item,index) => <li key={`${item.candidate_id}:${index}`} className="rounded-md border px-3 py-2"><p className="truncate font-medium">{item.target.label}</p><p className="truncate text-xs">{item.chapters.map(chapter=>chapter.title).join(", ") || "No chapter relationship"}</p></li>)}</ul>
      <Button size="sm" variant="outline" onClick={()=>{setPage(1);setOpen(true);}}>{proposal.items.length > 5 ? `Review all ${proposal.items.length}` : "Review target details"}</Button>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent className="max-h-[85dvh] overflow-y-auto" maxWidthClassName="sm:max-w-2xl"><DialogHeader><DialogTitle>Curriculum fit details</DialogTitle><DialogDescription>Exact targets, chapter relationships and original supporting postings.</DialogDescription></DialogHeader>
      {proposal.items.slice((page - 1) * 10, page * 10).map((item,index) => (
        <div key={`${item.candidate_id}:${index}`} className="space-y-1 rounded-md border p-2">
          <p className="font-medium">{item.target.label}</p>
          <p className="text-xs">{item.disposition} · {item.target.source} · {item.target.origin} · target {item.target.identity}</p>
          <p className="text-xs">Chapters: {item.chapters.map(chapter => chapter.title).join(", ") || "No chapter relationship"}</p>
          {!!item.concepts?.length && <div className="space-y-1 text-xs">
            <p className="font-medium">Proposed concepts</p>
            {item.concepts.map((concept, index) => <div key={index}>
              <p>{concept.name}</p>
              {concept.description !== null && <p>{concept.description}</p>}
            </div>)}
          </div>}
          {item.qualifying_posting_links.map(url => <p key={url} className="text-xs"><EvidenceLink url={url} label="Original job posting"/></p>)}
          {missing.some(value => value.candidate_id === item.candidate_id) && <p className="text-xs text-destructive">Needs supporting job posting</p>}
        </div>
      ))}
      <div className="flex justify-between"><Button size="sm" disabled={page===1} onClick={()=>setPage(page-1)}>Previous page</Button><span>Page {page} of {Math.max(1,Math.ceil(proposal.items.length/10))}</span><Button size="sm" disabled={page*10>=proposal.items.length} onClick={()=>setPage(page+1)}>Next page</Button></div>
      </DialogContent></Dialog>
      {!!missing.length && <p role="alert" className="text-xs text-destructive">Needs supporting job posting for {missing.length} curriculum targets. Review target details before approval.</p>}
      {proposal.omissions.map((omission, index) => <p key={index} className="text-xs">{omission}</p>)}
      {!current && <p className="text-xs text-destructive">{withdrawal ? "Review revisions changed or withdrawal review is invalid. Prepare withdrawal again." : "Review revisions changed. Confirm the current selection for a new mapping review."}</p>}
      {!withdrawal && !!proposal.omissions.length && !proposal.omissions_acknowledged && <p className="text-xs text-destructive">Acknowledge the current evidence omissions before approval.</p>}
      <Button size="sm" disabled={!canApprove || disabled || busy || !!success} onClick={() => void approve()}>{busy ? "Approving…" : withdrawal ? "Withdraw approval" : "Approve and publish"}</Button>
      </>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {success && <p role="status">{success}</p>}
    </section>
  );
}
