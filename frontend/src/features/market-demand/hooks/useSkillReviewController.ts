import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { confirmSkillReviewSelection, continueWithAvailableEvidence, saveSkillReviewDraft, skillReviewErrorMessage } from "@/features/market-demand/api";
import { applyCategorySelection, applyIndividualSelection, applyRecommendationChanges, reconcileDraft } from "@/features/market-demand/selection";
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
  const live = useRef({courseId, review, disabled});

  if (model.incoming !== review || model.courseId !== courseId) {
    const sameRun = model.courseId === courseId && !!review && model.snapshot?.run_id === review.run_id;
    const same = sameRun && sameRevision(model.snapshot, review);
    const previousDirty = !sameDraft(model.draft, draftOf(model.snapshot)) || model.reconciliationIds.length > 0;
    const reconciled = reconcileDraft(model.draft, review?.candidates.map(item => item.candidate_id) ?? []);
    const names = reconciled.removed_ids.map(id => model.snapshot?.candidates.find(item => item.candidate_id === id)?.display_name ?? id);
    // New identities must be explicitly selected even if a refreshed snapshot suggests them.
    const knownIds = new Set(model.snapshot?.candidates.map(item => item.candidate_id));
    const serverDraft = draftOf(review);
    const nextDraft = sameRun && previousDirty ? reconciled.draft : sameRun ? {
      ...serverDraft, selected_candidate_ids: serverDraft.selected_candidate_ids.filter(id => knownIds.has(id)),
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
    if (live.current.courseId !== courseId || !sameRevision(live.current.review, model.snapshot)) {
      generation.current += 1;
      activeRequest.current = null;
    }
    live.current = {courseId, review: model.snapshot, disabled};
  }, [courseId, model.snapshot, disabled]);
  useEffect(() => () => {generation.current += 1; activeRequest.current = null;}, []);

  const pendingReconciliationIds = model.reconciliationIds;
  const dirty = !sameDraft(model.draft, draftOf(model.snapshot)) || pendingReconciliationIds.length > 0;


  const locked = disabled || model.busy;
  const mutate = (next: SelectionDraft) => {
    if (locked || activeRequest.current !== null || sameDraft(next, model.draft)) return;
    setModel({...model, draft: next, undo: model.draft, success: null, error: null});
  };
  const revision = (snapshot: SkillReview) => ({run_id: snapshot.run_id!, expected_candidate_revision: snapshot.candidate_revision, expected_selection_revision: snapshot.selection_revision});

  const perform = async (action: "save" | "confirm" | "continue"): Promise<SkillReview> => {
    if (live.current.courseId !== courseId || !sameRevision(live.current.review, model.snapshot)) throw new Error("Skill review changed; use the current review actions");
    if (!model.snapshot?.run_id || live.current.disabled || activeRequest.current !== null) throw new Error("Skill review is unavailable or busy");
    if (model.reviewRequired) throw new Error("Review the changed revisions before saving");
    if (action === "continue" && dirty) throw new Error("Save the draft before acknowledging evidence");
    const request = ++generation.current;
    activeRequest.current = request;
    setModel(current => ({...current, busy: true, error: null, success: null}));
    const assertCurrent = () => {
      if (generation.current !== request) throw new Error("Skill review changed while the request was pending");
    };
    const accept = (response: SkillReview) => {
      assertCurrent();
      if (response.run_id !== model.snapshot!.run_id) throw new Error("Skill review response belongs to a different run");
      live.current = {...live.current, review: response};
      setModel(current => ({...current, snapshot: response, draft: draftOf(response), reconciliationIds: [], reviewRequired: false, undo: null}));
      onReviewChange(response);
      return response;
    };
    let acknowledged = model.snapshot;
    try {
      if (action === "save" || (action === "confirm" && dirty)) {
        acknowledged = accept(await saveSkillReviewDraft(courseId, {...revision(acknowledged), ...model.draft,
          ...(pendingReconciliationIds.length ? {resolved_reconciliation_ids: pendingReconciliationIds} : {})}));
      }
      if (action === "confirm") {
        assertCurrent();
        if (needsEvidenceAcknowledgement(acknowledged) || acknowledged.reconciliations?.some(record => !record.resolved) || !acknowledged.selected_candidate_ids.length) {
          throw new Error("Review reconciliation and evidence omissions before confirming a selection");
        }
        acknowledged = accept(await confirmSkillReviewSelection(courseId, revision(acknowledged)));
      }
      if (action === "continue") acknowledged = accept(await continueWithAvailableEvidence(courseId, revision(acknowledged)));
      assertCurrent();
      setModel(current => ({...current, success: action === "save" ? "Draft saved" : action === "confirm" ? "Selection confirmed for mapping" : "Evidence omissions acknowledged; supporting postings are still required"}));
      return acknowledged;
    } catch (cause) {
      if (request === generation.current) setModel(current => ({...current, error: skillReviewErrorMessage(cause, "Skill review request failed")}));
      throw cause;
    } finally {
      if (request === generation.current) {
        activeRequest.current = null;
        setModel(current => ({...current, busy: false}));
      }
    }
  };

  return {
    review: model.snapshot, draft: model.draft, view: model.view, dirty, busy: model.busy, disabled,
    reviewRequired: model.reviewRequired, error: model.error, success: model.success, canUndo: !!model.undo,
    reconciliation: model.reconciliation, pendingReconciliationIds,
    needsEvidenceAcknowledgement: needsEvidenceAcknowledgement(model.snapshot),
    setCandidate: (id, checked) => {if (model.snapshot?.candidates.some(item => item.candidate_id === id)) mutate(applyIndividualSelection(model.draft, id, checked));},
    setCategory: (id, checked) => mutate(applyCategorySelection(model.draft, model.snapshot?.candidates.filter(item => item.category_id === id).map(item => item.candidate_id) ?? [], checked)),
    applyProposal: (id, chosenIds) => {
      const proposal = model.snapshot?.recommendations.find(item => item.id === id);
      if (!proposal || proposal.candidate_revision !== model.snapshot?.candidate_revision || proposal.base_selection_revision !== model.snapshot.selection_revision) return;
      const changes = proposal.changes.filter(change => model.snapshot!.candidates.some(item => item.candidate_id === change.candidate_id));
      mutate(applyRecommendationChanges(model.draft, changes, chosenIds ?? changes.map(change => change.candidate_id)));
    },
    acknowledgeReconciliation: (id, checked = true) => {
      if (locked || activeRequest.current !== null || !model.snapshot?.reconciliations?.some(record => record.reconciliation_id === id && !record.resolved)) return;
      setModel({...model, reconciliationIds: checked ? [...new Set([...model.reconciliationIds, id])] : model.reconciliationIds.filter(item => item !== id), error: null, success: null});
    },
    acknowledgeIncomingReview: () => {if (!locked && activeRequest.current === null) setModel({...model, reviewRequired: false});},
    updateView: update => setModel(current => ({...current, view: {...current.view, ...update}})),
    undo: () => {if (!locked && activeRequest.current === null && model.undo) setModel({...model, draft: model.undo, undo: null, success: null, error: null});},
    save: () => perform("save"), reviewMappings: () => perform("confirm"), acknowledgeAvailableEvidence: () => perform("continue"),
    onReviewChange,
  };
}
