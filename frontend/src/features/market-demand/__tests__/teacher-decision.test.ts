import {expect,it} from 'vitest';
import {resolveTeacherDecision, detectPendingSelection} from '@/features/market-demand/teacher-decision';
import {reviewFixture,integrationFixture} from '@/features/market-demand/__tests__/review-fixtures';
import type {AgentState, ChatMessage} from '@/features/market-demand/types';
const state = {fetched_jobs:null,job_groups:null,selected_jobs:null} as AgentState;
const terms = [{role:'agent',content:'Search Terms: "SQL analyst", "Data engineer"'}] as ChatMessage[];
it('prioritizes pending terms and exact group names over reviews',()=>{
 expect(resolveTeacherDecision(state,terms,integrationFixture())).toBe('search_queries');
 const groups={...state,fetched_jobs:[{title:'Analyst',company:'Acme'}],job_groups:{'BI / Data & Reporting':[0]}} as AgentState;
 expect(resolveTeacherDecision(groups,terms,integrationFixture())).toBe('job_groups');
 expect(detectPendingSelection(groups,terms)?.items[0].id).toBe('BI / Data & Reporting');
});
it('distinguishes current curriculum, candidates and working without adding evidence stages',()=>{
 expect(resolveTeacherDecision(state,[],integrationFixture())).toBe('curriculum');
 expect(resolveTeacherDecision(state,[],reviewFixture())).toBe('skills');
 expect(resolveTeacherDecision(state,[],null)).toBe('working');
});
