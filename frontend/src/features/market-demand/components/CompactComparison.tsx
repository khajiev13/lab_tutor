import {useState} from "react";
import {Button} from "@/components/ui/button";
import {Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle} from "@/components/ui/dialog";
import {EvidenceChart} from "@/features/market-demand/components/EvidenceChart";
import {buildCompactComparison} from "@/features/market-demand/compact-comparison";
import type {CompactComparisonRow} from "@/features/market-demand/compact-comparison";
import type {DescriptorChoice, SkillReview, WorkspaceQuestion} from "@/features/market-demand/types";

export interface CompactComparisonProps {
  review: SkillReview; candidateIds: string[]; open: boolean; onOpenChange: (open: boolean) => void;
  onAsk: (question: WorkspaceQuestion, descriptorChoices?: DescriptorChoice[]) => void;
}
function ComparisonBody({review, candidateIds, onAsk}: Pick<CompactComparisonProps, "review" | "candidateIds" | "onAsk">) {
  const [metric, setMetric] = useState<"frequency" | "IM">("frequency");
  const [occupationCode, setOccupationCode] = useState<string | null>(review.analysis_metadata?.occupations[0]?.soc_code ?? null);
  const [choices, setChoices] = useState<DescriptorChoice[]>([]);
  const [page, setPage] = useState(1);
  const [focused, setFocused] = useState<string | null>(null);
  const candidates = new Map(review.candidates.map(candidate => [candidate.candidate_id, candidate]));
  const comparedIds = [...new Set(candidateIds)].filter(id => candidates.has(id));
  // Page skills before deduplicating descriptors: a shared descriptor must not
  // turn 58 chosen skills into one unbounded Ask context or silently drop IDs.
  const pages = Math.max(1, Math.ceil(comparedIds.length / 5));
  const current = Math.min(page, pages);
  const offset = (current - 1) * 5;
  const visibleIds = comparedIds.slice(offset, offset + 5);
  const model = buildCompactComparison(review, visibleIds, metric, occupationCode, choices);
  const rows = model.rows;
  const descriptorOptions = new Map(buildCompactComparison(review, visibleIds, metric, occupationCode).rows
    .filter(row => row.status === "ambiguous" && row.mappings.length === 0).map(row => [row.candidateIds[0], row.evidenceIds]));
  const numeric = rows.filter(row => row.value !== null);
  const ask = (row: CompactComparisonRow) => {
    const exactChoices = row.candidateIds.flatMap(candidateId => {
      const evidence = candidates.get(candidateId)?.onet_associations.find(item => row.evidenceIds.includes(item.evidence.id) &&
        item.evidence.soc_code === model.occupation?.soc_code && item.evidence.release === model.release);
      return evidence && row.mappings.length > 0 ? [{candidate_id: candidateId, evidence_id: evidence.evidence.id}] : [];
    });
    onAsk({text: metric === "frequency" ? `Explain the collected job evidence for ${row.label}.` :
      `Explain ${row.label} and its mapping context for ${model.occupation?.title ?? "the occupation"}, O*NET release ${model.release ?? "unavailable"}; this is descriptor importance, not student mastery.`,
      candidateIds: [...row.candidateIds], occupationCodes: model.occupation ? [model.occupation.soc_code] : []}, exactChoices);
  };
  const valueText = (row: CompactComparisonRow) => {
    if (row.value === null) {
      if (row.status === "ambiguous") return row.mappings.length ? "Unavailable · conflicting saved descriptor values" : "Choose a descriptor to compare";
      return `Unavailable · ${row.status.replaceAll("_", " ")}`;
    }
    if (metric === "IM") return `${row.value} / 5 importance`;
    const counts = candidates.get(row.candidateIds[0])!.job_metrics;
    return `${row.value}% · ${counts.supporting_posting_count} of ${counts.assessed_posting_count} assessed postings${counts.selected_posting_count !== undefined ? ` · ${counts.selected_posting_count} selected` : ""}${counts.coverage_status ? ` · ${counts.coverage_status} coverage` : ""}`;
  };
  return <div className="min-w-0 space-y-3">
    <div className="flex flex-wrap gap-2" aria-label="Comparison measure">
      <Button size="sm" variant={metric === "frequency" ? "secondary" : "outline"} aria-pressed={metric === "frequency"} onClick={() => {setMetric("frequency"); setPage(1); setFocused(null);}}>Collected jobs</Button>
      <Button size="sm" variant={metric === "IM" ? "secondary" : "outline"} aria-pressed={metric === "IM"} onClick={() => {setMetric("IM"); setPage(1); setFocused(null);}}>O*NET importance</Button>
    </div>
    {metric === "IM" && <div className="space-y-2 text-sm">
      <label className="block space-y-1"><span>Confirmed occupation</span>
        <select aria-label="Confirmed occupation" className="w-full rounded-md border bg-background p-2" value={model.occupation?.soc_code ?? ""}
          onChange={event => {setOccupationCode(event.target.value || null); setChoices([]); setPage(1); setFocused(null);}}>
          <option value="">Choose occupation</option>{review.analysis_metadata?.occupations.map(role => <option key={role.soc_code} value={role.soc_code}>{role.title} ({role.soc_code})</option>)}
        </select>
      </label>
      <p>O*NET release {model.release ?? "unavailable"} · Importance (IM), original 1–5 scale. Related and broader descriptors provide mapping context.</p>
      {(!model.occupation || !model.release) && <p>Choose a confirmed occupation with a stored release to ask about O*NET evidence.</p>}
    </div>}
    {!model.rows.length ? <p className="text-sm">Choose skills to compare from Browse skills.</p> : <>
      <p className="text-xs text-muted-foreground" aria-live="polite">Showing {visibleIds.length} of {comparedIds.length} skills · entries {offset + 1}–{offset + visibleIds.length}</p>
      {numeric.length && model.scale ? <EvidenceChart key={metric} label={metric === "frequency" ? "Collected job sample frequency" : `O*NET importance for ${model.occupation!.title}`}
        className="h-64 sm:h-72" onFocus={({candidateId}) => setFocused(candidateId)} option={width => ({
          animation: false, grid: {left: 8, right: 24, top: 16, bottom: 40, containLabel: true},
          xAxis: {type: "value", min: model.scale![0], max: model.scale![1], name: metric === "frequency" ? "Sample frequency (%)" : "Importance (1–5)", nameLocation: "middle", nameGap: 28},
          yAxis: {type: "category", inverse: true, data: numeric.map(row => row.label), axisLabel: {width: Math.max(40, Math.min(180, width * 0.35)), overflow: "truncate"}},
          series: [{type: "bar", data: numeric.map(row => ({value: row.value, focus: {candidateId: row.candidateIds[0], ...(model.occupation ? {occupationCode: model.occupation.soc_code} : {}), ...(row.evidenceIds[0] ? {evidenceId: row.evidenceIds[0]} : {})},
            tooltipText: `${row.label}: ${valueText(row)}${model.occupation ? ` · ${model.occupation.title} · release ${model.release}` : ""}`}))}],
        })}/> : <p className="text-sm">No comparable reported values. Unavailable evidence is listed below.</p>}
      <p className="text-sm">{model.insight}</p>
      <ul aria-label="Comparison values" className="space-y-2">{rows.map(row => <li key={JSON.stringify([row.candidateIds, row.evidenceIds])}
        className="space-y-1 rounded-md border p-2 text-sm" aria-current={row.candidateIds.includes(focused ?? "") ? "true" : undefined}>
        <strong className="block break-words">{row.label}</strong><p>{valueText(row)}</p>
        {row.candidateIds.filter(id => descriptorOptions.has(id)).map(id => <label key={id} className="block space-y-1">
          <span>Choose a descriptor for {candidates.get(id)!.display_name}</span>
          <select aria-label={`Descriptor for ${candidates.get(id)!.display_name}`} className="w-full rounded-md border bg-background p-2" value={choices.find(choice => choice.candidate_id === id)?.evidence_id ?? ""}
            onChange={event => setChoices([...choices.filter(choice => choice.candidate_id !== id), ...(event.target.value ? [{candidate_id: id, evidence_id: event.target.value}] : [])])}>
            <option value="">Choose a descriptor</option>{candidates.get(id)!.onet_associations.filter(item => descriptorOptions.get(id)!.includes(item.evidence.id)).map(item =>
              <option key={item.evidence.id} value={item.evidence.id}>{item.evidence.label} · {item.relation} · {item.evidence.element_id}</option>)}
          </select>
        </label>)}
        <div className="flex flex-wrap items-center gap-2">{row.sourceUrl && <a href={row.sourceUrl} target="_blank" rel="noreferrer" aria-label={`Original source for ${row.label}`} className="underline">Original source</a>}
          <Button size="sm" variant="ghost" aria-label={`Inspect ${row.label}`} onClick={() => setFocused(row.candidateIds[0])}>Inspect</Button>
          <Button size="sm" variant="outline" disabled={metric === "IM" && (!model.occupation || !model.release)} aria-label={`Ask about ${row.label}`} onClick={() => ask(row)}>Ask the agent</Button>
        </div>
      </li>)}</ul>
      {pages > 1 && <div className="flex items-center justify-between gap-2">
        <Button size="sm" variant="outline" aria-label="Previous comparison page" disabled={current === 1} onClick={() => setPage(current - 1)}>Previous</Button>
        <span className="text-xs">Page {current} of {pages}</span>
        <Button size="sm" variant="outline" aria-label="Next comparison page" disabled={current === pages} onClick={() => setPage(current + 1)}>Next</Button>
      </div>}
    </>}
  </div>;
}
export function CompactComparison({review, candidateIds, open, onOpenChange, onAsk}: CompactComparisonProps) {
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent maxWidthClassName="sm:max-w-2xl" className="max-h-[85dvh] overflow-y-auto">
      <DialogHeader><DialogTitle>Compare skills</DialogTitle><DialogDescription>Inspect one measure at a time for your chosen skills. Questions explain evidence; choices remain yours.</DialogDescription></DialogHeader>
      {open && <ComparisonBody review={review} candidateIds={candidateIds} onAsk={onAsk}/>}
    </DialogContent>
  </Dialog>;
}
