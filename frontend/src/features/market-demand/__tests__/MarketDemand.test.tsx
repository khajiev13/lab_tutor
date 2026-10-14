import { createContext, useContext, useEffect, useState } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
it('keeps the full original agent conversation and current choices inline with ordinary workflow replies', async () => {
 const send = vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:null,send,messages:[
  {id:'earlier',role:'agent',content:'Earlier market finding',agent:'supervisor',toolCalls:[],isStreaming:false},
  {id:'teacher',role:'user',content:'Find relevant jobs',toolCalls:[],isStreaming:false},
  {id:'latest',role:'agent',content:'Search Terms: "Data analyst", "Data scientist"',agent:'skill_finder',toolCalls:[],isStreaming:false},
 ]});
 expect(screen.getByText('Earlier market finding')).toBeVisible();
 expect(screen.getByText('Find relevant jobs')).toBeVisible();
 expect(screen.getByRole('combobox',{name:'Market country'})).toBeVisible();
 expect(screen.getByRole('checkbox',{name:'Data analyst'})).toBeVisible();
 expect(screen.queryByRole('button',{name:/History and setup|Stage workflow response|Browse skills|Save draft|Undo local change/})).not.toBeInTheDocument();
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Explain these search terms'}});
 fireEvent.keyDown(screen.getByRole('textbox',{name:'Question'}),{key:'Enter',code:'Enter'});
 await waitFor(()=>expect(send).toHaveBeenCalledWith({mode:'workflow',text:'Explain these search terms'}));
});

it('expands categories in place, keeps exclusions across pages and confirms partial changed evidence in one click', async () => {
 const api = await import('@/features/market-demand/api');
 const {largeReviewFixture,reconciliationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...largeReviewFixture(),reconciliations:reconciliationFixture().reconciliations,evidence_omissions:['Indeed unavailable in this market'],extraction_coverage:{status:'partial' as const,acknowledged:false}};
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 vi.mocked(api.confirmSkillReviewSelection).mockImplementation(async(_id,body)=>({...review,...body,selection_revision:3}));
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('checkbox',{name:'Select category Tools (12 current members)'}));
 fireEvent.click(screen.getByRole('button',{name:'Expand Tools'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Job skill 01'}));
 fireEvent.click(screen.getByRole('button',{name:'Next Tools page'}));
 expect(screen.getByRole('checkbox',{name:'Select Job skill 12'})).toBeChecked();
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Job skill 12'}));
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Keep this question'}});
 expect(screen.queryByRole('button',{name:/Save draft|Undo local change|Browse skills|Acknowledge available evidence|Save reviewed choices/})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 await waitFor(()=>expect(send).toHaveBeenCalledOnce());
 expect(api.confirmSkillReviewSelection).toHaveBeenCalledWith(1,expect.objectContaining({
  expected_candidate_revision:1,expected_selection_revision:2,confirm_current_evidence:true,
  selected_candidate_ids:['job-02','job-03','job-04','job-05','job-06','job-07','job-08','job-09','job-10','job-11'],
  excluded_candidate_ids:['reference-1','job-01','job-12'],expected_omissions:['Indeed unavailable in this market'],
 }));
 expect(api.saveSkillReviewDraft).not.toHaveBeenCalled();expect(api.continueWithAvailableEvidence).not.toHaveBeenCalled();expect(api.approveSkillIntegration).not.toHaveBeenCalled();
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('Keep this question');
});

it('sends exact job-group names and retains the choice and question through unknown-outcome recovery',async()=>{
 const send=vi.fn().mockResolvedValueOnce({outcome:'detached'}).mockResolvedValueOnce({outcome:'completed'});
 const reconcile=vi.fn().mockResolvedValue(undefined);
 await openReviewWorkspace({skillReview:null,send,reconcile,agentState:{...EMPTY_STATE,fetched_jobs:[{title:'Analyst'}],job_groups:{'BI / Data & Reporting':[0],'Data Scientists':[0]}}});
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Keep my question'}});
 fireEvent.click(screen.getByRole('checkbox',{name:'BI / Data & Reporting'}));
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 await screen.findByRole('button',{name:'Check analysis status'});
 expect(send).toHaveBeenCalledWith({mode:'workflow',text:'Select these job groups by exact name: ["BI / Data & Reporting"]. Preserve these names; do not convert them to indices.'});
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('Keep my question');
 expect(screen.getByRole('checkbox',{name:'BI / Data & Reporting'})).toBeChecked();
 expect(screen.getByRole('button',{name:/Confirm Selection/})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Check analysis status'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:/Confirm Selection/})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 await waitFor(()=>expect(send).toHaveBeenCalledTimes(2));
});

it('keeps double-click confirmation single-flight and never maps when confirmation fails',async()=>{
 const api=await import('@/features/market-demand/api');
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...reviewFixture(),selected_candidate_ids:['python']};
 let reject!:(cause:Error)=>void;
 vi.mocked(api.confirmSkillReviewSelection).mockImplementation(()=>new Promise((_resolve,failure)=>{reject=failure;}));
 const send=vi.fn();await openReviewWorkspace({skillReview:review,send});
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Retain this'}});
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 expect(api.confirmSkillReviewSelection).toHaveBeenCalledOnce();
 await act(async()=>reject(new Error('Confirmation offline')));
 expect(await screen.findByRole('alert')).toHaveTextContent('Confirmation offline');
 fireEvent.click(screen.getByRole('button',{name:'Expand Tools'}));
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeChecked();
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('Retain this');
 expect(send).not.toHaveBeenCalled();expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});

it('keeps the question and current choices through restoration timeout and offers retry',async()=>{
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=reviewFixture();const retryRestoration=vi.fn();
 const {rerender}=await openReviewWorkspace({skillReview:review,retryRestoration});
 fireEvent.click(screen.getByRole('checkbox',{name:'Select category Tools (2 current members)'}));
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Keep my question'}});
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:review,isRestored:false,error:'Restoration timed out',retryRestoration}));
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');rerender(<TestRouter><Page/></TestRouter>);
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('Keep my question');
 expect(screen.getByRole('button',{name:/Confirm Selection/})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Retry restoration'}));expect(retryRestoration).toHaveBeenCalledOnce();
});

it('keeps final publication distinct from selection confirmation and ordinary workflow chat',async()=>{
 const api=await import('@/features/market-demand/api');
 const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=integrationFixture();const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:review,send});
 expect(screen.queryByRole('button',{name:/Confirm Selection/})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Approve and publish'})).toBeEnabled();
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Discuss the mapping'}});
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith({mode:'workflow',text:'Discuss the mapping'}));
 expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});

