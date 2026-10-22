import asyncio
import logging
import time
from collections.abc import Sequence
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph_swarm import SwarmState, create_handoff_tool
from langgraph_swarm.handoff import get_handoff_destinations
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .extractor import extraction_tool_results, skill_extractor_subgraph
from .prompts import (
    CONCEPT_LINKER_PROMPT,
    CURRICULUM_MAPPER_PROMPT,
    SKILL_CLEANER_PROMPT,
    SKILL_FINDER_PROMPT,
    SUPERVISOR_PROMPT,
)
from .state import owned_sync_execution, pipeline_summary, snapshot_state, tool_store
from .tools import (
    CONCEPT_LINKER_TOOLS,
    CURRICULUM_MAPPER_TOOLS,
    SKILL_CLEANER_TOOLS,
    SKILL_FINDER_TOOLS,
    SUPERVISOR_TOOLS,
    mapping_prerequisite_error,
    owned_sync_tools,
)
from .workspace_chat import WorkspaceRuntimeContext, route_entry, workspace_review

logger = logging.getLogger(__name__)


async def _require_mapping_chapters(state: dict) -> dict | Command:
    """Guard both fresh handoffs and resumed mapper checkpoints before inference."""
    error = await owned_sync_execution(mapping_prerequisite_error)()
    if error:
        # Parent-command updates persist history but bypass message streaming.
        get_stream_writer()({"type": "mapping_prerequisite", "message": error})
        return Command(
            graph=Command.PARENT,
            goto=END,
            update={
                "messages": [AIMessage(content=error, name="supervisor")],
                "active_agent": "supervisor",
            },
        )
    return {"messages": []}


# ── App-owned async checkpoint storage ────────────────────────
_ASYNC_CHECKPOINTER: AsyncPostgresSaver | None = None
_CONN_POOL: AsyncConnectionPool | None = None
_CHECKPOINT_INIT_LOCK: asyncio.Lock | None = None


