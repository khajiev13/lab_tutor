import {Button} from "@/components/ui/button";
import {Checkbox} from "@/components/ui/checkbox";
import {Table, TableBody, TableCell, TableHead, TableHeader, TableRow} from "@/components/ui/table";
import type {SkillReviewController} from "@/features/market-demand/hooks/useSkillReviewController";
import type {RatingResolution, WorkspaceData, WorkspacePage, WorkspaceQuestion, WorkspaceRow} from "@/features/market-demand/types";

export interface WorkspaceViewProps {
  data: WorkspaceData;
  controller: SkillReviewController;
  onAsk: (request: WorkspaceQuestion) => void;
}

export function DemandValue({row}: {row: WorkspaceRow}) {
  const metrics = row.candidate.job_metrics;
  if (row.demand === null) return <span>Unavailable: {metrics.assessed_posting_count === 0 ? "No assessed postings" : "sample frequency not reported"}</span>;
  return <span>{row.demand}% · {metrics.supporting_posting_count ?? "unavailable"} / {metrics.assessed_posting_count} supporting / assessed</span>;
}

export function RatingValue({rating, label, candidateId, controller}: {rating: RatingResolution; label: string; candidateId: string; controller: SkillReviewController}) {
  if (rating.status === "ambiguous") return <div className="space-y-1">
    <p>Multiple matched descriptors — choose one for this role; comparisons require the same descriptor.</p>
    <select aria-label={`Descriptor for ${label}`} className="max-w-full rounded-md border bg-background p-2 text-foreground" value={controller.view.descriptorChoices.find(choice => choice.candidate_id === candidateId && rating.evidence.some(item => item.id === choice.evidence_id))?.evidence_id ?? ""}
      onChange={event => controller.updateView({descriptorChoices: [
        ...controller.view.descriptorChoices.filter(choice => choice.candidate_id !== candidateId || !rating.evidence.some(item => item.id === choice.evidence_id)),
        ...(event.target.value ? [{candidate_id: candidateId, evidence_id: event.target.value}] : []),
      ]})}>
      <option value="">Choose descriptor</option>
      {rating.evidence.map(item => <option key={item.id} value={item.id}>{item.label} · {item.release} · {item.family} · {item.element_id}</option>)}
    </select>
  </div>;
  if (rating.status !== "reported") return <span>Unavailable: {rating.status === "no_association" ? "no equivalent association in this release" : rating.status.replaceAll("_", " ")}</span>;
  return <div><p>{rating.value} / {rating.metric === "IM" ? 5 : 7}</p><p className="text-xs text-muted-foreground">{rating.evidence.label} · {rating.evidence.release} · {rating.evidence.family} · {rating.evidence.element_id} · {rating.evidence.id}</p></div>;
}

export function WorkspacePaging({page, controller}: {page: WorkspacePage; controller: SkillReviewController}) {
  return <div className="flex flex-wrap items-center gap-2 text-sm">
    <p aria-live="polite">Rows {page.start}–{page.end} of {page.total}</p>
    <Button variant="outline" size="sm" disabled={page.page <= 1} onClick={() => controller.updateView({page: page.page - 1})}>Previous rows</Button>
    <Button variant="outline" size="sm" disabled={page.page >= page.pageCount} onClick={() => controller.updateView({page: page.page + 1})}>Next rows</Button>
  </div>;
}

