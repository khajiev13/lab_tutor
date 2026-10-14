import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { AgentState, JobSourceAvailability } from "@/features/market-demand/types";

import {createContext, useContext, useState} from "react";
const TestChildren = createContext<React.ReactNode>(null);
function RouterContents() {return useContext(TestChildren);}
const routers: ReturnType<typeof createMemoryRouter>[] = [];
afterEach(() => {routers.splice(0).forEach(router => router.dispose());});
function TestRouter({children}: {children: React.ReactNode}) {
 const [router]=useState(() => {const value=createMemoryRouter([{path:"*",element:<RouterContents/>}],{initialEntries:["/courses/1/market-analyst"]}); routers.push(value); return value;});
 return <TestChildren.Provider value={children}><RouterProvider router={router}/></TestChildren.Provider>;
}
const context = vi.hoisted(() => ({ courseId: 1 }));
vi.mock("@/features/courses/context/CourseDetailContext", () => ({
  CourseDetailProvider: ({children}: {children: React.ReactNode}) => <>{children}</>,
  useCourseDetail: () => ({courseId: context.courseId, course: {id: context.courseId, title: "Test Course"}}),
}));
vi.mock("react-router-dom", async () => ({
  ...await vi.importActual("react-router-dom"),
  useParams: () => ({id: String(context.courseId)}),
}));
vi.mock("@/features/market-demand/api", () => ({
  fetchConversationHistory: vi.fn(),
  getMarketExecutionStatus: vi.fn(),
  fetchAgentState: vi.fn(),
  fetchSkillReview: vi.fn(),
  fetchJobSources: vi.fn(),
  streamMarketDemandChat: vi.fn(),
  deleteConversation: vi.fn(),
  fetchOnetReleases: vi.fn(),
  searchOnetOccupations: vi.fn(),
  confirmOnetOccupations: vi.fn(),
  confirmSkillReviewSelection: vi.fn(),
}));
import {
  fetchConversationHistory,
  getMarketExecutionStatus,
  fetchAgentState,
  fetchSkillReview,
  fetchJobSources,
  streamMarketDemandChat,
} from "@/features/market-demand/api";
import MarketDemandPage from "@/features/market-demand/pages/MarketDemandPage";

const restored: AgentState = {
  course_id: 1,
  course_title: "Test Course",
  course_description: null,
  job_search_country: "Uzbekistan",
  job_search_country_confirmed: true,
  job_search_location: "Uzbekistan",
  fetched_jobs: null,
  job_groups: null,
  selected_jobs: null,
  extracted_skills: null,
  total_jobs_for_extraction: null,
  existing_graph_skills: null,
  existing_concepts: null,
  curriculum_mapping: null,
  selected_for_insertion: null,
  skill_concepts: null,
  insertion_results: null,
  skill_job_urls: null,
  sources: ["headhunter"],
  evidence_sources: ["jobs"],
};
const catalog: JobSourceAvailability[] = [
  {id:"indeed", label:"Indeed", availability:"unsupported_country", reason:"Indeed is unavailable in Uzbekistan"},
  {id:"linkedin", label:"LinkedIn", availability:"available", reason:null},
  {id:"headhunter", label:"HeadHunter", availability:"available", reason:null},
];

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getMarketExecutionStatus).mockResolvedValue({status: "idle", state_updated_at: null});
  context.courseId = 1;
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "t"});
  vi.mocked(fetchAgentState).mockResolvedValue(restored);
  vi.mocked(fetchSkillReview).mockResolvedValue({run_id:null,candidate_revision:0,selection_revision:0,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]});
  vi.mocked(fetchJobSources).mockResolvedValue(catalog);
  vi.mocked(streamMarketDemandChat).mockResolvedValue(undefined);
});

