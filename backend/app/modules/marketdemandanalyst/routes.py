"""
Market Demand Agent — FastAPI SSE streaming endpoint.

Exposes the multi-agent swarm over Server-Sent Events so the React
frontend can render token-by-token agent text, tool calls, tool results,
and state updates in real time.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.database import AsyncSessionLocal, SessionLocal, get_async_db, get_db
from app.core.neo4j import get_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.courses.materials_readiness_service import require_materials_ready
from app.modules.courses.models import Course
from app.modules.courses.readiness_service import CourseReadinessService
from app.modules.curricularalignmentarchitect.skill_prerequisites.review_repository import (
    PrerequisiteReviewRepository,
)
from app.modules.curricularalignmentarchitect.skill_prerequisites.service import (
    schedule_skill_prerequisite_rebuild as schedule_prerequisite_rebuild,
)
from app.modules.occupation_reference.repository import OccupationReferenceRepository
from app.modules.occupation_reference.service import (
    OccupationReferenceService,
    get_occupation_reference_service,
)

from .countries import DEFAULT_JOB_SEARCH_COUNTRY, normalize_job_search_country
from .graph import get_graph
from .job_sources import JobSourceService, get_job_source_service
from .neo4j_repository import MarketSkillGraphRepository
from .projection_service import SkillEvidenceProjector
from .repository import MarketReviewRepository, load_async_thread_state
from .review_service import SkillReviewService
from .schemas import (
    EvidenceSource,
    ExecutionStatus,
    IntegrationApproval,
    IntegrationApprovalResult,
    JobSource,
    JobSourceOption,
    MarketStreamError,
    SkillReview,
    SkillReviewDraft,
    SkillReviewRevision,
    SkillSelectionConfirmation,
    VacancyEvidence,
    WorkspaceContext,
)
from .service import MarketConfigurationService
from .state import (
    STATE_KEYS,
    bind_tool_store,
    restore_state,
    snapshot_state,
    tool_store,
)
from .thread_state_service import (
    ThreadBusy,
    ThreadLease,
    ThreadStateService,
    get_thread_state_service,
)
from .worker_progress import WorkerStalledError
from .workspace_chat import WorkspaceRuntimeContext, safe_workspace_metadata
from .workspace_service import WorkspaceContextService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["market-demand"])

# Agent display metadata (shared with frontend via agent_start events)
AGENT_META: dict[str, dict[str, str]] = {
    "supervisor": {"displayName": "Supervisor", "emoji": "📊"},
    "workspace_review": {"displayName": "Evidence assistant", "emoji": "🤖"},
    "skill_finder": {"displayName": "Skill Finder", "emoji": "🔍"},
    "curriculum_mapper": {"displayName": "Curriculum Mapper", "emoji": "🗺️"},
    "skill_cleaner": {"displayName": "Skill Cleaner", "emoji": "🧹"},
    "concept_linker": {"displayName": "Concept Linker", "emoji": "🔗"},
}


TeacherDep = Annotated[User, Depends(require_role(UserRole.TEACHER))]


def get_market_review_repository(
    db: Session = Depends(get_db),
) -> MarketReviewRepository:
    return MarketReviewRepository(db)


def get_skill_review_service(
    repository: MarketReviewRepository = Depends(get_market_review_repository),
) -> SkillReviewService:
    return SkillReviewService(repository)


def get_workspace_context_service(
    repository: MarketReviewRepository = Depends(get_market_review_repository),
    db: Session = Depends(get_db),
) -> WorkspaceContextService:
    return WorkspaceContextService(repository, OccupationReferenceRepository(db))


def get_skill_evidence_projector(
    repository: MarketReviewRepository = Depends(get_market_review_repository),
    driver=Depends(get_neo4j_driver),
) -> SkillEvidenceProjector:
    return SkillEvidenceProjector(
        repository, MarketSkillGraphRepository(driver) if driver is not None else None
    )


def get_market_configuration_service(
    repository: MarketReviewRepository = Depends(get_market_review_repository),
    jobs: JobSourceService = Depends(get_job_source_service),
    occupations: OccupationReferenceService = Depends(get_occupation_reference_service),
) -> MarketConfigurationService:
    return MarketConfigurationService(repository, jobs, occupations)


def _sse(event: str, data: dict) -> str:
    """Format a single SSE frame."""
    payload = json.dumps({"type": event, **data}, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _resolve_agent(ns: tuple) -> str:
    """Extract agent name from subgraph namespace tuple."""
    if ns:
        return ns[0].split(":")[0]
    return "unknown"


def _schedule_skill_prerequisite_rebuild(
    course_id: int,
    trigger_reason: str,
) -> None:
    db = SessionLocal()
    try:
        CourseReadinessService(db).mark_market_gate_complete(course_id)
        PrerequisiteReviewRepository(db).mark_stale(course_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to update readiness gates for course %s before prerequisite rebuild",
            course_id,
        )
        return
    finally:
        db.close()

    try:
        schedule_prerequisite_rebuild(course_id, trigger_reason)
    except Exception:
        logger.exception(
            "Failed to schedule prerequisite rebuild for course %s", course_id
        )


# Detached process-local snapshots; every load still reads authoritative SQL.
_state_cache = get_thread_state_service().cache


def _load_owned_course(session: Session, course_id: int, teacher_id: int) -> Course:
    course = session.get(Course, course_id)
    if course is None or course.teacher_id != teacher_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )
    return course


def _get_owned_course(course_id: int, teacher: User, db: Session) -> Course:
    try:
        return _load_owned_course(db, course_id, teacher.id)
    except OperationalError:
        logger.warning(
            "Course lookup failed for teacher=%s course=%s; retrying with a fresh session",
            teacher.id,
            course_id,
            exc_info=True,
        )
        with contextlib.suppress(Exception):
            db.rollback()
        with contextlib.suppress(Exception):
            bind = db.get_bind()
            if bind is not None:
                bind.dispose()
        with contextlib.suppress(Exception):
            db.close()

        retry_db = SessionLocal()
        try:
            return _load_owned_course(retry_db, course_id, teacher.id)
        except OperationalError as retry_exc:
            logger.exception(
                "Database unavailable during course lookup for teacher=%s course=%s",
                teacher.id,
                course_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is temporarily unavailable. Please retry in a moment.",
            ) from retry_exc
        finally:
            with contextlib.suppress(Exception):
                retry_db.close()


def _get_thread_id(user_id: int, course_id: int) -> str:
    return f"mda-{user_id}-course-{course_id}"


def _seed_course_context(
    course: Course, country: str | None = DEFAULT_JOB_SEARCH_COUNTRY
) -> None:
    selected_country = normalize_job_search_country(country)
    tool_store["course_id"] = course.id
    tool_store["course_title"] = course.title
    tool_store["course_description"] = course.description or ""
    # Preserve existing search settings if already set (don't overwrite mid-session).
    if "job_search_country" not in tool_store:
        tool_store["job_search_country"] = selected_country.key
    if "job_search_location" not in tool_store:
        tool_store["job_search_location"] = selected_country.location
    if "job_search_country_confirmed" not in tool_store:
        tool_store["job_search_country_confirmed"] = False


def _restore_thread_state(
    persisted: dict[str, Any] | None,
    course: Course,
    country: str | None = None,
) -> None:
    # When a thread has no persisted snapshot yet, clear any prior thread's state.
    restore_state(persisted or {})
    has_fetched_jobs = bool(tool_store.get("fetched_jobs"))
    requested_country = country.strip() if isinstance(country, str) else None
    if requested_country and not has_fetched_jobs:
        selected_country = normalize_job_search_country(requested_country)
        tool_store["job_search_country"] = selected_country.key
        tool_store["job_search_location"] = selected_country.location
        tool_store["job_search_country_confirmed"] = True
    elif not has_fetched_jobs:
        raw_country = (
            str(tool_store.get("job_search_country", "")).strip()
            or str(tool_store.get("job_search_location", "")).strip()
            or DEFAULT_JOB_SEARCH_COUNTRY
        )
        selected_country = normalize_job_search_country(raw_country)
        tool_store["job_search_country"] = selected_country.key
        tool_store["job_search_location"] = selected_country.location
        tool_store.setdefault("job_search_country_confirmed", False)
    elif "job_search_country" not in tool_store and "job_search_location" in tool_store:
        with contextlib.suppress(ValueError):
            legacy_country = normalize_job_search_country(
                str(tool_store["job_search_location"])
            )
            tool_store["job_search_country"] = legacy_country.jobspy_country
    if has_fetched_jobs and "job_search_country_confirmed" not in tool_store:
        tool_store["job_search_country_confirmed"] = True
    _seed_course_context(
        course,
        str(
            tool_store.get("job_search_country")
            or requested_country
            or DEFAULT_JOB_SEARCH_COUNTRY
        ),
    )


def _persist_state(
    thread_id: str,
    state: dict | None = None,
    *,
    lease: ThreadLease | None = None,
    service: ThreadStateService | None = None,
) -> None:
    """Queue detached snapshots in their execution's write order."""
    service = service or get_thread_state_service()
    snapshot = snapshot_state(state)
    if lease is not None:
        service.save(lease, snapshot)
        return

    async def persist():
        claimed = await service.claim(thread_id)
        try:
            await service.save(claimed, snapshot)
        finally:
            await service.release(claimed)

    asyncio.create_task(persist())


