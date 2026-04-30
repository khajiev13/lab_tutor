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
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import BaseModel
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import AsyncSessionLocal, SessionLocal, get_db
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.skill_prerequisites.service import (
    schedule_skill_prerequisite_rebuild as schedule_prerequisite_rebuild,
)

from .countries import DEFAULT_JOB_SEARCH_COUNTRY, normalize_job_search_country
from .graph import get_graph
from .models import MDAThreadState
from .state import STATE_KEYS, restore_state, snapshot_state, tool_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses", tags=["market-demand"])

# Agent display metadata (shared with frontend via agent_start events)
AGENT_META: dict[str, dict[str, str]] = {
    "supervisor": {"displayName": "Supervisor", "emoji": "📊"},
    "skill_finder": {"displayName": "Skill Finder", "emoji": "🔍"},
    "curriculum_mapper": {"displayName": "Curriculum Mapper", "emoji": "🗺️"},
    "skill_cleaner": {"displayName": "Skill Cleaner", "emoji": "🧹"},
    "concept_linker": {"displayName": "Concept Linker", "emoji": "🔗"},
}


TeacherDep = Annotated[User, Depends(require_role(UserRole.TEACHER))]


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
    try:
        schedule_prerequisite_rebuild(course_id, trigger_reason)
    except Exception:
        logger.exception(
            "Failed to schedule prerequisite rebuild for course %s", course_id
        )


# In-memory cache for persisted state (avoids 2-3s Azure PG round-trips on
# every request). Invalidated on write in _persist_state / delete.
_state_cache: dict[str, dict[str, Any] | None] = {}


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
        tool_store["job_search_country"] = selected_country.jobspy_country
    if "job_search_location" not in tool_store:
        tool_store["job_search_location"] = selected_country.location


def _restore_thread_state(
    persisted: dict[str, Any] | None,
    course: Course,
    country: str | None = None,
) -> None:
    # When a thread has no persisted snapshot yet, clear any prior thread's state.
    restore_state(persisted or {})
    has_fetched_jobs = bool(tool_store.get("fetched_jobs"))
    requested_country = country.strip() if isinstance(country, str) else None
    if not has_fetched_jobs:
        raw_country = (
            requested_country
            or str(tool_store.get("job_search_country", "")).strip()
            or str(tool_store.get("job_search_location", "")).strip()
            or DEFAULT_JOB_SEARCH_COUNTRY
        )
        selected_country = normalize_job_search_country(raw_country)
        tool_store["job_search_country"] = selected_country.jobspy_country
        tool_store["job_search_location"] = selected_country.location
    elif "job_search_country" not in tool_store and "job_search_location" in tool_store:
        with contextlib.suppress(ValueError):
            legacy_country = normalize_job_search_country(
                str(tool_store["job_search_location"])
            )
            tool_store["job_search_country"] = legacy_country.jobspy_country
    _seed_course_context(
        course,
        str(
            tool_store.get("job_search_country")
            or requested_country
            or DEFAULT_JOB_SEARCH_COUNTRY
        ),
    )


async def _persist_state_to_db(thread_id: str, state: dict[str, Any]) -> None:
    """Write state snapshot to PostgreSQL (background-safe)."""
    t0 = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                pg_insert(MDAThreadState)
                .values(
                    thread_id=thread_id,
                    state_json=state,
                )
                .on_conflict_do_update(
                    index_elements=["thread_id"],
                    set_={"state_json": state, "updated_at": func.now()},
                )
            )
            await session.execute(stmt)
            await session.commit()
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "[PERF] _persist_state_to_db took %.1fms (thread=%s)", elapsed, thread_id
        )
    except Exception:
        logger.exception("[PERF] _persist_state_to_db FAILED (thread=%s)", thread_id)


def _persist_state(thread_id: str) -> None:
    """Snapshot state into cache and schedule a non-blocking DB write."""
    state = snapshot_state()
    _state_cache[thread_id] = state
    asyncio.create_task(_persist_state_to_db(thread_id, state))


async def _load_persisted_state(thread_id: str) -> dict[str, Any] | None:
    """Load persisted agent state, using in-memory cache when available."""
    if thread_id in _state_cache:
        logger.info("[PERF] _load_persisted_state cache HIT (thread=%s)", thread_id)
        return _state_cache[thread_id]

    t0 = time.perf_counter()
    for attempt in range(2):
        try:
            async with AsyncSessionLocal() as session:
                row = await session.get(MDAThreadState, thread_id)
                if row:
                    _state_cache[thread_id] = row.state_json
                    elapsed = (time.perf_counter() - t0) * 1000
                    logger.info(
                        "[PERF] _load_persisted_state took %.1fms (DB, thread=%s)",
                        elapsed,
                        thread_id,
                    )
                    return row.state_json
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
            _state_cache[thread_id] = None
            return None
    _state_cache[thread_id] = None
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "[PERF] _load_persisted_state took %.1fms (not found, thread=%s)",
        elapsed,
        thread_id,
    )
    return None


