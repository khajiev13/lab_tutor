import type {
  InsightKind, OccupationReferenceContext, RunReviewContext, SkillReview, WorkspaceContext, WorkspaceViewState,
} from "@/features/market-demand/types";

type ContextResult<T> = {ok: true; context: T} | {ok: false; reason: "save_required" | "invalid_context"};
const invalid = {ok: false, reason: "invalid_context"} as const;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const soc = /^\d{2}-\d{4}\.\d{2}$/;
const views = ["overview", "demand_importance", "occupations", "data"];
const insights = ["common_sample", "occupation_difference", "shared_importance"];
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function onlyKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).every(key => keys.includes(key));
}
function characters(value: string): number {return Array.from(value).length;}
function oneOf(value: unknown, options: string[]): value is string {return typeof value === "string" && options.includes(value);}
export function isWorkspaceMessageValid(value: unknown): value is string {return typeof value === "string" && characters(value) <= 8000;}
function stringList(value: unknown, maximum: number, accepts: (item: string) => boolean, distinct = false): value is string[] {
  return Array.isArray(value) && value.length <= maximum && value.every(item => typeof item === "string" && accepts(item)) &&
    (!distinct || new Set(value).size === value.length);
}
function revision(value: unknown): boolean {return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;}

export function validateWorkspaceContext(context: unknown): context is WorkspaceContext {
  if (!record(context) || context.version !== 1) return false;
  try {
    if (new TextEncoder().encode(JSON.stringify(context)).byteLength > 16 * 1024) return false;
  } catch {return false;}
  if (context.kind === "occupation_reference") {
    return onlyKeys(context, ["kind", "version", "intent", "release", "occupation_codes", "element_ids", "metric"]) &&
      context.intent === "explain" && typeof context.release === "string" && characters(context.release) <= 20 && /^\d+\.\d+$/.test(context.release) &&
      stringList(context.occupation_codes, 5, value => soc.test(value), true) && context.occupation_codes.length >= 1 &&
      stringList(context.element_ids, 20, value => characters(value) >= 1 && characters(value) <= 30, true) && oneOf(context.metric, ["IM", "LV"]);
  }
  if (context.kind !== "run_review" || !onlyKeys(context, ["kind", "version", "intent", "run_id", "expected_candidate_revision", "expected_selection_revision",
    "view", "focused_candidate_id", "candidate_ids", "filters", "occupation_codes", "metric", "descriptor_choices", "insight_kind", "has_unsaved_changes"])) return false;
  const filters = context.filters;
  const choices = context.descriptor_choices;
  return oneOf(context.intent, ["explain", "propose_selection"]) && typeof context.run_id === "string" && uuid.test(context.run_id) &&
    revision(context.expected_candidate_revision) && revision(context.expected_selection_revision) && oneOf(context.view, views) &&
    (context.focused_candidate_id === null || (typeof context.focused_candidate_id === "string" && uuid.test(context.focused_candidate_id))) &&
    stringList(context.candidate_ids, 20, value => uuid.test(value), true) &&
    record(filters) && onlyKeys(filters, ["category_ids", "search", "scope"]) && stringList(filters.category_ids, 10, () => true) &&
    typeof filters.search === "string" && characters(filters.search) <= 120 && oneOf(filters.scope, ["all", "selected"]) &&
    stringList(context.occupation_codes, 5, value => soc.test(value), true) && oneOf(context.metric, ["frequency", "IM", "LV"]) &&
    Array.isArray(choices) && choices.length <= 20 && choices.every(choice => record(choice) && onlyKeys(choice, ["candidate_id", "evidence_id"]) &&
      typeof choice.candidate_id === "string" && uuid.test(choice.candidate_id) && typeof choice.evidence_id === "string" && uuid.test(choice.evidence_id)) &&
    (context.insight_kind === null || oneOf(context.insight_kind, insights)) && typeof context.has_unsaved_changes === "boolean";
}

export function copyWorkspaceContext<T extends WorkspaceContext>(context: T): T {
  return structuredClone(context);
}

export function buildRunReviewContext(input: {
  review: SkillReview; view: WorkspaceViewState; dirty: boolean; intent: RunReviewContext["intent"];
  candidateIds?: string[]; insightKind?: InsightKind | null;
}): ContextResult<RunReviewContext> {
  const {review, view, dirty, intent} = input;
  if (!review.run_id) return invalid;
  if (dirty && (view.filters.scope === "selected" || intent === "propose_selection")) return {ok: false, reason: "save_required"};
  const context: RunReviewContext = {kind: "run_review", version: 1, intent, run_id: review.run_id,
    expected_candidate_revision: review.candidate_revision, expected_selection_revision: review.selection_revision, view: view.view,
    focused_candidate_id: view.focusedCandidateId, candidate_ids: input.candidateIds ?? [], filters: view.filters,
    occupation_codes: view.occupationCodes, metric: view.metric, descriptor_choices: view.descriptorChoices,
    insight_kind: input.insightKind ?? null, has_unsaved_changes: dirty};
  if (!validateWorkspaceContext(context)) return invalid;
  const candidates = new Map(review.candidates.map(candidate => [candidate.candidate_id, candidate]));
  if ((context.focused_candidate_id && !candidates.has(context.focused_candidate_id)) || context.candidate_ids.some(id => !candidates.has(id)) ||
    context.filters.category_ids.some(id => !review.categories.some(category => category.category_id === id)) ||
    context.occupation_codes.some(code => !review.analysis_metadata?.occupations.some(occupation => occupation.soc_code === code))) return invalid;
  const roleChoices = new Set<string>();
  const descriptors = new Map<string, string>();
  for (const choice of context.descriptor_choices) {
    const candidate = candidates.get(choice.candidate_id);
    const association = candidate?.onet_associations.find(row => row.evidence.id === choice.evidence_id);
    if (!association || association.relation !== "equivalent" || association.evidence.release !== review.analysis_metadata?.onet_release ||
      !["essential", "transferable"].includes(association.evidence.family) || !association.evidence.element_id ||
      !context.occupation_codes.includes(association.evidence.soc_code)) return invalid;
    const evidence = association.evidence;
    const roleKey = JSON.stringify([choice.candidate_id, evidence.soc_code]);
    if (roleChoices.has(roleKey)) return invalid;
    roleChoices.add(roleKey);
    const key = JSON.stringify([evidence.release, evidence.family, evidence.element_id]);
    const previous = descriptors.get(choice.candidate_id);
    if ((context.view === "occupations" || context.insight_kind === "occupation_difference" || context.insight_kind === "shared_importance") && previous && previous !== key) return invalid;
    descriptors.set(choice.candidate_id, key);
  }
  return {ok: true, context: copyWorkspaceContext(context)};
}

export function buildOccupationReferenceContext(input: {
  release: string; occupationCodes: string[]; elementIds?: string[]; metric: "IM" | "LV";
}): ContextResult<OccupationReferenceContext> {
  const context: OccupationReferenceContext = {kind: "occupation_reference", version: 1, intent: "explain", release: input.release,
    occupation_codes: input.occupationCodes, element_ids: input.elementIds ?? [], metric: input.metric};
  return validateWorkspaceContext(context) ? {ok: true, context: copyWorkspaceContext(context)} : invalid;
}

export function removeContextFocus(context: WorkspaceContext): WorkspaceContext {
  const copy = copyWorkspaceContext(context);
  if (copy.kind === "occupation_reference") return {...copy, element_ids: []};
  return {...copy, focused_candidate_id: null, candidate_ids: [], descriptor_choices: [], insight_kind: null};
}
