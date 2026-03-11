import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ChatMessage } from "../types";

// Mock the agent-response component (it's a complex UI library component)
vi.mock("@/components/ui/agent-response", () => ({
  AgentResponse: ({
    message,
    agentName,
    isStreaming,
  }: {
    message: string;
    agentName: string;
    isStreaming: boolean;
    avatar: React.ReactNode;
    toolCalls: unknown[];
  }) => (
    <div data-testid="agent-response">
      <span data-testid="agent-name">{agentName}</span>
      <span data-testid="agent-content">{message}</span>
      {isStreaming && <span data-testid="streaming">streaming</span>}
    </div>
  ),
}));

vi.mock("@/components/ui/loader", () => ({
  Loader: () => <div data-testid="loader">loading...</div>,
}));

import { AgentMessage } from "../components/AgentMessage";

describe("AgentMessage", () => {
  it("renders agent content via AgentResponse", () => {
    const message: ChatMessage = {
      id: "a1",
      role: "agent",
      agent: "supervisor",
      agentDisplayName: "Supervisor",
      agentEmoji: "📊",
      content: "I found 15 jobs",
      toolCalls: [],
      isStreaming: false,
    };

    render(<AgentMessage message={message} />);
    expect(screen.getByTestId("agent-content")).toHaveTextContent("I found 15 jobs");
    expect(screen.getByTestId("agent-name")).toHaveTextContent("Supervisor");
  });

  it("shows loader when streaming with no content", () => {
    const message: ChatMessage = {
      id: "a2",
      role: "agent",
      agent: "curriculum_mapper",
      agentDisplayName: "Curriculum Mapper",
      agentEmoji: "🗺️",
      content: "",
      toolCalls: [],
      isStreaming: true,
    };

    render(<AgentMessage message={message} />);
    expect(screen.getByTestId("loader")).toBeInTheDocument();
  });

  it("renders with tool calls", () => {
    const message: ChatMessage = {
      id: "a3",
      role: "agent",
      agent: "supervisor",
      agentDisplayName: "Supervisor",
      agentEmoji: "📊",
      content: "Fetching jobs...",
      toolCalls: [
        {
          id: "tc1",
          name: "fetch_jobs",
          args: { search_terms: "Python" },
          status: "success",
          result: { count: 42 },
        },
      ],
      isStreaming: false,
    };

    render(<AgentMessage message={message} />);
    expect(screen.getByTestId("agent-response")).toBeInTheDocument();
  });

  it("falls back to agentDisplayName when agent is not in config", () => {
    const message: ChatMessage = {
      id: "a4",
      role: "agent",
      // no agent field
      agentDisplayName: "Custom Agent",
      agentEmoji: "🤖",
      content: "Hello",
      toolCalls: [],
      isStreaming: false,
    };

    render(<AgentMessage message={message} />);
    expect(screen.getByTestId("agent-name")).toHaveTextContent("Custom Agent");
  });
});
