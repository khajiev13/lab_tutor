import { createContext, useContext, useEffect, useState } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

const TestChildren = createContext<React.ReactNode>(null);
function RouterContents() {return useContext(TestChildren);}
const testRouters: ReturnType<typeof createMemoryRouter>[] = [];
afterEach(() => {testRouters.splice(0).forEach(router => router.dispose());});
function TestRouter({children}: {children: React.ReactNode}) {
 const [router] = useState(() => {const value = createMemoryRouter([{path:"*",element:<RouterContents/>}],{initialEntries:["/courses/1/market-analyst"]}); testRouters.push(value); return value;});
 useEffect(() => () => router.dispose(), [router]);
 return <TestChildren.Provider value={children}><RouterProvider router={router}/></TestChildren.Provider>;
}
// ── Mocks (before imports) ──────────────────────────────────

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

vi.mock("@/features/courses/context/CourseDetailContext", () => ({
  CourseDetailProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCourseDetail: () => ({
    course: { id: 1, title: "Test Course" },
    courseId: 1,
    getStepStatus: () => "not-started",
  }),
}));

vi.mock("@/features/market-demand/hooks/useAgentStream", () => ({
  useAgentStream: vi.fn(),
}));



const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: "1" }),
  };
});

import type {
  AgentState,
  PipelineStageId,
  StageStatus,
  SendResult,
} from "@/features/market-demand/types";
import type { UseAgentStreamReturn } from "@/features/market-demand/hooks/useAgentStream";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
vi.mock("@/features/market-demand/api", async () => ({skillReviewErrorMessage: (await vi.importActual<typeof import("@/features/market-demand/api")>("@/features/market-demand/api")).skillReviewErrorMessage,fetchJobSources: vi.fn(async () => [{id:"indeed",label:"Indeed",availability:"available",reason:null},{id:"linkedin",label:"LinkedIn",availability:"available",reason:null}]), confirmOnetOccupations:vi.fn(), saveSkillReviewDraft:vi.fn(), confirmSkillReviewSelection:vi.fn(), approveSkillIntegration:vi.fn(), continueWithAvailableEvidence:vi.fn(), getOccupationSkills:vi.fn(), fetchOnetReleases:vi.fn(async()=>({items:[{version:"31.0",active:true,attribution:"O*NET"}]})), searchOnetOccupations:vi.fn(async()=>({items:[{soc_code:"15-2051.00",title:"Data Scientists",description:"Analyze data"}],total:1,release:"31.0"}))}));

import { confirmOnetOccupations, saveSkillReviewDraft } from "@/features/market-demand/api";

import { ChatInput } from "@/features/market-demand/components/ChatInput";
import { ConnectionStatus } from "@/features/market-demand/components/ConnectionStatus";
import { PipelineStepper } from "@/features/market-demand/components/PipelineStepper";
import { UserMessage } from "@/features/market-demand/components/UserMessage";

// ── Shared constants ────────────────────────────────────────

const EMPTY_STATE: AgentState = {
  course_id: null,
  course_title: null,
  course_description: null,
  job_search_country: "USA",
  job_search_country_confirmed: false,
  job_search_location: "United States",
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
};

const ALL_PENDING: Record<PipelineStageId, StageStatus> = {
  fetch: "active",
  select: "pending",
  extract: "pending",
  map: "pending",
  approve: "pending",
  link: "pending",
  insert: "pending",
};

function mockStreamReturn(overrides: Partial<UseAgentStreamReturn> = {}): UseAgentStreamReturn {
  return {
    isRestored: true,
    resetRecovery: "none",
    retryRestoration: vi.fn(),
    skillReview: null,
    refreshSkillReview: vi.fn(),
    applySkillReview: vi.fn(),
    messages: [],
    isStreaming: false,
    isLoadingHistory: false,
    currentAgent: null,
    agentState: EMPTY_STATE,
    pipelineStages: ALL_PENDING,
    threadId: null,
    send: vi.fn().mockResolvedValue({outcome: "completed"}),
    closeLiveResponse: vi.fn(),
    reconcile: vi.fn().mockResolvedValue(undefined),
    execution: {status: "idle", state_updated_at: null, outcome: "unknown"},
    streamError: null,
    recoverableCommand: null,
    stop: vi.fn(),
    clearConversation: vi.fn(),
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(confirmOnetOccupations).mockReset();
  vi.mocked(saveSkillReviewDraft).mockReset();
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
});

