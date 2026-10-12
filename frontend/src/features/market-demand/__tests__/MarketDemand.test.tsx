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
const workspaceObservers = new Map<Element,ResizeObserverCallback>();
function measureWorkspace(entries: ResizeObserverEntry[], observer: ResizeObserver) {for (const entry of entries) workspaceObservers.get(entry.target)?.([entry],observer);}
vi.stubGlobal("ResizeObserver", class {callback:ResizeObserverCallback; constructor(callback: ResizeObserverCallback){this.callback=callback;} observe(node:Element){workspaceObservers.set(node,this.callback);} disconnect(){}});
const compareFailure=vi.hoisted(() => ({enabled:false}));
vi.mock('@/features/market-demand/components/WorkspaceCompare',async () => {
 const actual=await vi.importActual<typeof import('@/features/market-demand/components/WorkspaceCompare')>('@/features/market-demand/components/WorkspaceCompare');
 return {default:(props:import('@/features/market-demand/components/WorkspaceDataTable').WorkspaceViewProps) => {if(compareFailure.enabled) throw new Error('Chart-view loading failed'); return <actual.default {...props}/>;}};
});
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
  ChatMessage,
  PipelineStageId,
  StageStatus,
  SendCommand,
  SendResult,
} from "@/features/market-demand/types";
import type { UseAgentStreamReturn } from "@/features/market-demand/hooks/useAgentStream";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
vi.mock("@/features/market-demand/api", async () => ({skillReviewErrorMessage: (await vi.importActual<typeof import("@/features/market-demand/api")>("@/features/market-demand/api")).skillReviewErrorMessage,fetchJobSources: vi.fn(async () => [{id:"indeed",label:"Indeed",availability:"available",reason:null},{id:"linkedin",label:"LinkedIn",availability:"available",reason:null}]), confirmOnetOccupations:vi.fn(), saveSkillReviewDraft:vi.fn(), getOccupationSkills:vi.fn(), fetchOnetReleases:vi.fn(async()=>({items:[{version:"31.0",active:true,attribution:"O*NET"}]})), searchOnetOccupations:vi.fn(async()=>({items:[{soc_code:"15-2051.00",title:"Data Scientists",description:"Analyze data"}],total:1,release:"31.0"}))}));

import { confirmOnetOccupations, saveSkillReviewDraft, getOccupationSkills } from "@/features/market-demand/api";

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
  compareFailure.enabled=false;
  vi.mocked(confirmOnetOccupations).mockReset();
  vi.mocked(saveSkillReviewDraft).mockReset();
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
});

