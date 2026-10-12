import {Button} from "@/components/ui/button";
import {Checkbox} from "@/components/ui/checkbox";
import {Table, TableBody, TableCell, TableHead, TableHeader, TableRow} from "@/components/ui/table";
import {EvidenceChart} from "@/features/market-demand/components/EvidenceChart";
import {DemandValue, RatingValue, WorkspacePaging, WorkspaceRatingControls} from "@/features/market-demand/components/WorkspaceDataTable";
import type {WorkspaceViewProps} from "@/features/market-demand/components/WorkspaceDataTable";
import type {ChartFocus} from "@/features/market-demand/types";
import {buildWorkspaceData} from "@/features/market-demand/workspace-data";

export default function WorkspaceCompare({data, controller, onAsk}: WorkspaceViewProps) {
  const scatter = controller.view.view !== "occupations";
  const roles = controller.review?.analysis_metadata?.occupations ?? [];
  const codes = data.scope.occupationCodes.filter(code => data.scope.confirmedOccupationCodes.includes(code));
  // Scatter always reports Importance even if a preceding heatmap used Level.
  const shown = scatter && data.scope.metric !== "IM" && controller.review
    ? buildWorkspaceData(controller.review, controller.draft, {...controller.view, metric: "IM"}) : data;
  const page = shown.heatmapPage;
  const metric = !scatter && controller.view.metric === "LV" ? "LV" : "IM";
  const activeRole = roles.find(role => role.soc_code === controller.view.activeOccupationCode && codes.includes(role.soc_code));
  const roleName = (code: string) => roles.find(role => role.soc_code === code)?.title ?? code;
  const focus = ({candidateId, occupationCode, evidenceId}: ChartFocus) => {
    const candidate = controller.review?.candidates.find(row => row.candidate_id === candidateId);
    const otherChoices = controller.view.descriptorChoices.filter(choice => choice.candidate_id !== candidateId ||
      !candidate?.onet_associations.some(item => item.evidence.id === choice.evidence_id && item.evidence.soc_code === occupationCode));
    controller.updateView({focusedCandidateId: candidateId,
      ...(occupationCode ? {activeOccupationCode: occupationCode} : {}),
      ...(evidenceId ? {descriptorChoices: [...otherChoices, {candidate_id: candidateId, evidence_id: evidenceId}]} : {}),
    });
  };
  const heatmap = page.rows.flatMap((row, y) => codes.flatMap((code, x) => {
    const rating = row.ratings[code];
    return rating?.status === "reported" ? [{value: [x, y, rating.value],
      focus: {candidateId: row.candidateId, occupationCode: code, evidenceId: rating.evidence.id},
      tooltipText: `${row.label} · ${roleName(code)}: ${rating.value} / ${metric === "IM" ? 5 : 7} · ${rating.evidence.label} · ${rating.evidence.release} · ${rating.evidence.element_id}`}]: [];
  }));
  const chart = scatter ? {
    animation: false, grid: {left: 12, right: 28, top: 40, bottom: 48, containLabel: true},
    xAxis: {type: "value", min: 0, max: 100, name: "Sample frequency (%)", nameLocation: "middle", nameGap: 30},
    yAxis: {type: "value", min: 1, max: 5, name: "Importance (1–5)", interval: 1},
    series: [{type: "scatter", symbolSize: 14, itemStyle: {color: "#2563eb"}, data: shown.scatterPoints.map(row => ({value: [row.demand, row.importance],
      focus: {candidateId: row.candidateId, occupationCode: activeRole?.soc_code, evidenceId: row.importanceRating.evidence.id},
      tooltipText: `${row.label} · ${activeRole?.title}: ${row.demand}% sample frequency · ${row.importance} / 5 Importance · ${row.importanceRating.evidence.label} · ${row.importanceRating.evidence.release}`}))}],
  } : {
    animation: false, grid: {left: 12, right: 24, top: 72, bottom: 72, containLabel: true},
    xAxis: {type: "category", position: "top", data: codes.map(roleName), axisLabel: {interval: 0, width: 120, overflow: "truncate"}, splitArea: {show: false}},
    yAxis: {type: "category", inverse: true, data: page.rows.map(row => row.label), axisLabel: {width: 150, overflow: "truncate"}},
    visualMap: {min: metric === "IM" ? 1 : 0, max: metric === "IM" ? 5 : 7, orient: "horizontal", left: "center", bottom: 0,
      text: [metric === "IM" ? "Importance 5" : "Level 7", metric === "IM" ? "Importance 1" : "Level 0"], inRange: {color: ["#bfdbfe", "#1d4ed8"]}},
    series: [{type: "heatmap", data: heatmap, label: {show: true, color: "#18181b", textBorderColor: "#ffffff", textBorderWidth: 3},
      itemStyle: {borderColor: "#71717a", borderWidth: 1}}],
  };
  return <section aria-label="Occupation comparison" className="space-y-4">
    <div className="flex flex-wrap gap-2">
      <Button variant={scatter ? "secondary" : "outline"} size="sm" aria-pressed={scatter} onClick={() => controller.updateView({view: "demand_importance", metric: "IM", page: 1})}>Demand and importance</Button>
      <Button variant={scatter ? "outline" : "secondary"} size="sm" aria-pressed={!scatter} onClick={() => controller.updateView({view: "occupations", page: 1})}>Across occupations</Button>
    </div>
    {!roles.length ? <p>No confirmed occupations. Occupational comparison is unavailable; explore occupation references separately.</p> : <>
      <fieldset className="space-y-2 rounded-md border p-3"><legend className="px-1 text-sm font-medium">Confirmed occupations · display up to 5</legend>
        {roles.map(role => <label key={role.soc_code} className="flex items-center gap-2 text-sm"><Checkbox aria-label={`Display ${role.title}`} checked={codes.includes(role.soc_code)} disabled={!codes.includes(role.soc_code) && codes.length >= 5}
          onCheckedChange={checked => {
            const next = checked === true ? [...codes, role.soc_code] : codes.filter(code => code !== role.soc_code);
            controller.updateView({occupationCodes: next, page: 1, ...(next.includes(controller.view.activeOccupationCode ?? "") ? {} : {activeOccupationCode: null})});
          }}/>{role.title} ({role.soc_code})</label>)}
        <p className="text-xs text-muted-foreground">Hidden confirmed occupations can be displayed immediately. Adding a role outside this run requires a new analysis.</p>
      </fieldset>
      {!codes.length ? <p>No occupations displayed. Re-enable a confirmed occupation above.</p> : <>
        {codes.length === 1 && <p className="text-sm">Single-role reference view · {roleName(codes[0])}</p>}
        {scatter ? <label className="block space-y-1 text-sm"><span className="block">Compare occupation</span>
          <select aria-label="Compare occupation" value={activeRole?.soc_code ?? ""} className="max-w-full rounded-md border bg-background p-2 text-foreground" onChange={event => controller.updateView({activeOccupationCode: event.target.value || null, page: 1})}>
            <option value="">Choose occupation</option>{codes.map(code => <option key={code} value={code}>{roleName(code)} ({code})</option>)}
          </select></label> : <WorkspaceRatingControls data={data} controller={controller}/>}
        <p className="text-sm text-muted-foreground">{scatter ? "Sample frequency (0–100%) and Importance (1–5) for one chosen occupation; no combined score." : `${metric === "IM" ? "Importance (1–5)" : "Level (0–7)"}; comparisons require the same O*NET descriptor and release.`} Unavailable ratings remain inspectable below and in Data.</p>
        {!data.rows.length ? <p>No matching skills. Change the filters to inspect evidence.</p> : <>
          {scatter && !activeRole ? <p>Choose an occupation to compare demand and importance.</p> : (scatter ? shown.scatterPoints.length : heatmap.length) > 0 ?
            <EvidenceChart label={scatter ? `Demand and importance for ${activeRole!.title}` : `${metric === "IM" ? "Importance" : "Level"} by confirmed occupation`} option={chart} className={scatter ? "h-96" : "h-128"} onFocus={focus}/> :
            <p>No reported comparable ratings available. Inspect unavailable reasons below.</p>}
          <WorkspacePaging page={page} controller={controller}/>
          <Table><TableHeader><TableRow><TableHead>Skill</TableHead>{scatter ? <><TableHead>Sample frequency</TableHead><TableHead>Importance · {activeRole?.title ?? "choose occupation"}</TableHead></> : codes.map(code => <TableHead key={code}>{roleName(code)}</TableHead>)}<TableHead>Question</TableHead></TableRow></TableHeader>
            <TableBody>{page.rows.map(row => <TableRow key={row.candidateId}><TableCell className="whitespace-normal"><Button variant="ghost" size="sm" aria-label={`Inspect ${row.label}`} onClick={() => focus({candidateId: row.candidateId})}>{row.label}</Button></TableCell>
              {scatter ? <><TableCell className="whitespace-normal"><DemandValue row={row}/></TableCell><TableCell className="whitespace-normal"><RatingValue rating={row.rating} label={`${row.label} · ${activeRole?.title ?? "occupation"}`} candidateId={row.candidateId} controller={controller}/></TableCell></> : codes.map(code => {
                const rating = row.ratings[code];
                return <TableCell key={code} className="whitespace-normal"><div className="space-y-1"><RatingValue rating={rating} label={`${row.label} · ${roleName(code)}`} candidateId={row.candidateId} controller={controller}/>
                  <Button variant="ghost" size="sm" aria-label={`Inspect ${row.label} · ${roleName(code)}`} onClick={() => focus({candidateId: row.candidateId, occupationCode: code, ...("evidence" in rating && !Array.isArray(rating.evidence) ? {evidenceId: rating.evidence.id} : {})})}>Inspect cell</Button></div></TableCell>;
              })}
              <TableCell><Button variant="ghost" size="sm" aria-label={`Ask about ${row.label}`} onClick={() => onAsk({text: `Explain the occupational evidence and unavailable ratings for ${row.label}.`, candidateIds: [row.candidateId], occupationCodes: scatter && activeRole ? [activeRole.soc_code] : [...codes]})}>Ask agent</Button></TableCell>
            </TableRow>)}</TableBody>
          </Table>
          <Button variant="outline" size="sm" onClick={() => controller.updateView({view: "data", page: 1})}>View all in Data</Button>
        </>}
      </>}
    </>}
  </section>;
}
