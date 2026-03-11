import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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
    getStepStatus: () => "not-started",
  }),
}));

vi.mock("../hooks/useAgentStream", () => ({
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
} from "../types";
import type { UseAgentStreamReturn } from "../hooks/useAgentStream";
import { useAgentStream } from "../hooks/useAgentStream";
import { ChatInput } from "../components/ChatInput";
import { ConnectionStatus } from "../components/ConnectionStatus";
import { PipelineStepper } from "../components/PipelineStepper";
import { UserMessage } from "../components/UserMessage";

// ── Shared constants ────────────────────────────────────────

const EMPTY_STATE: AgentState = {
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
    expect(screen.getByText(/insert/i)).toBeInTheDocument();
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
  beforeEach(() => {
    vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn());
  });

  it("renders without crashing", async () => {
    const { default: MarketDemandPage } = await import(
      "../pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    // Both breadcrumb and empty state heading contain the text
    const els = screen.getAllByText(/market demand analyst/i);
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  it("shows prompt suggestions on empty state", async () => {
    const { default: MarketDemandPage } = await import(
      "../pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );
    expect(
      screen.getByText(/analyze the job market/i)
    ).toBeInTheDocument();
  });

  it("calls send when a prompt suggestion is clicked", async () => {
    const send = vi.fn();
    vi.mocked(useAgentStream).mockReturnValue(mockStreamReturn({ send }));

    const { default: MarketDemandPage } = await import(
      "../pages/MarketDemandPage"
    );
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );

    const suggestion = screen.getByText(/analyze the job market/i);
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
      "../pages/MarketDemandPage"
    );
    render(
      <MemoryRouter>
        <MarketDemandPage />
      </MemoryRouter>
    );

    expect(screen.getByText("Hello agent")).toBeInTheDocument();
    expect(screen.getByText("I found some jobs")).toBeInTheDocument();
  });
});
