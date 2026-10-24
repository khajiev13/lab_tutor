"""Bound autonomous tool loops using completed rounds and saved stage progress."""

import hashlib
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .state import tool_store

_PROGRESS_KEYS = (
    "run_id",
    "candidate_revision",
    "selection_revision",
    "selected_candidate_ids",
    "curriculum_mapping",
    "mapped_skills",
    "_cleaned_results",
    "final_skills",
    "selected_for_insertion",
    "skill_concepts",
    "insertion_results",
)


class WorkerStalledError(RuntimeError):
    def __init__(self, agent: str, tools: list[str]):
        self.agent = agent
        self.tools = tools
        super().__init__(
            f"{agent.replace('_', ' ').title()} stopped after repeating "
            f"{', '.join(tools)} three times without progress."
        )


class WorkerOutputLimitError(RuntimeError):
    def __init__(self, agent: str):
        super().__init__(
            f"{agent.replace('_', ' ').title()} reached the model output limit. "
            "The incomplete response was not applied."
        )


def _fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def worker_progress(state: dict, agent: str) -> dict:
    """Return checkpointed progress, or stop before a fourth unchanged round.

    Tool-call IDs and UI change IDs are bookkeeping, not workflow progress.
    A new human message, worker, result, argument or stage change starts a new run.
    """
    messages = state.get("messages", [])
    start = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ),
        0,
    )
    turn = (
        messages[start].id
        if messages and isinstance(messages[start], HumanMessage)
        else None
    )
    latest = next(
        (
            m
            for m in reversed(messages[start:])
            if isinstance(m, AIMessage) and m.name == agent and m.tool_calls
        ),
        None,
    )
    previous = state.get("worker_progress") or {}
    if latest is None:
        return {}
    results = {
        m.tool_call_id: m for m in messages[start:] if isinstance(m, ToolMessage)
    }
    if any(call["id"] not in results for call in latest.tool_calls):
        return previous
    if previous.get("turn") == turn and previous.get("message") == latest.id:
        return previous
    rounds = [
        {
            "tool": call["name"],
            "args": call["args"],
            "result": results[call["id"]].content,
            "status": results[call["id"]].status,
        }
        for call in latest.tool_calls
    ]
    signature = _fingerprint(sorted(rounds, key=_fingerprint))
    progress = _fingerprint({key: tool_store.get(key) for key in _PROGRESS_KEYS})
    repeated = (
        previous.get("turn") == turn
        and previous.get("agent") == agent
        and previous.get("signature") == signature
        and previous.get("progress") == progress
    )
    count = previous.get("count", 0) + 1 if repeated else 1
    if count >= 3:
        raise WorkerStalledError(
            agent, sorted({call["name"] for call in latest.tool_calls})
        )
    return {
        "turn": turn,
        "agent": agent,
        "message": latest.id,
        "signature": signature,
        "progress": progress,
        "count": count,
    }
