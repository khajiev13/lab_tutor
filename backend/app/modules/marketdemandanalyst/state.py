import asyncio
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

# Bound mappings propagate through asyncio tasks and LangChain's copied worker context.
# The fallback supports standalone CLI tools; HTTP requests always bind explicitly.
_tool_context: ContextVar[dict | None] = ContextVar("market_tool_store", default=None)
_cli_store: dict = {}
_tool_tasks: ContextVar[set[asyncio.Task] | None] = ContextVar(
    "market_tool_tasks", default=None
)


def owned_sync_execution(func: Callable) -> Callable:
    """Keep actual worker completion owned when its async waiter is cancelled."""

    @wraps(func)
    async def execute(*args, **kwargs):
        task = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
        owned = _tool_tasks.get()
        if owned is not None:
            # Register before yielding to either the executor or cancellation.
            owned.add(task)
        return await asyncio.shield(task)

    return execute


class ToolStore(MutableMapping):
    def _current(self) -> dict:
        bound = _tool_context.get()
        return _cli_store if bound is None else bound

    def __getitem__(self, key):
        return self._current()[key]

    def __setitem__(self, key, value):
        self._current()[key] = value

    def __delitem__(self, key):
        del self._current()[key]

    def __iter__(self) -> Iterator:
        return iter(self._current())

    def __len__(self) -> int:
        return len(self._current())


tool_store = ToolStore()


@contextmanager
def bind_tool_store(state: dict, *, tool_tasks: set[asyncio.Task] | None = None):
    """Bind one execution's mutable state; reset safely on failure/cancellation."""
    token = _tool_context.set(state)
    tasks_token = _tool_tasks.set(tool_tasks)
    try:
        yield state
    finally:
        _tool_context.reset(token)
        _tool_tasks.reset(tasks_token)


# Keys we track for persistence and state_update SSE events
STATE_KEYS: list[str] = [
    "teacher_id",
    "extraction_coverage",
    "onet_evidence",
    "sources",
    "evidence_sources",
    "onet_release",
    "selected_onet_occupations",
    "onet_selection_confirmed",
    "run_id",
    "candidate_revision",
    "source_outcomes",
    "selection_revision",
    "publication_revision",
    "selected_candidate_ids",
    "excluded_candidate_ids",
    "selection_confirmation",
    "review_stage",
    "skill_review_change_id",
    "course_id",
    "course_title",
    "course_description",
    "job_search_country",
    "job_search_country_confirmed",
    "job_search_location",
    "fetched_jobs",
    "job_groups",
    "selected_jobs",
    "extracted_skills",
    "total_jobs_for_extraction",
    "existing_graph_skills",
    "existing_concepts",
    "curated_skills",
    "curriculum_mapping",
    "mapped_skills",
    "final_skills",
    "selected_for_insertion",
    "skill_concepts",
    "_cleaned_results",
    "insertion_results",
    "skill_job_urls",
    "_raw_skill_urls",
]


def _skill_name_key(name: str) -> str:
    return name.strip().casefold()


def mapping_breakdown() -> dict[str, int | bool]:
    """Summarize how curated skills flow through curriculum mapping."""
    curated = tool_store.get("curated_skills") or []
    mapping = tool_store.get("curriculum_mapping") or []

    curated_names = {
        str(item.get("candidate_id", ""))
        if tool_store.get("run_id")
        else _skill_name_key(str(item.get("name", "")))
        for item in curated
        if isinstance(item, dict) and item.get("name")
    }
    mapping_names_list = [
        str(item.get("candidate_id", ""))
        if tool_store.get("run_id")
        else _skill_name_key(str(item.get("name", "")))
        for item in mapping
        if isinstance(item, dict) and item.get("name")
    ]
    mapping_names = {name for name in mapping_names_list if name}

    counts = {"covered": 0, "gap": 0, "new_topic_needed": 0}
    for item in mapping:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "")).strip().lower()
        if status in counts:
            counts[status] += 1

    curated_total = len(curated_names) if curated_names else len(curated)
    missing = len(curated_names - mapping_names) if curated_names else 0
    unexpected = len(mapping_names - curated_names) if curated_names else 0
    duplicates = max(len(mapping_names_list) - len(mapping_names), 0)

    return {
        "curated_total": curated_total,
        "mapping_rows": len(mapping),
        "mapped_name_count": len(mapping_names),
        "covered": counts["covered"],
        "gap": counts["gap"],
        "new_topic_needed": counts["new_topic_needed"],
        "mapped_for_insertion": counts["gap"] + counts["new_topic_needed"],
        "missing": missing,
        "unexpected": unexpected,
        "duplicates": duplicates,
        "is_complete": bool(curated_total)
        and missing == 0
        and unexpected == 0
        and duplicates == 0
        and len(mapping) == curated_total,
    }