describe("automatic job sources in the original chat flow", () => {
  it("starts without setup and sends all three providers together when no configuration was saved", async()=>{
    vi.mocked(fetchAgentState).mockResolvedValue({...restored,sources:undefined});
    vi.mocked(streamMarketDemandChat).mockImplementation(async({onEvent})=>{onEvent({type:"stream_end",outcome:"completed"});});
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await waitFor(()=>expect(screen.getByRole("button",{name:"Send message"})).toBeDisabled());
    await waitFor(()=>expect(screen.getByRole("textbox",{name:"Question"})).toBeEnabled());
    expect(screen.getByRole("combobox",{name:"Market country"})).toBeVisible();
    expect(screen.queryByRole("checkbox",{name:"HeadHunter"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button",{name:/History and setup|Analysis setup/})).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox",{name:"Question"}),{target:{value:"Analyze the market"}});
    fireEvent.click(screen.getByRole("button",{name:"Send message"}));
    await waitFor(()=>expect(streamMarketDemandChat).toHaveBeenCalledWith(expect.objectContaining({
      mode:"workflow",country:"Uzbekistan",sources:["indeed","linkedin","headhunter"],evidence_sources:["jobs"],
    })));
    expect(fetchJobSources).not.toHaveBeenCalled();
  });

  it("preserves saved provider settings in suggestions, inline selection and typed workflow replies",async()=>{
    vi.mocked(streamMarketDemandChat).mockImplementation(async({onEvent})=>{onEvent({type:"stream_end",outcome:"completed"});});
    vi.mocked(streamMarketDemandChat).mockImplementationOnce(async({onEvent})=>{
      onEvent({type:"agent_start",agent:"supervisor",messageId:"a1",displayName:"Supervisor",emoji:""});
      onEvent({type:"text_delta",messageId:"a1",delta:'Search Terms: "data analyst", "data scientist"'});
      onEvent({type:"text_done",messageId:"a1"});onEvent({type:"stream_end",outcome:"completed"});
    });
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await waitFor(()=>expect(screen.getByRole("textbox",{name:"Question"})).toBeEnabled());
    await userEvent.click(screen.getByRole("button",{name:"Analyze the job market for this course and find relevant postings"}));
    fireEvent.click(await screen.findByRole("button",{name:"Select all"}));
    fireEvent.click(screen.getByRole("button",{name:/Confirm Selection/}));
    await waitFor(()=>expect(streamMarketDemandChat).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByRole("textbox",{name:"Question"}),{target:{value:"Continue using the saved configuration"}});
    fireEvent.click(screen.getByRole("button",{name:"Send message"}));
    await waitFor(()=>expect(streamMarketDemandChat).toHaveBeenCalledTimes(3));
    expect(vi.mocked(streamMarketDemandChat).mock.calls.map(([args])=>({country:args.country,sources:args.sources,evidence_sources:args.evidence_sources}))).toEqual([
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"]},
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"]},
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"]},
    ]);
  });

  it("lets available sources proceed when a configured provider is unsupported in this market",async()=>{
    vi.mocked(fetchAgentState).mockResolvedValue({...restored,sources:["indeed","linkedin","headhunter"]});
    vi.mocked(fetchJobSources).mockRejectedValue(new Error("Catalog offline"));
    vi.mocked(streamMarketDemandChat).mockImplementation(async({onEvent})=>{onEvent({type:"stream_end",outcome:"completed"});});
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await waitFor(()=>expect(screen.getByRole("textbox",{name:"Question"})).toBeEnabled());
    fireEvent.change(screen.getByRole("textbox",{name:"Question"}),{target:{value:"Collect available postings"}});
    fireEvent.click(screen.getByRole("button",{name:"Send message"}));
    await waitFor(()=>expect(streamMarketDemandChat).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(fetchJobSources).not.toHaveBeenCalled();
  });

  it("locks the original country selector after collection starts",async()=>{
    const saved = await fetchSkillReview(1);
    vi.mocked(fetchSkillReview).mockResolvedValue({...saved,run_id:"run-1"});
    vi.mocked(fetchAgentState).mockResolvedValue({...restored,run_id:"run-1",source_outcomes:{headhunter:{status:"success",received_count:1,usable_count:1,warnings:[]}}});
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await waitFor(()=>expect(screen.getByRole("textbox",{name:"Question"})).toBeEnabled());
    expect(screen.getByRole("combobox",{name:"Market country"})).toBeDisabled();
    expect(screen.queryByRole("checkbox",{name:"O*NET references"})).not.toBeInTheDocument();
  });

  it("renders durable candidate categories inline without treating extracted category prose as approval",async()=>{
    const {reviewFixture}=await import("@/features/market-demand/__tests__/review-fixtures");
    vi.mocked(fetchSkillReview).mockResolvedValue(reviewFixture());
    vi.mocked(fetchAgentState).mockResolvedValue({...restored,run_id:"run-1",extracted_skills:[{name:"Legacy Python",category:"legacy",frequency:1,pct:100}]});
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    fireEvent.click(await screen.findByRole("button",{name:"Expand Tools"}));
    expect(screen.getByRole("checkbox",{name:"Select Python"})).toBeVisible();
    expect(screen.queryByRole("checkbox",{name:/Legacy Python/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox",{name:"Select Python"}));
    expect(streamMarketDemandChat).not.toHaveBeenCalled();
  });
});

it("keeps mapping retry blocked when the execution-status read fails after detachment",async()=>{
 const {reviewFixture}=await import("@/features/market-demand/__tests__/review-fixtures");const api=await import("@/features/market-demand/api");
 const review={...reviewFixture(),selected_candidate_ids:["python"],approved_references:[]};
 vi.mocked(fetchSkillReview).mockResolvedValue(review);vi.mocked(fetchAgentState).mockResolvedValue({...restored,run_id:"run-1"});vi.mocked(api.confirmSkillReviewSelection).mockResolvedValue(review);
 render(<TestRouter><MarketDemandPage/></TestRouter>);
 await waitFor(()=>expect(screen.getByRole("button",{name:/Confirm Selection/})).toBeEnabled());
 vi.mocked(getMarketExecutionStatus).mockRejectedValue(new Error("Only status offline"));
 fireEvent.click(screen.getByRole("button",{name:/Confirm Selection/}));
 await screen.findByRole("button",{name:"Check analysis status"});
 fireEvent.click(screen.getByRole("button",{name:"Check analysis status"}));
 await waitFor(()=>expect(getMarketExecutionStatus).toHaveBeenCalledTimes(3));
 expect(screen.getByRole("button",{name:/Confirm Selection/})).toBeDisabled();
 expect(streamMarketDemandChat).toHaveBeenCalledOnce();
 vi.mocked(getMarketExecutionStatus).mockResolvedValue({status:"busy",state_updated_at:null});
 fireEvent.click(screen.getByRole("button",{name:"Check analysis status"}));
 await screen.findByText(/still running/);
 expect(streamMarketDemandChat).toHaveBeenCalledOnce();
 vi.mocked(getMarketExecutionStatus).mockResolvedValue({status:"idle",state_updated_at:null});
 fireEvent.click(screen.getByRole("button",{name:"Check analysis status"}));
 await waitFor(()=>expect(screen.getByRole("button",{name:/Confirm Selection/})).toBeEnabled());
});

it("ignores a prior course idle status after switching to an unknown-status course",async()=>{
 const {reviewFixture}=await import("@/features/market-demand/__tests__/review-fixtures");const api=await import("@/features/market-demand/api");
 const review={...reviewFixture(),selected_candidate_ids:["python"],approved_references:[]};
 vi.mocked(fetchSkillReview).mockImplementation(async id=>({...review,run_id:`run-${id}`}));
 vi.mocked(fetchAgentState).mockImplementation(async id=>({...restored,course_id:id,run_id:`run-${id}`}));
 vi.mocked(api.confirmSkillReviewSelection).mockResolvedValue(review);
 const {rerender}=render(<TestRouter><MarketDemandPage/></TestRouter>);
 await waitFor(()=>expect(screen.getByRole("button",{name:/Confirm Selection/})).toBeEnabled());
 fireEvent.click(screen.getByRole("button",{name:/Confirm Selection/}));
 await screen.findByRole("button",{name:"Check analysis status"});
 let finishOld!:(status:{status:"idle";state_updated_at:null})=>void;
 vi.mocked(getMarketExecutionStatus).mockImplementation(id=>id===1?new Promise(resolve=>{finishOld=resolve;}):Promise.reject(new Error("New course status offline")));
 fireEvent.click(screen.getByRole("button",{name:"Check analysis status"}));
 await waitFor(()=>expect(getMarketExecutionStatus).toHaveBeenCalledTimes(3));
 context.courseId=2;rerender(<TestRouter><MarketDemandPage/></TestRouter>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Expand Tools"})).toBeEnabled());
 await act(async()=>finishOld({status:"idle",state_updated_at:null}));
 expect(screen.getByRole("button",{name:/Confirm Selection/})).toBeDisabled();
 expect(screen.getByRole("button",{name:"Check analysis status"})).toBeVisible();
 expect(streamMarketDemandChat).toHaveBeenCalledOnce();
});
