import logging
import time
from collections.abc import Sequence

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .prompts import (
    CONCEPT_LINKER_PROMPT,
    CURRICULUM_MAPPER_PROMPT,
    SUPERVISOR_PROMPT,
)
from .state import pipeline_summary
from .tools import (
    CONCEPT_LINKER_TOOLS,
    CURRICULUM_MAPPER_TOOLS,
    SUPERVISOR_TOOLS,
    load_curriculum_context,
)

logger = logging.getLogger(__name__)

# ── Shared async checkpointer (lazy-init) ──────────────────────
_ASYNC_CHECKPOINTER: AsyncPostgresSaver | None = None
_CONN_POOL: AsyncConnectionPool | None = None


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
    """Return the shared checkpointer backed by a connection pool.

    Uses AsyncConnectionPool so each checkpoint operation gets a fresh
    connection, avoiding idle-timeout drops during long tool calls.
    """
    global _ASYNC_CHECKPOINTER, _CONN_POOL  # noqa: PLW0603
    if _ASYNC_CHECKPOINTER is None:
        t0 = time.perf_counter()
        conn_string = _get_checkpoint_db_url()
        kwargs = {
            "conninfo": conn_string,
            "min_size": 1,
            "max_size": 5,
            "max_idle": 120,
            "check": AsyncConnectionPool.check_connection,
            "kwargs": {
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        }
        _CONN_POOL = AsyncConnectionPool(**kwargs, open=False)
        await _CONN_POOL.open()
        pool_ms = (time.perf_counter() - t0) * 1000
        logger.info("[PERF] Checkpointer pool opened in %.1fms", pool_ms)
        t1 = time.perf_counter()
        _ASYNC_CHECKPOINTER = AsyncPostgresSaver(conn=_CONN_POOL)
        await _ASYNC_CHECKPOINTER.setup()
        setup_ms = (time.perf_counter() - t1) * 1000
        logger.info(
            "[PERF] Checkpointer setup took %.1fms (total init %.1fms)",
            setup_ms,
            (time.perf_counter() - t0) * 1000,
        )
    return _ASYNC_CHECKPOINTER


def _create_llm() -> ChatOpenAI:
    from app.core.settings import settings

    api_key = settings.llm_api_key or ""
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=api_key,  # type: ignore[arg-type]
        temperature=0,
        streaming=True,
        timeout=settings.llm_timeout_seconds,
        extra_body={"enable_thinking": False},
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
        # Dynamic pipeline context (reads tool_store at call time)
        ctx = pipeline_summary()
        full_prompt = system_prompt
        if ctx:
            full_prompt += f"\n\n# Current Pipeline State\n{ctx}"

        # Trim to last N messages
        messages: list[BaseMessage] = list(state.get("messages", []))
        logger.debug(
            "Prompt builder: %d total messages, trimming to last %d",
            len(messages),
            max_messages,
        )
        if len(messages) > max_messages:
            messages = messages[-max_messages:]

        # Log each message type for debugging
        for i, m in enumerate(messages):
            content_preview = str(m.content)[:120] if m.content else "(empty)"
            logger.debug("  msg[%d] %s: %s", i, type(m).__name__, content_preview)

        return [SystemMessage(content=full_prompt), *messages]

    return _prompt


async def get_graph():
    """Return the shared compiled graph, building it on first call.

    Architecture: Supervisor (teacher-facing) orchestrates autonomous workers.
    - Supervisor → start_analysis_pipeline (programmatic extraction + auto-route
      to curriculum_mapper) — no LLM needed for this transition.
    - Curriculum Mapper → supervisor (presents findings for teacher review).
    - Supervisor → concept_linker (after teacher approves skills).
    - Concept Linker → supervisor (reports final stats).
    """
    global _COMPILED_GRAPH, _LLM_INSTANCE  # noqa: PLW0603
    if _COMPILED_GRAPH is not None:
        return _COMPILED_GRAPH, _LLM_INSTANCE

    graph_build_start = time.perf_counter()
    llm = _create_llm()
    _LLM_INSTANCE = llm

    t0 = time.perf_counter()
    curriculum_ctx = load_curriculum_context(teacher_email=None)
    logger.info(
        "[PERF] load_curriculum_context (Neo4j) took %.1fms",
        (time.perf_counter() - t0) * 1000,
    )
    supervisor_prompt = SUPERVISOR_PROMPT.format(curriculum_context=curriculum_ctx)

    # ── Handoff tools ──
    handoff_to_concept_linker = create_handoff_tool(
        agent_name="concept_linker",
        description=(
            "Transfer to the Concept Linker after the teacher approves "
            "skills for insertion. It will link concepts and write to Neo4j."
        ),
    )
    handoff_to_supervisor = create_handoff_tool(
        agent_name="supervisor",
        description="Transfer to the Supervisor to report results to the teacher.",
    )

    # ── Create agents ──
    # Supervisor: the only agent that talks to the teacher.
    # start_analysis_pipeline (in SUPERVISOR_TOOLS) runs extraction
    # programmatically and returns Command(goto="curriculum_mapper"),
    # skipping the LLM for this fixed transition.
    supervisor = create_react_agent(
        llm,
        tools=[*SUPERVISOR_TOOLS, handoff_to_concept_linker],
        prompt=_make_prompt(supervisor_prompt),
        name="supervisor",
    )

    curriculum_mapper = create_react_agent(
        llm,
        tools=[*CURRICULUM_MAPPER_TOOLS, handoff_to_supervisor],
        prompt=_make_prompt(CURRICULUM_MAPPER_PROMPT),
        name="curriculum_mapper",
    )

    concept_linker = create_react_agent(
        llm,
        tools=[*CONCEPT_LINKER_TOOLS, handoff_to_supervisor],
        prompt=_make_prompt(CONCEPT_LINKER_PROMPT),
        name="concept_linker",
    )

    # ── Build swarm (3 agents — no skill_extractor LLM) ──
    workflow = create_swarm(
        [supervisor, curriculum_mapper, concept_linker],
        default_active_agent="supervisor",
    )

    t0 = time.perf_counter()
    checkpointer = await _get_async_checkpointer()
    logger.info(
        "[PERF] _get_async_checkpointer took %.1fms", (time.perf_counter() - t0) * 1000
    )
    _COMPILED_GRAPH = workflow.compile(checkpointer=checkpointer)
    total_ms = (time.perf_counter() - graph_build_start) * 1000
    logger.info("[PERF] Graph build total %.1fms", total_ms)
    return _COMPILED_GRAPH, _LLM_INSTANCE