def _get_checkpoint_db_url() -> str:
    """Derive a psycopg-compatible URL from the app's DATABASE_URL."""
    from app.core.settings import settings

    url = settings.database_url
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    for prefix in ("postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            url = "postgresql://" + url.removeprefix(prefix)
    return url


async def _get_async_checkpointer() -> AsyncPostgresSaver:
    """Return ready storage; failed or concurrent setup never exposes a partial saver."""
    global _ASYNC_CHECKPOINTER, _CONN_POOL, _CHECKPOINT_INIT_LOCK  # noqa: PLW0603
    if _CHECKPOINT_INIT_LOCK is None:
        _CHECKPOINT_INIT_LOCK = asyncio.Lock()
    async with _CHECKPOINT_INIT_LOCK:
        if _ASYNC_CHECKPOINTER is not None:
            return _ASYNC_CHECKPOINTER
        t0 = time.perf_counter()
        pool = AsyncConnectionPool(
            conninfo=_get_checkpoint_db_url(),
            min_size=1,
            max_size=5,
            max_idle=120,
            check=AsyncConnectionPool.check_connection,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        try:
            await pool.open()
            saver = AsyncPostgresSaver(conn=pool)
            await saver.setup()
        except BaseException:
            # Includes startup cancellation. A later call must create a fresh pool
            # and finish real migrations, not reuse a partially initialized saver.
            await pool.close()
            raise
        _CONN_POOL = pool
        _ASYNC_CHECKPOINTER = saver
        logger.info(
            "[PERF] Checkpoint storage ready in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return saver


async def initialize_market_checkpoint_storage() -> None:
    """Migrate storage before serving requests, without creating an LLM/graph.

    PostgreSQL concurrent index creation waits for older read transactions.
    Running setup inside an authenticated request can wait on that same request's
    auth session, which cannot close until the request finishes.
    """
    await _get_async_checkpointer()


async def close_market_checkpoint_storage() -> None:
    """Release app-owned storage after requests drain, including startup failures."""
    global _ASYNC_CHECKPOINTER, _CONN_POOL, _CHECKPOINT_INIT_LOCK  # noqa: PLW0603
    global _COMPILED_GRAPH, _LLM_INSTANCE  # noqa: PLW0603
    if _CHECKPOINT_INIT_LOCK is None:
        return
    async with _CHECKPOINT_INIT_LOCK:
        pool = _CONN_POOL
        _ASYNC_CHECKPOINTER = None
        _CONN_POOL = None
        _COMPILED_GRAPH = None
        _LLM_INSTANCE = None
        if pool is not None:
            await pool.close()
    # Locks with waiters and psycopg pools belong to the old event loop. A new
    # application lifespan must not inherit either of them (including in tests).
    _CHECKPOINT_INIT_LOCK = None


def _create_llm() -> ChatOpenAI:
    from app.core.settings import settings

    api_key = settings.llm_api_key or ""
    return ChatOpenAI(
        model=settings.llm_agent_model,
        base_url=settings.llm_base_url,
        api_key=api_key,  # type: ignore[arg-type]
        temperature=0,
        streaming=True,
        timeout=settings.llm_timeout_seconds,
        extra_body={"thinking": {"type": "disabled"}}
        if settings.llm_agent_model.casefold().startswith("deepseek")
        else {"enable_thinking": False},
    )


# ── Shared compiled graph (lazy-init) ─────────────────────────
_COMPILED_GRAPH = None
_LLM_INSTANCE = None
# Maximum number of recent messages the LLM sees per turn.
# Older messages are trimmed from the prompt (not from the checkpoint).
_MAX_PROMPT_MESSAGES = 10


def _make_prompt(
    system_prompt: str,
    max_messages: int = _MAX_PROMPT_MESSAGES,
):
    """Return a callable that builds [SystemMessage + trimmed history].

    The callable is invoked by create_react_agent on every LLM call.
    It dynamically appends the current pipeline state from tool_store and
    keeps only the last *max_messages* conversation messages so the context
    window stays bounded.
    """

    def _prompt(state: dict) -> Sequence[BaseMessage]:
        # Dynamic course + pipeline context (reads checkpoint state first, then tool_store)
        course_id = state.get("course_id")
        course_title = state.get("course_title")
        course_description = state.get("course_description")

        course_lines: list[str] = []
        if course_id:
            course_lines.append(f"Course ID: {course_id}")
        if course_title:
            course_lines.append(f"Course Title: {course_title}")
        if course_description:
            course_lines.append(f"Course Description: {course_description}")

        ctx = pipeline_summary()
        full_prompt = system_prompt
        if course_lines:
            full_prompt += "\n\n# Current Course Context\n" + "\n".join(course_lines)
        if ctx:
            full_prompt += f"\n\n# Current Pipeline State\n{ctx}"
        if tool_store.get("run_id"):
            full_prompt += (
                "\n\n# Durable source and review contract\n"
                f"Evidence sources: {tool_store.get('evidence_sources', ['jobs'])}; "
                f"job providers: {tool_store.get('sources', [])}. "
                "Use only those providers; never add a fallback. O*NET references "
                "are local lookup work in fetch_jobs, not an autonomous agent. "
                "Require confirmed occupations before O*NET collection. "
                "For O*NET-only analysis call fetch_jobs with empty search_terms "
                "after occupation confirmation; skip job queries/group approval. "
                "In mixed mode collect both sources, then await teacher job-group "
                "approval before start_extraction. Reference candidates in state "
                "do not mean vacancy extraction is complete. "
                "Retry failed posting/chunk assessments or failed association inference "
                "with start_extraction. Call start_extraction alone after any other tool results. "
                "Fully assessed postings with only fixed O*NET "
                "association bounds must not be selected or extracted again. "
                "get_skills_by_category is read-only and can present current omissions "
                "alongside inline skill choices. Partial/error sources do not block "
                "job-group selection or extraction of available postings. Show a brief "
                "partial or changed evidence note at the existing Confirm Selection "
                "action; it saves exact choices and current evidence consent together. "
                "Report assessed/selected sample counts and coverage separately "
                "from O*NET ratings and recommendations. Teachable communication "
                "and social competencies are valid when explicitly supported. "
                "Use candidate IDs and preserve evidence during all handoffs. "
                "Confirmed skill selection and final integration approval are teacher "
                "API decisions. Model tools cannot grant final approval or publish. "
                "For advice use propose_skill_selection with candidate IDs, add/remove "
                "actions and specific reasons. Recommendations are immutable diffs; "
                "they never change a saved draft or override exclusions. "
                "approve_skill_selection ignores model-provided choices for this run "
                "and loads only the exact server-confirmed teacher shortlist. "
                "O*NET-only candidates need supporting job postings before publication."
            )

        if (tool_store.get("skill_priority_status") or {}).get("assessment_id"):
            full_prompt += (
                "\n\n# Stored skill priority policy version 1\n"
                "Use only the validated priority_assessment and priority summaries from "
                "get_skills_by_category. The automatic Skill Priority Analyst has already "
                "run; do not retry extraction for missing priority scores. Supplied "
                "derived category means and separately labeled AI importance estimates "
                "are allowed by this policy; never invent or recalculate scores. "
                "Keep occupational importance separate from posting frequency. "
                "Priority-only omissions do not require evidence acknowledgment. "
                "Retain mandatory job-evidence consent, exact teacher skill confirmation "
                "and final publication approval. Present the existing Choose skills decision."
            )

        # Trim to last N messages
        messages: list[BaseMessage] = list(state.get("messages", []))
        logger.debug(
            "Prompt builder: %d total messages, trimming to last %d",
            len(messages),
            max_messages,
        )
        if len(messages) > max_messages:
            messages = messages[-max_messages:]

        # Guardrail: trimming can leave ToolMessage entries whose parent
        # AI tool_calls message was cut off, which causes provider 400s.
        kept_tool_call_ids: set[str] = set()
        sanitized: list[BaseMessage] = []
        for msg in messages:
            if isinstance(msg, AIMessage):
                for tc in msg.tool_calls or []:
                    tc_id = tc.get("id")
                    if tc_id:
                        kept_tool_call_ids.add(tc_id)
                sanitized.append(msg)
                continue

            if isinstance(msg, ToolMessage):
                tc_id = msg.tool_call_id
                if tc_id and tc_id in kept_tool_call_ids:
                    sanitized.append(msg)
                else:
                    logger.debug(
                        "Prompt builder: dropped orphan ToolMessage id=%s name=%s",
                        tc_id,
                        msg.name,
                    )
                continue

            sanitized.append(msg)

        messages = sanitized

        # Log each message type for debugging
        for i, m in enumerate(messages):
            content_preview = str(m.content)[:120] if m.content else "(empty)"
            logger.debug("  msg[%d] %s: %s", i, type(m).__name__, content_preview)

        return [SystemMessage(content=full_prompt), *messages]

    return _prompt


class MarketSwarmState(SwarmState):
    skill_priority_status: dict | None


async def skill_priority_analyst(
    state: SwarmState, runtime: Runtime[WorkspaceRuntimeContext]
) -> Command:
    """Assess the saved extraction once, under the outer conversation lease."""
    from app.core.database import SessionLocal
    from app.core.settings import settings

    from .models import MarketAnalysisRun
    from .priority_service import get_skill_priority_service
    from .schemas import PriorityScope
    from .thread_state_service import ThreadStateService

    context = runtime.context
    update = {"active_agent": "skill_finder", "skill_priority_status": None}
    results = extraction_tool_results(state.get("messages", []))
    if results:
        update["messages"] = results
    if not tool_store.get("run_id") or not settings.market_skill_priority_enabled:
        tool_store["skill_priority_status"] = None
        return Command(goto="skill_finder", update=update)
    if (
        context is None
        or context.resolved is not None
        or context.lease is None
        or context.course_id != tool_store.get("course_id")
        or context.teacher_id != tool_store.get("teacher_id")
    ):
        raise ValueError("Priority analysis requires the owned workflow context")
    lease = context.lease
    scope = PriorityScope(
        run_id=UUID(tool_store["run_id"]),
        course_id=context.course_id,
        teacher_id=context.teacher_id,
        expected_candidate_revision=tool_store.get("candidate_revision") or 0,
    )
    service = get_skill_priority_service()
    # All snapshot writes join the outer lease's ordered, shielded task chain.
    # Cancellation cannot release ownership before the actual SQL worker ends.
    service._require_lease(lease, f"mda-{scope.teacher_id}-course-{scope.course_id}")
    snapshots = ThreadStateService()
    await snapshots.save(lease, snapshot_state())
    writer = get_stream_writer()

    def progress(assessment):
        value = {
            "assessment_id": str(assessment.assessment_id),
            "status": assessment.status,
            "deadline_at": assessment.deadline_at.isoformat(),
            "message": "Assessing skill importance…"
            if assessment.status == "running"
            else "",
        }
        tool_store["skill_priority_status"] = value
        writer({"type": "skill_priority_status", "value": value})
        return value

    attempt = asyncio.create_task(service.assess(scope, lease))
    try:
        # assess commits its running envelope before its first transport await.
        # Emit explicit custom progress while a silent model call is in flight.
        await asyncio.sleep(0)
        if not attempt.done():
            with SessionLocal() as db:
                run = db.get(MarketAnalysisRun, scope.run_id)
                raw = run.priority_assessment if run is not None else None
            if raw is not None:
                from .schemas import PriorityAssessment

                running = PriorityAssessment.model_validate(raw)
                if running.status == "running":
                    progress(running)
                    await snapshots.save(lease, snapshot_state())
        assessment = await attempt
    finally:
        if not attempt.done():
            attempt.cancel()
            await asyncio.gather(attempt, return_exceptions=True)
    # assess returns only after the final CAS commit (or a scoreless stale result).
    tool_store["skill_review_change_id"] = str(assessment.assessment_id)
    value = progress(assessment)
    await snapshots.save(lease, snapshot_state())
    update["skill_priority_status"] = value
    return Command(goto="skill_finder", update=update)


async def get_graph():
    """Return the shared compiled graph, building it on first call.

    Architecture: 5-agent swarm with linear forward chain + Supervisor hub.
    - Supervisor → Skill Finder (fetch jobs, extract, teacher picks skills).
    - Skill Finder → Curriculum Mapper (map curated skills to chapters).
    - Curriculum Mapper → Skill Cleaner (remove redundant vs book skills).
    - Skill Cleaner → Concept Linker (extract concepts, write to Neo4j).
    - Concept Linker → Supervisor (report results).
    - Supervisor can re-enter any agent if teacher changes mind.
    """
    global _COMPILED_GRAPH, _LLM_INSTANCE  # noqa: PLW0603
    if _COMPILED_GRAPH is not None:
        return _COMPILED_GRAPH, _LLM_INSTANCE

    graph_build_start = time.perf_counter()
    llm = _create_llm()
    _LLM_INSTANCE = llm

    # ── Handoff tools ──
    handoff_to_supervisor = create_handoff_tool(
        agent_name="supervisor",
        description=(
            "Transfer back to Supervisor ONLY if the teacher wants to change direction, "
            "you encounter an error you cannot resolve, or you have completed the final "
            "step in the chain (Concept Linker). Do NOT use this if you can proceed forward."
        ),
    )
    handoff_to_skill_finder = create_handoff_tool(
        agent_name="skill_finder",
        description="Transfer to Skill Finder to fetch jobs and extract skills. Use ONLY after search terms are ready.",
    )
    handoff_to_curriculum_mapper = create_handoff_tool(
        agent_name="curriculum_mapper",
        description="Transfer to Curriculum Mapper ONLY after the teacher has confirmed their skill selection.",
    )
    handoff_to_skill_cleaner = create_handoff_tool(
        agent_name="skill_cleaner",
        description="Transfer to Skill Cleaner ONLY after all curated skills have been mapped to chapters.",
    )
    handoff_to_concept_linker = create_handoff_tool(
        agent_name="concept_linker",
        description="Transfer to Concept Linker ONLY after redundant skills have been cleaned.",
    )

    # ── Create agents ──
    # Supervisor: hub that can jump to any agent for re-entry.
    supervisor = create_react_agent(
        llm,
        tools=[
            *owned_sync_tools(SUPERVISOR_TOOLS),
            handoff_to_skill_finder,
            handoff_to_curriculum_mapper,
            handoff_to_skill_cleaner,
            handoff_to_concept_linker,
        ],
        prompt=_make_prompt(SUPERVISOR_PROMPT),
        name="supervisor",
    )

    # Skill Finder: fetches jobs, extracts skills, teacher picks.
    skill_finder = create_react_agent(
        llm,
        tools=[
            *owned_sync_tools(SKILL_FINDER_TOOLS),
            handoff_to_curriculum_mapper,
            handoff_to_supervisor,
        ],
        prompt=_make_prompt(SKILL_FINDER_PROMPT),
        name="skill_finder",
    )

    mapper_tools = [
        *owned_sync_tools(CURRICULUM_MAPPER_TOOLS),
        handoff_to_skill_cleaner,
        handoff_to_supervisor,
    ]
    curriculum_mapper = create_react_agent(
        llm.bind_tools(mapper_tools, tool_choice="required"),
        tools=mapper_tools,
        prompt=_make_prompt(CURRICULUM_MAPPER_PROMPT),
        pre_model_hook=_require_mapping_chapters,
        name="curriculum_mapper",
    )

    cleaner_tools = [
        *owned_sync_tools(SKILL_CLEANER_TOOLS),
        handoff_to_concept_linker,
        handoff_to_supervisor,
    ]
    skill_cleaner = create_react_agent(
        llm.bind_tools(cleaner_tools, tool_choice="required"),
        tools=cleaner_tools,
        prompt=_make_prompt(SKILL_CLEANER_PROMPT),
        name="skill_cleaner",
    )

    linker_tools = [*owned_sync_tools(CONCEPT_LINKER_TOOLS), handoff_to_supervisor]
    concept_linker = create_react_agent(
        llm.bind_tools(linker_tools, tool_choice="required"),
        tools=linker_tools,
        prompt=_make_prompt(CONCEPT_LINKER_PROMPT),
        name="concept_linker",
    )

    # ── Build swarm (5 agents) ──
    agents = [
        supervisor,
        skill_finder,
        curriculum_mapper,
        skill_cleaner,
        concept_linker,
    ]
    workflow = StateGraph(MarketSwarmState, context_schema=WorkspaceRuntimeContext)
    for agent in agents:
        workflow.add_node(
            agent.name, agent, destinations=tuple(get_handoff_destinations(agent))
        )
    workflow.add_node("workspace_review", workspace_review)
    workflow.add_node(
        "skill_priority_analyst", skill_priority_analyst, destinations=("skill_finder",)
    )
    workflow.add_conditional_edges(
        START,
        route_entry,
        [agent.name for agent in agents]
        + ["workspace_review", "skill_extractor", "skill_priority_analyst"],
    )

    # ── Add skill_extractor subgraph (map-reduce, no LLM agent) ──
    workflow.add_node("skill_extractor", skill_extractor_subgraph)

    t0 = time.perf_counter()
    checkpointer = await _get_async_checkpointer()
    logger.info(
        "[PERF] _get_async_checkpointer took %.1fms", (time.perf_counter() - t0) * 1000
    )
    _COMPILED_GRAPH = workflow.compile(checkpointer=checkpointer)
    total_ms = (time.perf_counter() - graph_build_start) * 1000
    logger.info("[PERF] Graph build total %.1fms", total_ms)
    return _COMPILED_GRAPH, _LLM_INSTANCE
