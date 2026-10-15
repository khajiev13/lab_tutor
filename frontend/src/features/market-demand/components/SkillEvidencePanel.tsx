import { useEffect, useEffectEvent, useRef, useState } from "react";
import {ArrowUpRight, ChevronRight} from "lucide-react";
import {Dialog, DialogContent, DialogDescription, DialogTitle} from "@/components/ui/dialog";
import {groupPostingEvidence, postingPassageKey} from "@/features/market-demand/posting-evidence";
import type {PostingEvidenceGroup} from "@/features/market-demand/posting-evidence";
import {DescriptorChooser} from "@/features/market-demand/components/WorkspaceDataTable";
import { Button } from "@/components/ui/button";
import { isUsablePostingUrl, priorityLabel } from "@/features/market-demand/selection";
import { fetchPostingEvidence } from "@/features/market-demand/api";
import type { CategoryPriority, DescriptorChoice, OnetMetric, PostingEvidence, PriorityAssessment, RatingResolution, SkillCandidate } from "@/features/market-demand/types";

export function EvidenceLink({url, label}: {url: string; label: string}) {
  if (!isUsablePostingUrl(url)) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer" className="break-all text-primary underline">{label}<ArrowUpRight aria-hidden="true" className="ml-1 inline size-3"/></a>;
}

interface SnapshotCheck {
  posting?: PostingEvidence;
  loading: boolean;
  error?: string;
}

function isPurged(posting: PostingEvidence) {
  return !!posting.purged_at || posting.status === "purged";
}

function PostingDetails({group, checks, load, dialog}: {
  group: PostingEvidenceGroup; checks: Record<string, SnapshotCheck>; load: (ids: string[]) => void; dialog: boolean;
}) {
  const loaded = group.snapshotIds.map(id => checks[id]?.posting).filter((posting): posting is PostingEvidence => !!posting);
  const current = loaded.find(posting => !isPurged(posting));
  const loading = group.snapshotIds.some(id => checks[id]?.loading);
  return <article className="space-y-2 rounded-md border p-3">
    <h3 className="font-medium">{current?.title ?? `Posting ${group.snapshotIds.join(", ") || "link"}`}{current?.company && ` · ${current.company}`}</h3>
    {group.originalUrls.map(url => {
      const identity = current?.title?.trim() || `Posting ${group.snapshotIds.join(", ") || new URL(url).pathname.split("/").filter(Boolean).at(-1) || new URL(url).hostname}`;
      const employer = current?.company?.trim();
      return <p key={url}><EvidenceLink url={url} label={`${dialog ? "Original posting" : "Original job posting"} · ${identity}${employer ? ` · ${employer}` : ""}`}/></p>;
    })}
    {!group.snapshotIds.length && <p>No retained posting content. Retained provenance only.</p>}
    {group.snapshotIds.map(id => {
      const check = checks[id];
      const posting = check?.posting;
      const purged = !!posting && isPurged(posting);
      const reference = group.references.find(item => item.snapshot_id === id)!;
      const availability = posting ? purged ? "purged" : posting.status : check?.loading ? "checking current availability" : check?.error ? "current availability unavailable" : "current availability not checked";
      return <div key={id} className="space-y-2">
        <p>{reference.provider} · retrieved {posting?.retrieved_at ?? reference.retrieved_at} · {availability}</p>
        {check?.error && <p role="alert" className="text-destructive">{check.error}</p>}
        {purged && <p>Posting content unavailable: purged {posting!.purged_at ?? "(date not reported)"}. Retained provenance only.</p>}
        {posting && !purged && <>
          {group.references.filter(item => item.snapshot_id === id).map(item => <div key={postingPassageKey(item)} className="space-y-1">
            <p>{item.evidence_kind === "provider_tag" ? "Provider tag" : "Validated source passage"}: {item.original_phrase}</p>
            {item.excerpt && <blockquote className="border-l-2 pl-2">{item.excerpt}</blockquote>}
            {item.excerpt_start != null && <p>Cleaned text offsets: {item.excerpt_start}–{item.excerpt_end} (end exclusive)</p>}
          </div>)}
          <details><summary className="cursor-pointer"><ChevronRight aria-hidden="true" className="mr-1 inline size-3"/>Full posting description · {posting.title ?? id}</summary>
            <p className="whitespace-pre-wrap">{posting.description_text}</p>
            <details><summary className="cursor-pointer">Original description (text)</summary><pre className="whitespace-pre-wrap break-all">{posting.original_description}</pre></details>
            <details><summary className="cursor-pointer">Full returned provider data</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(posting.raw_payload, null, 2)}</pre></details>
          </details>
        </>}
      </div>;
    })}
    {!!group.snapshotIds.length && <Button variant="outline" size="sm" disabled={loading} onClick={() => load(group.snapshotIds)}>{loading ? "Loading evidence…" : loaded.length ? "Reload full posting evidence" : "Load full posting evidence"}</Button>}
  </article>;
}