async def _sse_stream(
    graph: Any,
    input_data: dict,
    config: dict,
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
    current_agent: str | None = None
    current_message_id: str | None = None
    seen_tool_calls: set[str] = set()
    # Buffer to accumulate tool call args across chunks
    tool_call_args: dict[str, str] = {}
    # Map chunk index → tool call id (for chunks that omit the id)
    tool_index_to_id: dict[int, str] = {}
    prev_state = snapshot_state()
    thread_id = config.get("configurable", {}).get("thread_id", "")

    stream_start = time.perf_counter()
    event_count = 0
    last_event_time = stream_start
    tool_timings: dict[str, float] = {}  # tool_call_id → start time

    # Producer task: fills a queue from graph.astream so we can inject SSE keep-alive
    # comments during silent periods (e.g. the fan-out extraction runs for several
    # minutes emitting no SSE-visible messages, which triggers Azure's 240-second
    # TCP idle timeout and kills the connection).
    _queue: asyncio.Queue[tuple | Exception | None] = asyncio.Queue()

    async def _graph_producer() -> None:
        try:
            async for item in graph.astream(
                input_data,
                config=config,
                stream_mode="messages",
                subgraphs=True,
            ):
                await _queue.put(item)
        except Exception as exc:
            await _queue.put(exc)
        finally:
            await _queue.put(None)

    _producer = asyncio.create_task(_graph_producer())

    try:
        logger.info("[PERF] SSE stream starting (thread=%s)", thread_id)
        while True:
            try:
                item = await asyncio.wait_for(_queue.get(), timeout=30.0)
            except TimeoutError:
                # Keep-alive SSE comment resets Azure TCP idle clock
                yield ": keep-alive\n\n"
                continue

            if item is None:
                break
            if isinstance(item, Exception):
                raise item

            ns, (msg, _metadata) = item
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

            if isinstance(msg, AIMessageChunk):
                agent = _resolve_agent(ns)

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
                for tc in msg.tool_call_chunks or []:
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
                        "status": "success",
                    },
                )

                # Check for state changes after tool execution
                new_state = snapshot_state()
                should_rebuild_prerequisites = False
                for key in STATE_KEYS:
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
                if new_state != prev_state and thread_id:
                    _persist_state(thread_id)
                prev_state = new_state

    except Exception as exc:
        logger.exception("Graph stream error: %s", exc)
    finally:
        _producer.cancel()

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
    yield _sse("stream_end", {})


class ChatRequest(BaseModel):
    message: str = ""
    country: str | None = None
    location: str | None = None  # Deprecated; old clients sent this as country.


@router.post("/{course_id}/market-demand/chat")
async def market_demand_chat(
    course_id: int,
    body: ChatRequest,
    teacher: TeacherDep,
    db: Session = Depends(get_db),
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

    # Load persisted state and graph concurrently (both hit PostgreSQL)
    t0 = time.perf_counter()
    persisted, (graph, _llm) = await asyncio.gather(
        _load_persisted_state(thread_id),
        get_graph(),
    )
    parallel_ms = (time.perf_counter() - t0) * 1000
    logger.info("[PERF] Parallel state+graph load took %.1fms", parallel_ms)

    _restore_thread_state(persisted, course, requested_country)

    config = {"configurable": {"thread_id": thread_id}}
    input_data = {
        "messages": [HumanMessage(content=body.message)],
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

    setup_ms = (time.perf_counter() - chat_start) * 1000
    logger.info("[PERF] /chat setup total %.1fms before SSE stream", setup_ms)

    return StreamingResponse(
        _sse_stream(graph, input_data, config),
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

    # Restore tool_store from persisted state so pipeline stages are correct
    _restore_thread_state(persisted, course)

    if not state or not state.values:
        return {"messages": [], "threadId": thread_id}

    raw_messages = state.values.get("messages", [])
    if not raw_messages:
        logger.info("[PERF] /history: no messages found")
        return {"messages": [], "threadId": thread_id}

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
            chat_messages.append(
                {
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
                        "status": "success",
                    }
                )

        elif isinstance(msg, ToolMessage):
            # Attach result to matching tool call in the current agent message
            if current_agent_msg:
                for tc in current_agent_msg["toolCalls"]:
                    if tc["id"] == msg.tool_call_id:
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
    return {"messages": chat_messages, "threadId": thread_id}


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

    # 1. Delete persisted agent state
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(MDAThreadState).where(MDAThreadState.thread_id == thread_id)
        )
        await session.commit()

    # 2. Delete LangGraph checkpoint
    graph, _ = await get_graph()
    checkpointer = graph.checkpointer
    if checkpointer and hasattr(checkpointer, "adelete_thread"):
        try:
            await checkpointer.adelete_thread(thread_id)
        except Exception:
            logger.exception("Failed to delete checkpoint for thread %s", thread_id)

    # 3. Clear in-memory tool_store and state cache
    tool_store.clear()
    _state_cache.pop(thread_id, None)

    return {"status": "deleted", "threadId": thread_id}
