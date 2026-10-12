import type {SelectionDraft} from "@/features/market-demand/selection";
import type {
  DescriptorChoice, DescriptorKey, NormalizedWorkspaceScope, OnetEvidence, PatternObservation,
  RatingResolution, SkillCandidate, SkillReview, WorkspaceData, WorkspacePage, WorkspaceRow, WorkspaceViewState,
} from "@/features/market-demand/types";

// Shared backend contract: ECMAScript WhiteSpace/LineTerminator edge trim after NFKC.
// Native trim removes BOM, retains NEL/Python-only controls, and preserves internal characters.
function normalizedText(value: string): string {
  return value.normalize("NFKC").trim().toLowerCase();
}

// JavaScript's string comparison uses UTF-16 units, unlike Python's code points.
function compareText(a: string, b: string): number {
  const left = Array.from(a, char => char.codePointAt(0)!);
  const right = Array.from(b, char => char.codePointAt(0)!);
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return left.length - right.length;
}
function compareCandidates(a: SkillCandidate, b: SkillCandidate): number {
  return compareText(normalizedText(a.display_name), normalizedText(b.display_name)) || compareText(a.candidate_id, b.candidate_id);
}
function descriptorKey(evidence: OnetEvidence): DescriptorKey {
  return [evidence.release, evidence.family, evidence.element_id];
}
function sameDescriptor(a: DescriptorKey, b: DescriptorKey): boolean {
  return a.every((value, index) => value === b[index]);
}
function eligibleEvidence(candidate: SkillCandidate, occupationCode: string, release: string | null): OnetEvidence[] {
  const unique = new Map<string, OnetEvidence>();
  for (const {relation, evidence} of candidate.onet_associations) {
    if (relation === "equivalent" && evidence.id && release && evidence.release === release &&
      evidence.soc_code === occupationCode && ["essential", "transferable"].includes(evidence.family) && evidence.element_id) {
      if (!unique.has(evidence.id)) unique.set(evidence.id, evidence);
    }
  }
  return [...unique.values()].sort((a, b) => compareText(a.id, b.id));
}

export function resolveOnetRating(candidate: SkillCandidate, occupationCode: string, metric: "IM" | "LV", release: string | null, evidenceId?: string): RatingResolution {
  const rows = eligibleEvidence(candidate, occupationCode, release);
  const chosen = evidenceId ? rows.find(row => row.id === evidenceId) : undefined;
  if (evidenceId && !chosen) return {status: "no_association"};
  if (!rows.length) return {status: "no_association"};
  if (!chosen && rows.some(row => !sameDescriptor(descriptorKey(row), descriptorKey(rows[0])))) {
    return {status: "ambiguous", evidence: rows};
  }
  const evidence = chosen ?? rows[0];
  const key = descriptorKey(evidence);
  const rating = evidence.ratings?.[metric];
  if (!rating) return {status: "missing", evidence, descriptorKey: key};
  if (rating.status !== "reported") return {status: rating.status, evidence, descriptorKey: key};
  const [minimum, maximum] = metric === "IM" ? [1, 5] : [0, 7];
  if (rating.scale_id !== metric || rating.minimum !== minimum || rating.maximum !== maximum ||
    typeof rating.value !== "number" || !Number.isFinite(rating.value) || rating.value < minimum || rating.value > maximum) {
    return {status: "missing", evidence, descriptorKey: key};
  }
  return {status: "reported", value: rating.value, metric, evidence, descriptorKey: key};
}