export function WorkspaceRatingControls({data, controller}: Pick<WorkspaceViewProps, "data" | "controller">) {
  const roles = controller.review?.analysis_metadata?.occupations ?? [];
  const codes = data.scope.occupationCodes.filter(code => data.scope.confirmedOccupationCodes.includes(code));
  return <div className="flex flex-wrap gap-3">
    <label className="space-y-1 text-sm"><span className="block">Compare occupation</span>
      <select aria-label="Compare occupation" className="rounded-md border bg-background p-2 text-foreground" value={codes.includes(controller.view.activeOccupationCode ?? "") ? controller.view.activeOccupationCode! : ""}
        onChange={event => controller.updateView({activeOccupationCode: event.target.value || null, page: 1})}>
        <option value="">Choose occupation</option>
        {roles.filter(role => codes.includes(role.soc_code)).map(role => <option key={role.soc_code} value={role.soc_code}>{role.title} ({role.soc_code})</option>)}
      </select>
    </label>
    <label className="space-y-1 text-sm"><span className="block">Compare metric</span>
      <select aria-label="Compare metric" className="rounded-md border bg-background p-2 text-foreground" value={controller.view.metric === "LV" ? "LV" : "IM"}
        onChange={event => controller.updateView({metric: event.target.value === "LV" ? "LV" : "IM", page: 1})}>
        <option value="IM">Importance (1–5)</option><option value="LV">Level (0–7)</option>
      </select>
    </label>
  </div>;
}

export function WorkspaceDataTable({data, controller, onAsk}: WorkspaceViewProps) {
  const page = data.tablePage;
  const sort = (field: string) => controller.updateView({sort: {field, direction: controller.view.sort.field === field && controller.view.sort.direction === "asc" ? "desc" : "asc"}, page: 1});
  const direction = (field: string) => controller.view.sort.field === field ? controller.view.sort.direction === "asc" ? "ascending" as const : "descending" as const : "none" as const;
  return <section aria-label="Evidence data" className="space-y-4">
    <WorkspaceRatingControls data={data} controller={controller}/>
    {!data.rows.length ? <p>No matching skills. Change the filters to inspect evidence.</p> : <>
      <WorkspacePaging page={page} controller={controller}/>
      <Table>
        <TableHeader><TableRow>
          <TableHead>Shortlist</TableHead>
          <TableHead aria-sort={direction("name")}><Button variant="ghost" size="sm" aria-label="Sort by name" onClick={() => sort("name")}>Skill</Button></TableHead>
          <TableHead aria-sort={direction("frequency")}><Button variant="ghost" size="sm" aria-label="Sort by frequency" onClick={() => sort("frequency")}>Sample frequency (0–100%)</Button></TableHead>
          <TableHead aria-sort={direction("rating")}><Button variant="ghost" size="sm" aria-label="Sort by rating" onClick={() => sort("rating")}>Reported {controller.view.metric === "LV" ? "Level (0–7)" : "Importance (1–5)"}</Button></TableHead>
          <TableHead>Evidence</TableHead>
        </TableRow></TableHeader>
        <TableBody>{page.rows.map(row => <TableRow key={row.candidateId} data-state={row.selected ? "selected" : undefined}>
          <TableCell><Checkbox aria-label={`Select ${row.label}`} checked={row.selected} disabled={controller.busy || controller.disabled} onCheckedChange={checked => controller.setCandidate(row.candidateId, checked === true)}/></TableCell>
          <TableCell className="whitespace-normal"><p>{row.label}</p>{row.candidate.posting_support === "missing" && <p className="text-xs text-muted-foreground">Needs job evidence</p>}</TableCell>
          <TableCell className="whitespace-normal"><DemandValue row={row}/></TableCell>
          <TableCell className="whitespace-normal"><RatingValue rating={row.rating} label={`${row.label} · ${controller.review?.analysis_metadata?.occupations.find(role => role.soc_code === controller.view.activeOccupationCode)?.title ?? "occupation"}`} candidateId={row.candidateId} controller={controller}/></TableCell>
          <TableCell><div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" aria-label={`Inspect ${row.label}`} onClick={() => controller.updateView({focusedCandidateId: row.candidateId})}>Inspect</Button>
            <Button variant="ghost" size="sm" aria-label={`Ask about ${row.label}`} onClick={() => onAsk({text: `Explain the evidence and unavailable values for ${row.label}.`, candidateIds: [row.candidateId], occupationCodes: controller.view.activeOccupationCode ? [controller.view.activeOccupationCode] : []})}>Ask agent</Button></div></TableCell>
        </TableRow>)}</TableBody>
      </Table>
    </>}
  </section>;
}
