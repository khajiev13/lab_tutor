import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { AgentState, JobSourceAvailability } from "@/features/market-demand/types";

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
  context.courseId = 1;
  vi.mocked(fetchConversationHistory).mockResolvedValue({messages: [], threadId: "t"});
  vi.mocked(fetchAgentState).mockResolvedValue(restored);
  vi.mocked(fetchSkillReview).mockResolvedValue({run_id:null,candidate_revision:0,selection_revision:0,categories:[],candidates:[],selected_candidate_ids:[],excluded_candidate_ids:[],recommendations:[],source_outcomes:{},extraction_coverage:{},integration_review:null,publication_revision:0,approved_references:[]});
  vi.mocked(fetchJobSources).mockResolvedValue(catalog);
  vi.mocked(streamMarketDemandChat).mockResolvedValue(undefined);
});

describe("shared teacher source configuration", () => {
  it("restores sources and serializes them from suggestion, selection and typed replies", async () => {
    vi.mocked(streamMarketDemandChat).mockImplementationOnce(async ({onEvent}) => {
      onEvent({type:"agent_start",agent:"supervisor",messageId:"a1",displayName:"Supervisor",emoji:""});
      onEvent({type:"text_delta",messageId:"a1",delta:'Search Terms: "data analyst", "data scientist"'});
      onEvent({type:"text_done",messageId:"a1"});
      onEvent({type:"stream_end"});
    });
    render(<MemoryRouter><MarketDemandPage/></MemoryRouter>);
    const user = userEvent.setup();
    expect(await screen.findByRole("checkbox", {name:"HeadHunter"}, {timeout: 10000})).toBeChecked();
    expect(screen.getByRole("checkbox", {name:"Indeed"})).toBeDisabled();
    expect(screen.getByRole("checkbox", {name:"LinkedIn"})).not.toBeChecked();
    await user.click(screen.getByText("Analyze the job market for this course and find relevant postings"));
    await user.click(await screen.findByRole("button", {name:"Select all"}));
    await user.click(screen.getByRole("button", {name:/Confirm Selection/}));
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
    render(<MemoryRouter><MarketDemandPage/></MemoryRouter>);
    expect(await screen.findByText(/Source catalog unavailable: Catalog offline/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Type your response...")).toBeDisabled();
    expect(streamMarketDemandChat).not.toHaveBeenCalled();
  });

  it("does not apply an old course provider catalog to the new course", async () => {
    let finishOld!: (items: JobSourceAvailability[]) => void;
    vi.mocked(fetchJobSources).mockImplementationOnce(() => new Promise(resolve => {finishOld = resolve;}));
    const {rerender} = render(<MemoryRouter><MarketDemandPage/></MemoryRouter>);
    await waitFor(() => expect(fetchJobSources).toHaveBeenCalledWith(1, "Uzbekistan", expect.any(AbortSignal)));
    context.courseId = 2;
    rerender(<MemoryRouter><MarketDemandPage/></MemoryRouter>);
    expect(await screen.findByRole("checkbox", {name:"HeadHunter"}, {timeout: 10000})).toBeInTheDocument();
    await act(async () => {finishOld([{id:"indeed",label:"Old course provider",availability:"available",reason:null}]);});
    expect(screen.queryByRole("checkbox", {name:"Old course provider"})).not.toBeInTheDocument();
  });
});
