"""One-invocation evidence review, isolated from workflow tool permissions."""

import json
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime
from langgraph_swarm import SwarmState
from pydantic import ValidationError

from app.core.database import SessionLocal

from .prompts import WORKSPACE_REVIEW_PROMPT
from .repository import MarketReviewRepository
from .review_service import SkillReviewService
from .schemas import (
    RecommendationChange,
    ResolvedContextMetadata,
    ResolvedWorkspaceContext,
    SkillReview,
    SkillReviewRevision,
)
from .state import owned_sync_execution, tool_store


@dataclass(frozen=True)
class WorkspaceRuntimeContext:
    resolved: ResolvedWorkspaceContext | None = None
    course_id: int | None = None
    teacher_id: int | None = None
    intent: Literal["explain", "propose_selection"] = "explain"


def route_entry(state: SwarmState, runtime: Runtime[WorkspaceRuntimeContext]) -> str:
    if runtime.context is not None and runtime.context.resolved is not None:
        return "workspace_review"
    return state.get("active_agent") or "supervisor"


def create_workspace_proposal(
    course_id: int,
    teacher_id: int,
    revision: SkillReviewRevision,
    changes: list[RecommendationChange],
) -> tuple[SkillReview, dict]:
    """Reuse the outer execution lease and the resolved, exact SQL revisions."""
    with SessionLocal() as db:
        service = SkillReviewService(MarketReviewRepository(db))
        try:
            return service.create_recommendation(
                course_id,
                teacher_id,
                revision,
                [change.model_dump(mode="json") for change in changes],
            )
        except BaseException:
            service.rollback()
            raise


def _proposal_tool(context: WorkspaceRuntimeContext) -> StructuredTool:
    assert context.resolved is not None and context.resolved.revision is not None
    assert context.course_id is not None and context.teacher_id is not None
    # Capture separate copies before model invocation. No model-supplied identity
    # or revision can replace this invocation's validated SQL context.
    revision = context.resolved.revision.model_copy(deep=True)
    course_id, teacher_id = context.course_id, context.teacher_id

    def propose_skill_selection(changes: list[RecommendationChange]) -> str:
        """Propose one immutable add/remove diff with candidate IDs and reasons.

        The teacher must apply and save it; this cannot change saved selections,
        override exclusions, configure sources, map skills or publish anything.
        """
        review, fields = create_workspace_proposal(
            course_id, teacher_id, revision, changes
        )
        # The recommendation service has committed its matching snapshot already.
        # These fields support stream refresh events, never a stale snapshot save.
        tool_store.update(fields)
        return json.dumps(
            {"proposal_id": str(review.recommendations[-1].id), "status": "proposed"}
        )

    return StructuredTool.from_function(
        propose_skill_selection,
        coroutine=owned_sync_execution(propose_skill_selection),
    )


async def workspace_review(
    state: SwarmState, runtime: Runtime[WorkspaceRuntimeContext]
) -> dict:
    from .graph import get_graph

    context = runtime.context
    if context is None or context.resolved is None:
        raise ValueError("Workspace review requires resolved runtime context")
    if context.intent != context.resolved.intent:
        raise ValueError("Workspace intent does not match resolved context")
    _, llm = await get_graph()
    proposal = (
        _proposal_tool(context) if context.intent == "propose_selection" else None
    )
    model = llm.bind_tools([proposal]) if proposal is not None else llm
    # Retain conversation history in the checkpoint/UI, but do not feed earlier
    # model conclusions back as evidence for the freshly resolved attachment.
    question = next(
        (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)),
        None,
    )
    prompt = [
        SystemMessage(content=WORKSPACE_REVIEW_PROMPT),
        SystemMessage(
            content="Evidence data for this invocation only:\n"
            + json.dumps(context.resolved.model_bundle, ensure_ascii=False)
        ),
        *([question] if question is not None else []),
    ]
    reply = await model.ainvoke(prompt)
    reply.name = "workspace_review"
    if reply.invalid_tool_calls:
        # Providers may retain malformed calls in additional_kwargs as well.
        # Persist a clean message, never an unanswerable provider call envelope.
        return {
            "messages": [
                AIMessage(
                    id=reply.id,
                    content="The model returned an invalid action. Please ask the question again; no action was taken.",
                    name="workspace_review",
                )
            ]
        }
    if not reply.tool_calls:
        return {"messages": [reply]}

    # No general ToolNode or handoff exists on this path. Check the entire batch
    # before invoking anything; even a mixed allowed/forbidden batch writes nothing.
    allowed = (
        proposal is not None
        and len(reply.tool_calls) == 1
        and reply.tool_calls[0]["name"] == proposal.name
    )
    if not allowed:
        # Complete every fabricated call in history, so the next workflow remains
        # valid for providers which require one result per assistant tool call.
        denied = [
            ToolMessage(
                content="This action is unavailable in contextual review. Use the explicit workflow action.",
                tool_call_id=call["id"],
                name=call["name"],
                status="error",
            )
            for call in reply.tool_calls
        ]
        return {
            "messages": [
                reply,
                *denied,
                AIMessage(
                    content="This question cannot run workflow actions. Use the explicit workflow action to continue.",
                    name="workspace_review",
                ),
            ]
        }

    result = await proposal.ainvoke(reply.tool_calls[0])
    # One immutable recommendation per turn; no second chance to invoke tools.
    return {
        "messages": [
            reply,
            result,
            AIMessage(
                content="The proposal is ready for review. Your saved shortlist is unchanged; apply the proposed changes and Save draft to keep them.",
                name="workspace_review",
            ),
        ]
    }


def safe_workspace_metadata(value: object) -> dict | None:
    """Restore only context facts, never retained source or model payloads."""
    try:
        metadata = ResolvedContextMetadata.model_validate(value).model_dump(mode="json")
    except ValidationError:
        return None
    source_fields = {
        "excerpt",
        "source_excerpt",
        "raw_payload",
        "model_bundle",
        "payload",
        "description",
        "description_text",
        "original_description",
        "source_text",
        "original_phrase",
        "content",
    }

    def redact(item):
        if isinstance(item, dict):
            return {
                key: redact(val)
                for key, val in item.items()
                if key not in source_fields
            }
        if isinstance(item, list):
            return [redact(val) for val in item]
        return item

    return redact(metadata)