it('does not attach chart context to ordinary questions and returns to workflow after a chart question',async()=>{
 const {workspaceReviewFixture,workspaceEvidenceFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture();review.selected_candidate_ids=[review.candidates[0].candidate_id];review.candidates[0].onet_associations=[workspaceEvidenceFixture()];
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:review,send});
 expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Analysis details'}));
 fireEvent.click(await screen.findByRole('button',{name:/Ask about Python/}));
 expect(screen.getByText('Chart evidence attached for this question')).toBeVisible();
 await waitFor(()=>expect(screen.getByRole('textbox',{name:'Question'})).toHaveFocus());
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'contextual',context:expect.objectContaining({candidate_ids:[review.candidates[0].candidate_id],intent:'explain'})})));
 await waitFor(()=>expect(screen.queryByText('Chart evidence attached for this question')).not.toBeInTheDocument());
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'Continue with the agents'}});
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenLastCalledWith({mode:'workflow',text:'Continue with the agents'}));
});

it('rejects a late review from a different active run',async()=>{
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 await openReviewWorkspace({skillReview:reviewFixture(),agentState:{...EMPTY_STATE,run_id:'new-run'}});
 expect(screen.queryByRole('region',{name:'Choose skills'})).not.toBeInTheDocument();
});

it('refreshes stale confirmation evidence while retaining the exact current choices and typed question',async()=>{
 const api=await import('@/features/market-demand/api');const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=reviewFixture();const refreshSkillReview=vi.fn().mockResolvedValue(undefined);const send=vi.fn();
 vi.mocked(api.confirmSkillReviewSelection).mockRejectedValue(new Error('Evidence changed. Refresh before confirming.'));
 await openReviewWorkspace({skillReview:review,refreshSkillReview,send});
 fireEvent.click(screen.getByRole('checkbox',{name:'Select category Tools (2 current members)'}));
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'My retained question'}});
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 fireEvent.click(await screen.findByRole('button',{name:'Refresh current evidence'}));
 await waitFor(()=>expect(refreshSkillReview).toHaveBeenCalledOnce());
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('My retained question');
 expect(screen.getByRole('checkbox',{name:'Select category Tools (2 current members)'})).toBeChecked();
 expect(send).not.toHaveBeenCalled();
});