async function ensureSetup() {
 if (!screen.queryByRole("dialog")) fireEvent.click(screen.getByRole("button",{name:/History and setup/}));
 if (!screen.queryByRole("region",{name:"Analysis setup"})) fireEvent.click(screen.getByRole("button",{name:"Analysis setup"}));
 await screen.findByRole("checkbox",{name:"Job postings"});
 await act(async () => {await Promise.resolve();});
}
// ── ChatInput ───────────────────────────────────────────────

function ControlledChatInput({onSend, isStreaming}: {onSend: (text: string) => void; isStreaming: boolean}) {
  const [value, setValue] = useState("");
  return <ChatInput value={value} onChange={setValue} onSend={text => {onSend(text); setValue("");}} onCloseLiveResponse={vi.fn()} isStreaming={isStreaming}/>;
}

describe("ChatInput", () => {
  it("calls onSend with input text on Enter", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ControlledChatInput onSend={onSend} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText("Type your response...");
    await user.type(textarea, "find python jobs{enter}");

    expect(onSend).toHaveBeenCalledWith("find python jobs");
  });

  it("does not send empty messages", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ControlledChatInput onSend={onSend} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText("Type your response...");
    await user.type(textarea, "{enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows stop button when streaming", () => {
    render(<ControlledChatInput onSend={vi.fn()} isStreaming={true} />);
    // The stop button is icon-only (Square icon), find by role
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("clears input after send", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ControlledChatInput onSend={onSend} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText("Type your response...");
    await user.type(textarea, "test message{enter}");

    expect(textarea).toHaveValue("");
  });
});

// ── ConnectionStatus ────────────────────────────────────────

describe("ConnectionStatus", () => {
  it("shows Ready when idle", () => {
    render(<ConnectionStatus isStreaming={false} hasError={false} />);
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("shows Error when hasError is true", () => {
    render(<ConnectionStatus isStreaming={false} hasError={true} />);
    expect(screen.getByText("Error")).toBeInTheDocument();
  });

  it("shows Streaming when streaming", () => {
    render(<ConnectionStatus isStreaming={true} hasError={false} />);
    expect(screen.getByText("Streaming")).toBeInTheDocument();
  });
});

// ── PipelineStepper ─────────────────────────────────────────

describe("PipelineStepper", () => {
  it("renders all 7 stages", () => {
    render(<PipelineStepper stages={ALL_PENDING} />);
    expect(screen.getByText(/fetch jobs/i)).toBeInTheDocument();
    expect(screen.getByText(/select/i)).toBeInTheDocument();
    expect(screen.getByText(/extract/i)).toBeInTheDocument();
    expect(screen.getByText(/update knowledge map/i)).toBeInTheDocument();
  });

  it("marks completed stages", () => {
    const stages: Record<PipelineStageId, StageStatus> = {
      ...ALL_PENDING,
      fetch: "complete",
      select: "complete",
      extract: "active",
    };
    const { container } = render(<PipelineStepper stages={stages} />);
    expect(container.querySelector("div")).toBeInTheDocument();
  });
});

// ── UserMessage ─────────────────────────────────────────────

describe("UserMessage", () => {
  it("renders user message content", () => {
    render(<UserMessage content="Find me some jobs" />);
    expect(screen.getByText("Find me some jobs")).toBeInTheDocument();
  });
});



// ── MarketDemandPage ────────────────────────────────────────

async function openReviewWorkspace(overrides: Partial<UseAgentStreamReturn> = {}) {
 const {workspaceReviewFixture} = await import('@/features/market-demand/__tests__/review-fixtures');
 const review = workspaceReviewFixture();
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:review,...overrides}));
 const {default:Page} = await import('@/features/market-demand/pages/MarketDemandPage');
 const rendered=render(<TestRouter><Page/></TestRouter>);
 await act(async () => {await Promise.resolve();});
 return {review,...rendered};
}
it('shows five chosen skills and continues save then confirm then explicit mapping without publishing', async () => {
 const api = await import('@/features/market-demand/api');
 const {largeReviewFixture} = await import('@/features/market-demand/__tests__/review-fixtures');
 const review = largeReviewFixture(); review.selected_candidate_ids=review.candidates.slice(0,58).map(item=>item.candidate_id);
 const order:string[]=[];
 const send=vi.fn(async()=>{order.push('mapping-request');return {outcome:'completed' as const};});
 vi.mocked(api.saveSkillReviewDraft).mockImplementation(async(_id,body)=>{order.push('save');return {...review,selected_candidate_ids:body.selected_candidate_ids,selection_revision:3};});
 vi.mocked(api.confirmSkillReviewSelection).mockImplementation(async()=>{order.push('confirm');return {...review,selected_candidate_ids:review.selected_candidate_ids.slice(1),selection_revision:3};});
 await openReviewWorkspace({skillReview:review,send});
 expect(within(screen.getByRole('region',{name:'Choose skills'})).getAllByRole('listitem')).toHaveLength(5);
 expect(screen.getByRole('button',{name:'Review all 58'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Remove Job skill 01'}));
 fireEvent.click(screen.getByRole('button',{name:'Continue'}));
 await waitFor(()=>expect(order).toEqual(['save','confirm','mapping-request']));
 expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'workflow',text:expect.stringMatching(/curriculum/)}));
 expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});
