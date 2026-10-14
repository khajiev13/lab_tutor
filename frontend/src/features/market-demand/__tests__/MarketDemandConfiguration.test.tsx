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
}));
import {
  fetchConversationHistory,
  getMarketExecutionStatus,
  fetchAgentState,
  fetchSkillReview,
  fetchJobSources,
  streamMarketDemandChat,
  fetchOnetReleases,
  searchOnetOccupations,
  confirmOnetOccupations,
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

async function openSetup() {
 fireEvent.click(screen.getByRole("button",{name:/History and setup/}));
 if (!screen.queryByRole("region",{name:"Analysis setup"})) fireEvent.click(screen.getByRole("button",{name:"Analysis setup"}));
}
function closeSetup() {fireEvent.click(screen.getByRole("button",{name:"Close"}));}

describe("shared teacher source configuration", () => {
  it("restores sources and serializes them from suggestion, selection and typed replies", async () => {
    vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
      onEvent({type:"agent_start",agent:"supervisor",messageId:"a1",displayName:"Supervisor",emoji:""});
      onEvent({type:"text_delta",messageId:"a1",delta:'Search Terms: "data analyst", "data scientist"'});
      onEvent({type:"text_done",messageId:"a1"});
      onEvent({type:"stream_end", outcome:"completed"});
    });
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
    const user = userEvent.setup();
    expect(await screen.findByRole("checkbox", {name:"HeadHunter"}, {timeout: 10000})).toBeChecked();
    expect(screen.getByRole("checkbox", {name:"Indeed"})).toBeDisabled();
    expect(screen.getByRole("checkbox", {name:"LinkedIn"})).not.toBeChecked();
    closeSetup();
    await user.click(screen.getByRole("button",{name:"Start an analysis"}));
    await user.click(await screen.findByRole("button", {name:"Select all"}));
    await user.click(screen.getByRole("button", {name:"Continue"}));
    await user.type(screen.getByPlaceholderText("Type your response..."), "Continue with my selected sources{enter}");
    await waitFor(() => expect(streamMarketDemandChat).toHaveBeenCalledTimes(3));
    expect(vi.mocked(streamMarketDemandChat).mock.calls.map(([args]) => ({
      country: args.country,
      sources: args.sources,
      evidence_sources: args.evidence_sources,
      onet_release: args.onet_release,
      onet_occupation_codes: args.onet_occupation_codes,
    }))).toEqual([
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"],onet_release:null,onet_occupation_codes:[]},
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"],onet_release:null,onet_occupation_codes:[]},
      {country:"Uzbekistan",sources:["headhunter"],evidence_sources:["jobs"],onet_release:null,onet_occupation_codes:[]},
    ]);
  });

  it("blocks collection when provider catalog fails instead of using defaults", async () => {
    vi.mocked(fetchJobSources).mockRejectedValueOnce(new Error("Catalog offline"));
    render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
    expect((await screen.findAllByText(/Source catalog unavailable: Catalog offline/)).length).toBeGreaterThan(0);
    closeSetup();
    expect(screen.getByPlaceholderText("Type your response...")).toBeDisabled();
    expect(streamMarketDemandChat).not.toHaveBeenCalled();
  });

  it("does not apply an old course provider catalog to the new course", async () => {
    let finishOld!: (items: JobSourceAvailability[]) => void;
    vi.mocked(fetchJobSources).mockImplementationOnce(() => new Promise(resolve => {finishOld = resolve;}));
    const {rerender} = render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
    await waitFor(() => expect(fetchJobSources).toHaveBeenCalledWith(1, "Uzbekistan", expect.any(AbortSignal)));
    context.courseId = 2;
    rerender(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
    expect(await screen.findByRole("checkbox", {name:"HeadHunter"}, {timeout: 10000})).toBeInTheDocument();
    await act(async () => {finishOld([{id:"indeed",label:"Old course provider",availability:"available",reason:null}]);});
    expect(screen.queryByRole("checkbox", {name:"Old course provider"})).not.toBeInTheDocument();
  });
});

