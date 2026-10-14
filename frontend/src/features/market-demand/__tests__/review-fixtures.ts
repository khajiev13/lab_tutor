import type { CandidateReconciliation, IntegrationReviewPayload, OnetAssociation, OnetEvidence, SkillReview, WorkspaceViewState } from "@/features/market-demand/types";

export function reviewFixture(): SkillReview {
  return {
    run_id: "run-1", candidate_revision: 1, selection_revision: 2,
    categories: [{category_id:"tools",label:"Tools"}],
    candidates: [
      {candidate_id:"python",display_name:"Python",category_id:"tools",original_labels:["Python"],aliases:[],evidence_references:[{snapshot_id:"snapshot-1",provider:"headhunter",original_url:"https://hh.uz/vacancy/123",original_phrase:"Python",evidence_kind:"extracted_text",excerpt:"Use Python",excerpt_start:0,excerpt_end:10,retrieved_at:"2026-10-09",status:"active"}],job_metrics:{supporting_posting_count:2,assessed_posting_count:4,selected_posting_count:5,percentage:50,coverage_status:"partial"},onet_associations:[],recommendation_reasons:["Used in assessed vacancies"],posting_support:"supported",qualifying_posting_links:["https://hh.uz/vacancy/123"]},
      {candidate_id:"sql",display_name:"SQL",category_id:"tools",original_labels:["SQL"],aliases:[],evidence_references:[],job_metrics:{supporting_posting_count:1,assessed_posting_count:4,selected_posting_count:5,percentage:25,coverage_status:"partial"},onet_associations:[],recommendation_reasons:[],posting_support:"supported",qualifying_posting_links:["https://hh.uz/vacancy/456"]},
      {candidate_id:"reference",display_name:"Reference skill",category_id:"tools",original_labels:[],aliases:[],evidence_references:[],job_metrics:{},onet_associations:[],recommendation_reasons:[],posting_support:"missing",qualifying_posting_links:[]},
    ],
    selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:3,
    approved_references:[{reference_id:"previous",label:"Published Python",category:"Tools",source:"market",origin:"jobs",qualifying_posting_links:["https://hh.uz/vacancy/old"],projection_status:"projected",available_for_new_selection:true}],
  };
}

export function integrationFixture(): SkillReview {
  const review = reviewFixture();
  return {...review,selected_candidate_ids:["python"],integration_review:{review_digest:"digest-1",candidate_revision:1,selection_revision:2,items:[{candidate_id:"python",target:{identity:"target-1",label:"Python programming",source:"market",origin:"jobs"},chapters:[{chapter_id:"chapter-1",title:"Programming"}],disposition:"new",qualifying_posting_links:["https://hh.uz/vacancy/123"],evidence_snapshot_ids:["snapshot-1"]}],omissions:[],omissions_acknowledged:true}};
}

export const reconciliationA = "11111111-1111-4111-8111-111111111111";
export const reconciliationB = "22222222-2222-4222-8222-222222222222";

export type ReconciledReview = SkillReview & {reconciliations: CandidateReconciliation[]};

export function reconciliationFixture(): ReconciledReview {
  return {
    ...reviewFixture(),
    selected_candidate_ids: ["python"],
    excluded_candidate_ids: ["sql"],
    reconciliations: [
      {reconciliation_id: reconciliationA, candidate_id: "python", previous_candidate_ids: ["old-python"],
        reason: "ambiguous_equivalent_merge", previous_candidates: [{candidate_id: "old-python", display_name: "Prior Python"}],
        previous_selected_candidate_ids: ["old-python"], previous_excluded_candidate_ids: [], resolved: false},
      {reconciliation_id: reconciliationB, candidate_id: null, previous_candidate_ids: ["old-sql"],
        reason: "candidate_removed", previous_candidates: [{candidate_id: "old-sql", display_name: "Removed SQL"}],
        previous_selected_candidate_ids: [], previous_excluded_candidate_ids: ["old-sql"], resolved: false},
    ],
  };
}

export type WithdrawalReview = SkillReview & {integration_review: IntegrationReviewPayload & {withdrawal: true}};

export function withdrawalFixture(): WithdrawalReview {
  const review = reconciliationFixture();
  return {...review, integration_review: {
    review_digest: "withdrawal-digest-1", candidate_revision: 1, selection_revision: 2,
    withdrawal: true, items: [], omissions: ["Posting evidence unavailable"], omissions_acknowledged: false,
  }};
}

export const workspaceRunId = "00000000-0000-0000-0000-000000000099";
export const workspaceCandidateId = "00000000-0000-0000-0000-000000000001";
export const workspaceEvidenceId = "00000000-0000-0000-0000-000000000011";
export const workspaceSoc = "15-1252.00";
export const workspaceOtherSoc = "15-1253.00";

export function workspaceViewFixture(): WorkspaceViewState {
  return {view: "overview", filters: {category_ids: [], search: "", scope: "all"}, focusedCandidateId: null,
    occupationCodes: [workspaceSoc, workspaceOtherSoc], activeOccupationCode: workspaceSoc, metric: "IM",
    descriptorChoices: [], sort: {field: "name", direction: "asc"}, page: 1};
}

export function workspaceReviewFixture(): SkillReview {
  const review = reviewFixture();
  return {...review, run_id: workspaceRunId, candidates: [{...review.candidates[0], candidate_id: workspaceCandidateId}],
    analysis_metadata: {country: null, job_sources: ["headhunter"], evidence_sources: ["jobs", "onet"], onet_release: "30.0",
      occupations: [{soc_code: workspaceSoc, title: "Developer"}, {soc_code: workspaceOtherSoc, title: "Tester"}],
      created_at: "2026-10-12", updated_at: "2026-10-12"}};
}

export function workspaceEvidenceFixture(overrides: Partial<OnetEvidence> = {}): OnetAssociation {
  return {relation: "equivalent", mapping_method: "reviewed", rationale: "Equivalent", evidence: {
    id: workspaceEvidenceId, release: "30.0", soc_code: workspaceSoc, occupation_title: "Developer", family: "essential",
    element_id: "2.B.3.m", label: "Programming", definition: "Writing programs", workplace_example: null,
    ratings: {IM: {scale_id: "IM", value: 4, minimum: 1, maximum: 5, status: "reported", date: null, quality: {}},
      LV: {scale_id: "LV", value: 0, minimum: 0, maximum: 7, status: "reported", date: null, quality: {}}},
    flags: {}, source_url: "https://onetonline.org", attribution: "O*NET", ...overrides}};
}

export function largeReviewFixture(): SkillReview {
  const base = reviewFixture();
  return {
    ...base,
    categories: [{category_id: "tools", label: "Tools"}, {category_id: "other", label: "Other skills"}],
    candidates: [
      ...Array.from({length: 58}, (_, index) => ({...base.candidates[0],
        candidate_id: `job-${String(index + 1).padStart(2, "0")}`,
        display_name: `Job skill ${String(index + 1).padStart(2, "0")}`,
        category_id: index < 12 ? "tools" : "other", aliases: [],
      })),
      ...Array.from({length: 394}, (_, index) => ({...base.candidates[2],
        candidate_id: `reference-${index + 1}`, display_name: `Reference skill ${index + 1}`,
        onet_associations: [workspaceEvidenceFixture()],
      })),
    ],
    excluded_candidate_ids: ["reference-1"],
  };
}