it('retains a failed-save draft without confirming mapping or publishing', async () => {
 const api=await import('@/features/market-demand/api');
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=reviewFixture();review.selected_candidate_ids=['python','sql'];
 vi.mocked(api.saveSkillReviewDraft).mockRejectedValue(new Error('Save offline'));
 const send=vi.fn(); await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Remove SQL'}));
 fireEvent.click(screen.getByRole('button',{name:'Continue'}));
 await screen.findAllByText(/Save offline/);
 expect(screen.getByText('Python')).toBeVisible();
 expect(api.confirmSkillReviewSelection).not.toHaveBeenCalled();expect(send).not.toHaveBeenCalled();expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});

it('sends exact job-group names, keeps typed text and requires status reconciliation before retrying a failed send', async()=>{
 const send=vi.fn().mockResolvedValueOnce({outcome:'failed',error:{message:'Request offline'}}).mockResolvedValueOnce({outcome:'completed'});
 const reconcile=vi.fn().mockResolvedValue(undefined);
 await openReviewWorkspace({skillReview:null,send,reconcile,agentState:{...EMPTY_STATE,fetched_jobs:[{title:'Analyst'}],job_groups:{'BI / Data & Reporting':[0],'Data Scientists':[0]}}});
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep my question'}});
 fireEvent.click(screen.getByRole('checkbox',{name:'BI / Data & Reporting'}));
 fireEvent.click(screen.getByRole('button',{name:'Continue'}));
 await screen.findByRole('button',{name:'Check workflow status before retrying'});
 expect(send).toHaveBeenCalledWith({mode:'workflow',text:'Select these job groups by exact name: ["BI / Data & Reporting"]. Preserve these names; do not convert them to indices.'});
 expect(screen.getByRole('textbox')).toHaveValue('Keep my question');
 expect(screen.getByRole('checkbox',{name:'BI / Data & Reporting'})).toBeChecked();
 expect(screen.getByRole('button',{name:'Continue'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Check workflow status before retrying'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Continue'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Continue'}));
 await waitFor(()=>expect(send).toHaveBeenCalledTimes(2));
 expect(reconcile).toHaveBeenCalledOnce();
});
it('keeps double-click Continue single flight and leaves detached work unretried until checked',async()=>{
 const api=await import('@/features/market-demand/api'); const {workspaceReviewFixture,workspaceCandidateId}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture();review.selected_candidate_ids=[workspaceCandidateId];
 let finish!:(value:SendResult)=>void;const send=vi.fn(()=>new Promise<SendResult>(resolve=>{finish=resolve;}));
 vi.mocked(api.confirmSkillReviewSelection).mockResolvedValue(review);
 const reconcile=vi.fn().mockRejectedValue(new Error('Status offline'));
 await openReviewWorkspace({skillReview:review,send,reconcile});
 const button=screen.getByRole('button',{name:'Continue'});
 fireEvent.click(button);fireEvent.click(button);
 await waitFor(()=>expect(send).toHaveBeenCalledOnce());
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'A follow-up while mapping'}});
 await act(async()=>finish({outcome:'detached'}));
 expect(screen.getByRole('textbox')).toHaveValue('A follow-up while mapping');
 fireEvent.click(screen.getByRole('button',{name:'Check workflow status before retrying'}));
 await screen.findByText(/Status offline/);
 expect(send).toHaveBeenCalledOnce(); expect(api.confirmSkillReviewSelection).toHaveBeenCalledOnce();
 expect(screen.getByRole('button',{name:'Continue'})).toBeDisabled();
});
it('blocks zero choices and does not treat missing optional ONet ratings as a checkpoint',async()=>{
 await openReviewWorkspace();
 expect(screen.getByRole('button',{name:'Continue'})).toBeDisabled();
 expect(screen.queryByRole('button',{name:'Acknowledge available evidence'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));
 fireEvent.click(screen.getByRole('button',{name:'Close'}));
 expect(screen.getByRole('button',{name:'Continue'})).toBeEnabled();
});
it('exposes coverage as an explicit save-then-acknowledge action without confirmation or workflow',async()=>{
 const api=await import('@/features/market-demand/api'); const {workspaceReviewFixture,workspaceCandidateId}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture(); review.extraction_coverage={status:'partial',selected_postings:7,assessed_postings:4,acknowledged:false};
 const order:string[]=[];vi.mocked(api.saveSkillReviewDraft).mockImplementation(async(_id,body)=>{order.push('save');return {...review,selected_candidate_ids:body.selected_candidate_ids,selection_revision:3};});
 vi.mocked(api.continueWithAvailableEvidence).mockImplementation(async()=>{order.push('acknowledge');return {...review,selected_candidate_ids:[workspaceCandidateId],selection_revision:3,extraction_coverage:{...review.extraction_coverage,acknowledged:true}};});
 const send=vi.fn();await openReviewWorkspace({skillReview:review,send});
 expect(screen.getByText(/Some job evidence is incomplete/)).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));fireEvent.click(screen.getByRole('button',{name:'Close'}));
 fireEvent.click(screen.getByRole('button',{name:'Acknowledge available evidence'}));
 await waitFor(()=>expect(order).toEqual(['save','acknowledge']));
 expect(api.confirmSkillReviewSelection).not.toHaveBeenCalled();expect(send).not.toHaveBeenCalled();
});
it('requires explicit reconciliation checks and saving before Continue',async()=>{
 const {reconciliationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=reconciliationFixture();await openReviewWorkspace({skillReview:review});
 expect(screen.getByRole('region',{name:'Candidate reconciliation'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'Continue'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Save reviewed choices'})).toBeDisabled();
 fireEvent.click(screen.getByRole('checkbox',{name:'Acknowledge reconciliation for Prior Python'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'Acknowledge reconciliation for Removed SQL'}));
 expect(screen.getByRole('button',{name:'Save reviewed choices'})).toBeEnabled();
});
it('keeps source locks in history, preserves dirty choices and question after failed reset',async()=>{
 const clear=vi.fn().mockRejectedValue(new Error('Reset offline'));
 await openReviewWorkspace({clearConversation:clear});
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));fireEvent.click(screen.getByRole('button',{name:'Close'}));
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep my question'}});
 await ensureSetup();expect(screen.getByRole('checkbox',{name:'Job postings'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'New analysis'}));
 fireEvent.click(screen.getByRole('button',{name:'Discard and start new analysis'}));
 await screen.findByText('Reset offline');fireEvent.click(screen.getByRole('button',{name:'Cancel'}));
 expect(screen.getByRole('textbox')).toHaveValue('Keep my question');expect(screen.getByText('Python')).toBeVisible();
});
it('keeps reset recovery available when ordinary restoration is unavailable',async()=>{
 await openReviewWorkspace({isRestored:false,resetRecovery:'required',error:'Restore unavailable'});
 expect(screen.getByRole('button',{name:'Retry restoration'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Retry reset'}));
 expect(screen.getByRole('button',{name:'Confirm reset retry'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:'Save and start new analysis'})).not.toBeInTheDocument();
});
it('offers restoration retry after timeout while retaining the question and unsaved choices',async()=>{
 const {review,rerender}=await openReviewWorkspace();
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));fireEvent.click(screen.getByRole('button',{name:'Close'}));
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep my question'}});
 const retryRestoration=vi.fn();
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:review,isRestored:false,error:'Conversation restoration timed out. Retry restoration to try again.',retryRestoration}));
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');rerender(<TestRouter><Page/></TestRouter>);
 expect(screen.getByText(/Conversation restoration timed out/)).toBeVisible();
 expect(screen.queryByText('Restoring conversation...')).not.toBeInTheDocument();
 expect(screen.getByRole('textbox')).toHaveValue('Keep my question');
 expect(screen.getByRole('button',{name:'Remove Python'})).toBeVisible();
 expect(screen.getByRole('button',{name:'Send message'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Continue'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Retry restoration'}));
 expect(retryRestoration).toHaveBeenCalledOnce();
});
it('retains a dirty draft and blocks confirmation after a newer review arrives',async()=>{
 const {review,rerender}=await openReviewWorkspace();
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));fireEvent.click(screen.getByRole('button',{name:'Close'}));
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:{...review,candidate_revision:2}}));
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');rerender(<TestRouter><Page/></TestRouter>);
 expect(screen.getByText(/Review required:/)).toBeVisible();expect(screen.getByRole('button',{name:'Continue'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Remove Python'})).toBeVisible();
});
it('rejects a late review from another active run',async()=>{
 await openReviewWorkspace({agentState:{...EMPTY_STATE,run_id:'other-run'}});
 expect(screen.queryByRole('region',{name:'Choose skills'})).not.toBeInTheDocument();
});
it('ordinary review questions use Explain and never confirm or publish',async()=>{
 const api=await import('@/features/market-demand/api');const send=vi.fn().mockResolvedValue({outcome:'completed'});await openReviewWorkspace({send});
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Why these skills?'}});fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'contextual',context:expect.objectContaining({intent:'explain',candidate_ids:[],metric:'frequency'})})));
 expect(api.confirmSkillReviewSelection).not.toHaveBeenCalled();expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});
it('keeps primary curriculum approval distinct and hides skill Continue',async()=>{
 const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');await openReviewWorkspace({skillReview:integrationFixture()});
 expect(screen.getByRole('button',{name:'Approve and publish'})).toBeVisible();expect(screen.queryByRole('button',{name:'Continue'})).not.toBeInTheDocument();
});

it.each(['publication','withdrawal'] as const)('retains %s acknowledgement when the saved proposal clears',async(kind)=>{
 const api=await import('@/features/market-demand/api');
 const {integrationFixture,withdrawalFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=kind==='publication'?integrationFixture():withdrawalFixture();
 vi.mocked(api.approveSkillIntegration).mockResolvedValue({review:{...review,integration_review:null,approved_references:kind==='withdrawal'?[]:review.approved_references},projection_status:'pending'});
 vi.mocked(useAgentStream).mockImplementation(()=>{
   const [saved,setSaved]=useState(review);return mockStreamReturn({skillReview:saved,applySkillReview:setSaved});
 });
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');render(<TestRouter><Page/></TestRouter>);
 fireEvent.click(screen.getByRole('button',{name:kind==='publication'?'Approve and publish':'Withdraw approval'}));
 expect(await screen.findByRole('status')).toHaveTextContent(kind==='publication'?'Approval saved; publication waiting for projection':'Withdrawal saved; removal waiting for projection');
});

it('stages exact comparison descriptor context as Explain and derives IM from the selected occupation',async()=>{
 const {workspaceReviewFixture,workspaceEvidenceFixture,workspaceCandidateId,workspaceEvidenceId,workspaceSoc}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture();review.selected_candidate_ids=[workspaceCandidateId];review.candidates[0].onet_associations=[{...workspaceEvidenceFixture(),relation:'related'}];
 const send=vi.fn().mockResolvedValue({outcome:'completed'});await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Compare skills'}));
 fireEvent.click(screen.getByRole('button',{name:'O*NET importance'}));
 fireEvent.click(screen.getByRole('button',{name:/Ask about Programming/ }));
 expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(send).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'contextual',context:expect.objectContaining({intent:'explain',metric:'IM',view:'demand_importance',occupation_codes:[workspaceSoc],descriptor_choices:[{candidate_id:workspaceCandidateId,evidence_id:workspaceEvidenceId}]})})));
 fireEvent.click(screen.getByRole('button',{name:'Compare skills'}));fireEvent.click(screen.getByRole('button',{name:'Ask about Python'}));fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenLastCalledWith(expect.objectContaining({mode:'contextual',context:expect.objectContaining({intent:'explain',metric:'frequency',occupation_codes:[],descriptor_choices:[]})})));
});