async function ensureSetup() {
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

describe("MarketDemandPage", () => {
  it("passes the route course id into the market-demand hook", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(useAgentStream).toHaveBeenCalledWith(1, null, null);
  });

  it("renders an unconfirmed market country placeholder", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(screen.getByRole("combobox", { name: /market country/i })).toHaveTextContent(
      "Choose country"
    );
  });

  it("passes the selected market country into the market-demand hook", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    const user = userEvent.setup();
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    await user.click(screen.getByRole("combobox", { name: /market country/i }));
    await user.click(await screen.findByRole("option", { name: "China" }));

    expect(useAgentStream).toHaveBeenLastCalledWith(1, "China", null);
  });

  it("disables input while restoring conversation state", async () => {
    vi.mocked(useAgentStream).mockReturnValue(
      mockStreamReturn({ isLoadingHistory: true })
    );
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(screen.getByPlaceholderText("Type your response...")).toBeDisabled();
    expect(screen.getByRole("combobox", { name: /market country/i })).toHaveAttribute(
      "data-disabled"
    );
  });

  it("syncs the selector from restored agent state", async () => {
    vi.mocked(useAgentStream).mockReturnValue(
      mockStreamReturn({
        agentState: {
          ...EMPTY_STATE,
          job_search_country: "China",
          job_search_country_confirmed: true,
          job_search_location: "China",
        },
      })
    );
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(
      await screen.findByRole("combobox", { name: /market country/i })
    ).toHaveTextContent("China");
  });

  it("renders without crashing", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();
    // Both breadcrumb and empty state heading contain the text
    const els = screen.getAllByText(/market demand analyst/i);
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  it("shows actionable analysis setup on empty state", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();
    expect(
      screen.getByRole("button",{name:"Start an analysis"})
    ).toBeInTheDocument();
  });

  it("starts an explicit workflow from the analysis action", async () => {
    const send = vi.fn();
    vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({ send }));

    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    const user = userEvent.setup();
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    const suggestion = screen.getByRole("button",{name:"Start an analysis"});
    await screen.findByRole("checkbox", {name:"Indeed"});
    await user.click(suggestion);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("renders messages when present", async () => {
    const messages: ChatMessage[] = [
      {
        id: "u1",
        role: "user",
        content: "Hello agent",
        toolCalls: [],
        isStreaming: false,
      },
      {
        id: "a1",
        role: "agent",
        agent: "supervisor",
        agentDisplayName: "Supervisor",
        agentEmoji: "📊",
        content: "I found some jobs",
        toolCalls: [],
        isStreaming: false,
      },
    ];
    vi.mocked(useAgentStream).mockReturnValue(
      mockStreamReturn({ messages })
    );

    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(screen.getByText("Hello agent")).toBeInTheDocument();
    expect(screen.getByText("I found some jobs")).toBeInTheDocument();
  });

  it("uses source summary from the review instead of another thread state", async () => {
    vi.mocked(useAgentStream).mockReturnValue(
      mockStreamReturn({
        skillReview: {...(await import("@/features/market-demand/__tests__/review-fixtures")).reviewFixture(),analysis_metadata:{country:"Uzbekistan",job_sources:["headhunter"],evidence_sources:["jobs"],onet_release:null,occupations:[],created_at:"2026-10-01",updated_at:"2026-10-02"}},
        agentState: {
          ...EMPTY_STATE,
          job_search_country: "China",
          job_search_country_confirmed: true,
          fetched_jobs: [{ title: "Frontend Engineer", company: "Acme" }],
        },
      })
    );

    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <TestRouter>
        <MarketDemandPage />
      </TestRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await ensureSetup();

    expect(screen.getByLabelText("Analysis source summary")).toHaveTextContent("Market: Uzbekistan · Job sources: headhunter");
    expect(screen.getByLabelText("Analysis source summary")).not.toHaveTextContent("China");
  });
});

it("renders Uzbekistan as a supported market choice", async()=>{
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
 const {default:Page}=await import("@/features/market-demand/pages/MarketDemandPage");
 render(<TestRouter><Page/></TestRouter>);
 const user=userEvent.setup();
 await user.click(screen.getByRole("combobox",{name:/Market country/}));
 expect(await screen.findByRole("option",{name:"Uzbekistan"})).toBeInTheDocument();
});

it("shows source failures separately from successful empty collections",async()=>{
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({agentState:{...EMPTY_STATE,source_outcomes:{headhunter:{status:"error",received_count:0,usable_count:0,warnings:["Provider unavailable"]},linkedin:{status:"empty",received_count:0,usable_count:0,warnings:[]}}}}));
 const {default:Page}=await import("@/features/market-demand/pages/MarketDemandPage");
 render(<TestRouter><Page/></TestRouter>);
 await ensureSetup();
 expect(screen.getByText(/headhunter: error/i)).toBeInTheDocument();
 expect(screen.getByText(/linkedin: empty/i)).toBeInTheDocument();
 expect(screen.getByText("Provider unavailable")).toBeInTheDocument();
});

it("keeps input disabled when restoring saved source choices fails", async () => {
  const retry = vi.fn();
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({
    isRestored: false,
    error: "State unavailable",
    retryRestoration: retry,
  }));
  const {default: Page} = await import("@/features/market-demand/pages/MarketDemandPage");
  render(<TestRouter><Page/></TestRouter>);
  await screen.findByRole("checkbox", {name: "Indeed"});
  expect(screen.getByPlaceholderText("Type your response...")).toBeDisabled();
  expect(screen.getByText("State unavailable")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "Retry restoration"}));
  expect(retry).toHaveBeenCalled();
});


