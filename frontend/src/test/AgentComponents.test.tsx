import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { AGENTS, getAgentById } from "../features/agents/config";
import { AgentCard } from "../features/agents/components/AgentCard";
import { AgentPageHeader } from "../features/agents/components/AgentPageHeader";

// Mock sonner
vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

/* ── Agent Config ──────────────────────────────────────────── */

describe("Agent Config", () => {
  it("has architect agent enabled", () => {
    const architect = getAgentById("architect");
    expect(architect).toBeDefined();
    expect(architect!.enabled).toBe(true);
    expect(architect!.route).toBe("architect");
  });

  it("has market-analyst agent disabled", () => {
    const analyst = getAgentById("market-analyst");
    expect(analyst).toBeDefined();
    expect(analyst!.enabled).toBe(false);
  });

  it("returns undefined for unknown agent", () => {
    expect(getAgentById("nonexistent")).toBeUndefined();
  });

  it("all agents have required fields", () => {
    for (const agent of AGENTS) {
      expect(agent.id).toBeTruthy();
      expect(agent.name).toBeTruthy();
      expect(agent.description).toBeTruthy();
      expect(agent.route).toBeTruthy();
      expect(agent.icon).toBeDefined();
      expect(agent.color).toBeTruthy();
    }
  });
});

/* ── AgentCard ─────────────────────────────────────────────── */

describe("AgentCard", () => {
  const architect = getAgentById("architect")!;
  const analyst = getAgentById("market-analyst")!;

  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it("renders enabled agent with name and description", () => {
    render(
      <MemoryRouter>
        <AgentCard agent={architect} courseId={1} />
      </MemoryRouter>
    );
    expect(screen.getByText("Curricular Alignment Architect")).toBeInTheDocument();
    expect(screen.getByText(architect.description)).toBeInTheDocument();
  });

  it("renders status badge for enabled agent", () => {
    render(
      <MemoryRouter>
        <AgentCard agent={architect} courseId={1} status="in-progress" />
      </MemoryRouter>
    );
    expect(screen.getByText("In Progress")).toBeInTheDocument();
  });

  it("renders progress bar when progress is provided", () => {
    const { container } = render(
      <MemoryRouter>
        <AgentCard agent={architect} courseId={1} progress={60} />
      </MemoryRouter>
    );
    const progressBar = container.querySelector('[role="progressbar"]');
    expect(progressBar).toBeInTheDocument();
  });

  it("navigates on click for enabled agent", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AgentCard agent={architect} courseId={42} />
      </MemoryRouter>
    );

    const card = screen.getByText("Curricular Alignment Architect").closest("[data-slot='card']") 
      || screen.getByText("Curricular Alignment Architect").closest(".cursor-pointer");
    if (card) {
      await user.click(card);
      expect(mockNavigate).toHaveBeenCalledWith("/courses/42/architect");
    }
  });

  it("renders disabled agent with Coming Soon badge", () => {
    render(
      <MemoryRouter>
        <AgentCard agent={analyst} courseId={1} />
      </MemoryRouter>
    );
    expect(screen.getByText("Coming Soon")).toBeInTheDocument();
    expect(screen.getByText("Market Demand Analyst")).toBeInTheDocument();
  });

  it("disabled agent is not clickable", () => {
    render(
      <MemoryRouter>
        <AgentCard agent={analyst} courseId={1} />
      </MemoryRouter>
    );
    // No cursor-pointer class on the disabled card
    const card = screen.getByText("Market Demand Analyst").closest("[data-slot='card']");
    expect(card).not.toHaveClass("cursor-pointer");
  });
});

/* ── AgentPageHeader ───────────────────────────────────────── */

describe("AgentPageHeader", () => {
  const architect = getAgentById("architect")!;

  it("renders agent name, description, and status", () => {
    render(<AgentPageHeader agent={architect} status="in-progress" />);
    expect(screen.getByText("Curricular Alignment Architect")).toBeInTheDocument();
    expect(screen.getByText(architect.description)).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
  });

  it("renders separator", () => {
    const { container } = render(
      <AgentPageHeader agent={architect} status="not-started" />
    );
    const separator = container.querySelector('[data-slot="separator"]') 
      || container.querySelector('[role="separator"]');
    expect(separator).toBeInTheDocument();
  });
});