it('keeps the current skill decision visible and the draft editable during Explain streaming',async()=>{
 await openReviewWorkspace({isStreaming:true});
 expect(screen.getByRole('region',{name:'Choose skills'})).toBeVisible();
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'Keep typing'}});
 expect(screen.getByRole('textbox')).toHaveValue('Keep typing');
 expect(screen.getByRole('button',{name:'Send message'})).toBeDisabled();
});

it('recovers a curriculum proposal after explicitly applying a draft change with save confirm and remap',async()=>{
 const api=await import('@/features/market-demand/api');const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=integrationFixture();review.recommendations=[{id:'add-sql',candidate_revision:1,base_selection_revision:2,changes:[{candidate_id:'sql',action:'add',reason:'Add the SQL course skill'}]}];
 const order:string[]=[];vi.mocked(api.saveSkillReviewDraft).mockImplementation(async(_id,body)=>{order.push('save');return {...review,...body,selection_revision:3};});
 vi.mocked(api.confirmSkillReviewSelection).mockImplementation(async()=>{order.push('confirm');return {...review,selected_candidate_ids:['python','sql'],selection_revision:3};});
 const send=vi.fn(async()=>{order.push('mapping-request');return {outcome:'completed' as const};});await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Review all 1 proposed changes'}));
 fireEvent.click(screen.getByRole('button',{name:'Apply proposal to draft'}));
 expect(screen.getByRole('button',{name:'Undo local change'})).toBeEnabled();
 expect(screen.getByRole('button',{name:'Save draft'})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'Remap skills'}));
 await waitFor(()=>expect(order).toEqual(['save','confirm','mapping-request']));
 expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});
