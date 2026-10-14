import {expect, it} from "vitest";
import * as postingEvidence from "@/features/market-demand/posting-evidence";
import {reviewFixture} from "@/features/market-demand/__tests__/review-fixtures";
import type {VacancyEvidenceReference} from "@/features/market-demand/types";

function reference(snapshot: string, url: string, phrase: string): VacancyEvidenceReference {
  return {snapshot_id: snapshot, provider: "headhunter", original_url: url, original_phrase: phrase, evidence_kind: "extracted_text", excerpt: `${phrase} in practice`, excerpt_start: 0, excerpt_end: 20, retrieved_at: "2026-10-14", status: "active"};
}

it("groups_two_quotes_and_two_snapshots_under_one_posting", () => {
  const candidate = reviewFixture().candidates[0];
  candidate.evidence_references = [reference("a", "https://jobs.test/1", "Create ETL"), reference("b", "https://jobs.test/1", "Develop ETL/ELT"), reference("c", "https://jobs.test/2", "SQL"), reference("d", "https://jobs.test/3", "Python"), reference("e", "https://jobs.test/4", "Spark")];
  candidate.qualifying_posting_links = [];
  const groups = postingEvidence.groupPostingEvidence(candidate);
  expect(groups).toHaveLength(4);
  expect(groups.flatMap(group => group.references)).toHaveLength(5);
  expect(groups[0].snapshotIds).toEqual(["a", "b"]);
  expect(groups[0].references.map(item => item.original_phrase)).toEqual(["Create ETL", "Develop ETL/ELT"]);
});

it("unions snapshot and exact provider URL identities transitively without losing original links", () => {
  const candidate = reviewFixture().candidates[0];
  candidate.evidence_references = [reference("a", "https://jobs.test/1?view=a", "Create ETL"), reference("b", "https://jobs.test/2", "SQL"), reference("a", "https://jobs.test/2", "Python"), reference("c", "https://jobs.test/1?view=b", "Spark"), {...reference("d", "https://jobs.test/2", "R"), provider: "linkedin"}];
  candidate.qualifying_posting_links = ["https://jobs.test/link-only", "https://jobs.test/2"];
  const groups = postingEvidence.groupPostingEvidence(candidate);
  expect(groups).toHaveLength(4);
  expect(groups[0].snapshotIds).toEqual(["a", "b"]);
  expect(groups[0].originalUrls).toEqual(["https://jobs.test/1?view=a", "https://jobs.test/2"]);
  expect(groups[3]).toMatchObject({originalUrls: ["https://jobs.test/link-only"], snapshotIds: [], references: []});
});

it("deduplicates only identical quotations and keeps same-offset passages from different snapshots", () => {
  const candidate = reviewFixture().candidates[0];
  const first = reference("a", "https://jobs.test/1", "Create ETL");
  candidate.evidence_references = [first, {...first}, {...first, snapshot_id: "b"}, {...first, excerpt: "Another validated passage"}, {...first, evidence_kind: "provider_tag"}];
  candidate.qualifying_posting_links = [];
  const groups = postingEvidence.groupPostingEvidence(candidate);
  expect(groups).toHaveLength(1);
  expect(groups[0].references).toHaveLength(4);
});
