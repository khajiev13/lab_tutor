import {isUsablePostingUrl} from "@/features/market-demand/selection";
import {resolveOnetRating} from "@/features/market-demand/workspace-data";
import type {AnalysisOccupation, DescriptorChoice, OnetAssociation, SkillCandidate, SkillReview} from "@/features/market-demand/types";

export interface CompactComparisonRow {
  candidateIds: string[];
  evidenceIds: string[];
  label: string;
  value: number | null;
  status: string;
  mappings: {candidateId: string; relation: OnetAssociation["relation"]}[];
  sourceUrl: string | null;
}
export interface CompactComparisonModel {
  metric: "frequency" | "IM";
  occupation: AnalysisOccupation | null;
  release: string | null;
  scale: [number, number] | null;
  rows: CompactComparisonRow[];
  insight: string;
}
function sourceUrl(value: string): string | null {
  try {const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? value : null;}
  catch {return null;}
}
function unavailable(candidate: SkillCandidate, status = "no_association", evidenceIds: string[] = []): CompactComparisonRow {
  return {candidateIds: [candidate.candidate_id], evidenceIds, label: candidate.display_name, value: null, status, mappings: [], sourceUrl: null};
}
function descriptor(association: OnetAssociation): string {
  const {release, soc_code, family, element_id} = association.evidence;
  return JSON.stringify([release, soc_code, family, element_id]);
}
function contextRating(association: OnetAssociation): {status: string; value: number | null} {
  const rating = association.evidence.ratings.IM;
  if (!rating) return {status: "missing", value: null};
  if (rating.status !== "reported") return {status: rating.status, value: null};
  if (rating.scale_id !== "IM" || rating.minimum !== 1 || rating.maximum !== 5 ||
    typeof rating.value !== "number" || !Number.isFinite(rating.value) || rating.value < 1 || rating.value > 5) return {status: "missing", value: null};
  return {status: "reported", value: rating.value};
}
function frequency(candidate: SkillCandidate): CompactComparisonRow {
  const {supporting_posting_count: supporting, assessed_posting_count: assessed, percentage} = candidate.job_metrics;
  const reported = Number.isInteger(assessed) && assessed! > 0 && Number.isInteger(supporting) && supporting! >= 0 && supporting! <= assessed! &&
    typeof percentage === "number" && Number.isFinite(percentage) && percentage >= 0 && percentage <= 100;
  return {...unavailable(candidate, reported ? "reported" : "missing"), value: reported ? percentage! : null,
    sourceUrl: candidate.qualifying_posting_links.find(isUsablePostingUrl) ?? null};
}

export function buildCompactComparison(review: SkillReview, candidateIds: string[], metric: "frequency" | "IM", occupationCode: string | null, descriptorChoices: DescriptorChoice[] = []): CompactComparisonModel {
  const byId = new Map(review.candidates.map(candidate => [candidate.candidate_id, candidate]));
  const candidates = [...new Set(candidateIds)].flatMap(id => byId.has(id) ? [byId.get(id)!] : []);
  const occupation = metric === "IM" ? review.analysis_metadata?.occupations.find(role => role.soc_code === occupationCode) ?? null : null;
  const release = metric === "IM" ? review.analysis_metadata?.onet_release ?? null : null;
  const rows: CompactComparisonRow[] = [];
  const shared = new Map<string, CompactComparisonRow>();
  for (const candidate of candidates) {
    if (metric === "frequency") {rows.push(frequency(candidate)); continue;}
    const eligible = [...new Map(candidate.onet_associations.filter(({relation, evidence}) => relation !== "unmatched" &&
      occupation && release && evidence.release === release && evidence.soc_code === occupation.soc_code && evidence.id && evidence.element_id &&
      ["essential", "transferable"].includes(evidence.family)).map(item => [item.evidence.id, item])).values()];
    const choices = descriptorChoices.filter(choice => choice.candidate_id === candidate.candidate_id);
    const chosen = eligible.filter(item => choices.some(choice => choice.evidence_id === item.evidence.id));
    if (choices.length && chosen.length !== 1) {rows.push(unavailable(candidate, "ambiguous", eligible.map(item => item.evidence.id))); continue;}
    if (!chosen.length && new Set(eligible.map(descriptor)).size > 1) {
      rows.push(unavailable(candidate, "ambiguous", eligible.map(item => item.evidence.id))); continue;
    }
    const association = chosen[0] ?? eligible[0];
    if (!association) {rows.push(unavailable(candidate)); continue;}
    // Equivalent ratings retain the shared resolver's stricter candidate semantics.
    // Related/broader rows rate an official descriptor, explicitly labelled as context.
    const resolved = association.relation === "equivalent"
      ? resolveOnetRating(candidate, occupation!.soc_code, "IM", release, association.evidence.id) : contextRating(association);
    const value = resolved.status === "reported" && "value" in resolved ? resolved.value : null;
    const key = descriptor(association);
    let row = shared.get(key);
    if (!row) {
      row = {candidateIds: [], evidenceIds: [], label: association.evidence.label, value, status: resolved.status, mappings: [], sourceUrl: sourceUrl(association.evidence.source_url)};
      shared.set(key, row); rows.push(row);
    } else if (row.value !== value || row.status !== resolved.status) {
      // Contradictory saved values cannot yield an arbitrary numeric bar.
      row.value = null; row.status = "ambiguous";
    }
    row.candidateIds.push(candidate.candidate_id);
    row.evidenceIds.push(association.evidence.id);
    row.mappings.push({candidateId: candidate.candidate_id, relation: association.relation});
  }
  for (const row of shared.values()) {
    const evidenceLabel = row.label;
    row.label = `${evidenceLabel} — ${row.mappings.map(mapping => `${mapping.relation === "broader" ? "broader than" : `${mapping.relation} to`} ${byId.get(mapping.candidateId)!.display_name}`).join("; ")}`;
  }
  const reported = rows.filter(row => row.value !== null);
  let insight = metric === "frequency" ? "No assessed posting frequencies are available for these skills." : "No comparable reported values are available for this occupation and release.";
  if (reported.length && metric === "frequency") {
    const first = byId.get(reported[0].candidateIds[0])!;
    const count = first.job_metrics.supporting_posting_count!;
    const denominator = first.job_metrics.assessed_posting_count!;
    const tie = reported.slice(1).find(row => {
      const other = byId.get(row.candidateIds[0])!;
      return row.value === reported[0].value && other.job_metrics.supporting_posting_count === count && other.job_metrics.assessed_posting_count === denominator;
    });
    insight = tie ? `${first.display_name} and ${tie.label} each appear in ${count} of ${denominator} assessed postings in this collected sample.`
      : `${first.display_name} appears in ${count} of ${denominator} assessed postings in this collected sample.`;
  } else if (reported.length) {
    insight = `${reported[0].label} has reported O*NET importance ${reported[0].value} / 5 for ${occupation!.title}, release ${release}.`;
  }
  return {metric, occupation, release, scale: metric === "frequency" ? [0, 100] : occupation && release ? [1, 5] : null, rows, insight};
}