function resolveChosenRating(candidate: SkillCandidate, code: string, metric: "IM" | "LV", release: string | null, choices: DescriptorChoice[]): RatingResolution {
  const rows = eligibleEvidence(candidate, code, release);
  const chosen = rows.filter(row => choices.some(choice => choice.candidate_id === candidate.candidate_id && choice.evidence_id === row.id));
  if (chosen.length > 1) return {status: "ambiguous", evidence: chosen};
  return resolveOnetRating(candidate, code, metric, release, chosen[0]?.id);
}
function comparisonRatings(candidate: SkillCandidate, codes: string[], metric: "IM" | "LV", scope: NormalizedWorkspaceScope): Record<string, RatingResolution> {
  const ratings = Object.fromEntries(codes.map(code => [code, resolveChosenRating(candidate, code, metric, scope.release, scope.descriptorChoices)]));
  const descriptors = Object.values(ratings).filter(cell => "descriptorKey" in cell).map(cell => cell.descriptorKey);
  if (descriptors.some(key => !sameDescriptor(key, descriptors[0]))) {
    // Each role remains inspectable, but unlike descriptors cannot share a comparison scale.
    for (const code of codes) {
      if (ratings[code].status === "reported") ratings[code] = {status: "ambiguous", evidence: eligibleEvidence(candidate, code, scope.release)};
    }
  }
  return ratings;
}
function demand(candidate: SkillCandidate): number | null {
  const {percentage, assessed_posting_count: assessed} = candidate.job_metrics;
  return Number.isInteger(assessed) && assessed! > 0 && typeof percentage === "number" &&
    Number.isFinite(percentage) && percentage >= 0 && percentage <= 100 ? percentage : null;
}
function compareNumbers(a: number | null, b: number | null, direction: "asc" | "desc"): number {
  if (a === null) return b === null ? 0 : 1;
  if (b === null) return -1;
  return direction === "asc" ? a - b : b - a;
}
function pageRows(rows: WorkspaceRow[], page: number, pageSize: number): WorkspacePage {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(pageCount, Math.max(1, Number.isInteger(page) ? page : 1));
  const offset = (current - 1) * pageSize;
  return {rows: rows.slice(offset, offset + pageSize), page: current, pageSize, pageCount, total: rows.length,
    start: rows.length ? offset + 1 : 0, end: Math.min(offset + pageSize, rows.length)};
}

export function buildWorkspaceData(review: SkillReview, draft: SelectionDraft, view: WorkspaceViewState): WorkspaceData {
  const selected = new Set(draft.selected_candidate_ids);
  const search = normalizedText(view.filters.search);
  const candidates = review.candidates.filter(candidate =>
    (!view.filters.category_ids.length || view.filters.category_ids.includes(candidate.category_id)) &&
    (!search || [candidate.display_name, ...candidate.aliases, ...candidate.original_labels].some(label => normalizedText(label).includes(search))) &&
    (view.filters.scope !== "selected" || selected.has(candidate.candidate_id))).sort(compareCandidates);
  const confirmedOccupationCodes = review.analysis_metadata?.occupations.map(row => row.soc_code) ?? [];
  const occupationCodes = [...new Set(view.occupationCodes)].slice(0, 5);
  const scope: NormalizedWorkspaceScope = {candidates, release: review.analysis_metadata?.onet_release ?? null,
    confirmedOccupationCodes, occupationCodes, metric: view.metric, descriptorChoices: view.descriptorChoices.map(choice => ({...choice})),
    coverage: structuredClone({extraction_coverage: review.extraction_coverage, source_outcomes: review.source_outcomes})};
  const metric = view.metric === "LV" ? "LV" : "IM";
  const activeRole = view.activeOccupationCode && confirmedOccupationCodes.includes(view.activeOccupationCode) && occupationCodes.includes(view.activeOccupationCode)
    ? view.activeOccupationCode : null;
  const rows: WorkspaceRow[] = candidates.map(candidate => ({candidateId: candidate.candidate_id, label: candidate.display_name, candidate,
    selected: selected.has(candidate.candidate_id), demand: demand(candidate),
    rating: activeRole ? resolveChosenRating(candidate, activeRole, metric, scope.release, scope.descriptorChoices) : {status: "no_association"},
    ratings: comparisonRatings(candidate, occupationCodes.filter(code => confirmedOccupationCodes.includes(code)), metric, scope)}));
  const sortedRows = [...rows].sort((a, b) => {
    const field = view.sort.field;
    if (field === "name") return (view.sort.direction === "asc" ? 1 : -1) * compareText(normalizedText(a.label), normalizedText(b.label)) || compareText(a.candidateId, b.candidateId);
    const value = (row: WorkspaceRow) => field === "frequency" ? row.demand : row.rating.status === "reported" ? row.rating.value : null;
    return compareNumbers(value(a), value(b), view.sort.direction) || compareCandidates(a.candidate, b.candidate);
  });
  const scatterPoints: WorkspaceData["scatterPoints"] = [];
  if (activeRole) {
    for (const row of rows) {
      const importanceRating = resolveChosenRating(row.candidate, activeRole, "IM", scope.release, scope.descriptorChoices);
      if (row.demand !== null && importanceRating.status === "reported") {
        scatterPoints.push({...row, demand: row.demand, importance: importanceRating.value, importanceRating});
      }
    }
  }
  return {scope, rows, demandRows: [...rows].sort((a, b) => compareNumbers(a.demand, b.demand, "desc") || compareCandidates(a.candidate, b.candidate)).slice(0, 12),
    scatterPoints, heatmapPage: pageRows(occupationCodes.some(code => confirmedOccupationCodes.includes(code)) ? sortedRows : [], view.page, 12), tablePage: pageRows(sortedRows, view.page, 25), observations: derivePatternObservations(scope)};
}