async def _load_persisted_state(thread_id: str) -> dict[str, Any] | None:
    """Read authoritative state and retain a detached snapshot for observers."""
    t0 = time.perf_counter()
    for attempt in range(2):
        try:
            persisted = await load_async_thread_state(AsyncSessionLocal, thread_id)
            if persisted is not None:
                _state_cache[thread_id] = deepcopy(persisted)
                return deepcopy(persisted)
            break
        except Exception:
            if attempt == 0:
                logger.warning(
                    "_load_persisted_state failed for %s (attempt 1), retrying…",
                    thread_id,
                    exc_info=True,
                )
                continue
            logger.exception("_load_persisted_state failed for %s", thread_id)
            raise HTTPException(
                status_code=503, detail="Database is temporarily unavailable"
            ) from None
    _state_cache[thread_id] = None
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "[PERF] _load_persisted_state took %.1fms (not found, thread=%s)",
        elapsed,
        thread_id,
    )
    return None


def _stream_error(
    exc: BaseException, *, persistence: bool = False
) -> MarketStreamError:
    if persistence:
        return MarketStreamError(
            code="persistence_failed",
            message="The conversation could not be saved completely.",
            recovery="Refresh the conversation and review before taking another action.",
        )
    if isinstance(exc, WorkerStalledError):
        return MarketStreamError(
            code="worker_stalled",
            message=str(exc),
            recovery="Your confirmed skill selection is preserved. Refresh the review, then retry the saved workflow.",
        )
    if isinstance(exc, asyncio.CancelledError):
        return MarketStreamError(
            code="execution_interrupted",
            message="The server execution was interrupted.",
            recovery="Refresh execution status and the conversation before retrying.",
        )
    if isinstance(exc, HTTPException) and exc.status_code == 409:
        return MarketStreamError(
            code="context_stale",
            message="The evidence or saved shortlist changed during this question.",
            recovery="Refresh context and ask again using the current review.",
        )
    return MarketStreamError(
        code="execution_failed",
        message="The assistant could not finish this conversation turn.",
        recovery="Refresh execution status, conversation and review before retrying.",
    )


