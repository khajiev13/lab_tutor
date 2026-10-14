import type {SkillCandidate, VacancyEvidenceReference} from "@/features/market-demand/types";

export interface PostingEvidenceGroup {
  key: string;
  originalUrls: string[];
  snapshotIds: string[];
  references: VacancyEvidenceReference[];
}

export function postingPassageKey(reference: VacancyEvidenceReference): string {
  return JSON.stringify([reference.snapshot_id, reference.evidence_kind, reference.original_phrase,
    reference.excerpt_start, reference.excerpt_end, reference.excerpt]);
}

export function groupPostingEvidence(candidate: SkillCandidate): PostingEvidenceGroup[] {
  const references = candidate.evidence_references;
  const parents = references.map((_, index) => index);
  const root = (index: number): number => {
    while (parents[index] !== index) index = parents[index];
    return index;
  };
  const identities = new Map<string, number>();
  references.forEach((reference, index) => {
    const keys = [JSON.stringify(["snapshot", reference.snapshot_id])];
    if (reference.original_url) keys.push(JSON.stringify(["url", reference.provider, reference.original_url]));
    keys.forEach(key => {
      const previous = identities.get(key);
      if (previous !== undefined) parents[root(index)] = root(previous);
      identities.set(key, index);
    });
  });
  const groups = new Map<number, PostingEvidenceGroup>();
  const passages = new Map<number, Set<string>>();
  references.forEach((reference, index) => {
    const identity = root(index);
    if (!groups.has(identity)) {
      groups.set(identity, {key: JSON.stringify(["posting", references[identity].snapshot_id]), originalUrls: [], snapshotIds: [], references: []});
      passages.set(identity, new Set());
    }
    const group = groups.get(identity)!;
    if (reference.original_url && !group.originalUrls.includes(reference.original_url)) group.originalUrls.push(reference.original_url);
    if (!group.snapshotIds.includes(reference.snapshot_id)) group.snapshotIds.push(reference.snapshot_id);
    const passage = postingPassageKey(reference);
    if (!passages.get(identity)!.has(passage)) {
      group.references.push(reference);
      passages.get(identity)!.add(passage);
    }
  });
  const result = [...groups.values()];
  for (const url of new Set(candidate.qualifying_posting_links)) {
    if (!result.some(group => group.originalUrls.includes(url))) {
      result.push({key: JSON.stringify(["link", url]), originalUrls: [url], snapshotIds: [], references: []});
    }
  }
  return result;
}