it("blocks New analysis while an occupation confirmation is pending", async () => {
  let finish!: (value: never) => void;
  vi.mocked(confirmOnetOccupations).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  const clear = vi.fn(async () => undefined);
  const refresh = vi.fn(async () => undefined);
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({
    clearConversation: clear,
    refreshSkillReview: refresh,
    messages: [{id:"u1",role:"user",content:"Previous analysis",toolCalls:[],isStreaming:false}],
    agentState: {...EMPTY_STATE,run_id:"run-1",sources:["headhunter"],evidence_sources:["onet"],onet_release:"31.0",selected_onet_occupations:["15-2051.00"]},
  }));
  const {default: Page} = await import("@/features/market-demand/pages/MarketDemandPage");
  render(<TestRouter><Page/></TestRouter>);
  await ensureSetup();
  await waitFor(() => {
    const release = screen.getByRole("combobox", { name: "O*NET release" }) as HTMLSelectElement;
    const loading = !!screen.queryByText("Loading O*NET catalog…");
    const selected = !!screen.queryByText(/1 selected/);
    expect(
      screen.getByRole("button", { name: "Confirm occupations" }),
      `Picker readiness: release=${release.value}, loading=${loading}, selected=${selected}`
    ).toBeEnabled();
  }, { timeout: 10000 });
  fireEvent.click(screen.getByRole("button", {name:"Confirm occupations"}));
  await waitFor(() => expect(confirmOnetOccupations).toHaveBeenCalled());
  expect(screen.getByRole("button",{name:"New analysis"})).toBeDisabled();
  expect(clear).not.toHaveBeenCalled();
  await act(async () => {finish(null as never);});
  expect(refresh).toHaveBeenCalledOnce();

});

it("locks market and source settings during occupation confirmation", async () => {
  let finish!: (value: never) => void;
  vi.mocked(confirmOnetOccupations).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({
    agentState: {...EMPTY_STATE, run_id:"run-1", evidence_sources:["onet"], onet_release:"31.0", selected_onet_occupations:["15-2051.00"]},
  }));
  const {default: Page} = await import("@/features/market-demand/pages/MarketDemandPage");
  render(<TestRouter><Page/></TestRouter>);
  await waitFor(() => {
    const release = screen.getByRole("combobox", { name: "O*NET release" }) as HTMLSelectElement;
    const loading = !!screen.queryByText("Loading O*NET catalog…");
    const selected = !!screen.queryByText(/1 selected/);
    expect(
      screen.getByRole("button", { name: "Confirm occupations" }),
      `Picker readiness: release=${release.value}, loading=${loading}, selected=${selected}`
    ).toBeEnabled();
  }, { timeout: 10000 });
  fireEvent.click(screen.getByRole("button", {name:"Confirm occupations"}));
  await waitFor(() => expect(confirmOnetOccupations).toHaveBeenCalled());
  try {
    expect(screen.getByRole("combobox", {name:"Market country"})).toBeDisabled();
    expect(screen.getByRole("checkbox", {name:"Job postings"})).toBeDisabled();
  } finally {
    await act(async () => { finish(null as never); });
  }
});


it("splits at actual content width 1000 and retains the mounted composer at 999", async () => {
 const {default:Page} = await import("@/features/market-demand/pages/MarketDemandPage");
 render(<TestRouter><Page/></TestRouter>);
 await screen.findByRole("button",{name:"Start an analysis"});
 const workspace = screen.getByLabelText("Teacher evidence workspace");
 const resize = (width:number) => act(() => measureWorkspace([{contentRect:{width},target:workspace} as unknown as ResizeObserverEntry],{} as ResizeObserver));
 resize(999); expect(screen.getByRole("tab",{name:"Conversation"})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("tab",{name:"Conversation"}));
 const composer=screen.getByPlaceholderText("Type your response..."); fireEvent.change(composer,{target:{value:"Keep this draft"}});
 fireEvent.click(screen.getByRole("tab",{name:"Workspace"}));
 resize(1000); expect(screen.queryByRole("tab",{name:"Conversation"})).not.toBeInTheDocument();
 expect(screen.getByPlaceholderText("Type your response...")).toBe(composer); expect(composer).toHaveValue("Keep this draft");
});

