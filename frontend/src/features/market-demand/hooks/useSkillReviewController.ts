import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { confirmSkillReviewSelection, continueWithAvailableEvidence, saveSkillReviewDraft, skillReviewErrorMessage } from "@/features/market-demand/api";
import { applyCategorySelection, applyIndividualSelection, applyRecommendationChanges, reconcileDraft, jobBackedCandidates } from "@/features/market-demand/selection";
import type { SelectionDraft } from "@/features/market-demand/selection";
import type { SkillReview, WorkspaceViewState } from "@/features/market-demand/types";

interface Options {
  courseId: number;
  review: SkillReview | null;
  onReviewChange: (review: SkillReview) => void;
  disabled?: boolean;
}

export interface SkillReviewController {
  review: SkillReview | null;
  draft: SelectionDraft;
  view: WorkspaceViewState;
  dirty: boolean;
  busy: boolean;
  disabled: boolean;
  reviewRequired: boolean;
  error: string | null;
  success: string | null;
  canUndo: boolean;
  reconciliation: string;
  pendingReconciliationIds: string[];
  needsEvidenceAcknowledgement: boolean;
  setCandidate: (id: string, checked: boolean) => void;
  setCategory: (id: string, checked: boolean) => void;
  applyProposal: (id: string, chosenIds?: string[]) => void;
  acknowledgeReconciliation: (id: string, checked?: boolean) => void;
  acknowledgeIncomingReview: () => void;
  updateView: (update: Partial<WorkspaceViewState>) => void;
  undo: () => void;
  save: () => Promise<SkillReview>;
  reviewMappings: () => Promise<SkillReview>;
  confirmCurrentSelection: () => Promise<SkillReview>;
  acknowledgeAvailableEvidence: () => Promise<SkillReview>;
  onReviewChange: (review: SkillReview) => void;
}

function sameDraft(a: SelectionDraft, b: SelectionDraft) {
  return a.selected_candidate_ids.length === b.selected_candidate_ids.length &&
    a.excluded_candidate_ids.length === b.excluded_candidate_ids.length &&
    a.selected_candidate_ids.every(id => b.selected_candidate_ids.includes(id)) &&
    a.excluded_candidate_ids.every(id => b.excluded_candidate_ids.includes(id));
}
function draftOf(review: SkillReview | null): SelectionDraft {
  return {selected_candidate_ids: review?.selected_candidate_ids ?? [], excluded_candidate_ids: review?.excluded_candidate_ids ?? []};
}
function hasUnsupportedSelection(review: SkillReview | null, draft: SelectionDraft) {
  const eligible = new Set(review ? jobBackedCandidates(review).map(item => item.candidate_id) : []);
  return draft.selected_candidate_ids.some(id => !eligible.has(id));
}
function sameRevision(a: SkillReview | null, b: SkillReview | null) {
  return a?.run_id === b?.run_id && a?.candidate_revision === b?.candidate_revision && a?.selection_revision === b?.selection_revision;
}
function needsEvidenceAcknowledgement(review: SkillReview | null) {
  return !!review && !review.extraction_coverage.acknowledged && (
    review.extraction_coverage.status === "partial" || review.extraction_coverage.status === "failed" ||
    Object.values(review.source_outcomes).some(item => item.status === "partial" || item.status === "error")
  );
}
function initialView(): WorkspaceViewState {
  return {view: "overview", filters: {category_ids: [], search: "", scope: "all"}, focusedCandidateId: null,
    occupationCodes: [], activeOccupationCode: null, metric: "frequency", descriptorChoices: [],
    sort: {field: "name", direction: "asc"}, page: 1};
}