export function derivePatternObservations(scope: NormalizedWorkspaceScope): PatternObservation[] {
  const result: PatternObservation[] = [];
  let common = scope.candidates.filter(candidate => {
    const {supporting_posting_count: support, assessed_posting_count: assessed, percentage} = candidate.job_metrics;
    return Number.isInteger(assessed) && assessed! >= 10 && Number.isInteger(support) && support! >= 3 && support! <= assessed! &&
      typeof percentage === "number" && Number.isFinite(percentage) && percentage >= 50 && percentage <= 100;
  }).sort((a, b) => b.job_metrics.percentage! - a.job_metrics.percentage! || compareCandidates(a, b));
  if (common.length) {
    const denominator = common[0].job_metrics.assessed_posting_count!;
    common = common.filter(row => row.job_metrics.assessed_posting_count === denominator).slice(0, 3);
    result.push({kind: "common_sample", candidate_ids: common.map(row => row.candidate_id), occupation_codes: [], descriptor_keys: [],
      values: common.map(row => ({candidate_id: row.candidate_id, occupation_code: null, value: row.job_metrics.percentage!,
        supporting_count: row.job_metrics.supporting_posting_count!, assessed_count: denominator})), coverage: structuredClone(scope.coverage)});
  }
  if (scope.occupationCodes.length < 2 || !scope.occupationCodes.every(code => scope.confirmedOccupationCodes.includes(code))) return result;
  const used = new Set(common.map(row => row.candidate_id));
  const differences: {spread: number; candidate: SkillCandidate; observation: PatternObservation}[] = [];
  const shared: {candidate: SkillCandidate; observation: PatternObservation}[] = [];
  for (const candidate of scope.candidates) {
    if (used.has(candidate.candidate_id)) continue;
    const cells = scope.occupationCodes.map(code => resolveChosenRating(candidate, code, "IM", scope.release, scope.descriptorChoices));
    if (!cells.every((cell): cell is Extract<RatingResolution, {status: "reported"}> => cell.status === "reported")) continue;
    if (!cells.every(cell => sameDescriptor(cell.descriptorKey, cells[0].descriptorKey))) continue;
    const values = cells.map(cell => cell.value);
    const spread = Math.max(...values) - Math.min(...values);
    const observation: PatternObservation = {kind: spread >= 1 ? "occupation_difference" : "shared_importance",
      candidate_ids: [candidate.candidate_id], occupation_codes: [...scope.occupationCodes], descriptor_keys: [[...cells[0].descriptorKey]],
      values: cells.map((cell, index) => ({candidate_id: candidate.candidate_id, occupation_code: scope.occupationCodes[index],
        value: cell.value, supporting_count: null, assessed_count: null})), coverage: structuredClone(scope.coverage)};
    if (spread >= 1) differences.push({spread, candidate, observation});
    else if (Math.min(...values) >= 4) shared.push({candidate, observation});
  }
  const difference = differences.sort((a, b) => b.spread - a.spread || compareCandidates(a.candidate, b.candidate))[0];
  const important = shared.sort((a, b) => compareCandidates(a.candidate, b.candidate))[0];
  if (difference) result.push(difference.observation);
  else if (important) result.push(important.observation);
  return result.slice(0, 2);
}
