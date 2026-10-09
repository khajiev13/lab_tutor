import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { isUsablePostingUrl } from "@/features/market-demand/selection";
import { fetchPostingEvidence } from "@/features/market-demand/api";
import type { PostingEvidence, SkillCandidate, VacancyEvidenceReference } from "@/features/market-demand/types";

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

export function SkillEvidencePanel({courseId, candidate}: {courseId: number; candidate: SkillCandidate}) {
  return (
    <details className="space-y-2 text-xs">
      <summary className="cursor-pointer font-medium">Evidence for {candidate.display_name}</summary>
      {candidate.evidence_references.map(item => <PostingDetails key={item.snapshot_id} courseId={courseId} evidence={item}/>)}
      {candidate.qualifying_posting_links.filter(url => !candidate.evidence_references.some(item => item.original_url === url)).map(url => <p key={url}><EvidenceLink url={url} label="Original job posting"/></p>)}
      {candidate.onet_associations.map(({evidence}) => <p key={evidence.id}><EvidenceLink url={evidence.source_url} label={`O*NET reference: ${evidence.label} (${evidence.occupation_title})`}/></p>)}
    </details>
  );
}