export function useSkillReviewController({courseId, review, onReviewChange, disabled = false}: Options): SkillReviewController {
  const [model, setModel] = useState(() => ({courseId, incoming: review, snapshot: review, draft: draftOf(review),
    reconciliation: "", reconciliationIds: [] as string[], reviewRequired: false,
    undo: null as SelectionDraft | null, busy: false, error: null as string | null, success: null as string | null,
    view: initialView()}));
  const generation = useRef(0);
  const activeRequest = useRef<number | null>(null);
  const live = useRef({model, disabled, onReviewChange});

  if (model.incoming !== review || model.courseId !== courseId) {
    const sameRun = model.courseId === courseId && !!review && model.snapshot?.run_id === review.run_id;
    const same = sameRun && sameRevision(model.snapshot, review);
    const previousDirty = !sameDraft(model.draft, draftOf(model.snapshot)) || model.reconciliationIds.length > 0;
    const reconciled = reconcileDraft(model.draft, review?.candidates.map(item => item.candidate_id) ?? []);
    const names = reconciled.removed_ids.map(id => model.snapshot?.candidates.find(item => item.candidate_id === id)?.display_name ?? id);
    // New identities must be explicitly selected even if a refreshed snapshot suggests them.
    const knownIds = new Set(model.snapshot?.candidates.map(item => item.candidate_id));
    const serverDraft = draftOf(review);
    const nextDraft = sameRun && previousDirty ? {...reconciled.draft, selected_candidate_ids: model.draft.selected_candidate_ids} : sameRun ? {
      ...serverDraft, selected_candidate_ids: [...new Set([...serverDraft.selected_candidate_ids.filter(id => knownIds.has(id)),
        ...model.draft.selected_candidate_ids.filter(id => !review.candidates.some(item => item.candidate_id === id))])],
    } : serverDraft;
    const acknowledged = model.snapshot === review;
    setModel({...model, courseId, incoming: review, snapshot: review, draft: nextDraft,
      reconciliation: sameRun && names.length ? `Candidates removed or merged: ${names.join(", ")}. Review replacements explicitly; selections were not transferred.` : sameRun ? model.reconciliation : "",
      reconciliationIds: same ? model.reconciliationIds.filter(id => review?.reconciliations?.some(record => record.reconciliation_id === id && !record.resolved)) : [],
      reviewRequired: sameRun && (model.reviewRequired || (!same && previousDirty) || names.length > 0),
      undo: same ? model.undo : null, busy: same ? model.busy : false,
      error: same ? model.error : null, success: acknowledged ? model.success : null,
      view: sameRun ? model.view : initialView()});
  }

  useLayoutEffect(() => {
    if (live.current.model.courseId !== courseId || !sameRevision(live.current.model.snapshot, model.snapshot)) {
      generation.current += 1;
      activeRequest.current = null;
    }
    live.current = {model, disabled, onReviewChange};
  }, [courseId, model, disabled, onReviewChange]);
  useEffect(() => () => {generation.current += 1; activeRequest.current = null;}, []);

  const pendingReconciliationIds = model.reconciliationIds;
  const dirty = !sameDraft(model.draft, draftOf(model.snapshot)) || pendingReconciliationIds.length > 0;

  // Mirror the single model synchronously so batched and retained actions see
  // every preceding local operation, even before React commits another render.
  const writeModel = (update: (current: typeof model) => typeof model) => {
    const next = update(live.current.model);
    if (next === live.current.model) return;
    live.current = {...live.current, model: next};
    setModel(next);
  };
  const hasCurrentIdentity = () => live.current.model.courseId === courseId &&
    sameRevision(live.current.model.snapshot, model.snapshot);
  const updateLocal = (update: (current: typeof model) => typeof model, allowBusy = false) => {
    if (!hasCurrentIdentity()) return;
    if (!allowBusy && (live.current.disabled || live.current.model.busy || activeRequest.current !== null)) return;
    writeModel(update);
  };
  const mutate = (update: (current: typeof model) => SelectionDraft) => {
    updateLocal(current => {
      const next = update(current);
      return sameDraft(next, current.draft) ? current : {...current, draft: next, undo: current.draft, success: null, error: null};
    });
  };
  const revision = (snapshot: SkillReview) => ({run_id: snapshot.run_id!, expected_candidate_revision: snapshot.candidate_revision, expected_selection_revision: snapshot.selection_revision});

  const perform = async (action: "save" | "confirm" | "continue" | "confirm_current"): Promise<SkillReview> => {
    if (!hasCurrentIdentity()) throw new Error("Skill review changed; use the current review actions");
    const current = live.current.model;
    const requestDirty = !sameDraft(current.draft, draftOf(current.snapshot)) || current.reconciliationIds.length > 0;
    if (!current.snapshot?.run_id || live.current.disabled || activeRequest.current !== null) throw new Error("Skill review is unavailable or busy");
    if ((action !== "confirm_current" && current.reviewRequired) || (action !== "continue" && hasUnsupportedSelection(current.snapshot, current.draft))) throw new Error("Review changed choices or remove skills without supporting job postings before saving");
    if (action === "continue" && requestDirty) throw new Error("Save the draft before acknowledging evidence");
    const request = ++generation.current;
    activeRequest.current = request;
    writeModel(current => ({...current, busy: true, error: null, success: null}));
    const assertCurrent = () => {
      if (generation.current !== request) throw new Error("Skill review changed while the request was pending");
    };
    const accept = (response: SkillReview) => {
      assertCurrent();
      if (response.run_id !== current.snapshot!.run_id) throw new Error("Skill review response belongs to a different run");
      writeModel(current => ({...current, snapshot: response, draft: draftOf(response), reconciliationIds: [], reviewRequired: false, undo: null}));
      live.current.onReviewChange(response);
      return response;
    };
    let acknowledged = current.snapshot;
    try {
      if (action === "save" || (action === "confirm" && requestDirty)) {
        acknowledged = accept(await saveSkillReviewDraft(courseId, {...revision(acknowledged), ...current.draft,
          ...(current.reconciliationIds.length ? {resolved_reconciliation_ids: current.reconciliationIds} : {})}));
      }
      if (action === "confirm") {
        assertCurrent();
        if (hasUnsupportedSelection(acknowledged, draftOf(acknowledged)) || needsEvidenceAcknowledgement(acknowledged) || acknowledged.reconciliations?.some(record => !record.resolved) || !acknowledged.selected_candidate_ids.length) {
          throw new Error("Review reconciliation and evidence omissions before confirming a selection");
        }
        acknowledged = accept(await confirmSkillReviewSelection(courseId, revision(acknowledged)));
      }
      if (action === "confirm_current") {
        if (!current.draft.selected_candidate_ids.length) throw new Error("Choose at least one skill");
        const response = await confirmSkillReviewSelection(courseId, {...revision(acknowledged), ...current.draft,
          confirm_current_evidence: true, expected_omissions: acknowledged.evidence_omissions ?? []});
        assertCurrent();
        if (response.candidate_revision !== current.snapshot.candidate_revision || !sameDraft(draftOf(response), current.draft)) {
          throw new Error("The evidence or choices changed before confirmation. Refresh the current review and retry.");
        }
        acknowledged = accept(response);
      }
      if (action === "continue") acknowledged = accept(await continueWithAvailableEvidence(courseId, revision(acknowledged)));
      assertCurrent();
      writeModel(current => ({...current, success: action === "save" ? "Draft saved" : (action === "confirm" || action === "confirm_current") ? "Selection confirmed for mapping" : "Evidence omissions acknowledged; supporting postings are still required"}));
      return acknowledged;
    } catch (cause) {
      if (request === generation.current) writeModel(current => ({...current, error: skillReviewErrorMessage(cause, "Skill review request failed")}));
      throw cause;
    } finally {
      if (request === generation.current) {
        activeRequest.current = null;
        writeModel(current => ({...current, busy: false}));
      }
    }
  };

  return {
    review: model.snapshot, draft: model.draft, view: model.view, dirty, busy: model.busy, disabled,
    reviewRequired: model.reviewRequired || hasUnsupportedSelection(model.snapshot, model.draft), error: model.error, success: model.success, canUndo: !!model.undo,
    reconciliation: model.reconciliation, pendingReconciliationIds,
    needsEvidenceAcknowledgement: needsEvidenceAcknowledgement(model.snapshot),
    setCandidate: (id, checked) => mutate(current => {
      const exists = current.snapshot?.candidates.some(item => item.candidate_id === id);
      if (!exists) return !checked ? {selected_candidate_ids: current.draft.selected_candidate_ids.filter(item => item !== id),
        excluded_candidate_ids: current.draft.excluded_candidate_ids.filter(item => item !== id)} : current.draft;
      return !checked || jobBackedCandidates(current.snapshot!).some(item => item.candidate_id === id)
        ? applyIndividualSelection(current.draft, id, checked) : current.draft;
    }),
    setCategory: (id, checked) => mutate(current => applyCategorySelection(current.draft,
      (current.snapshot ? jobBackedCandidates(current.snapshot) : []).filter(item => item.category_id === id).map(item => item.candidate_id), checked)),
    applyProposal: (id, chosenIds) => mutate(current => {
      const proposal = current.snapshot?.recommendations.find(item => item.id === id);
      if (!proposal || proposal.candidate_revision !== current.snapshot?.candidate_revision || proposal.base_selection_revision !== current.snapshot.selection_revision) return current.draft;
      const eligible = new Set(jobBackedCandidates(current.snapshot).map(item => item.candidate_id));
      const changes = proposal.changes.filter(change => current.snapshot!.candidates.some(item => item.candidate_id === change.candidate_id) &&
        (change.action === "remove" || eligible.has(change.candidate_id)));
      return applyRecommendationChanges(current.draft, changes, chosenIds ?? changes.map(change => change.candidate_id));
    }),
    acknowledgeReconciliation: (id, checked = true) => updateLocal(current => {
      if (!current.snapshot?.reconciliations?.some(record => record.reconciliation_id === id && !record.resolved)) return current;
      return {...current, reconciliationIds: checked ? [...new Set([...current.reconciliationIds, id])] : current.reconciliationIds.filter(item => item !== id), error: null, success: null};
    }),
    acknowledgeIncomingReview: () => updateLocal(current => ({...current, reviewRequired: false})),
    updateView: update => updateLocal(current => ({...current, view: {...current.view, ...update}}), true),
    undo: () => updateLocal(current => current.undo ? {...current, draft: current.undo, undo: null, success: null, error: null} : current),
    confirmCurrentSelection: () => perform("confirm_current"),
    save: () => perform("save"), reviewMappings: () => perform("confirm"), acknowledgeAvailableEvidence: () => perform("continue"),
    onReviewChange,
  };
}
