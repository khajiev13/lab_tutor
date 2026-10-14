import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { skillReviewErrorMessage } from "@/features/market-demand/api";
import { SkillEvidencePanel } from "@/features/market-demand/components/SkillEvidencePanel";
import { IntegrationReview } from "@/features/market-demand/components/IntegrationReview";
import { categorySelectionState, jobBackedCandidates } from "@/features/market-demand/selection";
import type { SkillReviewController } from "@/features/market-demand/hooks/useSkillReviewController";
import type { SkillCandidate } from "@/features/market-demand/types";

interface Props {
  courseId: number;
  controller: SkillReviewController;
  onRefresh?: () => Promise<void>;
}

function importance(candidate: SkillCandidate, occupation: string): number | null {
  const metric = candidate.onet_associations.find(item => item.relation === "equivalent" && item.evidence.soc_code === occupation && item.evidence.ratings.IM?.status === "reported")?.evidence.ratings.IM;
  return metric?.value ?? null;
}

export function SkillReviewPanel({courseId, controller, onRefresh}: Props) {
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const {review: snapshot, draft, dirty, busy, disabled, success, pendingReconciliationIds, reviewRequired} = controller;
  if (!snapshot) return null;
  const error = controller.error ?? refreshError;
  const filter = controller.view.filters.search;
  const sort = controller.view.sort.field;
  const occupation = controller.view.activeOccupationCode ?? "";
  const reconciliations = snapshot.reconciliations ?? [];
  const unresolvedReconciliations = reconciliations.filter(record => !record.resolved);
  const locked = disabled || busy;
  const eligible = jobBackedCandidates(snapshot);
  const eligibleIds = new Set(eligible.map(item => item.candidate_id));
  const missingCount = snapshot.candidates.filter(item => draft.selected_candidate_ids.includes(item.candidate_id) && !eligibleIds.has(item.candidate_id)).length;
  const coverage = snapshot.extraction_coverage;
  const needsAcknowledgement = controller.needsEvidenceAcknowledgement;
  const occupations = [...new Map(snapshot.candidates.flatMap(item => item.onet_associations.map(({evidence}) => [evidence.soc_code,evidence.occupation_title] as const))).entries()];
  const activeOccupation = occupations.some(([code]) => code === occupation) ? occupation : "";
  const perform = (action: "save" | "confirm" | "continue") => {
    const request = action === "save" ? controller.save : action === "confirm" ? controller.reviewMappings : controller.acknowledgeAvailableEvidence;
    void request().catch(() => {}); // The controller retains the rejected request's error and draft.
  };
  const visible = (candidate: SkillCandidate) => `${candidate.display_name} ${candidate.aliases.join(" ")}`.toLowerCase().includes(filter.trim().toLowerCase());
  const compare = (a: SkillCandidate, b: SkillCandidate) => {
    const metric = sort === "importance" && activeOccupation ? [importance(a,activeOccupation),importance(b,activeOccupation)] : sort === "frequency" ? [a.job_metrics.percentage ?? null,b.job_metrics.percentage ?? null] : null;
    if (metric) {
      if (metric[0] === null && metric[1] !== null) return 1;
      if (metric[1] === null && metric[0] !== null) return -1;
      if (metric[0] !== null && metric[1] !== null && metric[0] !== metric[1]) return metric[1] - metric[0];
    }
    return a.display_name.localeCompare(b.display_name);
  };
  return (
    <section aria-label="Skill draft review" className="space-y-3 rounded-lg border bg-card p-3">
      <h2 className="text-sm font-semibold">Review categories and individual skills</h2>
      <p className="text-xs text-muted-foreground">Category selection includes every current member, including filtered results. New candidates stay unselected. Save the draft before confirming it for mapping.</p>
      <p className="text-sm">{draft.selected_candidate_ids.length} selected · {missingCount} needs supporting job posting</p>
      {missingCount > 0 && <p className="text-xs text-muted-foreground">To collect supporting job postings, start a new analysis and explicitly select job providers.</p>}
      <div className="flex flex-wrap gap-2 text-xs">
        <Input aria-label="Filter skills" placeholder="Filter skills" value={filter} onChange={event => controller.updateView({filters: {...controller.view.filters, search: event.target.value}})}/>
        <label>Active occupation <select aria-label="Active occupation" value={activeOccupation} onChange={event => controller.updateView({activeOccupationCode: event.target.value || null})} className="rounded-md border bg-background px-2 py-1"><option value="">Choose an occupation</option>{occupations.map(([code,title]) => <option key={code} value={code}>{title} ({code})</option>)}</select></label>
        <label>Sort skills <select aria-label="Sort skills" value={sort} onChange={event => controller.updateView({sort: {field: event.target.value, direction: event.target.value === "name" ? "asc" : "desc"}})} className="rounded-md border bg-background px-2 py-1"><option value="name">Name</option><option value="frequency">Job sample frequency</option><option value="importance" disabled={!activeOccupation}>O*NET importance</option></select></label>
      </div>
      {Object.entries(snapshot.source_outcomes).map(([source,outcome]) => <div key={source} className="text-xs"><p>{source}: {outcome.status} · {outcome.usable_count}/{outcome.received_count} usable</p>{outcome.warnings.map((warning,index) => <p key={index}>{warning}</p>)}</div>)}
      {coverage.status && <p className="text-xs">Extraction: {coverage.status} · {coverage.assessed_postings ?? "unavailable"}/{coverage.selected_postings ?? "unavailable"} postings assessed · {coverage.assessed_chunks ?? "unavailable"}/{coverage.total_chunks ?? "unavailable"} chunks assessed</p>}
      {coverage.warnings?.map((warning,index) => <p key={index} className="text-xs">{warning}</p>)}
      {needsAcknowledgement && <Button size="sm" variant="outline" disabled={locked || dirty} onClick={() => void perform("continue")}>Continue with available evidence</Button>}
      {dirty && <p className="text-xs">Unsaved shortlist changes</p>}
      {controller.reconciliation && <p role="alert" className="text-xs text-destructive">{controller.reconciliation}</p>}
      {reviewRequired && <div className="space-y-2 text-xs"><p>Review required. Check changed candidates and remove saved choices without supporting job evidence before continuing.</p><Button size="sm" variant="outline" disabled={locked} onClick={controller.acknowledgeIncomingReview}>I reviewed the changed revisions</Button></div>}
      {reconciliations.length > 0 && <section aria-label="Candidate reconciliation" className="space-y-2 rounded-md border p-3 text-xs">
        <h3 className="font-medium">Candidate reconciliation</h3>
        {unresolvedReconciliations.length > 0 && <p>Review each changed candidate and save explicit acknowledgements before confirming for mapping.</p>}
        {reconciliations.map(record => {
          const replacement = snapshot.candidates.find(candidate => candidate.candidate_id === record.candidate_id);
          const previousNames = record.previous_candidates.map(candidate => candidate.display_name);
          const label = previousNames.join(", ") || replacement?.display_name || record.reconciliation_id;
          return <div key={record.reconciliation_id} className="space-y-1 rounded-md border p-2">
            {record.previous_candidates.map(candidate => <p key={candidate.candidate_id}>{candidate.display_name}</p>)}
            {replacement && <p>Replacement: {replacement.display_name}</p>}
            <p>{record.reason.replaceAll("_", " ")}</p>
            {record.resolved ? <p>Reconciliation resolved</p> : <label className="flex items-center gap-2">
              <Checkbox aria-label={`Acknowledge reconciliation for ${label}`} checked={pendingReconciliationIds.includes(record.reconciliation_id)} disabled={locked} onCheckedChange={checked => controller.acknowledgeReconciliation(record.reconciliation_id, checked === true)}/>
              Acknowledge this reconciliation with Save draft
            </label>}
          </div>;
        })}
      </section>}
      {snapshot.categories.map(category => {
        const members = snapshot.candidates.filter(item => item.category_id === category.category_id);
        const memberIds = members.filter(item => eligibleIds.has(item.candidate_id)).map(item => item.candidate_id);
        const rows = members.filter(visible).sort(compare);
        const isCollapsed = collapsed.includes(category.category_id);
        const selectedCount = memberIds.filter(id => draft.selected_candidate_ids.includes(id)).length;
        return (
          <div key={category.category_id} className="rounded-md border">
            <div className="flex items-center gap-2 p-2">
              <Checkbox aria-label={`Select category ${category.label} (${memberIds.length} current members)`} checked={categorySelectionState(memberIds,draft.selected_candidate_ids)} disabled={locked || memberIds.length === 0} onCheckedChange={checked => controller.setCategory(category.category_id, checked === true)}/>
              <Button variant="ghost" size="sm" aria-expanded={!isCollapsed} onClick={() => setCollapsed(isCollapsed ? collapsed.filter(id => id !== category.category_id) : [...collapsed,category.category_id])}>{category.label}</Button>
              <span className="text-xs text-muted-foreground">{selectedCount}/{memberIds.length} selected · {rows.length} visible</span>
            </div>
            {!isCollapsed && <div className="space-y-2 p-2">{rows.map(candidate => (
              <div key={candidate.candidate_id} className={cn("space-y-2 rounded-md border p-2",candidate.posting_support === "missing" && "border-dashed")}>
                <label className="flex items-center gap-2 text-sm font-medium"><Checkbox aria-label={`Select ${candidate.display_name}`} checked={draft.selected_candidate_ids.includes(candidate.candidate_id)} disabled={locked || (!eligibleIds.has(candidate.candidate_id) && !draft.selected_candidate_ids.includes(candidate.candidate_id))} onCheckedChange={checked => controller.setCandidate(candidate.candidate_id, checked === true)}/>{candidate.display_name}</label>
                {!eligibleIds.has(candidate.candidate_id) && <p className="text-xs text-destructive">Needs supporting job posting</p>}
                <p className="text-xs">Job sample: {candidate.job_metrics.supporting_posting_count ?? "unavailable"} supporting / {candidate.job_metrics.assessed_posting_count ?? "unavailable"} assessed / {candidate.job_metrics.selected_posting_count ?? "unavailable"} selected · frequency {candidate.job_metrics.percentage == null ? "unavailable" : `${candidate.job_metrics.percentage}%`} · coverage {candidate.job_metrics.coverage_status ?? "unavailable"}</p>
                {candidate.onet_associations.map(association => (
                  <div key={`${association.evidence.id}:${association.relation}`} className="text-xs space-y-1">
                    <p>
                      {association.evidence.occupation_title} ({association.evidence.soc_code}) · {association.relation === "equivalent" ? "equivalent" : `${association.relation} context`} · O*NET {association.evidence.release} · {association.evidence.label}
                    </p>
                    <p>{association.evidence.definition}</p>
                    <p>Mapping: {association.mapping_method} · {association.rationale}</p>
                    {(["IM", "LV"] as const).map(scale => {
                      const metric = association.evidence.ratings[scale];
                      return (
                        <p key={scale}>
                          {scale}: {metric?.status === "reported" && metric.value != null
                            ? `${metric.value} (${metric.minimum}–${metric.maximum})`
                            : `unavailable (${metric?.status ?? "missing"})`}
                          {metric?.date ? ` · source date ${metric.date}` : ""}
                        </p>
                      );
                    })}
                    {Object.entries(association.evidence.flags).map(([flag, value]) => (
                      <p key={flag}>{flag}: {value == null ? "unavailable" : value ? "yes" : "no"}</p>
                    ))}
                    <p>{association.evidence.attribution}</p>
                  </div>
                ))}
                {candidate.recommendation_reasons.length > 0 && <div className="text-xs"><p className="font-medium">Agent reasons</p>{candidate.recommendation_reasons.map((reason,index) => <p key={index}>{reason}</p>)}</div>}
                <SkillEvidencePanel courseId={courseId} candidate={candidate}/>
              </div>
            ))}{rows.length === 0 && <p className="text-xs text-muted-foreground">No visible skills. Category selection still includes all {members.length} members.</p>}</div>}
          </div>
        );
      })}
      {snapshot.recommendations.map(proposal => {
        const current = proposal.candidate_revision === snapshot.candidate_revision && proposal.base_selection_revision === snapshot.selection_revision;
        const changes = proposal.changes.filter(change => snapshot.candidates.some(item => item.candidate_id === change.candidate_id));
        return (
          <div key={proposal.id} className="space-y-2 rounded-md border p-2 text-xs">
            <p className="font-medium">Agent suggestions (draft only)</p>
            {!current && <p>Suggestions are stale; request advice for the current revisions.</p>}
            {changes.map(change => {
              const key = `${proposal.id}:${change.candidate_id}`;
              const candidate = snapshot.candidates.find(item => item.candidate_id === change.candidate_id)!;
              const excluded = change.action === "add" && draft.excluded_candidate_ids.includes(change.candidate_id);
              return (
                <label key={key} className="flex items-start gap-2">
                  <Checkbox
                    aria-label={`Apply suggestion for ${candidate.display_name}`}
                    checked={suggestions.includes(key)}
                    disabled={locked || !current || excluded}
                    onCheckedChange={checked => setSuggestions(
                      checked ? [...suggestions, key] : suggestions.filter(id => id !== key)
                    )}
                  />
                  <span>
                    {change.action}: {candidate.display_name} · {change.reason}
                    {excluded && " · Explicit exclusion protected; select the skill yourself to include it"}
                  </span>
                </label>
              );
            })}
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={locked || !current || !changes.some(change => suggestions.includes(`${proposal.id}:${change.candidate_id}`))}
                onClick={() => controller.applyProposal(proposal.id,
                  changes.filter(change => suggestions.includes(`${proposal.id}:${change.candidate_id}`)).map(change => change.candidate_id))}
              >
                Apply selected suggestions
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={locked || !current}
                onClick={() => controller.applyProposal(proposal.id)}
              >
                Apply all suggestions
              </Button>
            </div>
          </div>
        );
      })}
      {snapshot.approved_references.length > 0 && !snapshot.integration_review && <div className="text-xs"><p className="font-medium">Previously published offering</p>{snapshot.approved_references.map(item => <p key={item.reference_id}>{item.label}</p>)}</div>}
      {error && <div className="text-xs"><p role="alert" className="text-destructive">{error}</p>{onRefresh && <Button size="sm" variant="outline" disabled={locked} onClick={() => void onRefresh().catch(cause=>setRefreshError(skillReviewErrorMessage(cause,"Review reload failed")))}>Reload current review</Button>}<p>Local choices are retained. Reload and review any changed candidates before retrying.</p></div>}
      {success && <p role="status" className="text-xs">{success}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={locked || !controller.canUndo} onClick={controller.undo}>Undo local change</Button>
        <Button size="sm" disabled={locked || !dirty || reviewRequired} onClick={() => void perform("save")}>Save draft</Button>
        <Button size="sm" disabled={locked || reviewRequired || needsAcknowledgement || unresolvedReconciliations.length > 0 || !draft.selected_candidate_ids.length} onClick={() => void perform("confirm")}>Confirm selection for mapping</Button>
      </div>
      <IntegrationReview courseId={courseId} review={snapshot} onReviewChange={controller.onReviewChange} disabled={locked} publicationDisabled={dirty || reviewRequired || needsAcknowledgement || unresolvedReconciliations.length > 0}/>
    </section>
  );
}