it('lets a new jobs-only run explore compact O*NET occupation importance in Details without changing sources or selecting skills',async()=>{
 const api=await import('@/features/market-demand/api');const {reviewFixture,workspaceEvidenceFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=reviewFixture();const send=vi.fn().mockResolvedValue({outcome:'completed'});
 const labels=['Planning','Decision Making','Writing','Critical Thinking','Math','Logic','Low Priority'];
 const values=[2,5,4,4.5,3.5,3,1];
 const items=labels.map((label,index)=>{
  const item=workspaceEvidenceFixture({id:`descriptor-${index}`,label,element_id:`element-${index}`,soc_code:'15-2051.00',occupation_title:'Data Scientists',release:'31.0'}).evidence;
  return {...item,ratings:{IM:{...item.ratings.IM!,value:values[index]}}};
 });
 vi.mocked(api.getOccupationSkills).mockResolvedValue({release:'31.0',soc_code:'15-2051.00',items});
 await openReviewWorkspace({skillReview:review,send,agentState:{...EMPTY_STATE,run_id:'run-1',sources:['indeed','linkedin','headhunter'],evidence_sources:['jobs']}});
 fireEvent.click(screen.getByRole('button',{name:'Analysis details'}));
 fireEvent.click(screen.getByRole('button',{name:'O*NET importance'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Search'})).toBeEnabled());
 fireEvent.change(screen.getByRole('textbox',{name:'Search occupations'}),{target:{value:'data'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 fireEvent.click(await screen.findByRole('button',{name:'Browse Data Scientists'}));
 const rows=await screen.findAllByRole('article');expect(rows).toHaveLength(5);
 expect(rows.map(row=>row.getAttribute('aria-label'))).toEqual(['Decision Making','Critical Thinking','Writing','Math','Logic']);
 expect(screen.getByText(/Occupation reference.*not.*individual job skill/i)).toBeVisible();
 expect(screen.queryByRole('combobox',{name:'Reference question metric'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Next reference page'}));
 expect(screen.getAllByRole('article')).toHaveLength(2);
 fireEvent.click(screen.getByRole('button',{name:'Ask about Planning'}));
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('Explain this O*NET descriptor and its reported evidence.');
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith(expect.objectContaining({mode:'contextual',context:{kind:'occupation_reference',version:1,intent:'explain',release:'31.0',occupation_codes:['15-2051.00'],element_ids:['element-0'],metric:'IM'}})));
 expect(api.confirmOnetOccupations).not.toHaveBeenCalled();expect(api.confirmSkillReviewSelection).not.toHaveBeenCalled();expect(api.approveSkillIntegration).not.toHaveBeenCalled();
 expect(screen.getByRole('checkbox',{name:'Select category Tools (2 current members)'})).not.toBeChecked();
});

it('retains typed follow-up and releases submitted chart context when the prior answer completes',async()=>{
 const {workspaceReviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture();review.selected_candidate_ids=[review.candidates[0].candidate_id];
 let complete!:(value:{outcome:'completed'})=>void;
 const send=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{complete=resolve;})).mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Analysis details'}));
 fireEvent.click(await screen.findByRole('button',{name:/Ask about Python/}));
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 fireEvent.change(screen.getByRole('textbox',{name:'Question'}),{target:{value:'My next workflow question'}});
 await act(async()=>complete({outcome:'completed'}));
 expect(screen.getByRole('textbox',{name:'Question'})).toHaveValue('My next workflow question');
 expect(screen.queryByText('Chart evidence attached for this question')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(()=>expect(send).toHaveBeenLastCalledWith({mode:'workflow',text:'My next workflow question'}));
});

it('lets the teacher change a current curriculum-fit selection inline and hides publication until confirmed again',async()=>{
 const api=await import('@/features/market-demand/api');const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=integrationFixture();const send=vi.fn().mockResolvedValue({outcome:'completed'});
 vi.mocked(api.confirmSkillReviewSelection).mockImplementation(async(_id,body)=>({...review,...body,selection_revision:3,integration_review:null}));
 await openReviewWorkspace({skillReview:review,send});
 expect(screen.getByRole('button',{name:'Approve and publish'})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'Change selection'}));
 fireEvent.click(screen.getByRole('button',{name:'Expand Tools'}));
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeChecked();
 expect(screen.queryByRole('button',{name:'Approve and publish'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('checkbox',{name:'Select SQL'}));
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 await waitFor(()=>expect(send).toHaveBeenCalledWith({mode:'workflow',text:'Map the confirmed selected skills to the curriculum and prepare the curriculum fit review. Do not approve or publish.'}));
 expect(api.confirmSkillReviewSelection).toHaveBeenCalledWith(1,expect.objectContaining({selected_candidate_ids:['python','sql'],confirm_current_evidence:true}));
 expect(api.approveSkillIntegration).not.toHaveBeenCalled();
});

it('automatically reveals current choices when the displayed curriculum-fit review is stale',async()=>{
 const {integrationFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...integrationFixture(),candidate_revision:2};
 await openReviewWorkspace({skillReview:review});
 expect(screen.getByRole('button',{name:/Confirm Selection/})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'Expand Tools'}));
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeChecked();
 expect(screen.queryByRole('button',{name:'Approve and publish'})).not.toBeInTheDocument();
});

it('keeps removed saved choices visibly repairable even when no current candidates remain',async()=>{
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...reviewFixture(),candidates:[],selected_candidate_ids:['removed-python']};
 await openReviewWorkspace({skillReview:review});
 expect(screen.getByRole('alert')).toHaveTextContent(/removed or lack supporting job postings/);
 expect(screen.getByRole('button',{name:/Confirm Selection/})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Remove unsupported removed-python'}));
 expect(screen.queryByRole('button',{name:'Remove unsupported removed-python'})).not.toBeInTheDocument();
});

it('keeps current choices editable after a completed reply that has not prepared a curriculum-fit review',async()=>{
 const api=await import('@/features/market-demand/api');const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...reviewFixture(),selected_candidate_ids:['python']};
 vi.mocked(api.confirmSkillReviewSelection).mockResolvedValue({...review,selection_revision:3,integration_review:null});
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:/Confirm Selection/}));
 await waitFor(()=>expect(send).toHaveBeenCalledOnce());
 expect(screen.getByRole('region',{name:'Choose skills'})).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'Expand Tools'}));
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeChecked();
 expect(screen.getByRole('checkbox',{name:'Select SQL'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:'Approve and publish'})).not.toBeInTheDocument();
});

