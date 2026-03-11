from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

# Module-level store shared between tools — persisted to DB per thread
tool_store: dict = {}

# Keys we track for persistence and state_update SSE events
STATE_KEYS: list[str] = [
    "fetched_jobs",
    "job_groups",
    "selected_jobs",
    "extracted_skills",
    "total_jobs_for_extraction",
    "existing_graph_skills",
    "existing_concepts",
    "curriculum_mapping",
    "selected_for_insertion",
    "skill_concepts",
    "insertion_results",
]


def snapshot_state() -> dict[str, Any]:
    """Take a JSON-serializable snapshot of all tracked tool_store keys."""
    result: dict[str, Any] = {}
    for key in STATE_KEYS:
        val = tool_store.get(key)
        if val is None:
            result[key] = None
        elif isinstance(val, (list, dict, str, int, float, bool)):
            result[key] = val
        else:
            result[key] = str(val)
    return result


def restore_state(state_json: dict[str, Any]) -> None:
    """Overwrite tool_store from a previously persisted snapshot."""
    tool_store.clear()
    for key in STATE_KEYS:
        if key in state_json and state_json[key] is not None:
            tool_store[key] = state_json[key]


def pipeline_summary() -> str:
    """Build a concise summary of current pipeline progress from tool_store.

    Returned text is injected into the system prompt so every agent knows
    where the pipeline stands without needing to call show_current_state.
    """
    parts: list[str] = []

    fetched = tool_store.get("fetched_jobs")
    groups = tool_store.get("job_groups")
    selected = tool_store.get("selected_jobs")
    extracted = tool_store.get("extracted_skills")
    mapping = tool_store.get("curriculum_mapping")
    approved = tool_store.get("selected_for_insertion")
    concepts = tool_store.get("skill_concepts")
    inserted = tool_store.get("insertion_results")

    if inserted:
        parts.append(f"Pipeline COMPLETE. Insertion results: {inserted}")
        return " | ".join(parts)

    if fetched:
        parts.append(f"Fetched {len(fetched)} jobs in {len(groups or {})} groups")
    if selected:
        parts.append(f"Selected {len(selected)} jobs for analysis")
    if extracted:
        parts.append(f"Extracted {len(extracted)} skills")
    if mapping:
        covered = sum(1 for m in mapping if m.get("status") == "covered")
        gap = sum(1 for m in mapping if m.get("status") == "gap")
        new_t = sum(1 for m in mapping if m.get("status") == "new_topic_needed")
        parts.append(
            f"Curriculum mapping: {covered} covered, {gap} gaps, {new_t} new topics"
        )
    if approved:
        parts.append(f"Teacher approved {len(approved)} skills for insertion")
    if concepts:
        parts.append(f"Concept linking done for {len(concepts)} skills")

    if not parts:
        parts.append("Pipeline not started yet — no jobs fetched")

    # Determine next step
    if not fetched:
        parts.append("NEXT: Fetch jobs")
    elif not selected:
        parts.append("NEXT: Ask teacher which job groups to select")
    elif not extracted:
        parts.append("NEXT: Extract skills from selected jobs")
    elif not mapping:
        parts.append("NEXT: Map skills to curriculum")
    elif not approved:
        parts.append("NEXT: Present mapping and get teacher approval")
    elif not concepts:
        parts.append("NEXT: Link concepts for approved skills")
    elif not inserted:
        parts.append("NEXT: Insert to Neo4j")

    return " | ".join(parts)


class AgentState(TypedDict):
    """State for the Market Demand Agent conversation."""

    messages: Annotated[list, add_messages]
    fetched_jobs: list[dict]
    selected_jobs: list[dict]
    extracted_skills: list[dict]
    existing_graph_skills: list[dict]
    existing_graph_concepts: list[str]
    curriculum_mapping: list[dict]
    selected_skills_for_insertion: list[dict]
    course_title: str
    course_description: str