// This component lives for one open inspection only. Neither bodies nor pending
// responses survive closing, course/candidate changes, or changed references.
function PostingInspection({courseId, groups, initialIds, onRequested, dialog}: {
  courseId: number; groups: PostingEvidenceGroup[]; initialIds: string[]; onRequested: (id: string) => void; dialog: boolean;
}) {
  const [checks, setChecks] = useState<Record<string, SnapshotCheck>>({});
  const session = useRef<{abort: AbortController; queue: string[]; requested: Set<string>; active: number} | null>(null);
  const load = (ids: string[], reload = true) => {
    const current = session.current;
    if (!current || current.abort.signal.aborted) return;
    const queued = [...new Set(ids)].filter(id => reload || !current.requested.has(id));
    queued.forEach(id => {current.requested.add(id); onRequested(id);});
    setChecks(previous => ({...previous, ...Object.fromEntries(queued.map(id => [id, {loading: true}]))}));
    current.queue.push(...queued);
    const pump = () => {
      while (!current.abort.signal.aborted && current.active < 3 && current.queue.length) {
        const id = current.queue.shift()!;
        current.active++;
        void fetchPostingEvidence(courseId, id, current.abort.signal).then(posting => {
          if (current.abort.signal.aborted) return;
          if (posting.snapshot_id !== id) throw new Error("Posting evidence unavailable: snapshot identity mismatch");
          setChecks(previous => ({...previous, [id]: {posting, loading: false}}));
        }).catch(cause => {
          if (!current.abort.signal.aborted) setChecks(previous => ({...previous, [id]: {loading: false, error: cause instanceof Error ? cause.message : "Posting evidence unavailable"}}));
        }).finally(() => {current.active--; pump();});
      }
    };
    pump();
  };
  const initialize = useEffectEvent(() => load(initialIds, false));
  useEffect(() => {
    const current = {abort: new AbortController(), queue: [], requested: new Set<string>(), active: 0};
    session.current = current;
    initialize();
    return () => current.abort.abort();
  }, []);
  return groups.map(group => <PostingDetails key={group.key} group={group} checks={checks} load={load} dialog={dialog}/>);
}

function metricText(metric: OnetMetric | undefined, name: "IM" | "LV") {
  if (!metric) return `${name}: unavailable (missing)`;
  if (metric.status !== "reported") return `${name}: unavailable (${metric.status})`;
  const [minimum, maximum] = name === "IM" ? [1, 5] : [0, 7];
  if (metric.scale_id !== name || metric.minimum !== minimum || metric.maximum !== maximum ||
    typeof metric.value !== "number" || !Number.isFinite(metric.value) || metric.value < minimum || metric.value > maximum) {
    return `${name}: unavailable (invalid reported value or scale)`;
  }
  return `${name}: ${metric.value} (${minimum}–${maximum})`;
}

interface Props {
  courseId: number;
  priorityAssessment?: PriorityAssessment | null;
  categoryPriority?: CategoryPriority | null;
  candidate: SkillCandidate;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  focusedEvidenceId?: string | null;
  returnFocusTo?: HTMLElement | null;
  ratings?: Record<string, RatingResolution>;
  descriptorChoices?: DescriptorChoice[];
  release?: string | null;
  onChooseDescriptor?: (evidenceId: string, occupationCode: string) => void;
}

