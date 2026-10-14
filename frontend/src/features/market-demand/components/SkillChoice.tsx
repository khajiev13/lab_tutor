import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import { categorySelectionState, jobBackedCandidates } from "@/features/market-demand/selection";
import type { SkillCandidate } from "@/features/market-demand/types";

export function SkillChoice({controller, onInspect, secondaryAction}: {
  controller: SkillReviewController;
  onInspect: (candidateId: string) => void;
  secondaryAction?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const {review, draft, view} = controller;
  if (!review) return null;
  const locked = controller.disabled || controller.busy;
  const eligible = jobBackedCandidates(review);
  const eligibleIds = new Set(eligible.map(candidate => candidate.candidate_id));
  const selected = new Set(draft.selected_candidate_ids);
  const unsupported = review.candidates.filter(candidate => selected.has(candidate.candidate_id) && !eligibleIds.has(candidate.candidate_id));
  const proposals = review.recommendations.flatMap(proposal => proposal.changes.map(change => ({proposal, change})));
  const proposedIds = new Set(proposals.map(({change}) => change.candidate_id));
  const compare = (a: SkillCandidate, b: SkillCandidate) => a.display_name.localeCompare(b.display_name) || a.candidate_id.localeCompare(b.candidate_id);
  const mainRows = [...unsupported.sort(compare), ...review.candidates.filter(candidate => selected.has(candidate.candidate_id) && eligibleIds.has(candidate.candidate_id)).sort(compare),
    ...review.candidates.filter(candidate => !selected.has(candidate.candidate_id) && proposedIds.has(candidate.candidate_id)).sort(compare)];
  const query = view.filters.search.trim().toLowerCase();
  const matches = (candidate: SkillCandidate) => `${candidate.display_name} ${candidate.aliases.join(" ")}`.toLowerCase().includes(query);
  const filtered = eligible.filter(matches);
  const pages = Math.max(1, Math.ceil(filtered.length / 10));
  const page = Math.min(Math.max(1, view.page), pages);
  const rows = filtered.slice((page - 1) * 10, page * 10);
  const referenceProposals = review.candidates.filter(candidate => !eligibleIds.has(candidate.candidate_id) && proposedIds.has(candidate.candidate_id) && !selected.has(candidate.candidate_id)).filter(matches).sort(compare);
  const proposalActions = (candidate: SkillCandidate) => proposals.filter(({change}) => change.candidate_id === candidate.candidate_id).map(({proposal, change}, index) => {
    const current = proposal.candidate_revision === review.candidate_revision && proposal.base_selection_revision === review.selection_revision;
    const excluded = change.action === "add" && draft.excluded_candidate_ids.includes(candidate.candidate_id);
    const unsupportedAdd = change.action === "add" && !eligibleIds.has(candidate.candidate_id);
    return <div key={`${proposal.id}:${index}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <span>Proposal: {change.action} · {change.reason}</span>
      {excluded && <span>Explicit exclusion protected</span>}
      {unsupportedAdd && <span>Needs supporting job posting</span>}
      {!current && <span>Proposal is stale; request current advice</span>}
      <Button size="sm" variant="outline" disabled={locked || !current || excluded || unsupportedAdd}
        aria-label={`Apply proposal for ${candidate.display_name}`}
        onClick={() => controller.applyProposal(proposal.id, [candidate.candidate_id])}>Apply</Button>
    </div>;
  });
  const skillRow = (candidate: SkillCandidate, checklist: boolean) => <div className="flex flex-wrap items-center justify-between gap-2">
    <div className="min-w-0 flex-1 space-y-1">
      {checklist ? <label className="flex items-center gap-2 text-sm">
        <Checkbox aria-label={`Select ${candidate.display_name}`} checked={selected.has(candidate.candidate_id)} disabled={locked}
          onCheckedChange={checked => controller.setCandidate(candidate.candidate_id, checked === true)}/>
        {candidate.display_name}
      </label> : <p className="text-sm font-medium">{candidate.display_name} {selected.has(candidate.candidate_id) && <span className="font-normal text-muted-foreground">· chosen</span>}</p>}
      {selected.has(candidate.candidate_id) && !eligibleIds.has(candidate.candidate_id) && <p className="text-xs text-destructive">Needs supporting job posting; remove this choice before continuing.</p>}
      {proposalActions(candidate)}
    </div>
    <div className="flex gap-1">
      <Button size="sm" variant="ghost" aria-label={`Inspect ${candidate.display_name}`} onClick={() => {setOpen(false); onInspect(candidate.candidate_id);}}>{candidate.job_metrics.supporting_posting_count ?? 0} jobs ›</Button>
      {!checklist && selected.has(candidate.candidate_id) && <Button size="sm" variant="ghost" disabled={locked}
        aria-label={`Remove ${candidate.display_name}`} onClick={() => controller.setCandidate(candidate.candidate_id, false)}>Remove</Button>}
    </div>
  </div>;
  return <section aria-label="Choose skills" className="space-y-2">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm">Which skills belong in this course?</p>
      <span className="text-xs text-muted-foreground">{draft.selected_candidate_ids.length} chosen · {eligible.length} job-backed skills</span>
    </div>
    {unsupported.length > 0 && <p role="alert" className="text-sm text-destructive">Review required: {unsupported.slice(0, 5).map(candidate => candidate.display_name).join(", ")}{unsupported.length > 5 ? ` and ${unsupported.length - 5} more saved choices` : ""} lost supporting job evidence. Remove these saved choices before continuing.</p>}
    {controller.reviewRequired && unsupported.length === 0 && <div className="space-y-2 text-sm">
      <p role="alert">Review required: {controller.reconciliation || "The saved review changed. Check your retained choices before continuing."}</p>
      <Button size="sm" variant="outline" disabled={locked} onClick={controller.acknowledgeIncomingReview}>I reviewed the changed choices</Button>
    </div>}
    {mainRows.length > 0 ? <ul className="space-y-1">{mainRows.slice(0, 5).map(candidate => <li key={candidate.candidate_id} className="rounded-md border px-3 py-1">{skillRow(candidate, false)}</li>)}</ul> : <p className="text-sm text-muted-foreground">No skills chosen yet</p>}
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button size="sm" variant="outline" disabled={controller.disabled}>
        {draft.selected_candidate_ids.length > 5 ? `Review all ${draft.selected_candidate_ids.length}` : mainRows.length > 5 ? `Review all ${mainRows.length} chosen or proposed skills` : "Browse skills"}
      </Button></DialogTrigger>
      <DialogContent className="max-h-[85dvh] overflow-y-auto" maxWidthClassName="sm:max-w-2xl">
        <DialogHeader><DialogTitle>Browse skills</DialogTitle><DialogDescription>Choose from {eligible.length} job-backed skills. Category checkboxes include every current member, across search and pages. Proposals require an explicit Apply.</DialogDescription></DialogHeader>
        <Input aria-label="Search skills" placeholder="Search skills" value={view.filters.search}
          onChange={event => controller.updateView({page: 1, filters: {...view.filters, search: event.target.value}})}/>
        <div className="flex flex-wrap gap-3">{review.categories.map(category => {
          const ids = eligible.filter(candidate => candidate.category_id === category.category_id).map(candidate => candidate.candidate_id);
          if (!ids.length) return null;
          return <label key={category.category_id} className="flex items-center gap-2 text-sm">
            <Checkbox aria-label={`Select category ${category.label} (${ids.length} current members)`}
              checked={categorySelectionState(ids, draft.selected_candidate_ids)} disabled={locked}
              onCheckedChange={checked => controller.setCategory(category.category_id, checked === true)}/>
            {category.label} ({ids.filter(id => selected.has(id)).length}/{ids.length})
          </label>;
        })}</div>
        {unsupported.length > 0 && <div className="space-y-2 rounded-md border border-destructive p-3"><p className="font-medium">Saved choices requiring review</p>{unsupported.map(candidate => <div key={candidate.candidate_id}>{skillRow(candidate, false)}</div>)}</div>}
        <div className="space-y-2">{rows.map(candidate => <div key={candidate.candidate_id} className="rounded-md border px-3 py-1">{skillRow(candidate, true)}</div>)}
          {!rows.length && <p className="text-sm">No matching job-backed skills. Category selection still includes every current member.</p>}
        </div>
        <div className="flex items-center justify-between gap-2">
          <Button size="sm" variant="outline" disabled={page === 1} onClick={() => controller.updateView({page: page - 1})}>Previous page</Button>
          <span className="text-xs">Page {page} of {pages} · {filtered.length} matching skills</span>
          <Button size="sm" variant="outline" disabled={page === pages} onClick={() => controller.updateView({page: page + 1})}>Next page</Button>
        </div>
        {referenceProposals.length > 0 && <div className="space-y-2 rounded-md border p-3"><p className="text-sm font-medium">Proposals needing job evidence ({referenceProposals.length})</p>
          {referenceProposals.map(candidate => <div key={candidate.candidate_id}>{skillRow(candidate, false)}</div>)}
        </div>}
      </DialogContent>
    </Dialog>
    {controller.error && <p role="alert" className="text-sm text-destructive">{controller.error} · Local choices retained.</p>}
    {controller.success && <p role="status" className="text-sm">{controller.success}</p>}
    <div className="ml-2 inline-flex flex-wrap gap-2">
      <Button size="sm" variant="outline" disabled={locked || !controller.canUndo} onClick={controller.undo}>Undo local change</Button>
      <Button size="sm" variant="ghost" disabled={locked || !controller.dirty || controller.reviewRequired}
        onClick={() => void controller.save().catch(() => {})}>Save draft</Button>
      {secondaryAction}
    </div>
  </section>;
}
