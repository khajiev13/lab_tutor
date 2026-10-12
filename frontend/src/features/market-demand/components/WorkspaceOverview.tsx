import {Button} from "@/components/ui/button";
import {EvidenceChart} from "@/features/market-demand/components/EvidenceChart";
import {DemandValue} from "@/features/market-demand/components/WorkspaceDataTable";
import type {WorkspaceViewProps} from "@/features/market-demand/components/WorkspaceDataTable";

export function WorkspaceOverview({data, controller, onAsk}: WorkspaceViewProps) {
  const plotted = data.demandRows.filter(row => row.demand !== null);
  const occupationName = (code: string) => controller.review?.analysis_metadata?.occupations.find(item => item.soc_code === code)?.title ?? code;
  const option = {
    animation: false,
    grid: {left: 12, right: 48, top: 20, bottom: 48, containLabel: true},
    xAxis: {type: "value", min: 0, max: 100, name: "Sample frequency (%)", nameLocation: "middle", nameGap: 30},
    yAxis: {type: "category", inverse: true, data: plotted.map(row => row.label), axisLabel: {width: 150, overflow: "truncate"}},
    series: [{type: "bar", label: {show: true, position: "right", formatter: "{c}%"},
      itemStyle: {color: "#2563eb"}, data: plotted.map(row => ({value: row.demand, focus: {candidateId: row.candidateId},
        tooltipText: `${row.label}: ${row.demand}% · ${row.candidate.job_metrics.supporting_posting_count ?? "unavailable"} / ${row.candidate.job_metrics.assessed_posting_count} supporting / assessed`}))}],
  };
  const partial = data.rows.some(row => row.candidate.job_metrics.coverage_status === "partial" || row.candidate.job_metrics.coverage_status === "failed") || data.scope.coverage.extraction_coverage.status === "partial" || data.scope.coverage.extraction_coverage.status === "failed" ||
    Object.values(data.scope.coverage.source_outcomes).some(item => item.status === "partial" || item.status === "error");
  return <section aria-label="Demand overview" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm">Showing {data.demandRows.length} of {data.rows.length} matching skills</p>
      <Button variant="outline" size="sm" onClick={() => controller.updateView({view: "data", page: 1})}>View all</Button></div>
    <p className="text-sm text-muted-foreground">Frequency in the collected sample; supporting / assessed postings. Filtering skills preserves the assessed denominator.</p>
    {partial && <p className="text-sm">Partial collected sample — unavailable or unassessed postings limit coverage.</p>}
    <div className="space-y-2 text-sm">
      {Object.entries(data.scope.coverage.source_outcomes).filter(([, outcome]) => outcome.status === "partial" || outcome.status === "error").map(([source, outcome]) => <div key={source} className="rounded-md border p-3">
        <p className="font-medium">{source}: {outcome.status} · {outcome.usable_count} usable / {outcome.received_count} received</p>
        {outcome.warnings.map((warning, i) => <p key={i}>{warning}</p>)}
      </div>)}
      {data.scope.coverage.extraction_coverage.warnings?.map((warning, i) => <p key={i}>{warning}</p>)}
    </div>
    {!data.rows.length ? <p>No matching skills. Change the filters to inspect evidence.</p> : <>
      {plotted.length ? <EvidenceChart option={option} label="Sample frequency, 0 to 100 percent" className="h-128" onFocus={focus => controller.updateView({focusedCandidateId: focus.candidateId})}/> : <p>No assessed postings or reported frequencies available for this sample.</p>}
      <ul aria-label="Overview values" className="space-y-2">{data.demandRows.map(row => <li key={row.candidateId} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3 text-sm">
        <div><p className="font-medium">{row.label}</p><DemandValue row={row}/>{row.candidate.posting_support === "missing" && <p>Needs job evidence</p>}</div>
        <Button variant="ghost" size="sm" aria-label={`Inspect ${row.label}`} onClick={() => controller.updateView({focusedCandidateId: row.candidateId})}>Inspect</Button>
      </li>)}</ul>
    </>}
    <div className="grid gap-3">{data.observations.slice(0, 2).map(observation => <article key={observation.kind} className="space-y-2 rounded-md border p-4 text-sm">
      <p className="font-medium">{observation.kind === "common_sample" ? "Common in this collected sample" : observation.kind === "occupation_difference" ? "Importance differs by occupation" : "Important across selected roles"}</p>
      <ul className="space-y-1">{observation.values.map((value, i) => <li key={`${value.candidate_id}-${i}`}>
        {data.rows.find(row => row.candidateId === value.candidate_id)?.label ?? value.candidate_id}: {value.occupation_code ? `${occupationName(value.occupation_code)} · ${value.value} / 5 Importance` : `${value.value}% · ${value.supporting_count} / ${value.assessed_count} supporting / assessed`}
      </li>)}</ul>
      <p className="text-muted-foreground">{observation.kind === "common_sample" ? "Collected sample only; assessed postings are the denominator." : `Same O*NET descriptor and release ${data.scope.release}; selected confirmed occupations only.`} {partial ? "Coverage is partial." : `Extraction coverage: ${observation.coverage.extraction_coverage.status ?? "not reported"}.`}</p>
      <div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => controller.updateView({focusedCandidateId: observation.candidate_ids[0], ...(observation.occupation_codes.length ? {activeOccupationCode: observation.occupation_codes[0]} : {})})}>Inspect evidence</Button>
        <Button variant="ghost" size="sm" onClick={() => onAsk({text: observation.kind === "common_sample" ? "Explain this collected-sample observation and its evidence limitations." : "Explain this occupational importance observation and its evidence limitations.", candidateIds: [...observation.candidate_ids], occupationCodes: [...observation.occupation_codes], insightKind: observation.kind})}>Ask agent</Button></div>
    </article>)}</div>
  </section>;
}