it.each(['stale','unsupported'] as const)('offers curriculum recovery for a %s proposal',async(kind)=>{
 const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');const review=integrationFixture();
 if(kind==='stale')review.integration_review!.selection_revision=1;
 else {review.candidates[0].posting_support='missing';review.candidates[0].qualifying_posting_links=[];}
 await openReviewWorkspace({skillReview:review});
 fireEvent.click(screen.getByRole('button',{name:'Edit skills'}));
 expect(screen.getByRole('button',{name:'Browse skills'})).toBeVisible();
 expect(screen.getByRole('button',{name:'Remap skills'})).toBeVisible();
 if(kind==='unsupported'){expect(screen.getByRole('button',{name:'Remap skills'})).toBeDisabled();fireEvent.click(screen.getByRole('button',{name:'Remove Python'}));expect(screen.getByRole('button',{name:'Save draft'})).toBeEnabled();}
});
it('shows source failure retry and evidence acknowledgement with zero candidates',async()=>{
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');const review=reviewFixture();
 review.candidates=[];review.approved_references=[];review.source_outcomes={headhunter:{status:'error',received_count:0,usable_count:0,warnings:['HeadHunter rate limit reached']}};review.extraction_coverage={status:'failed',acknowledged:false};
 const send=vi.fn().mockResolvedValue({outcome:'completed'});await openReviewWorkspace({skillReview:review,send});
 expect(screen.getByText(/headhunter: collection failed/)).toBeVisible();
 expect(screen.getByRole('button',{name:'Acknowledge available evidence'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Retry failed sources'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'workflow',text:expect.stringMatching(/Retry/)})));
});

it('retains the curriculum recovery editor and incoming-review acknowledgement when a dirty revision changes',async()=>{
 const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');const initial=integrationFixture();
 const {rerender}=await openReviewWorkspace({skillReview:initial});
 fireEvent.click(screen.getByRole('button',{name:'Edit skills'}));
 fireEvent.click(screen.getByRole('button',{name:'Browse skills'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'Select SQL'}));
 fireEvent.click(screen.getByRole('button',{name:'Close'}));
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:{...initial,candidate_revision:2}}));
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');rerender(<TestRouter><Page/></TestRouter>);
 expect(screen.getByRole('button',{name:'I reviewed the changed choices'})).toBeVisible();
 expect(screen.getByRole('button',{name:'Remap skills'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'I reviewed the changed choices'}));
 expect(screen.getByRole('button',{name:'Remap skills'})).toBeEnabled();
 expect(screen.getByRole('button',{name:'Save draft'})).toBeEnabled();
});
