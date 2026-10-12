import { useEffect, useRef, useState } from "react";
import {DescriptorChooser} from "@/features/market-demand/components/WorkspaceDataTable";
import { Button } from "@/components/ui/button";
import { isUsablePostingUrl } from "@/features/market-demand/selection";
import { fetchPostingEvidence } from "@/features/market-demand/api";
import type { DescriptorChoice, OnetMetric, PostingEvidence, RatingResolution, SkillCandidate, VacancyEvidenceReference } from "@/features/market-demand/types";

export function EvidenceLink({url, label}: {url: string; label: string}) {
  if (!isUsablePostingUrl(url)) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer" className="break-all text-primary underline">{label}</a>;
}

function PostingDetails({courseId, evidence}: {courseId: number; evidence: VacancyEvidenceReference}) {
  const [posting, setPosting] = useState<PostingEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => () => abortRef.current?.abort(), [courseId, evidence.snapshot_id]);
  const load = async () => {
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPostingEvidence(courseId, evidence.snapshot_id, abort.signal);
      if (!abort.signal.aborted) setPosting(response);
    } catch (cause) {
      if (!abort.signal.aborted) setError(cause instanceof Error ? cause.message : "Posting evidence unavailable");
    } finally {
      if (!abort.signal.aborted) setLoading(false);
    }
  };
  return (
    <div className="space-y-2 rounded-md border p-3">
      <EvidenceLink url={evidence.original_url} label="Original job posting"/>
      <p>{evidence.provider} · retrieved {evidence.retrieved_at} · {evidence.status}</p>
      <p>{evidence.evidence_kind === "provider_tag" ? "Provider tag" : "Validated source passage"}: {evidence.original_phrase}</p>
      {evidence.excerpt && <blockquote className="border-l-2 pl-2">{evidence.excerpt}</blockquote>}
      {evidence.excerpt_start != null && <p>Cleaned text offsets: {evidence.excerpt_start}–{evidence.excerpt_end} (end exclusive)</p>}
      {!posting && <Button variant="outline" size="sm" disabled={loading} onClick={() => void load()}>{loading ? "Loading evidence…" : "Load full posting evidence"}</Button>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {posting && (posting.purged_at ? <p>Posting content unavailable: purged {posting.purged_at}. Retained provenance only.</p> : (
        <div className="space-y-2">
          <p>{posting.title} · {posting.company}</p>
          <p className="whitespace-pre-wrap">{posting.description_text}</p>
          <details><summary className="cursor-pointer">Original description (text)</summary><pre className="whitespace-pre-wrap break-all">{posting.original_description}</pre></details>
          <details><summary className="cursor-pointer">Full returned provider data</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(posting.raw_payload, null, 2)}</pre></details>
        </div>
      ))}
    </div>
  );
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
  candidate: SkillCandidate;
  focusedEvidenceId?: string | null;
  ratings?: Record<string, RatingResolution>;
  descriptorChoices?: DescriptorChoice[];
  release?: string | null;
  onChooseDescriptor?: (evidenceId: string, occupationCode: string) => void;
}

export function SkillEvidencePanel({courseId, candidate, focusedEvidenceId, ratings, descriptorChoices, release, onChooseDescriptor}: Props) {
  const associations = [...new Map(candidate.onet_associations.map(item => [item.evidence.id, item])).values()];
  return (
    <details className="space-y-2 text-xs">
      <summary className="cursor-pointer font-medium">Evidence for {candidate.display_name}</summary>
      {candidate.evidence_references.map(item => <PostingDetails key={`${courseId}-${item.snapshot_id}`} courseId={courseId} evidence={item}/>)}
      {candidate.qualifying_posting_links.filter(url => !candidate.evidence_references.some(item => item.original_url === url)).map(url => <p key={url}><EvidenceLink url={url} label="Original job posting"/></p>)}
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
    </details>
  );
}
