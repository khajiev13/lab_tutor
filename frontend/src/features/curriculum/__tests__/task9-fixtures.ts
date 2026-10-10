export const referenceA = '11111111-1111-4111-8111-111111111111';
export const referenceB = '22222222-2222-4222-8222-222222222222';
export const referencePending = '33333333-3333-4333-8333-333333333333';
export const referenceWithdrawn = '44444444-4444-4444-8444-444444444444';
export const postingUrl = 'https://hh.uz/vacancy/101';

export function careerSkill(id = referenceA, overrides = {}) {
  return {
    skill_reference_id: id,
    label: 'Batch Processing',
    description: 'Process large datasets reliably.',
    category: 'data',
    source: 'book' as const,
    origin: 'onet',
    chapters: [{ chapter_id: 'chapter-1', title: 'Foundations' }],
    qualifying_posting_links: [postingUrl],
    evidence_references: [{ snapshot_id: 'snapshot-1', provider: 'headhunter' as const,
      original_url: postingUrl, original_phrase: 'Batch Processing', evidence_kind: 'provider_tag' as const,
      excerpt: null, excerpt_start: null, excerpt_end: null, retrieved_at: '2026-10-10T00:00:00Z', status: 'active' }],
    onet_associations: [{ relation: 'related' as const, mapping_method: 'teacher_review', rationale: 'Context only',
      evidence: { id: 'onet-1', release: '31.0', soc_code: '15-1252.00', occupation_title: 'Software Developers',
        family: 'essential' as const, element_id: '2.A.1.a', label: 'Reading Comprehension', definition: 'Understand written text.',
        workplace_example: null, ratings: { IM: {scale_id: 'IM', value: null, minimum: 1, maximum: 5,
          status: 'suppressed' as const, date: null, quality: {} } }, flags: {},
        source_url: 'https://www.onetonline.org/link/summary/15-1252.00', attribution: 'O*NET 31.0' } }],
    job_metrics: null,
    projection_status: 'projected' as const,
    available_for_new_selection: true,
    availability_reason: null,
    is_selected: false,
    peer_count: 0,
    ...overrides,
  };
}

export function task9Banks() {
  const skills = [careerSkill(), careerSkill(referenceB, { source: 'market', chapters: [{chapter_id: 'chapter-2', title: 'Streaming'}] }),
    careerSkill(referencePending, { label: 'Pending skill', projection_status: 'pending', available_for_new_selection: false, availability_reason: 'Awaiting projection' }),
    careerSkill(referenceWithdrawn, { label: 'Withdrawn skill', available_for_new_selection: false, availability_reason: 'Offering withdrawn' })];
  const rows = skills.map((skill) => ({ ...skill, name: skill.label }));
  return {
    career_skill_bank: skills,
    book_skill_banks: [{ book_id: 'book-1', title: 'Designing Data Systems', authors: 'Alex Example',
      chapters: [{chapter_id: 'chapter-1', title: 'Foundations', chapter_index: 1, skills: [rows[0]!] }] }],
    market_skill_bank: [{ url: postingUrl, title: 'Backend Engineer', company: 'Acme', site: 'HeadHunter',
      search_term: 'backend engineer', is_interested: false, skills: rows }],
    selected_skill_names: [], selected_skill_reference_ids: [], interested_posting_urls: [],
    peer_selection_counts: {}, peer_selection_counts_by_reference: {},
    selection_range: {min_skills: 1, max_skills: 35, is_default: false}, prerequisite_edges: [],
  };
}
