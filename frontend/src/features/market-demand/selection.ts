import type { RecommendationProposal, SkillCandidate, SkillReview } from "@/features/market-demand/types";

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