def snapshot_state(state: dict | None = None) -> dict[str, Any]:
    """Take a JSON-serializable snapshot of all tracked tool_store keys."""
    result: dict[str, Any] = {}
    for key in STATE_KEYS:
        val = (tool_store if state is None else state).get(key)
        if val is None:
            result[key] = None
        elif isinstance(val, (list, dict, str, int, float, bool)):
            result[key] = deepcopy(val)
        else:
            result[key] = str(val)
    return result


def restore_state(state_json: dict[str, Any]) -> None:
    """Overwrite tool_store from a previously persisted snapshot."""
    tool_store.clear()
    for key in STATE_KEYS:
        if key in state_json and state_json[key] is not None:
            tool_store[key] = deepcopy(state_json[key])


def pipeline_summary() -> str:
    """Build a concise summary of current pipeline progress from tool_store.

    Returned text is injected into the system prompt so every agent knows
    where the pipeline stands without needing to call show_current_state.
    """
    parts: list[str] = []

    course_id = tool_store.get("course_id")
    course_title = tool_store.get("course_title")
    job_search_country = tool_store.get("job_search_country")
    job_search_country_confirmed = bool(tool_store.get("job_search_country_confirmed"))
    fetched = tool_store.get("fetched_jobs")
    groups = tool_store.get("job_groups")
    selected = tool_store.get("selected_jobs")
    extracted = tool_store.get("extracted_skills")
    curated = tool_store.get("curated_skills")
    mapping = tool_store.get("curriculum_mapping")
    mapped = tool_store.get("mapped_skills")
    final = tool_store.get("final_skills")
    approved = tool_store.get("selected_for_insertion")
    concepts = tool_store.get("skill_concepts")
    inserted = tool_store.get("insertion_results")
    breakdown = mapping_breakdown()

    if course_id:
        if course_title:
            parts.append(f"Course {course_id}: {course_title}")
        else:
            parts.append(f"Course {course_id}")

    if job_search_country:
        country_status = (
            "confirmed" if job_search_country_confirmed else "not confirmed"
        )
        parts.append(f"Job market country: {job_search_country} ({country_status})")

    if tool_store.get("run_id"):
        parts.append(
            f"Teacher review: {tool_store.get('review_stage') or 'draft'}; "
            f"{len(tool_store.get('selected_candidate_ids') or [])} selected, "
            f"{len(tool_store.get('excluded_candidate_ids') or [])} explicitly excluded"
        )

    if inserted:
        parts.append(f"Pipeline COMPLETE. Insertion results: {inserted}")
        return " | ".join(parts)

    if fetched:
        parts.append(f"Fetched {len(fetched)} jobs in {len(groups or {})} groups")
    if selected:
        parts.append(f"Selected {len(selected)} jobs for analysis")
    if extracted:
        parts.append(f"Extracted {len(extracted)} skills")
    if curated:
        parts.append(f"Teacher curated {breakdown['curated_total']} skills")
    if mapping:
        parts.append(
            "Curriculum mapping: "
            f"{breakdown['covered']} covered, "
            f"{breakdown['gap']} gaps, "
            f"{breakdown['new_topic_needed']} new topics"
        )
        if breakdown["curated_total"]:
            parts.append(
                "Mapping coverage: "
                f"{breakdown['mapped_name_count']}/{breakdown['curated_total']} curated skills accounted for"
            )
    if mapped:
        total_mapped = sum(len(skills) for skills in mapped.values())
        parts.append(f"Mapped {total_mapped} skills to {len(mapped)} chapters")
    if final:
        parts.append(f"Cleaned to {len(final)} final skills")
    if approved:
        parts.append(f"Teacher approved {len(approved)} skills for insertion")
    if concepts:
        parts.append(f"Concept linking done for {len(concepts)} skills")

    if not parts:
        parts.append("Pipeline not started yet — no jobs fetched")

    # Determine next step from the furthest completed stage.
    if concepts and not inserted:
        parts.append("NEXT: Update Knowledge Map")
    elif final and not concepts:
        parts.append("NEXT: Link concepts for final skills")
    elif mapping or curated:
        if not mapping or not breakdown["is_complete"]:
            parts.append("NEXT: Map curated skills to curriculum")
        elif not final:
            parts.append("NEXT: Clean skills (remove redundant vs book skills)")
    elif extracted and not curated:
        parts.append("NEXT: Teacher picks skills from extracted list")
    elif selected and not extracted:
        parts.append("NEXT: Extract skills from selected jobs")
    elif fetched and not selected:
        parts.append("NEXT: Ask teacher which job groups to select")
    else:
        parts.append("NEXT: Fetch jobs")

    return " | ".join(parts)


class AgentState(TypedDict):
    """State for the Market Demand Agent conversation."""

    messages: Annotated[list, add_messages]
    course_id: int
    job_search_country: str
    job_search_country_confirmed: bool
    job_search_location: str
    fetched_jobs: list[dict]
    selected_jobs: list[dict]
    extracted_skills: list[dict]
    existing_graph_skills: list[dict]
    existing_graph_concepts: list[str]
    curriculum_mapping: list[dict]
    selected_skills_for_insertion: list[dict]
    course_title: str
    course_description: str