def _normalize_graph_stream(item: tuple) -> tuple:
    """Accept multi-mode subgraph envelopes and older messages-only adapters."""
    if len(item) == 3:
        return item
    namespace, data = item
    return namespace, "messages", data


def _priority_progress(data: object) -> dict | None:
    """Expose only the analyst's bounded status, never arbitrary custom content."""
    if not isinstance(data, dict) or data.get("type") != "skill_priority_status":
        return None
    value = data.get("value")
    if not isinstance(value, dict) or value.get("status") not in {
        "running",
        "ready",
        "partial",
        "unavailable",
        "stale",
    }:
        return None
    try:
        assessment_id = str(uuid.UUID(value["assessment_id"]))
        deadline = datetime.fromisoformat(value["deadline_at"])
        if deadline.tzinfo is None:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "assessment_id": assessment_id,
        "status": value["status"],
        "deadline_at": deadline.isoformat(),
        "message": "Assessing skill importance…"
        if value["status"] == "running"
        else "",
    }


async def _sse_stream(
    graph: Any,
    input_data: dict,
    config: dict,
    *,
    bound_state: dict | None = None,
    lease: ThreadLease | None = None,
    state_service: ThreadStateService | None = None,
    runtime_context: WorkspaceRuntimeContext | None = None,
    persistence_policy: Literal[
        "workflow_snapshot", "checkpoint_only", "proposal_snapshot"
    ] = "workflow_snapshot",
) -> AsyncGenerator[str, None]:
    """Stream the LangGraph swarm execution as SSE events.

    Uses graph.astream() (async) with the PostgreSQL checkpointer.

    Event types emitted:
      agent_start   — a new agent starts speaking
      text_delta    — incremental text token from LLM
      text_done     — agent finished its text
      tool_start    — tool call initiated (with accumulated args)
      tool_end      — tool returned a result
      state_update  — a tool_store key changed
      stream_end    — nothing more to send
    """
    if runtime_context is None:
        runtime_context = WorkspaceRuntimeContext(
            course_id=(bound_state or {}).get("course_id"),
            teacher_id=(bound_state or {}).get("teacher_id"),
            lease=lease,
        )
    else:
        runtime_context = replace(runtime_context, lease=lease)
    current_agent: str | None = None
    current_message_id: str | None = None
    seen_tool_calls: set[str] = set()
    # Buffer to accumulate tool call args across chunks
    tool_call_args: dict[str, str] = {}
    # Map chunk index → tool call id (for chunks that omit the id)
    tool_index_to_id: dict[int, str] = {}
    prev_state = snapshot_state(bound_state)
    thread_id = config.get("configurable", {}).get("thread_id", "")

    stream_start = time.perf_counter()
    event_count = 0
    last_event_time = stream_start
    tool_timings: dict[str, float] = {}  # tool_call_id → start time

    # Producer task: fills a queue from graph.astream so we can inject SSE keep-alive
    # comments during silent periods (e.g. the fan-out extraction runs for several
    # minutes emitting no SSE-visible messages, which triggers Azure's 240-second
    # TCP idle timeout and kills the connection).
    _queue: asyncio.Queue[tuple | MarketStreamError | None] = asyncio.Queue()
    outcome = "completed"

    async def _graph_producer() -> None:
        saving = False
        try:
            # Bind inside the producer: its tasks and synchronous LangChain tools
            # inherit this execution's mapping rather than the request's context.
            with bind_tool_store(
                bound_state if bound_state is not None else tool_store._current(),
                tool_tasks=lease.tool_tasks if lease is not None else None,
            ):
                graph_input = input_data
                progress = tool_store.get("skill_priority_status") or {}
                if (
                    runtime_context.resolved is None
                    and tool_store.get("run_id")
                    and progress.get("status") in {"pending", "running"}
                ):
                    from .extractor import extraction_tool_results

                    checkpoint = await graph.aget_state(config)
                    results = extraction_tool_results(
                        checkpoint.values.get("messages", [])
                    )
                    if results:
                        # Commit pairing as graph input before the analyst executes,
                        # including when extraction's parent update was interrupted.
                        graph_input = {
                            **input_data,
                            "messages": [*results, *input_data.get("messages", [])],
                        }
                async for item in graph.astream(
                    graph_input,
                    config=config,
                    stream_mode=["messages", "custom"],
                    subgraphs=True,
                    **(
                        {"context": runtime_context}
                        if runtime_context is not None
                        else {}
                    ),
                ):
                    namespace, mode, payload = _normalize_graph_stream(item)
                    if (
                        lease is not None
                        and state_service is not None
                        and persistence_policy == "workflow_snapshot"
                        and mode == "messages"
                        and isinstance(payload[0], ToolMessage)
                    ):
                        saving = True
                        await state_service.save(
                            lease,
                            bound_state
                            if bound_state is not None
                            else tool_store._current(),
                            synchronize_tools=True,
                        )
                        saving = False
                    await _queue.put((namespace, mode, payload))
        except asyncio.CancelledError as exc:
            await _queue.put(_stream_error(exc))
        except Exception as exc:
            logger.exception("Graph execution failed")
            await _queue.put(_stream_error(exc, persistence=saving))
        finally:

            async def finalize():
                try:
                    if lease is not None and state_service is not None:
                        try:
                            # Shielded adapters retain actual executor tasks. Drain
                            # them before capturing state or releasing SQL ownership.
                            if lease.tool_tasks:
                                results = await asyncio.gather(
                                    *lease.tool_tasks, return_exceptions=True
                                )
                                lease.tool_tasks.clear()
                                for result in results:
                                    if isinstance(result, BaseException):
                                        await _queue.put(_stream_error(result))
                            if persistence_policy == "workflow_snapshot":
                                await state_service.save(
                                    lease, snapshot_state(bound_state)
                                )
                        finally:
                            await state_service.release(lease)
                except Exception as exc:
                    logger.exception("Failed to persist completed graph execution")
                    await _queue.put(_stream_error(exc, persistence=True))
                finally:
                    await _queue.put(None)

            finalizing = asyncio.create_task(finalize())
            if lease is not None:
                lease.finalizing = finalizing
            await asyncio.shield(finalizing)

    _producer = asyncio.create_task(_graph_producer())
    if lease is not None:
        lease.producer = _producer

    try:
        logger.info("[PERF] SSE stream starting (thread=%s)", thread_id)
        if runtime_context is not None and runtime_context.resolved is not None:
            human = input_data["messages"][-1]
            yield _sse(
                "context_resolved",
                {
                    "messageId": human.id,
                    "workspace_context": human.additional_kwargs["workspace_context"],
                },
            )
        while True:
            try:
                item = await asyncio.wait_for(_queue.get(), timeout=30.0)
            except TimeoutError:
                # Keep-alive SSE comment resets Azure TCP idle clock
                yield ": keep-alive\n\n"
                continue

            if item is None:
                break
            if isinstance(item, MarketStreamError):
                outcome = "failed"
                yield _sse("error", item.model_dump())
                continue

            ns, mode, payload = item
            if (
                mode == "custom"
                and isinstance(payload, dict)
                and payload.get("type") == "mapping_prerequisite"
                and isinstance(payload.get("message"), str)
            ):
                # Deterministic guards use the normal teacher-facing text stream.
                ns, mode, payload = (
                    ("supervisor",),
                    "messages",
                    (AIMessage(content=payload["message"], name="supervisor"), {}),
                )
            if mode == "custom":
                progress = _priority_progress(payload)
                if progress is None:
                    continue
                yield _sse(
                    "state_update",
                    {"stateKey": "skill_priority_status", "value": progress},
                )
                prev_state["skill_priority_status"] = progress
                if progress["status"] != "running" and (bound_state or {}).get(
                    "run_id"
                ):
                    # Guidance has its own identity; the teacher revisions stay fixed.
                    yield _sse(
                        "skill_review_changed",
                        {
                            "run_id": bound_state["run_id"],
                            "candidate_revision": bound_state.get("candidate_revision")
                            or 0,
                            "selection_revision": bound_state.get("selection_revision")
                            or 0,
                            "publication_revision": bound_state.get(
                                "publication_revision"
                            )
                            or 0,
                        },
                    )
                    prev_state["skill_review_change_id"] = progress["assessment_id"]
                continue
            if mode != "messages":
                continue
            msg, _metadata = payload
            now = time.perf_counter()
            gap_ms = (now - last_event_time) * 1000
            last_event_time = now
            event_count += 1
            if gap_ms > 500:
                logger.warning(
                    "[PERF] SSE gap %.1fms between events #%d (msg_type=%s, agent=%s)",
                    gap_ms,
                    event_count,
                    type(msg).__name__,
                    _resolve_agent(ns),
                )
            logger.debug(
                "Stream msg: type=%s ns=%s content_len=%s content_type=%s additional_kwargs=%s",
                type(msg).__name__,
                ns,
                len(str(msg.content)) if msg.content else 0,
                type(msg.content).__name__,
                list(msg.additional_kwargs.keys())
                if hasattr(msg, "additional_kwargs") and msg.additional_kwargs
                else [],
            )

            if isinstance(msg, HumanMessage):
                continue

            if isinstance(msg, (AIMessage, AIMessageChunk)):
                agent = _resolve_agent(ns)
                if not ns and (
                    msg.name == "workspace_review"
                    or _metadata.get("langgraph_node") == "workspace_review"
                ):
                    agent = "workspace_review"

                # Emit agent_start when agent switches
                if agent != current_agent:
                    if current_message_id:
                        yield _sse("text_done", {"messageId": current_message_id})
                    current_agent = agent
                    current_message_id = f"msg-{uuid.uuid4().hex[:12]}"
                    meta = AGENT_META.get(agent, {"displayName": agent, "emoji": "🤖"})
                    yield _sse(
                        "agent_start",
                        {
                            "agent": agent,
                            "messageId": current_message_id,
                            **meta,
                        },
                    )

                # Text tokens
                if msg.content:
                    # After a tool call, current_message_id is None.
                    # Create a new message so the frontend can render the text.
                    if current_message_id is None:
                        current_message_id = f"msg-{uuid.uuid4().hex[:12]}"
                        meta = AGENT_META.get(
                            agent or "unknown",
                            {"displayName": agent, "emoji": "🤖"},
                        )
                        yield _sse(
                            "agent_start",
                            {
                                "agent": current_agent,
                                "messageId": current_message_id,
                                **meta,
                            },
                        )
                    yield _sse(
                        "text_delta",
                        {
                            "delta": msg.content,
                            "messageId": current_message_id,
                        },
                    )
                else:
                    # Log when content is falsy to debug silent agent
                    if msg.additional_kwargs:
                        logger.debug(
                            "AIMessageChunk with empty content but additional_kwargs: %s",
                            {k: str(v)[:100] for k, v in msg.additional_kwargs.items()},
                        )

                # Tool call chunks — accumulate args before emitting
                chunks = (
                    msg.tool_call_chunks
                    if isinstance(msg, AIMessageChunk)
                    else [
                        {**call, "args": json.dumps(call["args"]), "index": index}
                        for index, call in enumerate(msg.tool_calls)
                    ]
                )
                for tc in chunks or []:
                    tc_id = tc.get("id") or ""
                    tc_name = tc.get("name") or ""
                    tc_args = tc.get("args") or ""
                    tc_index = tc.get("index", 0)

                    # Map index → id on first chunk (which carries both)
                    if tc_id:
                        tool_index_to_id[tc_index] = tc_id

                    # Resolve id from index for subsequent chunks
                    resolved_id = tc_id or tool_index_to_id.get(tc_index, "")

                    # Accumulate args string for this tool call
                    if resolved_id and tc_args:
                        tool_call_args[resolved_id] = (
                            tool_call_args.get(resolved_id, "") + tc_args
                        )

                    if tc_name and resolved_id and resolved_id not in seen_tool_calls:
                        seen_tool_calls.add(resolved_id)

                        # End any in-progress text stream first
                        if current_message_id and current_agent:
                            yield _sse("text_done", {"messageId": current_message_id})
                            current_message_id = None

                        # Parse the accumulated args (may still be partial)
                        accumulated = tool_call_args.get(resolved_id, "")
                        try:
                            parsed_args = json.loads(accumulated) if accumulated else {}
                        except (json.JSONDecodeError, TypeError):
                            parsed_args = {}

                        tool_timings[resolved_id] = time.perf_counter()
                        logger.info(
                            "[PERF] Tool started: %s (id=%s, agent=%s)",
                            tc_name,
                            resolved_id,
                            current_agent,
                        )
                        yield _sse(
                            "tool_start",
                            {
                                "toolName": tc_name,
                                "toolCallId": resolved_id,
                                "args": parsed_args,
                                "agent": current_agent,
                            },
                        )

            elif isinstance(msg, ToolMessage):
                # End any in-progress text stream
                if current_message_id and current_agent:
                    yield _sse("text_done", {"messageId": current_message_id})
                    current_message_id = None

                # Parse result for structured data
                content = msg.content
                try:
                    parsed = (
                        json.loads(content) if isinstance(content, str) else content
                    )
                except (json.JSONDecodeError, TypeError):
                    parsed = content

                # Emit tool_args_update with the full accumulated args before tool_end
                tc_id = msg.tool_call_id or ""
                if tc_id and tc_id in tool_call_args:
                    accumulated = tool_call_args[tc_id]
                    try:
                        full_args = json.loads(accumulated) if accumulated else {}
                    except (json.JSONDecodeError, TypeError):
                        full_args = {}
                    if full_args:
                        yield _sse(
                            "tool_args_update",
                            {
                                "toolCallId": tc_id,
                                "args": full_args,
                            },
                        )

                tool_elapsed_ms = 0.0
                if tc_id in tool_timings:
                    tool_elapsed_ms = (
                        time.perf_counter() - tool_timings.pop(tc_id)
                    ) * 1000
                logger.info(
                    "[PERF] Tool finished: %s took %.1fms (id=%s)",
                    msg.name or "?",
                    tool_elapsed_ms,
                    tc_id,
                )

                yield _sse(
                    "tool_end",
                    {
                        "toolCallId": tc_id,
                        "toolName": msg.name or "",
                        "result": parsed,
                        "status": "error" if msg.status == "error" else "finished",
                    },
                )

                # Check for state changes after tool execution
                new_state = snapshot_state(bound_state)
                should_rebuild_prerequisites = False
                for key in STATE_KEYS:
                    if new_state.get("run_id") and key in {
                        "selected_candidate_ids",
                        "excluded_candidate_ids",
                        "selection_confirmation",
                        "review_stage",
                        "skill_review_change_id",
                    }:
                        continue
                    if new_state[key] != prev_state.get(key):
                        yield _sse(
                            "state_update",
                            {
                                "stateKey": key,
                                "value": new_state[key],
                            },
                        )
                        if key == "insertion_results" and new_state[key]:
                            should_rebuild_prerequisites = True
                if should_rebuild_prerequisites:
                    course_id = input_data.get("course_id")
                    if course_id is not None:
                        _schedule_skill_prerequisite_rebuild(
                            int(course_id),
                            "market_demand_insertion",
                        )
                if (
                    new_state != prev_state
                    and thread_id
                    and lease is None
                    and persistence_policy == "workflow_snapshot"
                ):
                    _persist_state(thread_id, bound_state)
                review_keys = (
                    "run_id",
                    "candidate_revision",
                    "selection_revision",
                    "publication_revision",
                    "skill_review_change_id",
                )
                if new_state.get("run_id") and any(
                    new_state.get(key) != prev_state.get(key) for key in review_keys
                ):
                    yield _sse(
                        "skill_review_changed",
                        {
                            "run_id": new_state["run_id"],
                            "candidate_revision": new_state.get("candidate_revision")
                            or 0,
                            "selection_revision": new_state.get("selection_revision")
                            or 0,
                            "publication_revision": new_state.get(
                                "publication_revision"
                            )
                            or 0,
                        },
                    )
                prev_state = new_state

    except Exception as exc:
        outcome = "failed"
        logger.exception("Graph stream rendering failed")
        # The owned producer still drains; wait for its finalization before ending
        # an attached response even if presentation failed.
        await asyncio.shield(_producer)
        yield _sse("error", _stream_error(exc).model_dump())
    finally:
        if lease is None:
            _producer.cancel()
        # Managed producers retain their execution lease through disconnects.
        # Late sync tool results are persisted before their guard is released.

    # Final text_done if we were mid-stream
    if current_message_id:
        yield _sse("text_done", {"messageId": current_message_id})

    total_ms = (time.perf_counter() - stream_start) * 1000
    logger.info(
        "[PERF] SSE stream finished: %.1fms total, %d events (thread=%s, last_agent=%s)",
        total_ms,
        event_count,
        thread_id,
        current_agent,
    )
    yield _sse("stream_end", {"outcome": outcome})


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=8000)
    workspace_context: WorkspaceContext | None = None
    sources: list[JobSource] | None = None
    evidence_sources: list[EvidenceSource] | None = None
    onet_release: str | None = None
    onet_occupation_codes: list[str] | None = None
    country: str | None = None
    location: str | None = None  # Deprecated; old clients sent this as country.

    @model_validator(mode="before")
    @classmethod
    def contextual_unknown_fields(cls, value):
        if (
            isinstance(value, dict)
            and value.get("workspace_context") is not None
            and set(value) - set(cls.model_fields)
        ):
            raise ValueError("Unknown contextual chat fields")
        return value

    @model_validator(mode="after")
    def contextual_configuration(self):
        configuration = {
            "sources",
            "evidence_sources",
            "onet_release",
            "onet_occupation_codes",
            "country",
            "location",
        }
        if self.workspace_context is not None and self.model_fields_set & configuration:
            raise ValueError("Contextual questions cannot change source configuration")
        return self