it("renders the durable nested review without treating extracted category prose as skill approval", async () => {
  const {reviewFixture} = await import("@/features/market-demand/__tests__/review-fixtures");
  vi.mocked(fetchSkillReview).mockResolvedValue(reviewFixture());
  vi.mocked(fetchAgentState).mockResolvedValue({...restored,run_id:"run-1",extracted_skills:[{name:"Legacy Python",category:"legacy",frequency:1,pct:100}]});
  render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
  closeSetup();
  await userEvent.click(await screen.findByRole("button",{name:"Browse skills"},{timeout:10000}));
  expect(screen.getByRole("checkbox",{name:"Select Python"})).toBeInTheDocument();
  closeSetup();
  expect(screen.queryByText("Select Skill Categories")).not.toBeInTheDocument();
  await openSetup();
  expect(screen.getByRole("checkbox",{name:"O*NET references"})).toBeDisabled();
  closeSetup();
  await userEvent.click(screen.getByRole("button",{name:"Browse skills"}));
  await userEvent.setup().click(screen.getByRole("checkbox",{name:"Select Python"}));
  expect(streamMarketDemandChat).not.toHaveBeenCalled();
});


it.each(["enable", "release"])("confirms pending %s configuration locally before the authoritative chat update", async (change) => {
 const state: AgentState = {...restored,run_id:"run-1",candidate_revision:0};
 if (change === "release") {
  state.evidence_sources = ["jobs", "onet"];
  state.onet_release = "30.0";
  state.selected_onet_occupations = ["15-1252.00"];
 }
 vi.mocked(fetchAgentState).mockResolvedValue(state);
 const saved = await fetchSkillReview(1);
 vi.mocked(fetchSkillReview).mockResolvedValue({...saved,run_id:"run-1"});
 vi.mocked(fetchOnetReleases).mockResolvedValue({items:[{version:"30.0",active:false,attribution:"O*NET"},{version:"31.0",active:true,attribution:"O*NET"}]});
 vi.mocked(searchOnetOccupations).mockResolvedValue({items:[{soc_code:"15-2051.00",title:"Data Scientists",description:"Analyze data"}],total:1,release:"31.0"});
 vi.mocked(confirmOnetOccupations).mockRejectedValue(new Error("Durable configuration has not enabled this release"));
 render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
 const user=userEvent.setup();
 await screen.findByRole("checkbox",{name:"HeadHunter"},{timeout:10000});
 if(change==="enable") await user.click(screen.getByRole("checkbox",{name:"O*NET references"}));
 else {
  await waitFor(()=>expect(screen.getByRole("combobox",{name:"O*NET release"})).toBeEnabled());
  await user.selectOptions(screen.getByRole("combobox",{name:"O*NET release"}),"31.0");
 }
 fireEvent.change(screen.getByRole("textbox",{name:"Search occupations"}),{target:{value:"data"}});
 await user.click(screen.getByRole("button",{name:"Search"}));
 await user.click(await screen.findByRole("checkbox",{name:/Data Scientists/}));
 await user.click(screen.getByRole("button",{name:"Confirm occupations"}));
 closeSetup();
 await waitFor(()=>expect(screen.getByPlaceholderText("Type your response...")).toBeEnabled());
 expect(confirmOnetOccupations).not.toHaveBeenCalled();
 fireEvent.change(screen.getByPlaceholderText("Type your response..."),{target:{value:"Collect using this configuration"}});
 fireEvent.keyDown(screen.getByPlaceholderText("Type your response..."),{key:"Enter",code:"Enter"});
 await waitFor(()=>expect(streamMarketDemandChat).toHaveBeenCalled());
 expect(vi.mocked(streamMarketDemandChat).mock.calls[0][0]).toMatchObject({sources:["headhunter"],evidence_sources:["jobs","onet"],onet_release:"31.0",onet_occupation_codes:["15-2051.00"]});
});

it("prevents configuration changes after collection starts",async()=>{
 const saved = await fetchSkillReview(1);
 vi.mocked(fetchSkillReview).mockResolvedValue({...saved,run_id:"run-1"});
 vi.mocked(fetchAgentState).mockResolvedValue({...restored,run_id:"run-1",source_outcomes:{headhunter:{status:"success",received_count:1,usable_count:1,warnings:[]}}});
 render(<TestRouter><MarketDemandPage/></TestRouter>);
    await openSetup();
 await waitFor(()=>expect(fetchAgentState).toHaveBeenCalled());
 if (!screen.queryByRole("region",{name:"Analysis setup"})) fireEvent.click(screen.getByRole("button",{name:"Analysis setup"}));
 await screen.findByText(/Source settings/);
 const provider=await screen.findByRole("checkbox",{name:"HeadHunter"},{timeout:10000});
 expect(screen.getByRole("checkbox",{name:"O*NET references"})).toBeDisabled();
 expect(provider).toBeDisabled();
});
