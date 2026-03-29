#!/usr/bin/env python3
"""
Market Demand Agent — Terminal Chat (Multi-Agent Swarm)

Interactive CLI for the Market Demand Analyst swarm.
Run from the backend directory:

    .venv/bin/python -m app.modules.marketdemandanalyst
"""

import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from rich.console import Console
from rich.panel import Panel

# Load .env from the backend directory (where this package lives)
_backend_dir = Path(__file__).resolve().parents[3]
load_dotenv(_backend_dir / ".env")

from .graph import build_graph  # noqa: E402

console = Console()

# Agent display names
AGENT_NAMES = {
    "supervisor": "📊 Supervisor",
    "skill_finder": "🔍 Skill Finder",
    "curriculum_mapper": "🗺️ Curriculum Mapper",
    "skill_cleaner": "🧹 Skill Cleaner",
    "concept_linker": "🔗 Concept Linker",
}


# ── Display helpers ──────────────────────────────────────────────


def _show_tool_result(name: str, result: str) -> None:
    if isinstance(result, str) and result.startswith("Successfully transferred to"):
        console.print(f"[dim]↪ {result}[/]")
        return
    truncated = (
        result
        if len(result) < 3000
        else result[:2500] + f"\n... ({len(result)} chars total)"
    )
    console.print(
        Panel(truncated, title=f"[bold green]✅ {name}[/]", border_style="green")
    )


# ── Graph streaming ──────────────────────────────────────────────


def _stream(graph, input_data, config) -> None:
    """Stream graph execution token-by-token using messages mode + subgraphs."""
    streaming_agent: str | None = None
    seen_tool_calls: set[str] = set()

    for ns, (msg, _metadata) in graph.stream(
        input_data, config=config, stream_mode="messages", subgraphs=True
    ):
        # Skip echoed-back human messages
        if isinstance(msg, HumanMessage):
            continue

        # ── AIMessageChunk: token-by-token from LLM ──
        if isinstance(msg, AIMessageChunk):
            # Text content → stream it live
            if msg.content:
                # Print agent header on first token
                agent = _resolve_agent_from_ns(ns)
                if agent != streaming_agent:
                    if streaming_agent is not None:
                        print()  # newline after previous agent's stream
                    display = AGENT_NAMES.get(agent, f"🤖 {agent}")
                    console.print(f"\n[bold]{display}:[/]")
                    streaming_agent = agent
                print(msg.content, end="", flush=True)

            # Tool call chunks → show tool name as it's decided
            for tc in msg.tool_call_chunks or []:
                tc_id = tc.get("id", "")
                tc_name = tc.get("name", "")
                if tc_name and tc_id and tc_id not in seen_tool_calls:
                    if streaming_agent is not None:
                        print()  # end text stream
                        streaming_agent = None
                    seen_tool_calls.add(tc_id)
                    agent = _resolve_agent_from_ns(ns)
                    display = AGENT_NAMES.get(agent, agent)
                    console.print(f"\n[bold]{display} → calling tool:[/]")
                    console.print(
                        Panel(
                            f"calling {tc_name}…",
                            title=f"[bold blue]🔧 {tc_name}[/]",
                            border_style="blue",
                        )
                    )

        # ── ToolMessage: tool returned a result ──
        elif isinstance(msg, ToolMessage):
            if streaming_agent is not None:
                print()
                streaming_agent = None
            _show_tool_result(msg.name or "tool", msg.content)

    # Final newline if we were mid-stream
    if streaming_agent is not None:
        print()


def _resolve_agent_from_ns(ns: tuple) -> str:
    """Extract agent name from the subgraph namespace tuple.

    With subgraphs=True, ns is e.g. ('supervisor:uuid',) — the first
    element before ':' is the agent name.
    """
    if ns:
        return ns[0].split(":")[0]
    return "unknown"


# ── Main loop ────────────────────────────────────────────────────


def main() -> None:
    console.print(
        Panel(
            "[bold]Market Demand Agent[/] — Multi-Agent Swarm\n"
            "Agents: Supervisor · Skill Finder · Curriculum Mapper · Skill Cleaner · Concept Linker\n"
            "Type [bold cyan]quit[/] or [bold cyan]exit[/] to stop.",
            border_style="bright_cyan",
        )
    )

    graph, llm = build_graph()
    console.print(f"[dim]LLM: {llm.model_name} @ {llm.openai_api_base}[/]")

    thread_id = f"mda-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    console.print(f"[dim]Thread: {thread_id}[/]\n")

    # ── Trigger agent greeting immediately ──
    _stream(
        graph,
        {"messages": [HumanMessage(content="")]},
        config,
    )

    while True:
        try:
            user_input = console.input("[bold cyan]You:[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye![/]")
            break

        _stream(
            graph,
            {"messages": [HumanMessage(content=user_input)]},
            config,
        )


if __name__ == "__main__":
    main()
