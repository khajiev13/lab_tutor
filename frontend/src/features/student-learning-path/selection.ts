import { skillBankKey } from '@/features/curriculum/skill-bank-display';
import type { BuildSelectedSkillInput, PrerequisiteEdge, SkillBanksResponse, StudentSkillBankJobPosting, StudentSkillBankSkill } from '@/features/student-learning-path/api';
import type { PrerequisiteReviewItem } from '@/features/student-learning-path/components/PrerequisiteReviewDialog';

export type SkillSource = 'book' | 'market';
export interface StudentSkillChoice extends StudentSkillBankSkill { key: string; source: SkillSource }
export interface ResolvedPrerequisiteEdge extends PrerequisiteEdge {
  prerequisite_key: string;
  dependent_key: string;
  prerequisite_selectable: boolean;
  availability_reason?: string | null;
}

export function isSkillAvailable(skill: StudentSkillBankSkill | undefined) {
  if (!skill) return false;
  if (skill.skill_reference_id) return skill.available_for_new_selection === true && skill.projection_status === 'projected';
  return skill.available_for_new_selection !== false;
}

export function collectStudentSkills(banks: SkillBanksResponse | null) {
  const choices = new Map<string, StudentSkillChoice>();
  const add = (skill: StudentSkillBankSkill, fallback: SkillSource) => {
    const source = skill.source === 'book' || skill.source === 'market' ? skill.source : fallback;
    const key = skillBankKey(skill, source);
    if (!choices.has(key)) choices.set(key, {...skill, key, source});
  };
  for (const book of banks?.book_skill_banks ?? []) for (const chapter of book.chapters) for (const skill of chapter.skills) add(skill, 'book');
  for (const posting of banks?.market_skill_bank ?? []) for (const skill of posting.skills) add(skill, 'market');
  for (const skill of banks?.career_skill_bank ?? []) {
    const key = `reference:${skill.skill_reference_id}`;
    choices.set(key, {...choices.get(key), ...skill, name: skill.label, key, source: skill.source});
  }
  return choices;
}

export function persistedStudentSelections(banks: SkillBanksResponse | null, choices: Map<string, StudentSkillChoice>) {
  const selected = new Set((banks?.selected_skill_reference_ids ?? []).map((id) => `reference:${id}`));
  for (const [key, skill] of choices) {
    if (skill.skill_reference_id) {
      if (banks?.selected_skill_reference_ids === undefined && skill.is_selected) selected.add(key);
      continue;
    }
    const uniqueLabel = [...choices.values()].filter((choice) => choice.name === skill.name).length === 1;
    if (skill.is_selected ?? (uniqueLabel && banks?.selected_skill_names.includes(skill.name))) selected.add(key);
  }
  // Keep saved legacy work locked even if it is no longer offered in a bank.
  for (const name of banks?.selected_skill_names ?? []) {
    if (![...choices.values()].some((skill) => skill.name === name)) selected.add(`saved:${name}`);
  }
  return selected;
}

export function hasSavedSelections(banks: SkillBanksResponse | null | undefined) {
  return Boolean(banks && (banks.selected_skill_names.length || banks.selected_skill_reference_ids?.length));
}

export function postingSkillChoices(posting: StudentSkillBankJobPosting, choices: Map<string, StudentSkillChoice>) {
  const skills = new Map<string, SkillSource>();
  for (const skill of posting.skills) {
    const key = skillBankKey(skill, 'market');
    const choice = choices.get(key);
    if (choice && isSkillAvailable(choice)) skills.set(key, choice.source);
  }
  return skills;
}

export function mergeDraftSelectedSkills(explicit: Map<string, SkillSource>, postings: Map<string, SkillSource>, excluded: Set<string>) {
  const merged = new Map(explicit);
  for (const [key, source] of postings) if (!excluded.has(key) && !merged.has(key)) merged.set(key, source);
  return merged;
}

export function buildSelectionPayload(selected: Map<string, SkillSource>, choices: Map<string, StudentSkillChoice>) {
  const selectedSkills: BuildSelectedSkillInput[] = [];
  const skillReferenceIds: string[] = [];
  for (const [key, source] of selected) {
    if (key.startsWith('reference:')) skillReferenceIds.push(key.slice('reference:'.length));
    else {
      const choice = choices.get(key);
      if (choice) selectedSkills.push({name: choice.name, source});
    }
  }
  return {selectedSkills, skillReferenceIds};
}

export function studentPeerCount(skill: StudentSkillBankSkill, banks: SkillBanksResponse | null) {
  return skill.skill_reference_id
    ? banks?.peer_selection_counts_by_reference?.[skill.skill_reference_id] ?? skill.peer_count ?? 0
    : skill.peer_count ?? banks?.peer_selection_counts[skill.name] ?? 0;
}