it('compares only job-backed skills in Details when none are selected',async()=>{
 const {largeReviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 await openReviewWorkspace({skillReview:largeReviewFixture()});
 fireEvent.click(screen.getByRole('button',{name:'Analysis details'}));
 expect(screen.getByText('Showing 5 of 58 skills · entries 1–5')).toBeVisible();
 expect(screen.getByText('Page 1 of 12')).toBeVisible();
});

it('shows persisted selected categories first and keeps category order stable through local checkbox edits',async()=>{
 const {reviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const base=reviewFixture();
 const review={...base,categories:[{category_id:'general',label:'General'},{category_id:'technical',label:'Technical'},{category_id:'reference',label:'Reference only'}],
  candidates:base.candidates.map(item=>({...item,category_id:item.candidate_id==='sql'?'technical':item.candidate_id==='reference'?'reference':'general'})),
  selected_candidate_ids:['sql']};
 await openReviewWorkspace({skillReview:review});
 const headings=()=>screen.getAllByRole('button',{name:/^Expand /}).map(button=>button.getAttribute('aria-label'));
 expect(headings()).toEqual(['Expand Technical','Expand General']);
 fireEvent.click(screen.getByRole('checkbox',{name:'Select category General (1 current members)'}));
 expect(headings()).toEqual(['Expand Technical','Expand General']);
 fireEvent.click(screen.getByRole('checkbox',{name:'Select category Technical (1 current members)'}));
 expect(headings()).toEqual(['Expand Technical','Expand General']);
 expect(screen.queryByRole('button',{name:'Expand Reference only'})).not.toBeInTheDocument();
});
