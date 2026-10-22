import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { categorySelectionState, currentPriorityAssessment, jobBackedCandidates, priorityLabel, priorityOrder } from "@/features/market-demand/selection";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";

export function SkillSelectionCard({controller, onConfirm, onInspect, disabled, confirmDisabled = false, browse = false}: {
  controller: SkillReviewController;
  onConfirm: () => void;
  onInspect: (id: string, element: HTMLElement) => void;
  disabled?: boolean;
  confirmDisabled?: boolean;
  browse?: boolean;
}) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [pages, setPages] = useState<Record<string, number>>({});
  const {review, draft} = controller;
  const key = review ? JSON.stringify([review.run_id, review.candidate_revision]) : "";
  const [sessionOrder, setSessionOrder] = useState(() => ({key, order: review ? priorityOrder(review) : null}));
  if (sessionOrder.key !== key) setSessionOrder({key, order: review ? priorityOrder(review) : null});
  if (!review) return null;
  const assessment = currentPriorityAssessment(review);
  const order = sessionOrder.key === key ? sessionOrder.order! : priorityOrder(review);
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
  categories.sort((a, b) => order.categoryIds.indexOf(a.category_id) - order.categoryIds.indexOf(b.category_id));
  const showCategories = browse || review.selected_candidate_ids.length === 0;
  const chosen = draft.selected_candidate_ids.flatMap(id => eligible.find(item => item.candidate_id === id) ?? []);
  const assessedCount = assessment ? eligible.filter(item => item.priority?.value != null).length : 0;
  const label = (priority: typeof eligible[number]["priority"]) => assessment && priority?.value != null ? priorityLabel(priority) : null;
  return <section aria-label={browse ? "Browse all skills" : "Choose skills"} className="flex min-h-0 w-full flex-col gap-1.5 rounded-lg border bg-card p-2.5">
    {browse && <h2 className="shrink-0 text-sm font-semibold">All skills</h2>}
    <p className="shrink-0 text-xs text-muted-foreground">{selected.size} selected · {eligible.length} skills from jobs</p>
    {controller.dirty && <p aria-live="polite" className="text-xs text-muted-foreground">Changes are not saved until you confirm.</p>}
    {assessment && <p className="text-xs text-muted-foreground">Importance guidance available for {assessedCount} of {eligible.length} skills. {assessment.status === "running" ? "Assessment is still running." : assessedCount < eligible.length && "Other skills have no reliable rating."}</p>}
    {!showCategories && <div className="space-y-1">
      {chosen.slice(0, 5).map((candidate, index) => <div key={candidate.candidate_id} className={index >= 3 ? "hidden items-center gap-2 sm:flex" : "flex items-center gap-2"}>
        <label className="flex min-w-0 flex-1 items-center gap-2 text-sm">
          <Checkbox aria-label={`Select ${candidate.display_name}`} checked disabled={locked} onCheckedChange={checked => controller.setCandidate(candidate.candidate_id, checked === true)}/>
          <span className="min-w-0 break-words">{candidate.display_name}{label(candidate.priority) && <span className="ml-2 text-xs text-muted-foreground">{label(candidate.priority)}</span>}</span>
        </label>
        <Button size="sm" variant="ghost" className="h-7 shrink-0" aria-label={`Inspect ${candidate.display_name}`} onClick={event => onInspect(candidate.candidate_id, event.currentTarget)}>{candidate.job_metrics.supporting_posting_count ?? 0} jobs ›</Button>
      </div>)}
      {chosen.length > 3 && <p className="text-xs text-muted-foreground sm:hidden">{chosen.length - 3} more selected · see Skills &amp; chart.</p>}
      {chosen.length > 5 && <p className="hidden text-xs text-muted-foreground sm:block">{chosen.length - 5} more selected · see Skills &amp; chart.</p>}
    </div>}
    {(showCategories || unsupported.length > 0) && <div role="region" aria-label="Skill categories and saved choices" tabIndex={0} className={showCategories ? "max-h-64 min-h-16 space-y-2 overflow-y-auto overscroll-contain" : "space-y-2"}>
    {unsupported.length > 0 && <div role="alert" className="space-y-2 text-sm">
      <p>These saved choices were removed or lack supporting job postings. Remove them and choose a current replacement.</p>
      {unsupported.map(id => <div key={id} className="flex items-center justify-between gap-2 rounded-md border px-2 py-1">
        <span className="min-w-0 break-words">{review.candidates.find(item => item.candidate_id === id)?.display_name ??
          review.reconciliations?.flatMap(item => item.previous_candidates).find(item => item.candidate_id === id)?.display_name ?? id}</span>
        <Button size="sm" variant="ghost" disabled={locked} aria-label={`Remove unsupported ${id}`} onClick={() => controller.setCandidate(id, false)}>Remove</Button>
      </div>)}
    </div>}
    {showCategories && <div className="space-y-2">{categories.map(category => {
      const memberOrder = order.candidateIdsByCategory[category.category_id] ?? [];
      const members = eligible.filter(candidate => candidate.category_id === category.category_id)
        .sort((a, b) => memberOrder.indexOf(a.candidate_id) - memberOrder.indexOf(b.candidate_id));
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
            <span className="min-w-0 break-words">{category.label} <span className="text-xs text-muted-foreground">({ids.filter(id => selected.has(id)).length}/{ids.length})</span>
              {assessment && category.priority?.value != null && priorityLabel(category.priority) && <span className="block text-xs font-normal text-muted-foreground sm:inline sm:pl-2">{priorityLabel(category.priority)}</span>}</span>
            {open ? <ChevronDown className="size-4 shrink-0"/> : <ChevronRight className="size-4 shrink-0"/>}
          </button>
        </div>
        {open && <div className="space-y-1 border-t px-3 py-2">
          {members.slice((page - 1) * 10, page * 10).map(candidate => <div key={candidate.candidate_id} className="flex items-center gap-2 py-1">
            <label className="flex min-w-0 flex-1 items-center gap-2 text-sm">
              <Checkbox aria-label={`Select ${candidate.display_name}`} checked={selected.has(candidate.candidate_id)} disabled={locked}
                onCheckedChange={checked => controller.setCandidate(candidate.candidate_id, checked === true)}/>
              <span className="min-w-0 break-words">{candidate.display_name}
                {label(candidate.priority) && <span className="block text-xs text-muted-foreground sm:inline sm:pl-2">{label(candidate.priority)}</span>}</span>
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
    })}</div>}
    </div>}
    {(limited || changed) && <div className="shrink-0 text-xs text-muted-foreground">
      <p>{limited ? "Incomplete job evidence. " : ""}{changed ? "Changed choices. " : ""}Confirm Selection saves your choices and accepts stated evidence limitations.</p>
      <details><summary className="cursor-pointer">Evidence and changed choice details</summary>
        <div role="region" aria-label="Evidence limitations and changed choice details" tabIndex={0} className="max-h-10 overflow-y-auto overscroll-contain sm:max-h-24">
        {omissions.map((item, index) => <p key={index} className="mt-1">{item}</p>)}
        {limited && !omissions.length && <p className="mt-1">{review.extraction_coverage.assessed_postings ?? "Unknown"} of {review.extraction_coverage.selected_postings ?? "unknown"} selected postings assessed.</p>}
        {controller.reconciliation && <p className="mt-1">{controller.reconciliation}</p>}
        {review.reconciliations?.filter(item => !item.resolved).map(item => <p key={item.reconciliation_id} className="mt-1">{item.previous_candidates.map(value => value.display_name).join(", ")} · {item.reason.replaceAll("_", " ")}</p>)}
        </div>
      </details>
    </div>}
    {!browse && <Button size="sm" className="sticky bottom-0 z-10 w-full shrink-0" disabled={locked || confirmDisabled || !selected.size || unsupported.length > 0} onClick={onConfirm}>Confirm Selection{selected.size > 0 ? ` (${selected.size})` : ""}</Button>}
  </section>;
}