@router.get("/{course_id}/market-demand/sources", response_model=list[JobSourceOption])
def market_demand_sources(
    course_id: int,
    teacher: TeacherDep,
    country: str = DEFAULT_JOB_SEARCH_COUNTRY,
    db: Session = Depends(get_db),
    service: JobSourceService = Depends(get_job_source_service),
):
    _get_owned_course(course_id, teacher, db)
    try:
        selected_country = normalize_job_search_country(country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.catalog(selected_country)


@router.get(
    "/{course_id}/market-demand/skill-review/postings/{snapshot_id}",
    response_model=VacancyEvidence,
)
def market_vacancy_evidence(
    course_id: int,
    snapshot_id: uuid.UUID,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
    repository: MarketReviewRepository = Depends(get_market_review_repository),
):
    _get_owned_course(course_id, teacher, db)
    snapshot = repository.get_vacancy_snapshot(snapshot_id, course_id, teacher.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Vacancy evidence not found")
    return VacancyEvidence(
        snapshot_id=snapshot.id,
        provider=snapshot.provider,
        native_id=snapshot.native_id,
        original_url=snapshot.original_url,
        title=snapshot.title,
        company=snapshot.company,
        description_text=snapshot.description_text,
        original_description=snapshot.original_description,
        raw_payload=snapshot.raw_payload,
        retrieved_at=snapshot.retrieved_at,
        status=snapshot.status,
        purged_at=snapshot.purged_at,
    )


@router.get(
    "/{course_id}/market-demand/execution-status", response_model=ExecutionStatus
)
async def get_market_execution_status(
    course_id: int,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    service.require_teacher(course_id, teacher.id)
    return await state_service.execution_status(
        service.thread_id(course_id, teacher.id)
    )


@router.get("/{course_id}/market-demand/skill-review", response_model=SkillReview)
def get_skill_review(
    course_id: int,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
):
    return service.get_review(course_id, teacher.id)


async def _teacher_review_write(
    course_id: int,
    teacher_id: int,
    body: SkillReviewRevision,
    service: SkillReviewService,
    state_service: ThreadStateService,
    write: Callable,
) -> SkillReview:
    service.require_teacher(course_id, teacher_id)
    try:
        lease = await state_service.claim(service.thread_id(course_id, teacher_id))
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        return write(course_id, teacher_id, body)
    except BaseException:
        service.rollback()
        raise
    finally:
        await state_service.release(lease)


@router.put("/{course_id}/market-demand/skill-review/draft", response_model=SkillReview)
async def save_skill_review_draft(
    course_id: int,
    body: SkillReviewDraft,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    return await _teacher_review_write(
        course_id, teacher.id, body, service, state_service, service.save_draft
    )


@router.post(
    "/{course_id}/market-demand/skill-review/selection-confirmation",
    response_model=SkillReview,
    dependencies=[Depends(require_materials_ready)],
)
async def confirm_skill_review_selection(
    course_id: int,
    body: SkillSelectionConfirmation,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    return await _teacher_review_write(
        course_id, teacher.id, body, service, state_service, service.confirm_selection
    )


@router.post(
    "/{course_id}/market-demand/skill-review/continue-with-available-evidence",
    response_model=SkillReview,
    dependencies=[Depends(require_materials_ready)],
)
async def continue_skill_review(
    course_id: int,
    body: SkillReviewRevision,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    return await _teacher_review_write(
        course_id,
        teacher.id,
        body,
        service,
        state_service,
        service.continue_with_available_evidence,
    )


@router.post(
    "/{course_id}/market-demand/skill-review/withdrawal-review",
    response_model=SkillReview,
    dependencies=[Depends(require_materials_ready)],
)
async def prepare_skill_withdrawal(
    course_id: int,
    body: SkillReviewRevision,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
):
    return await _teacher_review_write(
        course_id,
        teacher.id,
        body,
        service,
        state_service,
        service.prepare_withdrawal_review,
    )


@router.post(
    "/{course_id}/market-demand/integration-approval",
    response_model=IntegrationApprovalResult,
    dependencies=[Depends(require_materials_ready)],
)
async def approve_skill_integration(
    course_id: int,
    body: IntegrationApproval,
    teacher: TeacherDep,
    service: SkillReviewService = Depends(get_skill_review_service),
    state_service: ThreadStateService = Depends(get_thread_state_service),
    projector: SkillEvidenceProjector = Depends(get_skill_evidence_projector),
):
    result = await _teacher_review_write(
        course_id, teacher.id, body, service, state_service, service.approve_integration
    )
    result.projection_status = projector.project(
        course_id, result.review.publication_revision, run_id=body.run_id
    )
    result.review = service.get_review(course_id, teacher.id)
    return result


@router.post(
    "/{course_id}/market-demand/chat",
    dependencies=[Depends(require_materials_ready)],
)
async def market_demand_chat(
    course_id: int,
    body: ChatRequest,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
    auth_db: AsyncSession = Depends(get_async_db),
    state_service: ThreadStateService = Depends(get_thread_state_service),
    configuration_service: MarketConfigurationService = Depends(
        get_market_configuration_service
    ),
    workspace_service: WorkspaceContextService = Depends(get_workspace_context_service),
) -> StreamingResponse:
    """Stream a Market Demand Agent conversation turn.

    The client sends a user message (or empty string for initial greeting)
    and receives an SSE stream of agent events.
    """
    chat_start = time.perf_counter()
    course = _get_owned_course(course_id, teacher, db)
    # Deterministic thread_id per teacher+course so sessions stay course-scoped.
    thread_id = _get_thread_id(teacher.id, course.id)
    logger.info(
        "[PERF] /chat request received (thread=%s, msg_len=%d)",
        thread_id,
        len(body.message),
    )

    requested_country = body.country or body.location
    if requested_country:
        try:
            normalize_job_search_country(requested_country)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    try:
        lease = await state_service.claim(thread_id)
    except ThreadBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        runtime_context = None
        persistence_policy = "workflow_snapshot"
        if body.workspace_context is not None:
            # Resolve rolls back the read transaction and expires ORM objects.
            # Detach identities first; reading course.id afterwards reopens it.
            context_course_id, context_teacher_id = course.id, teacher.id
            resolved = workspace_service.resolve(
                context_course_id, context_teacher_id, body.workspace_context
            )
            runtime_context = WorkspaceRuntimeContext(
                resolved=resolved,
                course_id=context_course_id,
                teacher_id=context_teacher_id,
                intent=resolved.intent,
            )
            persistence_policy = (
                "proposal_snapshot"
                if resolved.intent == "propose_selection"
                else "checkpoint_only"
            )
            # Inspection must not configure sources, seed defaults, or write SQL.
            bound_state = deepcopy(await _load_persisted_state(thread_id) or {})
            graph, _llm = await get_graph()
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint = await graph.aget_state(config)
            # Fresh contextual input may replace a failed contextual-only turn.
            # Never discard pending workflow nodes or their nested work.
            if any(name != "workspace_review" for name in checkpoint.next) or any(
                task.name != "workspace_review" for task in checkpoint.tasks
            ):
                raise HTTPException(
                    409,
                    {
                        "code": "workflow_recovery_required",
                        "message": "An unfinished workflow needs recovery before this question can run.",
                        "recovery": "Recover the workflow, then refresh context",
                    },
                )
            input_data = {
                "messages": [
                    HumanMessage(
                        id=f"user-{uuid.uuid4().hex}",
                        content=body.message,
                        additional_kwargs={
                            "workspace_context": safe_workspace_metadata(
                                resolved.history_metadata
                            )
                        },
                    )
                ]
            }
        else:
            # Restore and validate durable configuration before graph work.
            t0 = time.perf_counter()
            persisted = await _load_persisted_state(thread_id)
            parallel_ms = (time.perf_counter() - t0) * 1000
            logger.info("[PERF] Persisted state load took %.1fms", parallel_ms)

            bound_state: dict = {}
            with bind_tool_store(bound_state):
                _restore_thread_state(persisted, course, requested_country)
            try:
                configuration_service.configure(
                    course.id,
                    teacher.id,
                    bound_state,
                    body.model_dump(exclude_unset=True),
                )
                configuration_service.save_snapshot(
                    thread_id, snapshot_state(bound_state)
                )
                db.commit()
            except LookupError as exc:
                db.rollback()
                raise HTTPException(404, str(exc)) from exc
            except ValueError as exc:
                db.rollback()
                raise HTTPException(
                    409 if "new analysis" in str(exc) or "locked" in str(exc) else 422,
                    str(exc),
                ) from exc
            except BaseException:
                db.rollback()
                raise
            graph, _llm = await get_graph()

            config = {"configurable": {"thread_id": thread_id}}
            input_data = {
                "messages": [
                    HumanMessage(id=f"user-{uuid.uuid4().hex}", content=body.message)
                ],
                "course_id": course.id,
                "course_title": course.title,
                "course_description": course.description or "",
            }

            # Pre-warm: read the checkpoint with retry so stale SSL connections in the
            # pool are discarded *before* we enter the SSE generator (where retry is
            # harder because we may have already yielded events).
            t0 = time.perf_counter()
            for attempt in range(2):
                try:
                    await graph.aget_state(config)
                    break
                except Exception:
                    if attempt == 0:
                        logger.warning(
                            "Chat pre-warm checkpoint read failed (attempt 1), retrying…"
                        )
                        continue
                    logger.warning(
                        "Chat pre-warm checkpoint read failed twice, proceeding anyway"
                    )
            prewarm_ms = (time.perf_counter() - t0) * 1000
            logger.info("[PERF] Checkpoint pre-warm took %.1fms", prewarm_ms)

        # Authentication/course dependencies outlive StreamingResponse. Their read
        # transactions must end before silent model work; all runtime data is detached.
        db.rollback()
        await auth_db.rollback()
        setup_ms = (time.perf_counter() - chat_start) * 1000
        logger.info("[PERF] /chat setup total %.1fms before SSE stream", setup_ms)

    except BaseException:
        await state_service.release(lease)
        raise

    return StreamingResponse(
        _sse_stream(
            graph,
            input_data,
            config,
            bound_state=bound_state,
            lease=lease,
            state_service=state_service,
            runtime_context=runtime_context,
            persistence_policy=persistence_policy,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Thread-Id": thread_id,
        },
    )


@router.get("/{course_id}/market-demand/state")
async def get_agent_state(
    course_id: int,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the persisted agent state for the user's thread."""
    course = _get_owned_course(course_id, teacher, db)
    thread_id = _get_thread_id(teacher.id, course.id)
    persisted = await _load_persisted_state(thread_id)
    with bind_tool_store({}):
        _restore_thread_state(persisted, course)
        return snapshot_state()


@router.get("/{course_id}/market-demand/history")
async def get_conversation_history(
    course_id: int,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return conversation history from the checkpoint for page refresh restoration.

    Reads the LangGraph checkpoint state and converts messages into
    the same ChatMessage format the frontend expects.

    Retries once on connection errors (stale SSL connections in the pool).
    """
    history_start = time.perf_counter()
    course = _get_owned_course(course_id, teacher, db)
    thread_id = _get_thread_id(teacher.id, course.id)
    logger.info("[PERF] /history request received (thread=%s)", thread_id)

    t0 = time.perf_counter()
    graph, _ = await get_graph()
    logger.info(
        "[PERF] /history get_graph() took %.1fms", (time.perf_counter() - t0) * 1000
    )

    config = {"configurable": {"thread_id": thread_id}}

    # Load checkpoint and persisted state concurrently
    async def _read_checkpoint():
        for attempt in range(2):
            try:
                return await graph.aget_state(config)
            except Exception:
                if attempt == 0:
                    logger.warning(
                        "Checkpoint read failed for %s (attempt 1), retrying…",
                        thread_id,
                    )
                    continue
                logger.exception("Failed to load checkpoint for thread %s", thread_id)
                return None

    t0 = time.perf_counter()
    state, persisted = await asyncio.gather(
        _read_checkpoint(),
        _load_persisted_state(thread_id),
    )
    checkpoint_ms = (time.perf_counter() - t0) * 1000
    logger.info("[PERF] /history parallel checkpoint+state took %.1fms", checkpoint_ms)

    # History reads do not mutate another running analysis.
    with bind_tool_store({}):
        _restore_thread_state(persisted, course)

    if not state or not state.values:
        return {"messages": [], "threadId": thread_id, "outcome": "unknown"}

    raw_messages = state.values.get("messages", [])
    if not raw_messages:
        logger.info("[PERF] /history: no messages found")
        return {"messages": [], "threadId": thread_id, "outcome": "unknown"}

    logger.info("[PERF] /history: converting %d raw messages", len(raw_messages))

    # Convert LangChain messages → frontend ChatMessage format
    chat_messages: list[dict[str, Any]] = []
    current_agent_msg: dict[str, Any] | None = None

    for msg in raw_messages:
        if isinstance(msg, HumanMessage):
            # Flush any pending agent message
            if current_agent_msg:
                chat_messages.append(current_agent_msg)
                current_agent_msg = None
            metadata = safe_workspace_metadata(
                msg.additional_kwargs.get("workspace_context")
            )
            chat_messages.append(
                {
                    **({"workspace_context": metadata} if metadata is not None else {}),
                    "id": msg.id or f"user-{len(chat_messages)}",
                    "role": "user",
                    "content": msg.content,
                    "toolCalls": [],
                    "isStreaming": False,
                }
            )

        elif isinstance(msg, (AIMessage, AIMessageChunk)):
            agent = _extract_agent_from_message(msg)
            # If same agent, append text; otherwise start new agent message
            if current_agent_msg and current_agent_msg.get("agent") == agent:
                current_agent_msg["content"] += msg.content or ""
            else:
                if current_agent_msg:
                    chat_messages.append(current_agent_msg)
                meta = AGENT_META.get(agent, {"displayName": agent, "emoji": "🤖"})
                current_agent_msg = {
                    "id": msg.id or f"agent-{len(chat_messages)}",
                    "role": "agent",
                    "agent": agent,
                    "agentDisplayName": meta["displayName"],
                    "agentEmoji": meta["emoji"],
                    "content": msg.content or "",
                    "toolCalls": [],
                    "isStreaming": False,
                }

            # Include tool calls from AIMessage
            for tc in getattr(msg, "tool_calls", []) or []:
                current_agent_msg["toolCalls"].append(
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("args", {}),
                        "status": "unknown",
                    }
                )

        elif isinstance(msg, ToolMessage):
            # Attach result to matching tool call in the current agent message
            if current_agent_msg:
                for tc in current_agent_msg["toolCalls"]:
                    if tc["id"] == msg.tool_call_id:
                        tc["status"] = "error" if msg.status == "error" else "finished"
                        try:
                            tc["result"] = (
                                json.loads(msg.content)
                                if isinstance(msg.content, str)
                                else msg.content
                            )
                        except (json.JSONDecodeError, TypeError):
                            tc["result"] = msg.content
                        break

    # Flush last agent message
    if current_agent_msg:
        chat_messages.append(current_agent_msg)

    total_ms = (time.perf_counter() - history_start) * 1000
    logger.info(
        "[PERF] /history total %.1fms, %d messages returned (thread=%s)",
        total_ms,
        len(chat_messages),
        thread_id,
    )
    return {"messages": chat_messages, "threadId": thread_id, "outcome": "unknown"}


def _extract_agent_from_message(msg: AIMessage | AIMessageChunk) -> str:
    """Extract agent name from message metadata or name field."""
    if hasattr(msg, "name") and msg.name:
        return msg.name
    return "unknown"


@router.delete("/{course_id}/market-demand/history")
async def delete_conversation(
    course_id: int,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
    state_service: ThreadStateService = Depends(get_thread_state_service),
) -> dict[str, str]:
    """Delete the conversation thread and all associated state.

    Deletes:
    - LangGraph checkpoint (messages, agent state)
    - Persisted tool_store state (jobs, skills, mapping, etc.)

    Does NOT delete Knowledge Map data — skills/concepts already integrated
    into the curriculum are kept.
    """
    course = _get_owned_course(course_id, teacher, db)
    thread_id = _get_thread_id(teacher.id, course.id)

    try:
        lease = await state_service.claim(thread_id)
    except ThreadBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        # Keep deletion's guard across checkpoint removal too; a new chat cannot
        # recreate a checkpoint in the gap between the two deletions.
        await state_service.delete(thread_id, lease=lease)
        graph, _ = await get_graph()
        checkpointer = graph.checkpointer
        if checkpointer and hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(thread_id)
    finally:
        await state_service.release(lease)

    return {"status": "deleted", "threadId": thread_id}