async function openReviewWorkspace(overrides: Partial<UseAgentStreamReturn> = {}) {
 const {workspaceReviewFixture} = await import('@/features/market-demand/__tests__/review-fixtures');
 const review = workspaceReviewFixture();
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({skillReview:review,...overrides}));
 const {default:Page} = await import('@/features/market-demand/pages/MarketDemandPage');
 const rendered=render(<TestRouter><Page/></TestRouter>);
 await act(async () => {await Promise.resolve();});
 const node=screen.getByLabelText('Teacher evidence workspace');
 act(() => measureWorkspace([{contentRect:{width:1000},target:node} as unknown as ResizeObserverEntry],{} as ResizeObserver));
 return {review,...rendered};
}
it('ordinary questions remain minimal Run Explain after inspecting a chart', async () => {
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({send});
 fireEvent.click(screen.getByRole('button',{name:'Inspect Python'}));
 fireEvent.change(screen.getByPlaceholderText('Type your response...'),{target:{value:'What does this analysis show?'}});
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(() => expect(send).toHaveBeenCalledOnce());
 expect(send.mock.calls[0][0]).toMatchObject({mode:'contextual',context:{intent:'explain',focused_candidate_id:null,candidate_ids:[],occupation_codes:[],filters:{scope:'all',search:'',category_ids:[]}}});
});
it('Ask stages editable context only and completed send removes focus without losing typed follow-up', async () => {
 let finish!: (result: {outcome:'completed'}) => void;
 const send=vi.fn<(command:SendCommand)=>Promise<SendResult>>(() => new Promise<{outcome:'completed'}>(resolve => {finish=resolve;}));
 await openReviewWorkspace({send});
 fireEvent.click(screen.getByRole('button',{name:'Inspect Python'}));
 fireEvent.click(within(screen.getByRole('region',{name:'Focused evidence'})).getByRole('button',{name:'Ask about Python'}));
 expect(send).not.toHaveBeenCalled(); expect(saveSkillReviewDraft).not.toHaveBeenCalled();
 expect(screen.getByLabelText('Attached context')).toHaveTextContent('Python');
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 fireEvent.change(screen.getByPlaceholderText('Type your response...'),{target:{value:'A new question'}});
 await act(async () => finish({outcome:'completed'}));
 expect(screen.getByPlaceholderText('Type your response...')).toHaveValue('A new question');
 expect(screen.getByLabelText('Attached context')).toHaveTextContent('No focused skills');
 expect(send.mock.calls[0][0]).toMatchObject({mode:'contextual',context:{intent:'explain'}});
});
it('retains all source, view and composer state when New analysis rejects', async () => {
 const clear=vi.fn(async () => {throw new Error('Analysis still running');});
 await openReviewWorkspace({clearConversation:clear});
 fireEvent.click(screen.getByRole('button',{name:'Data'}));
 fireEvent.change(screen.getByPlaceholderText('Type your response...'),{target:{value:'Keep question'}});
 fireEvent.click(screen.getByRole('button',{name:'New analysis'}));
 expect(screen.getByText(/current analysis will no longer be resumable/i)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Start new analysis'}));
 await screen.findByText('Analysis still running');
 expect(screen.getByLabelText('Evidence data')).toBeInTheDocument();
 expect(screen.getByPlaceholderText('Type your response...')).toHaveValue('Keep question');
 expect(screen.getByLabelText('Analysis source summary')).toHaveTextContent('headhunter');
 expect(clear).toHaveBeenCalledOnce();
});
it('Cancel New analysis makes no reset request and dirty save must acknowledge before reset', async () => {
 const clear=vi.fn(async () => undefined);
 const {review}=await openReviewWorkspace({clearConversation:clear});
 fireEvent.click(screen.getByRole('button',{name:'New analysis'})); fireEvent.click(screen.getByRole('button',{name:'Cancel'})); expect(clear).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));
 fireEvent.click(screen.getByRole('button',{name:'New analysis'}));
 let finish!: () => void;
 vi.mocked(saveSkillReviewDraft).mockImplementationOnce(() => new Promise(resolve => {finish=()=>resolve({...review,selection_revision:3,selected_candidate_ids:[review.candidates[0].candidate_id]});}));
 fireEvent.click(screen.getByRole('button',{name:'Save and start new analysis'}));
 await waitFor(() => expect(saveSkillReviewDraft).toHaveBeenCalledOnce()); expect(clear).not.toHaveBeenCalled();
 await act(async () => finish()); await waitFor(() => expect(clear).toHaveBeenCalledOnce());
 expect(screen.getByPlaceholderText('Type your response...')).toHaveValue('');
 expect(screen.getByRole('region',{name:'Analysis setup'})).toBeInTheDocument();
});
it('failed dirty save keeps the analysis and never requests reset', async () => {
 const clear=vi.fn(async () => undefined);
 await openReviewWorkspace({clearConversation:clear});
 vi.mocked(saveSkillReviewDraft).mockRejectedValueOnce(new Error('Save offline'));
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));
 fireEvent.click(screen.getByRole('button',{name:'New analysis'})); fireEvent.click(screen.getByRole('button',{name:'Save and start new analysis'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Save offline'); expect(clear).not.toHaveBeenCalled(); expect(screen.getByRole('checkbox',{name:'Select Python',hidden:true})).toBeChecked();
});
it('locks shortlist mutations when reconciliation cannot restore the workspace', async () => {
 await openReviewWorkspace({isRestored:false,error:'Snapshot unavailable'});
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeDisabled();
});
it('preserves an explicit role descriptor in inspector Ask context', async () => {
 const {workspaceReviewFixture,workspaceEvidenceFixture,workspaceSoc,workspaceEvidenceId} = await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture(); const association=workspaceEvidenceFixture();
 review.candidates[0].onet_associations=[association,workspaceEvidenceFixture({id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',element_id:'other',label:'Other descriptor'})];
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Compare'}));
 fireEvent.click(await screen.findByRole('checkbox',{name:'Display Developer'}));
 fireEvent.click(screen.getByRole('button',{name:'Data'}));
 fireEvent.change(screen.getByRole('combobox',{name:'Compare occupation'}),{target:{value:workspaceSoc}});
 fireEvent.change(screen.getByRole('combobox',{name:'Descriptor for Python · Developer'}),{target:{value:workspaceEvidenceId}});
 fireEvent.click(screen.getByRole('button',{name:'Inspect Python'}));
 fireEvent.click(within(screen.getByRole('region',{name:'Focused evidence'})).getByRole('button',{name:'Ask about Python'}));
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(() => expect(send).toHaveBeenCalledOnce());
 expect(send.mock.calls[0][0].context.descriptor_choices).toEqual([{candidate_id:review.candidates[0].candidate_id,evidence_id:workspaceEvidenceId}]);
});
it('offers Data filters from the same local shortlist without posting', async () => {
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 await openReviewWorkspace({send});
 fireEvent.click(screen.getByRole('button',{name:'Data'}));
 fireEvent.click(screen.getByRole('checkbox',{name:'Only shortlisted skills'}));
 expect(screen.getByText('No matching skills. Change the filters to inspect evidence.')).toBeInTheDocument();
 expect(send).not.toHaveBeenCalled(); expect(saveSkillReviewDraft).not.toHaveBeenCalled();
});

it('keeps Data and shortlist usable when the lazy Compare view fails', async () => {
 await openReviewWorkspace(); compareFailure.enabled=true;
 const logged=vi.spyOn(console,'error').mockImplementation(() => {});
 try {
  fireEvent.click(screen.getByRole('button',{name:'Compare'}));
  await screen.findByText('Charts unavailable. Open Data to inspect the evidence and shortlist.');
  expect(logged).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Data'}));
  expect(screen.getByLabelText('Evidence data')).toBeInTheDocument();
  expect(screen.getAllByRole('checkbox',{name:'Select Python'}).length).toBeGreaterThan(0);
 } finally {logged.mockRestore();}
});
it('shows unread messages on the narrow tab without switching panes or remounting the composer', async () => {
 const {rerender}=await openReviewWorkspace();
 const workspace=screen.getByLabelText('Teacher evidence workspace');
 act(() => measureWorkspace([{contentRect:{width:999},target:workspace} as unknown as ResizeObserverEntry],{} as ResizeObserver));
 const composer=screen.getByPlaceholderText('Type your response...');
 const current=vi.mocked(useAgentStream).mock.results.at(-1)!.value;
 vi.mocked(useAgentStream).mockReturnValue({...current,messages:[{id:'new',role:'agent',content:'New evidence explanation',toolCalls:[],isStreaming:false}]});
 const {default:Page}=await import('@/features/market-demand/pages/MarketDemandPage');
 rerender(<TestRouter><Page/></TestRouter>);
 expect(screen.getByLabelText('New conversation messages')).toBeInTheDocument();
 expect(screen.getByRole('tab',{name:'Workspace'})).toHaveAttribute('aria-selected','true');
 expect(screen.getByPlaceholderText('Type your response...')).toBe(composer);
});

it('returns to minimal Run Explain after an explicitly staged reference answer', async () => {
 const {workspaceReviewFixture,workspaceEvidenceFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review={...workspaceReviewFixture(),candidates:[]};
 const send=vi.fn().mockResolvedValue({outcome:'completed'});
 vi.mocked(getOccupationSkills).mockResolvedValue({release:'31.0',soc_code:'15-2051.00',items:[workspaceEvidenceFixture({release:'31.0',soc_code:'15-2051.00',occupation_title:'Data Scientists'}).evidence]});
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Explore O*NET occupations'}));
 await waitFor(() => expect(screen.getByRole('button',{name:'Search'})).toBeEnabled());
 fireEvent.change(screen.getByRole('textbox',{name:'Search occupations'}),{target:{value:'data'}});
 fireEvent.click(screen.getByRole('button',{name:'Search'}));
 fireEvent.click(await screen.findByRole('button',{name:'Browse Data Scientists (15-2051.00)'}));
 fireEvent.click(await screen.findByRole('button',{name:'Ask about Programming'}));
 expect(send).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await waitFor(() => expect(send).toHaveBeenCalledOnce());
 expect(send.mock.calls[0][0]).toMatchObject({mode:'contextual',context:{kind:'occupation_reference'}});
 await waitFor(() => expect(screen.getByLabelText('Attached context')).toHaveTextContent('Review attachment'));
 expect(screen.getByLabelText('Attached context')).toHaveTextContent('No focused skills');
});

it('retains explicitly replaced Ask context while a prior response completes', async () => {
 const {workspaceReviewFixture}=await import('@/features/market-demand/__tests__/review-fixtures');
 const review=workspaceReviewFixture(); review.candidates.push({...review.candidates[0],candidate_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',display_name:'SQL'});
 let finish!: (result:SendResult)=>void;
 const send=vi.fn<(command:SendCommand)=>Promise<SendResult>>(() => new Promise(resolve => {finish=resolve;}));
 await openReviewWorkspace({skillReview:review,send});
 fireEvent.click(screen.getByRole('button',{name:'Inspect Python'}));
 fireEvent.click(within(screen.getByRole('region',{name:'Focused evidence'})).getByRole('button',{name:'Ask about Python'}));
 fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 fireEvent.click(screen.getByRole('button',{name:'Inspect SQL'}));
 fireEvent.click(within(screen.getByRole('region',{name:'Focused evidence'})).getByRole('button',{name:'Ask about SQL'}));
 await act(async () => finish({outcome:'completed'}));
 expect(screen.getByLabelText('Attached context')).toHaveTextContent('SQL');
 fireEvent.change(screen.getByPlaceholderText('Type your response...'),{target:{value:'Keep SQL replacement'}});
 expect(screen.getByLabelText('Attached context')).toHaveTextContent('SQL');
 expect(screen.getByPlaceholderText('Type your response...')).toHaveValue('Keep SQL replacement');
});
it('retains selected draft and focused inspector across narrow panes', async () => {
 await openReviewWorkspace();
 const workspace=screen.getByLabelText('Teacher evidence workspace');
 act(() => measureWorkspace([{contentRect:{width:999},target:workspace} as unknown as ResizeObserverEntry],{} as ResizeObserver));
 fireEvent.click(screen.getByRole('checkbox',{name:'Select Python'}));
 fireEvent.click(screen.getByRole('button',{name:'Inspect Python'}));
 fireEvent.click(screen.getByRole('tab',{name:/^Conversation/}));
 fireEvent.change(screen.getByPlaceholderText('Type your response...'),{target:{value:'Preserved question'}});
 fireEvent.click(screen.getByRole('tab',{name:'Workspace'}));
 expect(screen.getByRole('checkbox',{name:'Select Python'})).toBeChecked();
 expect(screen.getByRole('region',{name:'Focused evidence'})).toHaveTextContent('Python');
 fireEvent.click(screen.getByRole('tab',{name:/^Conversation/}));
 expect(screen.getByPlaceholderText('Type your response...')).toHaveValue('Preserved question');
});
