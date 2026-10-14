import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { categorySelectionState, jobBackedCandidates } from "@/features/market-demand/selection";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";

export function SkillSelectionCard({controller, onConfirm, onInspect, disabled}: {
  controller: SkillReviewController;
  onConfirm: () => void;
  onInspect: (id: string, element: HTMLElement) => void;
  disabled?: boolean;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [pages, setPages] = useState<Record<string, number>>({});
  const {review, draft} = controller;
  if (!review) return null;
  const eligible = jobBackedCandidates(review);
  const eligibleIds = new Set(eligible.map(item => item.candidate_id));
  const selected = new Set(draft.selected_candidate_ids);
  const unsupported = draft.selected_candidate_ids.filter(id => !eligibleIds.has(id));
  const locked = disabled || controller.disabled || controller.busy;
  const omissions = review.evidence_omissions ?? [];
  const changed = controller.reviewRequired || review.reconciliations?.some(item => !item.resolved);
  const limited = omissions.length > 0 || controller.needsEvidenceAcknowledgement;
  const categories = [...review.categories];
  for (const candidate of eligible) {
    if (!categories.some(category => category.category_id === candidate.category_id)) {
      categories.push({category_id: candidate.category_id, label: candidate.category_id.replaceAll("_", " ")});
    }
  }
  return <section aria-label="Choose skills" className="w-full space-y-3 rounded-lg border bg-card p-3">
    <div><h2 className="text-sm font-semibold">Select Skills</h2><p className="text-xs text-muted-foreground">Choose categories to map against your curriculum. Expand a category to adjust individual skills.</p></div>
    <p className="text-xs text-muted-foreground">{selected.size} selected · {eligible.length} skills supported by job postings</p>
    {unsupported.length > 0 && <div role="alert" className="space-y-2 text-sm">
      <p>These saved choices were removed or lack supporting job postings. Remove them and choose a current replacement.</p>
      {unsupported.map(id => <div key={id} className="flex items-center justify-between gap-2 rounded-md border px-2 py-1">
        <span className="min-w-0 break-words">{review.candidates.find(item => item.candidate_id === id)?.display_name ??
          review.reconciliations?.flatMap(item => item.previous_candidates).find(item => item.candidate_id === id)?.display_name ?? id}</span>
        <Button size="sm" variant="ghost" disabled={locked} aria-label={`Remove unsupported ${id}`} onClick={() => controller.setCandidate(id, false)}>Remove</Button>
      </div>)}
    </div>}
    <div className="space-y-2">{categories.map(category => {
      const members = eligible.filter(candidate => candidate.category_id === category.category_id);
      if (!members.length) return null;
      const ids = members.map(candidate => candidate.candidate_id);
      const open = expanded.includes(category.category_id);
      const totalPages = Math.max(1, Math.ceil(members.length / 10));
      const page = Math.min(pages[category.category_id] ?? 1, totalPages);
      return <div key={category.category_id} className="rounded-md border">
        <div className="flex items-center gap-2 px-3 py-2">
          <Checkbox aria-label={`Select category ${category.label} (${ids.length} current members)`}
            checked={categorySelectionState(ids, draft.selected_candidate_ids)} disabled={locked}
            onCheckedChange={checked => controller.setCategory(category.category_id, checked === true)}/>
          <button type="button" aria-label={`${open ? "Collapse" : "Expand"} ${category.label}`} aria-expanded={open}
            className="flex min-w-0 flex-1 items-center justify-between gap-2 text-left text-sm"
            onClick={() => setExpanded(open ? expanded.filter(id => id !== category.category_id) : [...expanded, category.category_id])}>
            <span className="min-w-0 break-words">{category.label} <span className="text-xs text-muted-foreground">({ids.filter(id => selected.has(id)).length}/{ids.length})</span></span>
            {open ? <ChevronDown className="size-4 shrink-0"/> : <ChevronRight className="size-4 shrink-0"/>}
          </button>
        </div>
        {open && <div className="space-y-1 border-t px-3 py-2">
          {members.slice((page - 1) * 10, page * 10).map(candidate => <div key={candidate.candidate_id} className="flex items-center gap-2 py-1">
            <label className="flex min-w-0 flex-1 items-center gap-2 text-sm">
              <Checkbox aria-label={`Select ${candidate.display_name}`} checked={selected.has(candidate.candidate_id)} disabled={locked}
                onCheckedChange={checked => controller.setCandidate(candidate.candidate_id, checked === true)}/>
              <span className="min-w-0 break-words">{candidate.display_name}</span>
            </label>
            <Button size="sm" variant="ghost" className="shrink-0" aria-label={`Inspect ${candidate.display_name}`}
              onClick={event => onInspect(candidate.candidate_id, event.currentTarget)}>{candidate.job_metrics.supporting_posting_count ?? 0} jobs ›</Button>
          </div>)}
          {totalPages > 1 && <div className="flex items-center justify-between gap-2 pt-2 text-xs">
            <Button size="sm" variant="outline" aria-label={`Previous ${category.label} page`} disabled={page === 1}
              onClick={() => setPages({...pages, [category.category_id]: page - 1})}>Previous</Button>
            <span>Page {page} of {totalPages}</span>
            <Button size="sm" variant="outline" aria-label={`Next ${category.label} page`} disabled={page === totalPages}
              onClick={() => setPages({...pages, [category.category_id]: page + 1})}>Next</Button>
          </div>}
        </div>}
      </div>;
    })}</div>
    {(limited || changed) && <div className="space-y-1 text-xs text-muted-foreground">
      <p>{limited ? "Some job evidence is incomplete. " : ""}{changed ? "Some choices were merged or changed. " : ""}Confirm Selection saves these current choices and accepts the displayed evidence limitations for mapping.</p>
      <details><summary className="cursor-pointer">Evidence and changed choice details</summary>
        {omissions.map((item, index) => <p key={index} className="mt-1">{item}</p>)}
        {limited && !omissions.length && <p className="mt-1">{review.extraction_coverage.assessed_postings ?? "Unknown"} of {review.extraction_coverage.selected_postings ?? "unknown"} selected postings assessed.</p>}
        {controller.reconciliation && <p className="mt-1">{controller.reconciliation}</p>}
        {review.reconciliations?.filter(item => !item.resolved).map(item => <p key={item.reconciliation_id} className="mt-1">{item.previous_candidates.map(value => value.display_name).join(", ")} · {item.reason.replaceAll("_", " ")}</p>)}
      </details>
    </div>}
    <Button size="sm" className="w-full" disabled={locked || !selected.size || unsupported.length > 0} onClick={onConfirm}>Confirm Selection{selected.size > 0 ? ` (${selected.size})` : ""}</Button>
  </section>;
}
