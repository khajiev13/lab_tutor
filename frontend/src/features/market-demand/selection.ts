import type { CandidatePriority, CategoryPriority, RecommendationProposal, SkillCandidate, SkillReview } from "@/features/market-demand/types";

export interface SelectionDraft {
  selected_candidate_ids: string[];
  excluded_candidate_ids: string[];
}

export function categorySelectionState(memberIds: string[], selectedIds: string[]): boolean | "indeterminate" {
  const selected = new Set(selectedIds);
  const count = memberIds.filter(id => selected.has(id)).length;
  if (count === 0) return false;
  return count === memberIds.length ? true : "indeterminate";
}

export function applyCategorySelection(draft: SelectionDraft, memberIds: string[], checked: boolean): SelectionDraft {
  const members = new Set(memberIds);
  return {
    selected_candidate_ids: checked
      ? [...new Set([...draft.selected_candidate_ids, ...memberIds])]
      : draft.selected_candidate_ids.filter(id => !members.has(id)),
    excluded_candidate_ids: checked
      ? draft.excluded_candidate_ids.filter(id => !members.has(id))
      : [...new Set([...draft.excluded_candidate_ids, ...memberIds])],
  };
}

export function applyIndividualSelection(draft: SelectionDraft, id: string, checked: boolean): SelectionDraft {
  return applyCategorySelection(draft, [id], checked);
}

export function applyRecommendationChanges(draft: SelectionDraft, changes: RecommendationProposal["changes"], chosenIds: string[]): SelectionDraft {
  const chosen = new Set(chosenIds);
  return changes.reduce((current, change) => {
    if (!chosen.has(change.candidate_id)) return current;
    if (change.action === "add" && current.excluded_candidate_ids.includes(change.candidate_id)) return current;
    return applyIndividualSelection(current, change.candidate_id, change.action === "add");
  }, draft);
}

export function reconcileDraft(draft: SelectionDraft, candidateIds: string[]) {
  const current = new Set(candidateIds);
  return {
    draft: {
      selected_candidate_ids: draft.selected_candidate_ids.filter(id => current.has(id)),
      excluded_candidate_ids: draft.excluded_candidate_ids.filter(id => current.has(id)),
    },
    removed_ids: [...new Set([...draft.selected_candidate_ids, ...draft.excluded_candidate_ids])].filter(id => !current.has(id)),
  };
}

export function isUsablePostingUrl(value: string): boolean {
  if (!/^https?:\/\/[^/\\]/i.test(value)) return false;
  try {
    const url = new URL(value);
    return (url.protocol === "https:" || url.protocol === "http:") && !!url.hostname && !url.username && !url.password;
  } catch {
    return false;
  }
}

export function jobBackedCandidates(review: SkillReview): SkillCandidate[] {
  return review.candidates.filter(candidate => candidate.posting_support === "supported" &&
    candidate.qualifying_posting_links.some(isUsablePostingUrl))
    .sort((a, b) => a.display_name.localeCompare(b.display_name) || a.candidate_id.localeCompare(b.candidate_id));
}

export function priorityLabel(priority: CandidatePriority | CategoryPriority | null | undefined): string | null {
  if (!priority) return null;
  if (priority.basis === "unavailable" || priority.value === null) return "Not assessed";
  const category = "eligible_count" in priority;
  const source = category
    ? priority.basis === "ai_estimate" ? priority.complete ? "Estimated" : "Estimate" : "O*NET average"
    : priority.basis === "onet" ? "O*NET" : priority.basis === "onet_aggregate" ? "O*NET average" : "AI estimate";
  return `${Number(priority.value.toFixed(1))}/5 · ${source}${priority.complete ? "" : " · Partial"}`;
}

export function currentPriorityAssessment(review: SkillReview) {
  const assessment = review.priority_assessment;
  return assessment && assessment.status !== "stale" && assessment.run_id === review.run_id &&
    assessment.candidate_revision === review.candidate_revision ? assessment : null;
}

export function priorityOrder(review: SkillReview): {categoryIds: string[]; candidateIdsByCategory: Record<string, string[]>} {
  const eligible = jobBackedCandidates(review);
  const categories = [...review.categories];
  for (const candidate of eligible) {
    if (!categories.some(category => category.category_id === candidate.category_id)) {
      categories.push({category_id: candidate.category_id, label: candidate.category_id.replaceAll("_", " ")});
    }
  }
  const assessed = !!currentPriorityAssessment(review);
  const saved = new Set(eligible.filter(item => review.selected_candidate_ids.includes(item.candidate_id)).map(item => item.category_id));
  categories.sort((a, b) => assessed
    ? (a.priority?.display_order ?? Infinity) - (b.priority?.display_order ?? Infinity)
    : Number(saved.has(b.category_id)) - Number(saved.has(a.category_id)));
  return {categoryIds: categories.map(item => item.category_id), candidateIdsByCategory: Object.fromEntries(categories.map(category => {
    const members = eligible.filter(item => item.category_id === category.category_id);
    if (assessed) members.sort((a, b) => (a.priority?.display_order ?? Infinity) - (b.priority?.display_order ?? Infinity));
    return [category.category_id, members.map(item => item.candidate_id)];
  }))};
}
