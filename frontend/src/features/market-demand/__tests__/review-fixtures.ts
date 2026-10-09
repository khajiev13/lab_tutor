import type { SkillReview } from "@/features/market-demand/types";

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