export function SkillEvidencePanel({courseId, candidate, open, onOpenChange, focusedEvidenceId, returnFocusTo, ratings, descriptorChoices, release, onChooseDescriptor, priorityAssessment, categoryPriority}: Props) {
  const results = priorityAssessment?.results.filter(result => result.candidate_id === candidate.candidate_id) ?? [];
  const references = new Map(candidate.onet_associations.map(item => [item.evidence.id, item]));
  for (const evidence of priorityAssessment?.references ?? []) {
    const direct = results.find(result => result.direct_reference_id === evidence.id);
    const anchor = results.flatMap(result => result.associations).find(item => item.reference_id === evidence.id);
    if (!direct && !anchor) continue;
    const legacy = references.get(evidence.id);
    references.set(evidence.id, legacy ? {...legacy, evidence} : {evidence,
      relation: direct ? "equivalent" : anchor!.relation, mapping_method: "Skill importance assessment",
      rationale: direct?.explanation ?? anchor!.rationale});
  }
  const associations = [...references.values()];
  // Only request identities survive a disclosure session. Full bodies are
  // discarded on close and previously requested snapshots re-resolve on reopen.
  const [requestedPostings, setRequestedPostings] = useState<string[]>([]);
  const [inspecting, setInspecting] = useState(false);
  const groups = groupPostingEvidence(candidate);
  const sessionKey = JSON.stringify([courseId, candidate.candidate_id, candidate.evidence_references, candidate.qualifying_posting_links]);
  const priority = candidate.priority;
  const candidatePostingIds = new Set(candidate.evidence_references
    .filter(item => !["purged", "removed", "unavailable"].includes(item.status))
    .map(item => item.snapshot_id));
  const content = <div className="space-y-2 text-xs">
      {priorityAssessment && priority && <section aria-label="Skill importance evidence" className="space-y-2 rounded-md border p-3">
        <h3 className="font-medium">Importance · {priorityLabel(priority)}</h3>
        <p>{priority.basis === "onet" ? "Official O*NET importance for the matched role." : priority.basis === "ai_estimate" ? "AI estimate across assessed roles." : priority.basis === "onet_aggregate" ? "Lab Tutor average of official O*NET role ratings." : "No importance score available."}</p>
        <p>{priority.scored_contexts} of {priority.expected_contexts} role contexts assessed{priority.complete ? "." : " · Partial coverage."}</p>
        {categoryPriority && <p>Category: {priorityLabel(categoryPriority)} · {categoryPriority.scored_count} of {categoryPriority.eligible_count} skills assessed.</p>}
        <details><summary className="cursor-pointer">Assessment technical details</summary>
          <p>Lab Tutor summaries and AI estimates are not official O*NET ratings.</p>
          {categoryPriority && <p>Category sources: {categoryPriority.onet_count} O*NET, {categoryPriority.estimated_count} estimated, {categoryPriority.partial_count} partial, {categoryPriority.unavailable_count} unavailable.</p>}
          <p>Release: {priorityAssessment.release ?? "unavailable"} · model: {priorityAssessment.model_id} · policy: {priorityAssessment.policy_version}</p>
          {priorityAssessment.error_reasons.map((text, index) => <p key={index}>Assessment limitation: {text}</p>)}
        </details>
        {results.map(result => {
          const contexts = priorityAssessment.contexts.filter(item => result.soc_code === null
            ? item.soc_code === null && `unmapped:${item.group_id}` === result.context_key
            : item.soc_code === result.soc_code && item.posting_ids.some(id => candidatePostingIds.has(id)));
          return <div key={result.context_key} className="space-y-1 border-t pt-2">
            {!contexts.length && <p>Role unavailable · {result.soc_code ?? "No occupation code"}</p>}
            {contexts.map(context => <div key={context.group_id}>
              <p>{context.occupation_title ?? "Role unavailable"} · {result.soc_code ?? "No occupation code"}{context.inferred ? " · Inferred from postings" : ""}</p>
              <p>{context.rationale}</p>
              {context.unavailable_reason && <p>{context.unavailable_reason}</p>}
            </div>)}
            <p>{result.basis === "onet" ? `O*NET source value: ${result.official_value ?? "unavailable"}/5` :
              result.basis === "ai_estimate" ? `AI estimate: ${result.estimate ?? "unavailable"}/5` : "Not assessed"}</p>
            <p>{result.explanation}</p>
            {result.direct_reference_id && <p>Matched descriptor: {references.get(result.direct_reference_id)?.evidence.label ?? "Reference details unavailable"}</p>}
            {!!result.supporting_evidence_ids.length && <p>{new Set(result.supporting_evidence_ids).size} verified passages · see posting evidence below.</p>}
            {result.associations.map(item => <p key={item.reference_id}>{item.relation} reference: {references.get(item.reference_id)?.evidence.label ?? "Reference details unavailable"} · {item.rationale}</p>)}
            {result.limitations.map((text, index) => <p key={index}>Limitation: {text}</p>)}
            {result.unavailable_reason && <p>{result.unavailable_reason}</p>}
          </div>;
        })}
      </section>}
      {!!candidate.original_labels.length && <p>Original skill labels: {[...new Set(candidate.original_labels)].join(" · ")}</p>}
      <PostingInspection key={sessionKey} courseId={courseId} groups={groups} dialog={open !== undefined}
        initialIds={groups.flatMap(group => group.snapshotIds).filter(id => open !== undefined || requestedPostings.includes(`${courseId}-${id}`))}
        onRequested={id => setRequestedPostings(previous => previous.includes(`${courseId}-${id}`) ? previous : [...previous, `${courseId}-${id}`])}/>
      {candidate.posting_support === "missing" && <p>Needs job evidence — no qualifying posting evidence available.</p>}
      {!associations.length && <p>O*NET unavailable: no association.</p>}
      {ratings && Object.entries(ratings).map(([code, rating]) => <div key={code} className="space-y-1">
        <p>{code}: {rating.status === "reported" ? `${rating.value} / ${rating.metric === "IM" ? 5 : 7}` : rating.status === "ambiguous" ? "Multiple matched descriptors" : `Unavailable: ${rating.status.replaceAll("_", " ")}`}</p>
        {onChooseDescriptor && <DescriptorChooser candidate={candidate} occupationCode={code}
          release={release ?? ("descriptorKey" in rating ? rating.descriptorKey[0] : rating.status === "ambiguous" ? rating.evidence[0]?.release ?? null : null)}
          label={`${candidate.display_name} · ${code}`} ariaLabel={`Inspector descriptor for ${candidate.display_name} · ${code}`}
          selectedEvidenceIds={descriptorChoices ? descriptorChoices.filter(choice => choice.candidate_id === candidate.candidate_id).map(choice => choice.evidence_id) : "evidence" in rating && !Array.isArray(rating.evidence) ? [rating.evidence.id] : []}
          onChoose={id => onChooseDescriptor(id, code)}/>}
      </div>)}
      {associations.map(({evidence, relation, mapping_method, rationale}) => <div key={evidence.id} data-evidence-id={evidence.id} className="space-y-2 rounded-md border p-3">
        {focusedEvidenceId === evidence.id && <p className="font-medium">Focused chart evidence</p>}
        <p><EvidenceLink url={evidence.source_url} label={`O*NET reference: ${evidence.label} (${evidence.occupation_title})`}/></p>
        <p>{evidence.release} · {evidence.family} · {evidence.element_id} · {evidence.soc_code} · {evidence.id}</p>
        <p>{relation === "equivalent" ? "Equivalent association" : `${relation} contextual reference; not a plotted candidate rating`} · {mapping_method} · {rationale}</p>
        <p>{evidence.definition}</p>
        {evidence.workplace_example && <p>Workplace example: {evidence.workplace_example}</p>}
        {evidence.family !== "software" && (["IM", "LV"] as const).map(name => <div key={name}>
          <p>{metricText(evidence.ratings[name], name)}</p>
          {evidence.ratings[name] && <><p>Rating date: {evidence.ratings[name]!.date ?? "not reported"} · declared scale {evidence.ratings[name]!.minimum}–{evidence.ratings[name]!.maximum}</p>
            <pre className="whitespace-pre-wrap break-all">Quality: {JSON.stringify(evidence.ratings[name]!.quality, null, 2)}</pre></>}
        </div>)}
        {evidence.family === "software" && <p>Software-reference flags are categorical context, not importance or level.</p>}
        {!!Object.keys(evidence.flags).length && <pre className="whitespace-pre-wrap break-all">Flags: {JSON.stringify(evidence.flags, null, 2)}</pre>}
        <p>{evidence.attribution}</p>
      </div>)}
    </div>;
  if (open !== undefined) return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent maxWidthClassName="sm:max-w-3xl" className="max-h-[85dvh] overflow-y-auto" onCloseAutoFocus={event => {if (returnFocusTo?.isConnected) {event.preventDefault(); returnFocusTo.focus();}}}>
      <DialogTitle>Evidence for {candidate.display_name}</DialogTitle>
      <DialogDescription>Original postings and O*NET reference details for this skill.</DialogDescription>
      {open && content}
    </DialogContent>
  </Dialog>;
  return <details className="space-y-2 text-xs" onToggle={event => {
    if (event.target === event.currentTarget) setInspecting(event.currentTarget.open);
  }}>
    <summary className="cursor-pointer font-medium"><ChevronRight aria-hidden="true" className="mr-1 inline size-3"/>Evidence for {candidate.display_name}</summary>
    {inspecting && content}
  </details>;
}
