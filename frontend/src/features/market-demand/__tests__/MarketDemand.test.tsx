import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

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
} from "@/features/market-demand/types";
import type { UseAgentStreamReturn } from "@/features/market-demand/hooks/useAgentStream";
import { useAgentStream } from "@/features/market-demand/hooks/useAgentStream";
vi.mock("@/features/market-demand/api", () => ({fetchJobSources: vi.fn(async () => [{id:"indeed",label:"Indeed",availability:"available",reason:null},{id:"linkedin",label:"LinkedIn",availability:"available",reason:null}]), confirmOnetOccupations:vi.fn(), fetchOnetReleases:vi.fn(async()=>({items:[{version:"31.0",active:true,attribution:"O*NET"}]})), searchOnetOccupations:vi.fn(async()=>({items:[{soc_code:"15-2051.00",title:"Data Scientists",description:"Analyze data"}],total:1,release:"31.0"}))}));

import { confirmOnetOccupations } from "@/features/market-demand/api";

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
    messages: [],
    isStreaming: false,
    isLoadingHistory: false,
    currentAgent: null,
    agentState: EMPTY_STATE,
    pipelineStages: ALL_PENDING,
    threadId: null,
    send: vi.fn(),
    stop: vi.fn(),
    clearConversation: vi.fn(),
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
});

// ── ChatInput ───────────────────────────────────────────────

describe("ChatInput", () => {
  it("calls onSend with input text on Enter", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText("Type your response...");
    await user.type(textarea, "find python jobs{enter}");

    expect(onSend).toHaveBeenCalledWith("find python jobs");
  });

  it("does not send empty messages", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

    const textarea = screen.getByPlaceholderText("Type your response...");
    await user.type(textarea, "{enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("shows stop button when streaming", () => {
    render(<ChatInput onSend={vi.fn()} onStop={vi.fn()} isStreaming={true} />);
    // The stop button is icon-only (Square icon), find by role
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("clears input after send", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<ChatInput onSend={onSend} onStop={vi.fn()} isStreaming={false} />);

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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

    expect(useAgentStream).toHaveBeenCalledWith(1, null, null);
  });

  it("renders an unconfirmed market country placeholder", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

    expect(
      await screen.findByRole("combobox", { name: /market country/i })
    ).toHaveTextContent("China");
  });

  it("renders without crashing", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});
    // Both breadcrumb and empty state heading contain the text
    const els = screen.getAllByText(/market demand analyst/i);
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  it("shows prompt suggestions on empty state", async () => {
    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});
    expect(
      screen.getByText(/analyze the job market/i)
    ).toBeInTheDocument();
  });

  it("calls send when a prompt suggestion is clicked", async () => {
    const send = vi.fn();
    vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({ send }));

    const { default: MarketDemandPage } = await import(
      "@/features/market-demand/pages/MarketDemandPage"
    );
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

    const suggestion = screen.getByText(/analyze the job market/i);
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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

    expect(screen.getByText("Hello agent")).toBeInTheDocument();
    expect(screen.getByText("I found some jobs")).toBeInTheDocument();
  });

  it("shows the selected job market country in the state panel", async () => {
    vi.mocked(useAgentStream).mockReturnValue(
      mockStreamReturn({
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
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    if (!screen.queryByText("Restoring conversation...")) await screen.findByRole("checkbox", {name:"Indeed"});

    expect(screen.getByText(/market: China/i)).toBeInTheDocument();
  });
});

it("renders Uzbekistan as a supported market choice", async()=>{
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
 const {default:Page}=await import("@/features/market-demand/pages/MarketDemandPage");
 render(<MemoryRouter><Page/></MemoryRouter>);
 const user=userEvent.setup();
 await user.click(screen.getByRole("combobox",{name:/Market country/}));
 expect(await screen.findByRole("option",{name:"Uzbekistan"})).toBeInTheDocument();
});

it("shows source failures separately from successful empty collections",async()=>{
 vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({agentState:{...EMPTY_STATE,source_outcomes:{headhunter:{status:"error",received_count:0,usable_count:0,warnings:["Provider unavailable"]},linkedin:{status:"empty",received_count:0,usable_count:0,warnings:[]}}}}));
 const {default:Page}=await import("@/features/market-demand/pages/MarketDemandPage");
 render(<MemoryRouter><Page/></MemoryRouter>);
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
  render(<MemoryRouter><Page/></MemoryRouter>);
  await screen.findByRole("checkbox", {name: "Indeed"});
  expect(screen.getByPlaceholderText("Type your response...")).toBeDisabled();
  expect(screen.getByText("State unavailable")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", {name: "Retry restoration"}));
  expect(retry).toHaveBeenCalled();
});


it("does not restore an old occupation confirmation after clearing the analysis", async () => {
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
  const {rerender} = render(<MemoryRouter><Page/></MemoryRouter>);
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
  fireEvent.click(screen.getByRole("button", {name:"Clear"}));
  fireEvent.click(screen.getByRole("button", {name:"Delete"}));
  await waitFor(() => expect(clear).toHaveBeenCalled());
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
  rerender(<MemoryRouter><Page/></MemoryRouter>);
  await act(async () => {finish(null as never);});
  expect(refresh).not.toHaveBeenCalled();
  expect(vi.mocked(useAgentStream)).toHaveBeenLastCalledWith(1, null, null);
  expect(screen.queryByRole("button", {name:"Confirm occupations"})).not.toBeInTheDocument();
});

it("locks market and source settings during occupation confirmation", async () => {
  let finish!: (value: never) => void;
  vi.mocked(confirmOnetOccupations).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({
    agentState: {...EMPTY_STATE, run_id:"run-1", evidence_sources:["onet"], onet_release:"31.0", selected_onet_occupations:["15-2051.00"]},
  }));
  const {default: Page} = await import("@/features/market-demand/pages/MarketDemandPage");
  render(<MemoryRouter><Page/></MemoryRouter>);
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