export function buildPrerequisiteIndex(edges: PrerequisiteEdge[], choices: Map<string, StudentSkillChoice>) {
  const resolve = (id: string | null | undefined, name: string) => {
    if (id) return { key: `reference:${id}`, choice: choices.get(`reference:${id}`) };
    const matches = [...choices.values()].filter((skill) => skill.name === name);
    return matches.length === 1 ? { key: matches[0]!.key, choice: matches[0] } : { key: `ambiguous:${name}`, choice: undefined };
  };
  const index = new Map<string, ResolvedPrerequisiteEdge[]>();
  for (const edge of edges) {
    const prerequisite = resolve(edge.prerequisite_skill_reference_id, edge.prerequisite_name);
    const dependent = resolve(edge.dependent_skill_reference_id, edge.dependent_name);
    const dependentKeys = dependent.choice || edge.dependent_skill_reference_id ? [dependent.key] : [...choices.values()].filter((skill) => skill.name === edge.dependent_name).map((skill) => skill.key);
    for (const key of dependentKeys) {
      const existing = index.get(key) ?? [];
      if (existing.some((item) => item.prerequisite_key === prerequisite.key)) continue;
      existing.push({...edge, prerequisite_key: prerequisite.key, dependent_key: dependent.key,
        prerequisite_name: prerequisite.choice?.name ?? edge.prerequisite_name,
        dependent_name: choices.get(key)?.name ?? edge.dependent_name,
        prerequisite_selectable: Boolean(dependent.choice) && isSkillAvailable(prerequisite.choice),
        availability_reason: !dependent.choice ? 'Dependent identity is unavailable or ambiguous' :
          prerequisite.choice?.availability_reason ?? (!prerequisite.choice ? 'Prerequisite identity is unavailable or ambiguous' : null)});
      index.set(key, existing);
    }
  }
  return index;
}

export function collectTransitivePrerequisites(selected: Set<string>, index: Map<string, ResolvedPrerequisiteEdge[]>) {
  const visited = new Set<string>();
  const queue = [...selected];
  while (queue.length) for (const edge of index.get(queue.shift()!) ?? []) {
    if (visited.has(edge.prerequisite_key)) continue;
    visited.add(edge.prerequisite_key);
    queue.push(edge.prerequisite_key);
  }
  return visited;
}

export function buildPrerequisiteReviewItems(selected: Set<string>, acknowledged: Set<string>, index: Map<string, ResolvedPrerequisiteEdge[]>): PrerequisiteReviewItem[] {
  const items = new Map<string, PrerequisiteReviewItem>();
  const visited = new Set<string>();
  const queue = [...selected];
  while (queue.length) {
    const key = queue.shift()!;
    if (visited.has(key)) continue;
    visited.add(key);
    for (const edge of index.get(key) ?? []) {
      if (!selected.has(edge.prerequisite_key) && !acknowledged.has(edge.prerequisite_key)) {
        const existing = items.get(edge.prerequisite_key);
        if (existing) {
          if (!existing.dependentSkillNames.includes(edge.dependent_name)) existing.dependentSkillNames.push(edge.dependent_name);
        } else items.set(edge.prerequisite_key, {skillKey: edge.prerequisite_key, name: edge.prerequisite_name,
          dependentSkillNames: [edge.dependent_name], reasoning: edge.reasoning, confidence: edge.confidence,
          canAddToLearningPath: edge.prerequisite_selectable, availabilityReason: edge.availability_reason});
      }
      queue.push(edge.prerequisite_key);
    }
  }
  return [...items.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export function selectionError(error: unknown) {
  const detail = (error as {response?: {data?: {detail?: unknown}}})?.response?.data?.detail;
  if (typeof detail === 'string') return {message: detail, reconcile: false, referenceIds: [], names: []};
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') {
    const code = 'code' in detail ? detail.code : null;
    return {message: detail.message, reconcile: ['invalid_skill_reference', 'skill_unavailable', 'ambiguous_skill_name'].includes(String(code)),
      referenceIds: 'skill_reference_ids' in detail && Array.isArray(detail.skill_reference_ids) ? detail.skill_reference_ids.filter((id): id is string => typeof id === 'string') : [],
      names: 'skill_names' in detail && Array.isArray(detail.skill_names) ? detail.skill_names.filter((name): name is string => typeof name === 'string') : []};
  }
  return {message: 'Failed to start build', reconcile: false, referenceIds: [], names: []};
}
