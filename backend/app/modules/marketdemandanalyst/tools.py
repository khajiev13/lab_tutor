import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from copy import deepcopy
from typing import Annotated
from uuid import UUID, uuid4

import pandas as pd
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import InjectedToolArg
from langgraph.types import Command

from app.core.database import SessionLocal

from .countries import DEFAULT_JOB_SEARCH_COUNTRY, normalize_job_search_country
from .extractor import _get_extraction_llm
from .job_groups import group_jobs_by_title
from .service import get_market_source_service
from .state import mapping_breakdown, owned_sync_execution, tool_store

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
#  Neo4j connection helper (cached driver)
# ═══════════════════════════════════════════════════════════════════

_neo4j_driver_cache = None


def _get_neo4j_driver(*, force_new: bool = False):
    """Get or create a cached Neo4j driver."""
    global _neo4j_driver_cache
    if _neo4j_driver_cache is not None and not force_new:
        return _neo4j_driver_cache
    from neo4j import GraphDatabase

    uri = os.environ.get("LAB_TUTOR_NEO4J_URI") or os.environ.get(
        "NEO4J_URI", "bolt://localhost:7687"
    )
    user = os.environ.get("LAB_TUTOR_NEO4J_USERNAME") or os.environ.get(
        "NEO4J_USERNAME", "neo4j"
    )
    password = os.environ.get("LAB_TUTOR_NEO4J_PASSWORD") or os.environ.get(
        "NEO4J_PASSWORD", ""
    )
    _neo4j_driver_cache = GraphDatabase.driver(
        uri,
        auth=(user, password),
        max_connection_lifetime=5 * 60,  # rotate connections before Aura idles them
    )
    return _neo4j_driver_cache


@contextmanager
def _neo4j_session():
    """Yield a Neo4j session. Clears stale driver on SessionExpired so next call reconnects."""
    from neo4j.exceptions import SessionExpired

    database = os.environ.get("LAB_TUTOR_NEO4J_DATABASE") or os.environ.get(
        "NEO4J_DATABASE", "neo4j"
    )
    driver = _get_neo4j_driver()
    try:
        with driver.session(database=database) as session:
            yield session
    except SessionExpired:
        # Clear cached driver so the next call gets a fresh connection
        _get_neo4j_driver(force_new=True)
        raise


# ═══════════════════════════════════════════════════════════════════
#  Curriculum context loader — pre-loads course info for system prompt
# ═══════════════════════════════════════════════════════════════════


def load_curriculum_context(teacher_email: str | None = None) -> str:
    """Fetch course + chapter summaries for a given teacher from Neo4j.

    If teacher_email is None, defaults to the first teacher in the DB.
    Returns a compact text block suitable for embedding in a system prompt.

    TODO: Reimplement once transcript-based chapters are stored in Neo4j.
    Previous implementation traversed CLASS → BOOK → BOOK_CHAPTER, which
    assumed chapters came from books. Now chapters are built from categorized
    transcripts, so the graph traversal path will change (e.g. CLASS → CHAPTER
    or CLASS → TRANSCRIPT_COLLECTION → CHAPTER). The output format should
    remain the same: teacher name, course title, and per-chapter summaries
    with their skills.
    """
    # Chapters are now built from transcripts, not books.
    # This function needs to be reimplemented once the transcript-based
    # chapter graph schema is finalized.
    return "(Curriculum context not yet available — transcript-based chapters pending)"


def _require_course_context() -> dict[str, int | str]:
    """Return the active course context stored for this thread."""
    course_id = tool_store.get("course_id")
    if not isinstance(course_id, int):
        raise ValueError("No course_id set. Cannot proceed without course context.")

    return {
        "course_id": course_id,
        "course_title": str(tool_store.get("course_title") or ""),
        "course_description": str(tool_store.get("course_description") or ""),
    }


def _require_course_id() -> int:
    return int(_require_course_context()["course_id"])


def _parse_string_list(raw_value: str) -> list[str]:
    """Parse JSON arrays first, then newline-delimited or comma-delimited text."""
    raw = raw_value.strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]

    if "\n" in raw:
        return [
            line.strip().lstrip("-").strip()
            for line in raw.splitlines()
            if line.strip()
        ]

    return [item.strip() for item in raw.split(",") if item.strip()]


def _clear_tool_store_keys(*keys: str) -> None:
    for key in keys:
        tool_store.pop(key, None)


def _build_mapped_skills(mapping: list[dict]) -> dict[str, list[str]]:
    mapped: dict[str, list[str]] = {}
    for item in mapping:
        if item.get("status") not in {"gap", "new_topic_needed"}:
            continue
        chapter = str(item.get("target_chapter") or "unassigned")
        mapped.setdefault(chapter, []).append(str(item["name"]))
    return mapped


def _missing_mapping_chapter(row: dict) -> bool:
    return row.get("status") in {"gap", "new_topic_needed"} and str(
        row.get("target_chapter") or ""
    ).strip().casefold() in {"", "unassigned", "(unassigned)"}


def _fetch_existing_chapter_skill_rows(
    session,
    *,
    course_id: int,
    chapter_titles: list[str],
) -> list[dict]:
    result = session.run(
        "UNWIND $titles AS title "
        "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER) "
        "WHERE ch.title = title "
        "RETURN ch.title AS chapter, "
        "  COLLECT { "
        "    MATCH (ch)<-[:MAPPED_TO]-(sk:BOOK_SKILL) "
        "    RETURN sk { .id, .name, .description, skill_type: 'book', origin: 'book', graph_target_id: toString(sk.id), "
        "      concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] "
        "    } AS skill "
        "    ORDER BY sk.name "
        "  } AS book_skills, "
        "  COLLECT { "
        "    MATCH (ch)<-[:MAPPED_TO]-(sk) WHERE sk:MARKET_SKILL OR sk:CAREER_SKILL "
        "    RETURN sk { .id, .name, .description, skill_type: 'market', origin: coalesce(sk.origin, 'market_demand'), graph_target_id: coalesce(toString(sk.id), sk.evidence_target_id, sk.name), "
        "      concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] "
        "    } AS skill "
        "    ORDER BY sk.name "
        "  } AS market_skills "
        "ORDER BY chapter",
        {"course_id": course_id, "titles": chapter_titles},
    )
    rows = [dict(record) for record in result]
    for row in rows:
        combined = row.get("book_skills", []) + row.get("market_skills", [])
        row["skills"] = sorted(
            combined,
            key=lambda skill: (skill.get("skill_type", ""), skill.get("name", "")),
        )
    return rows


# ═══════════════════════════════════════════════════════════════════
#  Coordinator Tools
# ═══════════════════════════════════════════════════════════════════


@tool
def set_job_search_country(country: str) -> str:
    """Set the teacher-confirmed country for job crawling before fetching jobs."""
    selected_country = normalize_job_search_country(country)
    if tool_store.get("run_id"):
        try:
            configured = get_market_source_service().configure_country(
                dict(tool_store), selected_country.key
            )
        except (ValueError, LookupError) as exc:
            return (
                f"Country was not changed: {exc}. "
                "Explain this blocker to the teacher; do not retry the same country change or fetch jobs."
            )
        tool_store.update(configured)
        return f"Job search country set to {selected_country.label}."
    existing_jobs = tool_store.get("fetched_jobs")
    existing_country = str(tool_store.get("job_search_country", "")).strip()

    if existing_jobs and existing_country != selected_country.key:
        return (
            "Jobs have already been fetched for "
            f"{existing_country or 'the current country'}. "
            "Clear the conversation before changing the job market country."
        )

    tool_store["job_search_country"] = selected_country.key
    tool_store["job_search_location"] = selected_country.location
    tool_store["job_search_country_confirmed"] = True
    return f"Job search country set to {selected_country.label}."


@tool
def fetch_jobs(
    search_terms: str,
    country: str = "",
    results_per_site: int = 15,
    location: str = "",
) -> str:
    """Fetch real job postings from configured Indeed, LinkedIn, and HeadHunter sources.
    search_terms: comma-separated queries (e.g. "Bioinformatics Researcher, Lab Technician").
    Scrapes all terms, deduplicates by title+company.
    country: target market country; if blank, uses the country configured for this course.
    location: deprecated fallback interpreted as country for old clients/agent calls.
    IMPORTANT: Always use ONE call with all search terms. Never call this tool multiple times."""

    explicit_country = country.strip() or location.strip()
    if tool_store.get("run_id") and "jobs" not in tool_store.get(
        "evidence_sources", ["jobs"]
    ):
        return _fetch_selected_sources(search_terms, explicit_country, results_per_site)
    if not explicit_country and not tool_store.get("job_search_country_confirmed"):
        return (
            "Select a job market country before fetching jobs. "
            "Ask the teacher to choose a country, then call set_job_search_country."
        )

    if tool_store.get("run_id"):
        return _fetch_selected_sources(search_terms, explicit_country, results_per_site)

    from jobspy import scrape_jobs

    raw_country = (
        explicit_country
        or str(tool_store.get("job_search_country", "")).strip()
        or str(tool_store.get("job_search_location", "")).strip()
        or DEFAULT_JOB_SEARCH_COUNTRY
    )
    selected_country = normalize_job_search_country(raw_country)
    effective_location = selected_country.location
    tool_store["job_search_country"] = selected_country.jobspy_country
    tool_store["job_search_location"] = effective_location
    if explicit_country:
        tool_store["job_search_country_confirmed"] = True

    terms = [t.strip() for t in search_terms.split(",") if t.strip()]
    sites = ["indeed", "linkedin"]
    all_results: list[pd.DataFrame] = []
    errors: list[str] = []

    def _scrape_one(term: str, site: str) -> pd.DataFrame | None:
        df = scrape_jobs(
            site_name=[site],
            search_term=term,
            location=effective_location,
            results_wanted=results_per_site,
            hours_old=72,
            country_indeed=selected_country.jobspy_country,
            description_format="markdown",
            linkedin_fetch_description=(site == "linkedin"),
            verbose=0,
        )
        if len(df) > 0:
            df["_search_term"] = term
            return df
        return None

    tasks = [(term, site) for term in terms for site in sites]
    t_scrape = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as pool:
        futures = {
            pool.submit(_scrape_one, term, site): f"{site}/{term}"
            for term, site in tasks
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                df = future.result()
                if df is not None:
                    all_results.append(df)
            except Exception as e:
                errors.append(f"{label}: {type(e).__name__}: {e}")
    logger.info(
        "[PERF] fetch_jobs: scraped %d tasks in %.1fms (parallel, %d results, %d errors)",
        len(tasks),
        (time.perf_counter() - t_scrape) * 1000,
        len(all_results),
        len(errors),
    )

    if not all_results:
        msg = "No jobs found."
        if errors:
            msg += " Errors: " + "; ".join(errors)
        return msg

    combined = pd.concat(all_results, ignore_index=True)

    # Deduplicate by title+company (case-insensitive)
    seen: set[str] = set()
    jobs_list = []
    for _, row in combined.iterrows():
        desc = str(row.get("description", ""))
        if not desc or desc == "None" or len(desc) < 50:
            continue
        title = str(row.get("title", "N/A"))
        company = str(row.get("company_name") or row.get("company", "N/A"))
        dedup_key = f"{title.lower().strip()}|{company.lower().strip()}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        jobs_list.append(
            {
                "title": title,
                "company": company,
                "description": desc[:4000],
                "url": str(row.get("job_url", "")),
                "site": str(row.get("site", "")),
                "search_term": str(row["_search_term"]),
                "country": selected_country.jobspy_country,
                "location": str(row.get("location", "")),
            }
        )

    if not jobs_list:
        return "Scraped jobs but none had usable descriptions."

    # Store raw jobs and track which search term found each one
    tool_store["fetched_jobs"] = jobs_list

    groups = group_jobs_by_title(jobs_list)
    sorted_groups = list(groups.items())
    tool_store["job_groups"] = groups

    # Build grouped summary (this is all the LLM sees)
    lines = [f"Fetched {len(jobs_list)} unique jobs in {len(groups)} role groups:"]
    shown = sorted_groups[:10]
    for num, (cat, idxs) in enumerate(shown, 1):
        companies = list(dict.fromkeys(jobs_list[i]["company"] for i in idxs))[:4]
        lines.append(
            f"  [{num}] {cat} ({len(idxs)} jobs) — e.g. {', '.join(companies)}"
        )
    if len(sorted_groups) > 10:
        rest_count = sum(len(idxs) for _, idxs in sorted_groups[10:])
        lines.append(
            f"  ... and {len(sorted_groups) - 10} more groups ({rest_count} jobs)"
        )
    if errors:
        lines.append(f"Warnings: {'; '.join(errors)}")
    lines.append(
        "\nAsk the teacher which groups to keep, then transfer to Job Selector."
    )
    return "\n".join(lines)


def _fetch_selected_sources(search_terms: str, explicit_country: str, cap: int) -> str:
    service = get_market_source_service()
    try:
        config = service.load_config(dict(tool_store))
        if (
            explicit_country
            and normalize_job_search_country(explicit_country).key != config["country"]
        ):
            return "Start a new analysis to change the configured market."
        result = service.collect_sources(
            config,
            [term.strip() for term in search_terms.split(",") if term.strip()],
            results_per_source=cap,
        )
    except (ValueError, LookupError) as exc:
        return str(exc)
    jobs = result["jobs"]
    tool_store["fetched_jobs"] = jobs
    tool_store["selected_jobs"] = []
    tool_store["source_outcomes"] = result["source_outcomes"]
    tool_store["candidate_revision"] = result["candidate_revision"]
    tool_store["onet_evidence"] = result["onet_evidence"]
    if result["candidates"]:
        tool_store["extracted_skills"] = [
            {**c, "name": c["display_name"], "category": c["category_id"]}
            for c in result["candidates"]
        ]
    tool_store["job_groups"] = group_jobs_by_title(jobs)
    statuses = "; ".join(
        f"{source}: {outcome['status']} ({outcome['received_count']} received, {outcome['usable_count']} usable)"
        for source, outcome in result["source_outcomes"].items()
    )
    lines = [
        f"Selected evidence sources: {statuses}",
        f"Fetched {len(jobs)} extraction-eligible jobs.",
    ]
    lines.extend(
        f"[{i}] {name} ({len(indices)} jobs)"
        for i, (name, indices) in enumerate(tool_store["job_groups"].items(), 1)
    )
    if any(
        o["status"] in {"partial", "error"} for o in result["source_outcomes"].values()
    ):
        lines.append(
            "Some providers returned incomplete or unavailable evidence. Continue with the available job groups; disclose omissions with the skill selection. Supporting postings remain required for publication."
        )
    if "jobs" not in config["evidence_sources"]:
        lines.append(
            "O*NET draft references need supporting job postings. Start a new analysis with explicitly selected job providers to collect support."
        )
    elif jobs:
        lines.append(
            "Ask the teacher which job groups to select before extracting vacancies."
        )
    return "\n".join(lines)


@tool
def save_skills_for_insertion(skills_json: str) -> str:
    """Save a list of skills the teacher approved for future insertion into the knowledge graph.
    Input: JSON string like [{"name": "...", "category": "...", "target_chapter": "...", "rationale": "..."}]
    These are NOT inserted yet — only stored for review."""
    try:
        skills = json.loads(skills_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}. Please provide a valid JSON array."

    tool_store["selected_for_insertion"] = skills
    names = [s["name"] for s in skills]
    return f"Saved {len(skills)} skills for future insertion: {', '.join(names)}"


@tool
def show_current_state() -> str:
    """Check live chapter readiness and summarize collected and mapped skills."""
    breakdown = mapping_breakdown()
    chapter_error = mapping_prerequisite_error()
    lines = [
        "Live chapter readiness: "
        + (
            chapter_error
            or "ready — saved course chapters exist. Continue to Curriculum Mapper for confirmed skills."
        ),
        f"All fetched jobs: {len(tool_store.get('fetched_jobs', []))}",
        f"Selected jobs: {len(tool_store.get('selected_jobs', []))}",
        f"Extracted skills: {len(tool_store.get('extracted_skills', []))}",
        f"Curated skills: {breakdown['curated_total']}",
        f"Curriculum mapping rows: {breakdown['mapping_rows']}",
        "Mapping breakdown: "
        f"{breakdown['covered']} covered, "
        f"{breakdown['gap']} gaps, "
        f"{breakdown['new_topic_needed']} new topics, "
        f"{breakdown['missing']} skills awaiting mapping",
        f"Mapped skills: {sum(len(v) for v in tool_store.get('mapped_skills', {}).values())}",
        f"Final (cleaned) skills: {len(tool_store.get('final_skills', []))}",
        f"Saved for insertion: {len(tool_store.get('selected_for_insertion', []))}",
    ]
    return " | ".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Job Selector Tools
# ═══════════════════════════════════════════════════════════════════


@tool
def select_jobs_by_group(group_names: str) -> str:
    """Select entire groups from the fetched jobs.
    Prefer a JSON array string of exact group names, especially names containing commas.
    Pass supplied JSON names unchanged; do not replace them with group numbers.
    Also accepts legacy comma-separated names/numbers or "all" intents.
    Examples: '["Engineer, Platform", "Data Engineer"]', "1, 2, 5", or "all".
    """
    groups = tool_store.get("job_groups", {})
    jobs = tool_store.get("fetched_jobs", [])
    if not groups:
        return "No job groups found. The coordinator needs to fetch jobs first."

    group_list = list(groups.items())
    try:
        is_json_list = isinstance(json.loads(group_names), list)
    except json.JSONDecodeError:
        is_json_list = False
    requested = (
        _parse_string_list(group_names)
        if is_json_list
        else [g.strip() for g in group_names.split(",") if g.strip()]
    )

    normalized_requested = {req.casefold() for req in requested}
    if normalized_requested & {"all", "all groups", "every group", "everything", "*"}:
        all_indices: set[int] = set()
        matched_groups = []
        for cat, idxs in group_list:
            all_indices.update(idxs)
            matched_groups.append(f"{cat} ({len(idxs)})")

        selected = [jobs[i] for i in sorted(all_indices)]
        tool_store["selected_jobs"] = selected

        lines = [
            f"Selected {len(selected)} jobs from all {len(matched_groups)} groups:"
        ]
        for group in matched_groups:
            lines.append(f"  ✓ {group}")
        lines.append("\nSelection complete. Transfer back to Coordinator.")
        return "\n".join(lines)

    selected_indices: set[int] = set()
    matched_groups: list[str] = []

    for req in requested:
        normalized_req = req.casefold()

        # Try as number first
        if req.isdigit():
            idx = int(req) - 1
            if 0 <= idx < len(group_list):
                cat, idxs = group_list[idx]
                selected_indices.update(idxs)
                matched_groups.append(f"{cat} ({len(idxs)})")
            continue

        # Prefer exact name matches before substring matches.
        exact_match = next(
            (
                (cat, idxs)
                for cat, idxs in group_list
                if normalized_req == cat.casefold()
            ),
            None,
        )
        if exact_match:
            cat, idxs = exact_match
            selected_indices.update(idxs)
            matched_groups.append(f"{cat} ({len(idxs)})")
            continue

        # Try as substring match on group name
        for cat, idxs in group_list:
            if normalized_req in cat.casefold():
                selected_indices.update(idxs)
                matched_groups.append(f"{cat} ({len(idxs)})")
                break

    if not selected_indices:
        available = ", ".join(
            f"[{i + 1}] {cat}" for i, (cat, _) in enumerate(group_list)
        )
        return f'No groups matched "{group_names}". Available groups: {available}'

    selected = [jobs[i] for i in sorted(selected_indices)]
    tool_store["selected_jobs"] = selected

    lines = [f"Selected {len(selected)} jobs from {len(matched_groups)} groups:"]
    for g in matched_groups:
        lines.append(f"  ✓ {g}")
    lines.append("\nSelection complete. Transfer back to Coordinator.")
    return "\n".join(lines)


@tool
def start_extraction(
    runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None,
) -> Command | str | ToolMessage:
    """Start parallel skill extraction from selected job groups.
    Fans out one LLM call per job, merges duplicates, then returns
    control back to Skill Finder for teacher skill selection.
    Call start_extraction alone after any other tool results."""
    # Guard: if extraction already ran, do NOT re-run.
    existing = tool_store.get("extracted_skills", [])
    if existing and not tool_store.get("run_id"):
        count = len(existing)
        return (
            f"⚠️ Extraction already complete: {count} merged skills are ready. "
            "Call get_skills_by_category to review them. "
            "Do NOT call select_jobs_by_group or start_extraction again."
        )
    if tool_store.get("run_id"):
        try:
            service = get_market_source_service()
            if service.extraction_is_complete(
                dict(tool_store), tool_store.get("selected_jobs", [])
            ):
                return (
                    "The selected posting sample is already assessed. "
                    "Call get_skills_by_category for read-only teacher review. "
                    "Fixed O*NET association bounds cannot improve by repeating extraction. "
                    "Present current skills and evidence notes for the teacher's Confirm Selection action."
                )
        except (ValueError, LookupError) as exc:
            return str(exc)
    if runtime is not None and runtime.tool_call_id:
        current_request = next(
            (
                message
                for message in reversed(runtime.state.get("messages", []))
                if isinstance(message, AIMessage)
                and any(
                    call["id"] == runtime.tool_call_id for call in message.tool_calls
                )
            ),
            None,
        )
        if current_request is not None and len(current_request.tool_calls) > 1:
            return ToolMessage(
                content="Call start_extraction alone after any other tool results. This extraction handoff has not started.",
                name="start_extraction",
                tool_call_id=runtime.tool_call_id,
                status="error",
            )
    update = {"active_agent": "skill_finder"}
    if runtime is not None:
        update["messages"] = list(runtime.state.get("messages", []))
    jobs = tool_store.get("selected_jobs", [])
    if not jobs:
        if runtime is not None and runtime.tool_call_id:
            update["messages"].append(
                ToolMessage(
                    content="No jobs selected. Ask the teacher to select a job group.",
                    name="start_extraction",
                    tool_call_id=runtime.tool_call_id,
                )
            )
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update=update,
        )
    logger.info("start_extraction: routing to skill_extractor (%d jobs)", len(jobs))
    return Command(
        goto="skill_extractor",
        graph=Command.PARENT,
        # Keep active_agent as skill_finder — skill_extractor is a temporary
        # subgraph detour, not a real swarm agent. This ensures the checkpoint
        # never stores "skill_extractor" as active_agent, preventing KeyError
        # on __start__ routing when a new message arrives mid-extraction.
        update=update,
    )


# ═══════════════════════════════════════════════════════════════════
#  Curriculum Mapper Tools (hierarchical graph exploration)
# ═══════════════════════════════════════════════════════════════════


@tool
def list_chapters() -> str:
    """List all course chapters in the curriculum knowledge graph.
    Returns chapter titles and existing MARKET_SKILL counts.
    Call this first to get an overview of the course structure.

    Queries COURSE_CHAPTER nodes linked to CLASS via HAS_CHAPTER.
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER) "
                "RETURN ch.title AS title, ch.chapter_index AS idx, "
                "  [(ch)-[:INCLUDES_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT) | d.topic] AS doc_topics, "
                "  COLLECT { "
                "    MATCH (ch)-[:INCLUDES_DOCUMENT]->(:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c:CONCEPT) "
                "    RETURN DISTINCT c.name AS concept "
                "    ORDER BY concept "
                "  } AS concepts, "
                "  COLLECT { "
                "    MATCH (ch)<-[:MAPPED_TO]-(ms:MARKET_SKILL) "
                "    RETURN DISTINCT ms.name AS skill "
                "    ORDER BY skill "
                "  } AS market_skills "
                "ORDER BY ch.chapter_index",
                {"course_id": course_id},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError):
        logger.info(
            "[PERF] list_chapters FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map unavailable. Please try again in a moment."
    except AuthError:
        return "Knowledge Map connection failed. Check credentials."

    logger.info(
        "[PERF] list_chapters took %.1fms (%d chapters)",
        (time.perf_counter() - t0) * 1000,
        len(rows),
    )

    if not rows:
        return (
            "No course chapters found in the knowledge graph for this course. "
            "Return to Supervisor: the teacher needs to complete Build Chapters in "
            "the course setup before curriculum mapping can continue. "
            "Keep the confirmed skills. Do not invent chapter assignments or "
            "hand off an unassigned mapping to Skill Cleaner."
        )

    lines = [f"Course has {len(rows)} chapters:"]
    for r in rows:
        idx = r.get("idx", "?")
        title = r.get("title", "Untitled")
        ms = r.get("market_skills", [])
        docs = r.get("doc_topics", [])
        concepts = r.get("concepts", [])
        lines.append(f"\n  [{idx}] {title}")
        lines.append(
            f"      Documents: {len(docs)} | Concepts: {len(concepts)} | Market Skills: {len(ms)}"
        )
        if docs:
            lines.append(f"      Doc topics: {', '.join(str(d) for d in docs[:5])}")
        if ms:
            lines.append(
                f"      Existing market skills: {', '.join(str(s) for s in ms[:5])}"
            )
    return "\n".join(lines)


def mapping_prerequisite_error() -> str | None:
    """Check current course chapters without modifying the confirmed shortlist."""
    from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

    from app.modules.curricularalignmentarchitect.curriculum_planning.repository import (
        ChapterPlanRepository,
    )

    try:
        course_id = _require_course_id()
        with _neo4j_session() as session:
            ready = ChapterPlanRepository(session).has_plan(course_id)
    except ValueError as exc:
        return str(exc)
    except (Neo4jError, ServiceUnavailable, SessionExpired, OSError):
        logger.warning(
            "Chapter prerequisite check unavailable for mapping", exc_info=True
        )
        return (
            "Could not check course chapters. Retry when the Knowledge Map is available. "
            "Your confirmed skills are unchanged; curriculum mapping has not started."
        )
    if ready:
        return None
    return (
        "Build Chapters in the course setup before mapping skills to the curriculum. "
        "Your confirmed skills are unchanged. After chapters are saved, retry mapping."
    )


@tool
def get_chapter_details(chapter_indices: str) -> str:
    """Get documents, concepts, and existing MARKET_SKILL nodes for specific course chapters.
    Args:
        chapter_indices: comma-separated chapter numbers (e.g. "1, 2, 4")
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    indices = [
        int(x.strip()) for x in chapter_indices.split(",") if x.strip().isdigit()
    ]
    if not indices:
        return "Please provide valid chapter numbers (e.g. '1, 2, 4')."

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER) "
                "WHERE ch.chapter_index IN $indices "
                "RETURN ch.chapter_index AS ch_idx, ch.title AS ch_title, "
                "  [(ch)-[:INCLUDES_DOCUMENT]->(d:TEACHER_UPLOADED_DOCUMENT) | "
                "    d { .topic, .title } "
                "  ] AS documents, "
                "  COLLECT { "
                "    MATCH (ch)-[:INCLUDES_DOCUMENT]->(:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c:CONCEPT) "
                "    RETURN DISTINCT c.name AS concept "
                "    ORDER BY concept "
                "  } AS concepts, "
                "  COLLECT { "
                "    MATCH (ch)<-[:MAPPED_TO]-(ms:MARKET_SKILL) "
                "    RETURN ms { .name, .status, .demand_pct, .category, "
                "      concepts: [(ms)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c.name] "
                "    } AS market_skill "
                "    ORDER BY ms.name "
                "  } AS market_skills "
                "ORDER BY ch.chapter_index",
                {"course_id": course_id, "indices": indices},
            )
            chapters = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError):
        logger.info(
            "[PERF] get_chapter_details Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map unavailable. Please try again in a moment."
    except AuthError:
        return "Knowledge Map connection failed. Check the graph service credentials."
    logger.info(
        "[PERF] get_chapter_details Neo4j took %.1fms (%d chapters)",
        (time.perf_counter() - t0) * 1000,
        len(chapters),
    )

    lines = []
    for ch in chapters:
        idx = ch["ch_idx"]
        title = ch["ch_title"]
        lines.append(f"\n{'=' * 60}")
        lines.append(f"[{idx}] {title}")
        lines.append(f"{'=' * 60}")

        docs = ch.get("documents", [])
        if docs:
            lines.append("  Documents:")
            for d in docs:
                lines.append(f"    • {d.get('topic', d.get('title', 'Untitled'))}")

        concepts = ch.get("concepts", [])
        if concepts:
            lines.append(f"  Concepts ({len(concepts)}):")
            for c in concepts[:10]:
                lines.append(f"    • {c}")
            if len(concepts) > 10:
                lines.append(f"    ... and {len(concepts) - 10} more")

        mks = ch.get("market_skills", [])
        if mks:
            lines.append("  Market Skills (already in graph):")
            for ms in mks:
                demand = ms.get("demand_pct", "?")
                status = ms.get("status", "?")
                lines.append(f"    ★ {ms['name']} [{status}] (demand: {demand}%)")

    return "\n".join(lines)


@tool
def get_section_concepts(section_refs: str) -> str:
    """Get concepts mentioned in specific sections.
    Args:
        section_refs: comma-separated section references using the numbering
            from section titles (e.g. "1.1, 2.2, 4.1")
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    refs = [r.strip() for r in section_refs.split(",") if r.strip()]
    if not refs:
        return "Please provide section references (e.g. '1.1, 2.2')."

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "UNWIND $refs AS ref "
                "MATCH (cl:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)-[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SECTION]->(s:BOOK_SECTION) "
                "WHERE s.title STARTS WITH ref "
                "RETURN s.title AS section, "
                "  [(s)-[m:MENTIONS]->(c:CONCEPT) | "
                "    { name: c.name, definition: m.definition }] AS concepts "
                "ORDER BY s.title",
                {"course_id": course_id, "refs": refs},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError):
        logger.info(
            "[PERF] get_section_concepts Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map unavailable. Please try again in a moment."
    except AuthError:
        return "Knowledge Map connection failed. Check the graph service credentials."
    logger.info(
        "[PERF] get_section_concepts Neo4j took %.1fms (%d rows)",
        (time.perf_counter() - t0) * 1000,
        len(rows),
    )

    if not rows:
        return f"No sections found matching: {section_refs}"

    lines = []
    for r in rows:
        lines.append(f"\n[{r['section']}]")
        concepts = r.get("concepts", [])
        if concepts:
            for c in concepts:
                defn = c.get("definition", "")
                if defn:
                    defn = defn[:100] + "..." if len(defn) > 100 else defn
                    lines.append(f"  • {c['name']}: {defn}")
                else:
                    lines.append(f"  • {c['name']}")
        else:
            lines.append("  (no concepts)")

    return "\n".join(lines)


@tool
def check_skills_coverage(skill_names: str) -> str:
    """Check if market-extracted skills already exist in the knowledge graph.
    Searches both BOOK_SKILL nodes and CONCEPT nodes for matches.
    Args:
        skill_names: JSON array, newline-delimited list, or comma-separated EXACT skill names as returned by get_curated_skills.
            Use the full competency statements — do NOT simplify to bare technology keywords.
            CORRECT: "Query and analyze data using SQL, Deploy containerized applications using Kubernetes"
            WRONG:   "SQL, Kubernetes"
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    names = _parse_string_list(skill_names)
    if not names:
        return "Please provide skill names to check."

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "UNWIND $names AS skill_name "
                "RETURN skill_name, "
                "  COLLECT { "
                "    MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(sk:BOOK_SKILL) "
                "    WHERE toLower(toString(sk.name)) CONTAINS toLower(skill_name) "
                "       OR toLower(skill_name) CONTAINS toLower(toString(sk.name)) "
                "    RETURN DISTINCT sk.name AS matching_skill "
                "    ORDER BY matching_skill "
                "  } AS matching_skills, "
                "  COLLECT { "
                "    MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(ms:MARKET_SKILL) "
                "    WHERE toLower(ms.name) CONTAINS toLower(skill_name) "
                "       OR toLower(skill_name) CONTAINS toLower(ms.name) "
                "    RETURN DISTINCT ms.name AS matching_market_skill "
                "    ORDER BY matching_market_skill "
                "  } AS matching_market_skills, "
                "  COLLECT { "
                "    MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)-[:INCLUDES_DOCUMENT]->(:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c:CONCEPT) "
                "    WITH c, skill_name, "
                "      CASE WHEN valueType(c.name) STARTS WITH 'STRING' "
                "           THEN c.name ELSE head(c.name) END AS cname "
                "    WHERE toLower(cname) = toLower(skill_name) "
                "    RETURN DISTINCT cname AS exact_concept "
                "    ORDER BY exact_concept "
                "  } AS exact_concepts, "
                "  COLLECT { "
                "    MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)-[:INCLUDES_DOCUMENT]->(:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c2:CONCEPT) "
                "    WITH c2, skill_name, "
                "      CASE WHEN valueType(c2.name) STARTS WITH 'STRING' "
                "           THEN c2.name ELSE head(c2.name) END AS cname "
                "    WHERE toLower(cname) CONTAINS toLower(skill_name) "
                "      AND toLower(cname) <> toLower(skill_name) "
                "    RETURN DISTINCT cname AS related_concept "
                "    ORDER BY related_concept "
                "  }[0..5] AS related_concepts",
                {"course_id": course_id, "names": names},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError):
        logger.info(
            "[PERF] check_skills_coverage Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map unavailable. Please try again in a moment."
    except AuthError:
        return "Knowledge Map connection failed. Check the graph service credentials."
    logger.info(
        "[PERF] check_skills_coverage Neo4j took %.1fms (%d skills checked)",
        (time.perf_counter() - t0) * 1000,
        len(names),
    )

    lines = [f"Coverage check for {len(names)} skills:"]
    covered = 0
    partial = 0
    new = 0

    already_in_market = 0

    for r in rows:
        name = r["skill_name"]
        skills_match = r["matching_skills"]
        market_match = r["matching_market_skills"]
        exact = r["exact_concepts"]
        related = r["related_concepts"]

        if market_match:
            already_in_market += 1
            lines.append(
                f"  ⚠ {name} — ALREADY A MARKET_SKILL "
                f"(existing: {', '.join(market_match[:3])}). Skip or merge."
            )
        elif skills_match or exact:
            covered += 1
            matches = []
            if skills_match:
                matches.append(f"book skills: {', '.join(skills_match[:3])}")
            if exact:
                matches.append(f"concepts: {', '.join(exact[:3])}")
            lines.append(f"  ✓ {name} — COVERED ({'; '.join(matches)})")
        elif related:
            partial += 1
            lines.append(f"  ~ {name} — PARTIAL (related: {', '.join(related[:3])})")
        else:
            new += 1
            lines.append(f"  ✗ {name} — NEW (no match in graph)")

    lines.append(
        f"\nSummary: {already_in_market} already market skills, "
        f"{covered} covered by curriculum, {partial} partial, {new} new"
    )
    return "\n".join(lines)


@tool
def get_extracted_skills() -> str:
    """Retrieve the extracted market skills from the Skill Extractor's analysis.
    Call this to see what skills were found in the job market before mapping them."""
    skills = tool_store.get("extracted_skills", [])
    if not skills:
        return "No extracted skills found. Skill Extractor must run first."

    total = tool_store.get("total_jobs_for_extraction", "?")
    lines = [f"Market skills ({len(skills)} unique, from {total} jobs):"]
    for s in skills:
        lines.append(
            f"  {s['name']} ({s.get('category', '?')}) — "
            f"{s.get('frequency', '?')}/{total} jobs ({s.get('pct', '?')}%)"
        )
    return "\n".join(lines)


@tool
def get_curated_skills() -> str:
    """Retrieve the exact curated skill set the teacher approved for mapping."""
    if tool_store.get("run_id"):
        result = _durable_selection_tool()
        if not tool_store.get("curated_skills"):
            return result
    skills = tool_store.get("curated_skills", [])
    if not skills:
        return "No curated skills found. Teacher must approve a skill selection first."

    total = tool_store.get("total_jobs_for_extraction", "?")
    lines = [f"Curated skills ({len(skills)} selected by teacher, from {total} jobs):"]
    for skill in skills:
        identity = (
            f" [candidate_id: {skill['candidate_id']}]"
            if skill.get("candidate_id")
            else ""
        )
        lines.append(
            f"  {skill['name']}{identity} ({skill.get('category', '?')}) — "
            f"{skill.get('frequency', '?')}/{total} jobs ({skill.get('pct', '?')}%)"
        )
    return "\n".join(lines)


@tool
def save_curriculum_mapping(mapping_json: str) -> str:
    """Save the curriculum mapping analysis results.
    Args:
        mapping_json: JSON array of objects with keys:
            - candidate_id: unchanged ID from get_curated_skills when supplied
            - name: EXACT skill name from get_curated_skills (e.g.
              "Query and analyze data using SQL"). NEVER use bare technology
              keywords — the name must match what the Skill Extractor produced.
            - category: skill category
            - status: "covered" | "gap" | "new_topic_needed"
            - target_chapter: chapter title where this skill fits (if gap)
            - related_concepts: list of existing concept names this skill relates to
            - priority: "high" | "medium" | "low" based on market frequency
            - reasoning: why this mapping decision was made
    """
    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    if not isinstance(mapping, list):
        return "Expected a JSON array."

    prerequisite_error = mapping_prerequisite_error()
    if prerequisite_error:
        return prerequisite_error

    if tool_store.get("run_id"):
        confirmation_result = _durable_selection_tool()
        if not tool_store.get("curated_skills"):
            return confirmation_result
    curated = tool_store.get("curated_skills", [])
    if not curated:
        return "No curated skills found. Teacher must approve a skill selection first."

    if tool_store.get("run_id"):
        by_id = {str(c["candidate_id"]): c for c in curated}
        by_name = {}
        for c in curated:
            by_name.setdefault(c["name"].casefold(), []).append(c)
        resolved = []
        for row in mapping:
            if not isinstance(row, dict):
                return "Each curriculum mapping entry must be an object."
            candidate = (
                by_id.get(str(row.get("candidate_id")))
                if row.get("candidate_id")
                else None
            )
            matches = by_name.get(str(row.get("name", "")).casefold(), [])
            if candidate is None and not row.get("candidate_id") and len(matches) == 1:
                candidate = matches[0]
            if candidate is None:
                return "Mapping needs a current candidate_id; ambiguous names cannot carry evidence."
            if row.get("status") not in {"covered", "gap", "new_topic_needed"}:
                return "Mapping status must be covered, gap, or new_topic_needed."
            if _missing_mapping_chapter(row):
                return (
                    "Missing target_chapter. Use list_chapters to assign each gap "
                    "or new_topic_needed skill before saving. If no chapters exist, "
                    "return to Supervisor with the Build Chapters setup step; "
                    "do not hand off to Skill Cleaner."
                )
            resolved.append(
                {
                    **row,
                    "candidate_id": candidate["candidate_id"],
                    "name": candidate["name"],
                    "evidence_references": candidate.get("evidence_references", []),
                    "onet_associations": candidate.get("onet_associations", []),
                    "job_metrics": candidate.get("job_metrics", {}),
                    "qualifying_posting_links": candidate.get(
                        "qualifying_posting_links", []
                    ),
                }
            )
        if len({r["candidate_id"] for r in resolved}) != len(resolved) or {
            r["candidate_id"] for r in resolved
        } != set(by_id):
            return "Map every curated candidate_id exactly once."
        fields = {
            "curriculum_mapping": resolved,
            "mapped_skills": _build_mapped_skills(resolved),
            "_cleaned_results": None,
            "selected_for_insertion": None,
            "final_skills": None,
            "skill_concepts": None,
        }
        error = _persist_durable_mapping(fields)
        if error:
            return error
        return f"Saved mapping proposals for {len(resolved)} candidates with evidence retained."

    # Auto-correct skill names: match each entry's name against the actual
    # extracted_skills list. The LLM sometimes simplifies names (e.g. writes
    # "SQL Querying and Analysis" instead of the canonical
    # "Query and analyze data using SQL"). We find the best match using
    # case-insensitive substring overlap and replace the name with the canonical one.
    extracted = tool_store.get("extracted_skills", [])
    if extracted:
        canonical_names: list[str] = [s["name"] for s in extracted]

        def _best_match(name: str) -> str:
            name_lower = name.lower()
            # Exact match first
            for cn in canonical_names:
                if cn.lower() == name_lower:
                    return cn
            # Substring match: canonical contains submitted name or vice versa
            for cn in canonical_names:
                cn_lower = cn.lower()
                if name_lower in cn_lower or cn_lower in name_lower:
                    return cn
            # Word-overlap scoring
            query_words = set(name_lower.split())
            best, best_score = name, 0
            for cn in canonical_names:
                cn_words = set(cn.lower().split())
                score = len(query_words & cn_words)
                if score > best_score:
                    best_score = score
                    best = cn
            return best

        corrected_count = 0
        for item in mapping:
            original = item.get("name", "")
            corrected = _best_match(original)
            if corrected != original:
                item["name"] = corrected
                corrected_count += 1

        if corrected_count:
            logger.info(
                "save_curriculum_mapping: auto-corrected %d skill name(s) to canonical forms",
                corrected_count,
            )

    expected_names = {
        str(skill.get("name", "")).strip().casefold()
        for skill in curated
        if skill.get("name")
    }
    mapping_names: list[str] = []
    duplicate_names: list[str] = []
    seen_names: set[str] = set()
    allowed_statuses = {"covered", "gap", "new_topic_needed"}

    for item in mapping:
        if not isinstance(item, dict):
            return "Each curriculum mapping entry must be an object."

        name = str(item.get("name", "")).strip()
        if not name:
            return "Each curriculum mapping entry must include a skill name."

        status = str(item.get("status", "")).strip().lower()
        if status not in allowed_statuses:
            return (
                f"Invalid mapping status for '{name}': {item.get('status')}. "
                "Expected covered, gap, or new_topic_needed."
            )
        item["status"] = status

        if (
            status in {"gap", "new_topic_needed"}
            and not str(item.get("target_chapter", "")).strip()
        ):
            return (
                f"Missing target_chapter for '{name}'. "
                "Every gap or new_topic_needed skill must be assigned to a chapter."
            )

        key = name.casefold()
        mapping_names.append(key)
        if key in seen_names:
            duplicate_names.append(name)
        seen_names.add(key)

    if duplicate_names:
        return "Curriculum mapping contains duplicate skills: " + ", ".join(
            sorted(set(duplicate_names))
        )

    mapped_name_set = set(mapping_names)
    missing = sorted(
        skill.get("name", "")
        for skill in curated
        if skill.get("name") and skill["name"].strip().casefold() not in mapped_name_set
    )
    unexpected = sorted(
        item.get("name", "")
        for item in mapping
        if item.get("name") and item["name"].strip().casefold() not in expected_names
    )
    if missing or unexpected:
        lines = [
            "Curriculum mapping must account for every curated skill exactly once."
        ]
        if missing:
            lines.append(
                f"Missing curated skills ({len(missing)}): {', '.join(missing)}"
            )
        if unexpected:
            lines.append(
                f"Unexpected skills not in curated set ({len(unexpected)}): {', '.join(unexpected)}"
            )
        return "\n".join(lines)

    _clear_tool_store_keys(
        "final_skills",
        "selected_for_insertion",
        "skill_concepts",
        "insertion_results",
        "_cleaned_results",
    )
    tool_store["curriculum_mapping"] = mapping
    tool_store["mapped_skills"] = _build_mapped_skills(mapping)

    breakdown = mapping_breakdown()
    gaps = [item for item in mapping if item.get("status") == "gap"]
    new_topics = [item for item in mapping if item.get("status") == "new_topic_needed"]

    lines = [
        f"Curriculum mapping saved for {breakdown['curated_total']} curated skills: "
        f"{breakdown['covered']} covered, {breakdown['gap']} gaps, "
        f"{breakdown['new_topic_needed']} new topics needed.",
        f"Skills requiring insertion: {breakdown['mapped_for_insertion']}",
    ]
    if gaps:
        lines.append("GAP SKILLS (to add):")
        for g in gaps[:10]:
            lines.append(
                f"  {g['name']} → {g.get('target_chapter', 'TBD')} "
                f"[{g.get('priority', '?')}]"
            )
    if new_topics:
        lines.append("NEW TOPICS NEEDED:")
        for n in new_topics:
            lines.append(f"  {n['name']}")
    lines.append("\nTransfer to Skill Cleaner.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Concept Linker Tools
# ═══════════════════════════════════════════════════════════════════

_CONCEPT_EXTRACTION_PROMPT = """\
You are an expert curriculum analyst. Your task is to determine which \
foundational concepts a market-demanded skill requires, given the context \
of a university textbook chapter.

## INPUT

Skill: "{skill_name}"
Category: "{skill_category}"
Mapped to chapter: "{chapter_title}"
Teacher's rationale: "{rationale}"
Market demand: appeared in {frequency} of {total_jobs} analyzed job postings ({demand_pct}%)

## CHAPTER'S EXISTING CONCEPTS
(These are concepts already in the knowledge graph for this chapter. \
Use EXACT names when referencing them.)

{concept_list}

## EVIDENCE FROM JOB POSTINGS
(Excerpts from real job descriptions that mention this skill. Use these \
to understand what the industry expects someone with this skill to know.)

{job_snippets}

## TASK

1. **Existing concepts**: Which of the chapter's existing concepts does this \
skill REQUIRE as prerequisites or closely depend on? Select ONLY concepts with \
a genuine dependency — not just topical similarity. Use the EXACT concept names \
from the list above.

2. **New concepts**: Are there foundational concepts that this skill clearly \
requires which do NOT exist in the chapter yet? Only propose a new concept if:
   - It appears across multiple job postings (not a one-off technology)
   - It represents a teachable, well-defined concept (not a product name or brand)
   - It is not already covered by an existing concept under a different name
   For each new concept, provide a concise academic description (1-2 sentences).

## OUTPUT FORMAT
Return ONLY valid JSON, no commentary:
{{"existing_concepts": ["concept_name_1", "concept_name_2"], \
"new_concepts": [{{"name": "concept_name", "description": "One-line academic description"}}]}}

## GUIDELINES
- Prefer matching existing concepts over creating new ones (avoid duplication).
- A skill typically requires 2-6 concepts. 0 is suspicious; >8 is likely over-linking.
- New concepts should be framework-agnostic and curriculum-appropriate \
(e.g. "stream processing" not "Kafka Streams API")."""


def _fetch_chapter_concepts(chapter_title: str) -> list[str]:
    """Fetch the current course chapter's concept names from Neo4j."""
    try:
        course_id = _require_course_id()
    except ValueError:
        return []

    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->"
                "(ch:COURSE_CHAPTER {title: $chapter_title})-[:INCLUDES_DOCUMENT]->"
                "(:TEACHER_UPLOADED_DOCUMENT)-[:MENTIONS]->(c:CONCEPT) "
                "RETURN DISTINCT c.name AS name "
                "ORDER BY c.name",
                {"course_id": course_id, "chapter_title": chapter_title},
            )
            return [str(row["name"]) for row in result if row["name"]]
    except Exception:
        logger.exception(
            "Failed to fetch chapter concepts for course %s / chapter %s",
            course_id,
            chapter_title,
        )
        return []


def _find_job_snippets(skill_name: str, jobs: list[dict], window: int = 500) -> str:
    """Find relevant excerpts from job descriptions that mention a skill."""
    pattern = re.compile(re.escape(skill_name), re.IGNORECASE)
    snippets: list[str] = []
    for job in jobs:
        desc = job.get("description", "")
        match = pattern.search(desc)
        if match:
            start = max(0, match.start() - window // 2)
            end = min(len(desc), match.end() + window // 2)
            snippet = desc[start:end].strip()
            snippets.append(f"--- {job['title']} @ {job['company']} ---\n{snippet}")
        if len(snippets) >= 5:
            break
    return (
        "\n\n".join(snippets)
        if snippets
        else "(no direct mentions found in job descriptions)"
    )


@tool
def extract_concepts_for_skills() -> str:
    """Analyze all approved market skills and determine which concepts each requires.
    Reads from tool_store: selected_for_insertion, curriculum_mapping, extracted_skills, selected_jobs.
    For each skill, queries Neo4j for chapter concepts, finds job description evidence,
    and uses LLM to match existing concepts and propose new ones."""
    if tool_store.get("run_id"):
        return _prepare_durable_concepts()
    approved = tool_store.get("selected_for_insertion", [])
    if not approved:
        return "No approved skills found. Teacher must approve skills first."

    try:
        _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    mapping_list = tool_store.get("curriculum_mapping", [])
    mapping_lookup = {m["name"].lower(): m for m in mapping_list}

    skills_list = tool_store.get("extracted_skills", [])
    skills_lookup = {s["name"].lower(): s for s in skills_list}

    jobs = tool_store.get("selected_jobs", [])
    total_jobs = tool_store.get("total_jobs_for_extraction", len(jobs))
    skill_job_urls_lookup: dict[str, list[str]] = tool_store.get("skill_job_urls", {})

    llm = _get_extraction_llm()
    skill_concepts: dict[str, dict] = {}
    errors: list[str] = []

    for skill_info in approved:
        skill_name = skill_info["name"]
        skill_key = skill_name.lower()

        # Enrich from curriculum mapping and extracted skills
        cm = mapping_lookup.get(skill_key, {})
        es = skills_lookup.get(skill_key, {})

        chapter_title = skill_info.get("target_chapter") or cm.get("target_chapter", "")
        category = skill_info.get("category") or es.get("category", "unknown")
        frequency = es.get("frequency", 0)
        demand_pct = es.get("pct", 0.0)
        priority = cm.get("priority", "medium")
        status = cm.get("status", "gap")
        rationale = skill_info.get("rationale", "")
        reasoning = cm.get("reasoning", "")

        # Fetch chapter concepts from Neo4j
        chapter_concepts = (
            _fetch_chapter_concepts(chapter_title) if chapter_title else []
        )
        concept_list_str = (
            "\n".join(f"- {c}" for c in chapter_concepts)
            if chapter_concepts
            else "(no concepts found for this chapter)"
        )

        # Find job description evidence
        job_snippets = _find_job_snippets(skill_name, jobs)

        # LLM call
        prompt = _CONCEPT_EXTRACTION_PROMPT.format(
            skill_name=skill_name,
            skill_category=category,
            chapter_title=chapter_title or "(unassigned)",
            rationale=rationale or "(none provided)",
            frequency=frequency,
            total_jobs=total_jobs,
            demand_pct=demand_pct,
            concept_list=concept_list_str,
            job_snippets=job_snippets,
        )

        try:
            response = llm.invoke(prompt, config={"callbacks": []})
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            parsed = json.loads(text)
        except (json.JSONDecodeError, Exception) as e:
            errors.append(f"{skill_name}: {type(e).__name__}: {e}")
            parsed = {"existing_concepts": [], "new_concepts": []}

        # Find which jobs mentioned this skill (for SOURCED_FROM linking)
        # Use the provenance map built during extraction — the synthesized skill
        # name won't appear verbatim in job descriptions, so regex matching fails.
        source_job_urls = skill_job_urls_lookup.get(skill_name.lower(), [])

        skill_concepts[skill_name] = {
            "existing_concepts": parsed.get("existing_concepts", []),
            "new_concepts": parsed.get("new_concepts", []),
            "chapter_title": chapter_title,
            "category": category,
            "frequency": frequency,
            "demand_pct": demand_pct,
            "priority": priority,
            "status": status,
            "rationale": rationale,
            "reasoning": reasoning,
            "source_job_urls": source_job_urls,
        }

    tool_store["skill_concepts"] = skill_concepts
    logger.info(
        "[PERF] extract_concepts_for_skills took %.1fms (%d skills)",
        (time.perf_counter() - t0) * 1000,
        len(skill_concepts),
    )

    # Build summary for the agent
    lines = [f"Concept analysis complete for {len(skill_concepts)} skills:"]
    lines.append("")
    lines.append("| Skill | Chapter | Existing | New |")
    lines.append("|-------|---------|----------|-----|")
    total_existing = 0
    total_new = 0
    for name, data in skill_concepts.items():
        n_exist = len(data["existing_concepts"])
        n_new = len(data["new_concepts"])
        total_existing += n_exist
        total_new += n_new
        flag = " ⚠️" if n_exist == 0 and n_new == 0 else ""
        lines.append(
            f"| {name} | {data['chapter_title']} | {n_exist} | {n_new} |{flag}"
        )
    lines.append(f"| **TOTAL** | | **{total_existing}** | **{total_new}** |")

    if errors:
        lines.append(f"\n⚠️ Errors on {len(errors)} skills: {'; '.join(errors)}")

    return "\n".join(lines)


@tool
def insert_market_skills_to_neo4j() -> str:
    """Write MARKET_SKILL nodes, JOB_POSTING nodes, and all relationships to Neo4j.
    Creates: MARKET_SKILL nodes with full provenance, JOB_POSTING provenance nodes,
    RELEVANT_TO_CHAPTER, SOURCED_FROM, and REQUIRES_CONCEPT relationships.
    New concepts are embedded and deduplicated against existing concepts."""
    if tool_store.get("run_id"):
        return _project_durable_approval()

    from .repository import MarketReviewRepository

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)
    with SessionLocal() as db:
        if MarketReviewRepository(db).has_analysis_run(course_id):
            return "Durable analysis requires its current run and committed teacher approval. Restore the analysis context before insertion."

    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    skill_concepts = tool_store.get("skill_concepts")
    if not skill_concepts:
        return "No concept data found. Run extract_concepts_for_skills first."

    t0 = time.perf_counter()
    jobs = tool_store.get("selected_jobs", [])

    stats = {
        "skills": 0,
        "job_postings": 0,
        "chapter_links": 0,
        "sourced_from": 0,
        "existing_concept_links": 0,
        "new_concepts": 0,
        "concepts_merged": 0,
    }

    # Collect all new concepts across skills for batch embedding + dedup
    all_new_concepts: list[dict] = []
    skill_new_concept_ranges: dict[str, tuple[int, int]] = {}
    for skill_name, data in skill_concepts.items():
        new_list = data.get("new_concepts", [])
        start = len(all_new_concepts)
        all_new_concepts.extend(new_list)
        skill_new_concept_ranges[skill_name] = (start, start + len(new_list))

    try:
        with _neo4j_session() as session:
            # Pre-compute: embed all new concepts and find matches
            dedup_results: list[dict] = []
            if all_new_concepts:
                try:
                    from app.modules.embeddings.embedding_service import (
                        EmbeddingService,
                    )

                    dedup_results = EmbeddingService().embed_and_dedup_concepts(
                        session, all_new_concepts
                    )
                except Exception:
                    logger.exception(
                        "Concept embedding/dedup failed; falling back to create-only"
                    )
                    dedup_results = []

            # Step A: Create JOB_POSTING nodes
            for job in jobs:
                if not job.get("url"):
                    continue
                session.run(
                    "MERGE (j:JOB_POSTING {url: $url}) "
                    "SET j.title = $title, j.company = $company, "
                    "    j.site = $site, j.search_term = $search_term, "
                    "    j.country = $country, j.location = $location, "
                    "    j.description = $description",
                    {
                        "url": job["url"],
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "site": job.get("site", ""),
                        "search_term": job.get("search_term", ""),
                        "country": job.get("country", ""),
                        "location": job.get("location", ""),
                        "description": job.get("description", ""),
                    },
                )
                stats["job_postings"] += 1

            # Steps B-E: For each skill, create node + relationships
            for skill_name, data in skill_concepts.items():
                # B: Create MARKET_SKILL node (with shared :SKILL label)
                session.run(
                    "MERGE (s:MARKET_SKILL:SKILL {name: $name}) "
                    "ON CREATE SET s.created_at = datetime() "
                    "SET s.category = $category, "
                    "    s.course_id = coalesce(s.course_id, $course_id), "
                    "    s.frequency = $frequency, "
                    "    s.demand_pct = $demand_pct, "
                    "    s.priority = $priority, "
                    "    s.status = $status, "
                    "    s.target_chapter = $target_chapter, "
                    "    s.rationale = $rationale, "
                    "    s.reasoning = $reasoning, "
                    "    s.source = 'market_demand'",
                    {
                        "name": skill_name,
                        "course_id": course_id,
                        "category": data.get("category", ""),
                        "frequency": data.get("frequency", 0),
                        "demand_pct": data.get("demand_pct", 0.0),
                        "priority": data.get("priority", ""),
                        "status": data.get("status", ""),
                        "target_chapter": data.get("chapter_title", ""),
                        "rationale": data.get("rationale", ""),
                        "reasoning": data.get("reasoning", ""),
                    },
                )
                stats["skills"] += 1

                # C: Link chapter -> skill via MAPPED_TO
                chapter = data.get("chapter_title")
                if chapter:
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER {title: $chapter}) "
                        "MERGE (s)-[:MAPPED_TO]->(ch)",
                        {
                            "name": skill_name,
                            "course_id": course_id,
                            "chapter": chapter,
                        },
                    )
                    stats["chapter_links"] += 1

                # D: Link to job postings
                for url in data.get("source_job_urls", []):
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (j:JOB_POSTING {url: $url}) "
                        "MERGE (s)-[:SOURCED_FROM]->(j)",
                        {"name": skill_name, "course_id": course_id, "url": url},
                    )
                    stats["sourced_from"] += 1

                # E: Link to existing concepts
                for concept_name in data.get("existing_concepts", []):
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (c:CONCEPT) WHERE c.name = $cname "
                        "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                        {
                            "name": skill_name,
                            "course_id": course_id,
                            "cname": concept_name,
                        },
                    )
                    stats["existing_concept_links"] += 1

                # F: New concepts — embed, dedup, then create-or-merge + link
                start, end = skill_new_concept_ranges.get(skill_name, (0, 0))
                for i in range(start, end):
                    new_concept = all_new_concepts[i]
                    cname = new_concept["name"].strip().casefold()

                    if i < len(dedup_results):
                        dr = dedup_results[i]
                    else:
                        # Fallback: no dedup result (embedding failed)
                        dr = {"action": "create_no_embedding", "target_name": cname}

                    if dr["action"] == "merge":
                        # Similar concept already exists — link to it
                        session.run(
                            "MATCH (s:MARKET_SKILL {name: $sname}) "
                            "MATCH (c:CONCEPT {name: $cname}) "
                            "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                            {
                                "sname": skill_name,
                                "course_id": course_id,
                                "cname": dr["target_name"],
                            },
                        )
                        stats["concepts_merged"] += 1
                        logger.info(
                            "Merged new concept '%s' → existing '%s' (score=%.3f)",
                            cname,
                            dr["target_name"],
                            dr.get("score", 0),
                        )
                    elif dr["action"] == "create":
                        # No match — create with embedding
                        session.run(
                            "MERGE (c:CONCEPT {name: $cname}) "
                            "ON CREATE SET c.description = $desc, "
                            "              c.embedding   = $embedding, "
                            "              c.merge_count = 0, "
                            "              c.aliases     = [] "
                            "ON MATCH SET  c.embedding   = CASE WHEN c.embedding IS NULL "
                            "                              THEN $embedding "
                            "                              ELSE c.embedding END, "
                            "              c.description = CASE WHEN c.description IS NULL "
                            "                              THEN $desc "
                            "                              ELSE c.description END "
                            "WITH c "
                            "MATCH (s:MARKET_SKILL {name: $sname}) "
                            "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                            {
                                "cname": cname,
                                "desc": new_concept.get("description", ""),
                                "embedding": dr["embedding"],
                                "sname": skill_name,
                                "course_id": course_id,
                            },
                        )
                        stats["new_concepts"] += 1
                    else:
                        # Fallback: create without embedding (embedding service down)
                        session.run(
                            "MERGE (c:CONCEPT {name: $cname}) "
                            "SET c.description = $desc "
                            "WITH c "
                            "MATCH (s:MARKET_SKILL {name: $sname}) "
                            "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                            {
                                "cname": cname,
                                "desc": new_concept.get("description", ""),
                                "sname": skill_name,
                                "course_id": course_id,
                            },
                        )
                        stats["new_concepts"] += 1

    except (ServiceUnavailable, SessionExpired, OSError):
        _get_neo4j_driver(force_new=True)
        logger.info(
            "[PERF] insert_market_skills_to_neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map update failed. Connection was reset — try again."

    logger.info(
        "[PERF] insert_market_skills_to_neo4j took %.1fms (stats=%s)",
        (time.perf_counter() - t0) * 1000,
        stats,
    )
    tool_store["insertion_results"] = stats

    return (
        f"✅ Knowledge Map updated successfully!\n"
        f"  Skills added: {stats['skills']}\n"
        f"  Job postings linked: {stats['job_postings']}\n"
        f"  Chapter links created: {stats['chapter_links']}\n"
        f"  Source links created: {stats['sourced_from']}\n"
        f"  Existing concept links reused: {stats['existing_concept_links']}\n"
        f"  New concepts added: {stats['new_concepts']}\n"
        f"  Similar concepts merged: {stats['concepts_merged']}"
    )


@tool
def delete_market_skills(skill_names: str) -> str:
    """Delete MARKET_SKILL nodes and their relationships from Neo4j.
    Also removes orphaned JOB_POSTING nodes (those with no remaining SOURCED_FROM links).
    Args:
        skill_names: JSON array, newline-delimited list, or comma-separated MARKET_SKILL names to delete,
            or "all" to delete every MARKET_SKILL node.
    """
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    from .repository import MarketReviewRepository

    withdrawal_message = (
        "Durable analysis targets and resources are preserved. "
        "Prepare withdrawal in the teacher review and approve its server digest."
    )
    if tool_store.get("run_id"):
        return withdrawal_message
    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)
    with SessionLocal() as db:
        if MarketReviewRepository(db).has_analysis_run(course_id):
            return withdrawal_message

    names = _parse_string_list(skill_names)
    delete_all = len(names) == 1 and names[0].lower() == "all"

    try:
        with _neo4j_session() as session:
            if delete_all:
                result = session.run(
                    "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(s:MARKET_SKILL) "
                    "WITH collect(DISTINCT s) AS skills "
                    "FOREACH (skill IN skills | DETACH DELETE skill) "
                    "RETURN size(skills) AS deleted",
                    {"course_id": course_id},
                )
                deleted = result.single()["deleted"]
            else:
                result = session.run(
                    "UNWIND $names AS name "
                    "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(s:MARKET_SKILL) "
                    "WHERE toLower(s.name) = toLower(name) "
                    "WITH collect(DISTINCT s) AS skills "
                    "FOREACH (skill IN skills | DETACH DELETE skill) "
                    "RETURN size(skills) AS deleted",
                    {"course_id": course_id, "names": names},
                )
                deleted = result.single()["deleted"]

            # Clean up orphaned JOB_POSTING nodes
            orphan_result = session.run(
                "MATCH (j:JOB_POSTING) "
                "WHERE NOT EXISTS { (j)<-[:SOURCED_FROM]-() } "
                "DETACH DELETE j "
                "RETURN count(j) AS orphans"
            )
            orphans = orphan_result.single()["orphans"]

            # Clean up orphaned CONCEPT nodes (no remaining relationships)
            orphan_concepts_result = session.run(
                "MATCH (c:CONCEPT) "
                "WHERE NOT EXISTS { (c)-[]-() } "
                "DELETE c "
                "RETURN count(c) AS orphan_concepts"
            )
            orphan_concepts = orphan_concepts_result.single()["orphan_concepts"]

    except (ServiceUnavailable, SessionExpired, OSError):
        _get_neo4j_driver(force_new=True)
        return "Knowledge Map unavailable. Connection was reset — try again."

    scope = (
        f"all market skills for course {course_id}"
        if delete_all
        else f"course {course_id}, matching {skill_names}"
    )
    return (
        f"Deleted {deleted} MARKET_SKILL node(s) ({scope}).\n"
        f"Cleaned up {orphans} orphaned JOB_POSTING node(s).\n"
        f"Cleaned up {orphan_concepts} orphaned CONCEPT node(s)."
    )


# ═══════════════════════════════════════════════════════════════════
#  Skill Finder Tools (NEW)
# ═══════════════════════════════════════════════════════════════════


@tool
def get_skills_by_category() -> str:
    """Return current candidate IDs, categories and saved decisions for advice.
    Durable analyses return safe versioned JSON summaries. Legacy standalone
    runs return extracted skills grouped by category with frequency counts.
    Call this after extraction completes to present skills to the teacher."""
    if tool_store.get("run_id"):
        from .repository import MarketReviewRepository
        from .review_service import SkillReviewService, candidate_advice_summary

        with SessionLocal() as db:
            service = SkillReviewService(MarketReviewRepository(db))
            try:
                review = service.get_review(
                    tool_store["course_id"], tool_store["teacher_id"]
                )
                if str(review.run_id) != tool_store["run_id"]:
                    return "Review must belong to the active analysis."
                return json.dumps(candidate_advice_summary(review))
            except Exception as exc:
                return f"Candidate review unavailable: {exc}"
    skills = tool_store.get("extracted_skills", [])
    if not skills:
        return "No extracted skills found. Run start_extraction first."

    total_jobs = tool_store.get("total_jobs_for_extraction", "?")

    # Group by category
    by_cat: dict[str, list[dict]] = {}
    for s in skills:
        cat = s.get("category", "unknown")
        by_cat.setdefault(cat, []).append(s)

    lines = [f"Extracted {len(skills)} unique skills from {total_jobs} jobs:\n"]
    for cat, cat_skills in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        lines.append(f"## {cat.upper()} ({len(cat_skills)} skills)")
        for s in sorted(cat_skills, key=lambda x: -x.get("frequency", 0)):
            lines.append(
                f"  • {s['name']} — {s.get('frequency', '?')}/{total_jobs} jobs "
                f"({s.get('pct', '?')}%)"
            )
        lines.append("")

    lines.append(
        "Teacher can select by: specific names, entire categories, "
        "or 'top N per category'."
    )
    return "\n".join(lines)


def _durable_selection_tool(changes: list[dict] | None = None) -> str:
    """Reuse the graph execution's lease; never claim it again from a worker."""
    from .repository import MarketReviewRepository
    from .review_service import SkillReviewService
    from .schemas import SkillReviewRevision

    with SessionLocal() as db:
        service = SkillReviewService(MarketReviewRepository(db))
        try:
            course_id, teacher_id = tool_store["course_id"], tool_store["teacher_id"]
            current = service.get_review(course_id, teacher_id)
            if str(current.run_id) != tool_store.get("run_id"):
                raise ValueError("Review must belong to the active analysis")
            revisions = SkillReviewRevision(
                run_id=current.run_id,
                expected_candidate_revision=current.candidate_revision,
                expected_selection_revision=current.selection_revision,
            )
            if changes is None:
                fields = service.load_confirmed_selection(
                    course_id, teacher_id, revisions
                )
                result = f"Loaded {len(fields['curated_skills'])} exact teacher-confirmed skills for mapping."
            else:
                review, fields = service.create_recommendation(
                    course_id, teacher_id, revisions, changes
                )
                result = f"Saved proposal {review.recommendations[-1].id}. The teacher chooses the exact skills through Confirm Selection."
        except Exception as exc:
            service.rollback()
            if changes is None:
                _clear_tool_store_keys(
                    "selection_confirmation",
                    "curated_skills",
                    "curriculum_mapping",
                    "mapped_skills",
                    "final_skills",
                    "selected_for_insertion",
                    "skill_concepts",
                )
                tool_store["review_stage"] = "draft"
            return f"Selection {'confirmation' if changes is None else 'proposal'} failed: {exc}"
        # Durable run and matching snapshot committed before any SSE state changes.
        tool_store.update(fields)
        return result


@tool
def propose_skill_selection(changes_json: str) -> str:
    """Propose immutable add/remove diffs with candidate IDs and concrete reasons.

    Does not edit drafts, override exclusions, confirm choices or publish skills.
    changes_json is a nonempty JSON list of candidate_id, action and reason.
    """
    if not tool_store.get("run_id"):
        return "A current durable analysis is required for a selection proposal."
    try:
        changes = json.loads(changes_json)
        if not isinstance(changes, list):
            return "Proposal failed: provide a JSON list of changes."
    except json.JSONDecodeError:
        return "Proposal failed: provide valid JSON changes."
    return _durable_selection_tool(changes)


@tool
def approve_skill_selection(selection_json: str) -> str:
    """Load the exact server-confirmed teacher shortlist for downstream mapping.

    Current durable analyses ignore selection_json; only the teacher API can
    save and confirm choices. Legacy standalone runs retain name-based selection.
    Args:
        selection_json: JSON array of skill names the teacher wants to keep.
            Example: ["Query data using SQL", "Deploy apps using Kubernetes"]
            Or a JSON object with category-based selection:
            {"categories": ["cloud", "database"], "specific": ["Train ML models"], "top_n_per_category": 3}
    """
    if tool_store.get("run_id"):
        return _durable_selection_tool()

    try:
        selection = json.loads(selection_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}. Please provide a valid JSON array or object."

    extracted = tool_store.get("extracted_skills", [])
    if not extracted:
        return "No extracted skills to select from. Run extraction first."

    extracted_lookup = {s["name"].lower(): s for s in extracted}
    curated: list[dict] = []
    not_found: list[str] = []

    if isinstance(selection, list):
        # Direct list of skill names
        for name in selection:
            key = name.strip().lower()
            if key in extracted_lookup:
                curated.append(extracted_lookup[key])
            else:
                not_found.append(name)
    elif isinstance(selection, dict):
        # Category-based selection
        categories = [c.lower() for c in selection.get("categories", [])]
        specific = [s.lower() for s in selection.get("specific", [])]
        top_n = selection.get("top_n_per_category")

        if categories:
            for s in extracted:
                if s.get("category", "").lower() in categories:
                    curated.append(s)
        if specific:
            for name in specific:
                if name in extracted_lookup:
                    curated.append(extracted_lookup[name])
                else:
                    not_found.append(name)
        if top_n and isinstance(top_n, int):
            by_cat: dict[str, list[dict]] = {}
            for s in extracted:
                by_cat.setdefault(s.get("category", "unknown"), []).append(s)
            for cat_skills in by_cat.values():
                sorted_skills = sorted(cat_skills, key=lambda x: -x.get("frequency", 0))
                for s in sorted_skills[:top_n]:
                    if s not in curated:
                        curated.append(s)
    else:
        return "Expected a JSON array of skill names or a selection object."

    # Deduplicate by name
    seen: set[str] = set()
    deduped: list[dict] = []
    for s in curated:
        key = s["name"].lower()
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    _clear_tool_store_keys(
        "curriculum_mapping",
        "mapped_skills",
        "final_skills",
        "selected_for_insertion",
        "skill_concepts",
        "insertion_results",
        "_cleaned_results",
    )
    tool_store["curated_skills"] = deduped
    names = [s["name"] for s in deduped]
    result = f"Saved {len(deduped)} curated skills: {', '.join(names[:10])}"
    if len(names) > 10:
        result += f" ... and {len(names) - 10} more"
    if not_found:
        result += f"\n⚠ Not found in extracted skills: {', '.join(not_found)}"
    return result


# ═══════════════════════════════════════════════════════════════════
#  Skill Cleaner Tools (NEW)
# ═══════════════════════════════════════════════════════════════════


@tool
def load_mapped_skills() -> str:
    """Load the Mapper's output: market skills assigned to chapters.
    Returns the mapped_skills dict from tool_store."""
    if any(
        _missing_mapping_chapter(row)
        for row in tool_store.get("curriculum_mapping") or []
    ):
        return (
            "Chapter assignments are missing. Return to Supervisor for Curriculum "
            "Mapper to repair the mapping using list_chapters. Do not ask the teacher "
            "to repair individual assignments. If no chapters exist, explain the "
            "Build Chapters course setup step and preserve the confirmed skills."
        )
    breakdown = mapping_breakdown()
    if tool_store.get("curriculum_mapping") and not breakdown["is_complete"]:
        return (
            "Curriculum mapping is incomplete. "
            f"Accounted for {breakdown['mapped_name_count']}/{breakdown['curated_total']} "
            f"curated skills, with {breakdown['missing']} missing."
        )

    mapped = tool_store.get("mapped_skills")
    if not mapped:
        # Fall back to curriculum_mapping if mapped_skills not set
        mapping = tool_store.get("curriculum_mapping", [])
        if not mapping:
            return "No mapped skills found. Curriculum Mapper must run first."

        mapped = _build_mapped_skills(mapping)
        tool_store["mapped_skills"] = mapped

    lines = [f"Mapped skills across {len(mapped)} chapters:"]
    for chapter, skills in mapped.items():
        lines.append(f"\n  {chapter}: {len(skills)} skills")
        for s in skills:
            lines.append(f"    • {s}")
    return "\n".join(lines)


@tool
def load_existing_skills_for_chapters(chapter_titles: str) -> str:
    """Query Neo4j for existing BOOK_SKILL and MARKET_SKILL nodes linked to course chapters.
    Args:
        chapter_titles: JSON array, newline-delimited, or comma-separated chapter titles.
    Returns per-chapter existing skill lists."""
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    titles = _parse_string_list(chapter_titles)
    if not titles:
        return "Please provide chapter titles."

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            rows = _fetch_existing_chapter_skill_rows(
                session,
                course_id=course_id,
                chapter_titles=titles,
            )
    except (ServiceUnavailable, SessionExpired, OSError):
        logger.info(
            "[PERF] load_existing_skills_for_chapters FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return "Knowledge Map unavailable. Please try again in a moment."
    except AuthError:
        return "Knowledge Map connection failed. Check the graph service credentials."
    logger.info(
        "[PERF] load_existing_skills_for_chapters took %.1fms (%d rows)",
        (time.perf_counter() - t0) * 1000,
        len(rows),
    )

    if not rows:
        return f"No existing skills found for chapters: {chapter_titles}"

    lines = [f"Existing skills for {len(rows)} chapters:"]
    for r in rows:
        skills = r.get("skills", [])
        lines.append(
            f"\n  {r['chapter']} ({len(skills)} existing skills: "
            f"{len(r.get('book_skills', []))} book, {len(r.get('market_skills', []))} market):"
        )
        for sk in skills:
            desc = sk.get("description", "")
            desc_str = f" — {desc[:80]}" if desc else ""
            lines.append(
                f"    • [{sk.get('skill_type', 'unknown')}] {sk['name']}{desc_str}"
            )
    return "\n".join(lines)


@tool
def compare_and_clean(chapter_title: str) -> str:
    """Compare mapped market skills vs existing curriculum skills for one course chapter.
    Uses LLM to decide which market skills are redundant.
    Args:
        chapter_title: the course chapter to clean.
    Returns kept/dropped skill lists with reasoning."""
    if tool_store.get("run_id"):
        return _compare_durable_candidates(chapter_title)
    mapped = tool_store.get("mapped_skills", {})
    market_skills = mapped.get(chapter_title, [])
    if not market_skills:
        return f"No mapped market skills for chapter: {chapter_title}"

    try:
        course_id = _require_course_id()
    except ValueError as exc:
        return str(exc)

    # Fetch existing skills for this course chapter
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    existing_skills: list[str] = []
    try:
        with _neo4j_session() as session:
            rows = _fetch_existing_chapter_skill_rows(
                session,
                course_id=course_id,
                chapter_titles=[chapter_title],
            )
            skills_data = rows[0]["skills"] if rows else []
            existing_skills = [
                f"[{s.get('skill_type', 'unknown')}] {s['name']}: {s.get('description', '')}"
                for s in skills_data
            ]
    except (ServiceUnavailable, SessionExpired, OSError):
        _get_neo4j_driver(force_new=True)
        return "Knowledge Map unavailable. Please try again in a moment."

    if not existing_skills:
        # No existing skills to compare against — keep all market skills
        result_data = {
            "chapter": chapter_title,
            "kept": market_skills,
            "dropped": [],
        }
        _update_cleaned_results(result_data)
        return (
            f"Chapter '{chapter_title}': No existing skills to compare against. "
            f"Keeping all {len(market_skills)} market skills."
        )

    # LLM comparison
    llm = _get_extraction_llm()
    prompt = (
        "You are a curriculum deduplication expert. Compare new market skills against "
        "existing skills already in the course chapter for redundancy.\n\n"
        f"## Chapter: {chapter_title}\n\n"
        "## Existing Skills (already in curriculum):\n"
        + "\n".join(f"- {s}" for s in existing_skills)
        + "\n\n## New Market Skills to evaluate:\n"
        + "\n".join(f"- {s}" for s in market_skills)
        + "\n\n"
        "For each market skill, decide: KEEP or DROP.\n"
        "DROP only if an existing skill teaches essentially the same competency.\n"
        "When in doubt, KEEP — the teacher already selected these.\n\n"
        "Return ONLY valid JSON:\n"
        '{"kept": [{"name": "...", "reason": "..."}], '
        '"dropped": [{"name": "...", "overlaps_with": "...", "reason": "..."}]}'
    )

    try:
        response = llm.invoke(prompt, config={"callbacks": []})
        text = str(response.content).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        parsed = json.loads(text)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("compare_and_clean LLM parse error for %s: %s", chapter_title, e)
        # On error, keep all skills
        result_data = {
            "chapter": chapter_title,
            "kept": market_skills,
            "dropped": [],
        }
        _update_cleaned_results(result_data)
        return (
            f"LLM comparison failed for '{chapter_title}', keeping all "
            f"{len(market_skills)} market skills. Error: {e}"
        )

    kept = [k["name"] for k in parsed.get("kept", [])]
    dropped = [d["name"] for d in parsed.get("dropped", [])]

    result_data = {
        "chapter": chapter_title,
        "kept": kept,
        "dropped": dropped,
        "details": parsed,
    }
    _update_cleaned_results(result_data)

    lines = [f"Chapter '{chapter_title}':"]
    lines.append(f"  ✓ KEPT: {len(kept)} skills")
    for k in parsed.get("kept", []):
        lines.append(f"    • {k['name']} — {k.get('reason', '')}")
    lines.append(f"  ✗ DROPPED: {len(dropped)} skills")
    for d in parsed.get("dropped", []):
        lines.append(
            f"    • {d['name']} (overlaps: {d.get('overlaps_with', '?')}) — "
            f"{d.get('reason', '')}"
        )
    return "\n".join(lines)


def _update_cleaned_results(result_data: dict) -> None:
    """Accumulate per-chapter cleaning results into tool_store."""
    cleaned = tool_store.get("_cleaned_results", [])
    # Replace if chapter already processed
    cleaned = [c for c in cleaned if c["chapter"] != result_data["chapter"]]
    cleaned.append(result_data)
    tool_store["_cleaned_results"] = cleaned


@tool
def finalize_cleaned_skills() -> str:
    """Save the final cleaned skill list to tool_store and hand off to Concept Linker.
    Aggregates all per-chapter cleaning results into a flat list of surviving skills."""
    if tool_store.get("run_id"):
        return _finalize_durable_candidates()
    cleaned = tool_store.get("_cleaned_results", [])
    if not cleaned:
        return "No cleaning results found. Run compare_and_clean first."

    final_skills: list[str] = []
    total_dropped = 0
    for chapter_result in cleaned:
        final_skills.extend(chapter_result.get("kept", []))
        total_dropped += len(chapter_result.get("dropped", []))

    # Deduplicate
    seen: set[str] = set()
    deduped: list[str] = []
    for s in final_skills:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(s)

    tool_store["final_skills"] = deduped

    # Also update selected_for_insertion with enriched data from curated_skills
    curated = tool_store.get("curated_skills", [])
    curated_lookup = {s["name"].lower(): s for s in curated}
    mapping = tool_store.get("curriculum_mapping", [])
    mapping_lookup = {m["name"].lower(): m for m in mapping}

    enriched: list[dict] = []
    for name in deduped:
        skill_data = curated_lookup.get(name.lower(), {"name": name})
        map_data = mapping_lookup.get(name.lower(), {})
        enriched.append(
            {
                **skill_data,
                "name": name,
                "category": skill_data.get("category", "unknown"),
                "target_chapter": map_data.get("target_chapter", ""),
                "rationale": map_data.get("reasoning", ""),
            }
        )

    tool_store["selected_for_insertion"] = enriched

    return (
        f"Finalized {len(deduped)} clean skills (dropped {total_dropped} redundant). "
        f"Ready for Concept Linker."
    )


def _review_revision():
    from .schemas import SkillReviewRevision

    return SkillReviewRevision(
        run_id=tool_store["run_id"],
        expected_candidate_revision=tool_store["candidate_revision"],
        expected_selection_revision=tool_store["selection_revision"],
    )


def _persist_durable_mapping(fields: dict) -> str | None:
    from .repository import MarketReviewRepository
    from .review_service import SkillReviewService

    with SessionLocal() as db:
        service = SkillReviewService(MarketReviewRepository(db))
        try:
            committed = service.save_mapping_state(
                tool_store["course_id"],
                tool_store["teacher_id"],
                _review_revision(),
                fields,
            )
        except Exception as exc:
            service.rollback()
            return (
                f"Mapping change refused: {getattr(exc, 'detail', type(exc).__name__)}"
            )
    tool_store.update(committed)
    return None


def _finalize_durable_candidates() -> str:
    result = _durable_selection_tool()
    curated = {row["candidate_id"]: row for row in tool_store.get("curated_skills", [])}
    if not curated:
        return result
    mapping = tool_store.get("curriculum_mapping") or []
    if {row.get("candidate_id") for row in mapping} != set(curated) or len(
        mapping
    ) != len(curated):
        return "Map every confirmed candidate_id before cleaning."
    decisions = {}
    for chapter in tool_store.get("_cleaned_results") or []:
        for decision in (chapter.get("details") or {}).get("kept", []):
            decisions[decision.get("candidate_id")] = {"disposition": "new"}
        for decision in (chapter.get("details") or {}).get("dropped", []):
            decisions[decision.get("candidate_id")] = {
                **decision,
                "disposition": "merged",
            }
        # The no-existing-skills branch also stores explicit ID decisions.
        for candidate_id in chapter.get("kept", []):
            decisions.setdefault(candidate_id, {"disposition": "new"})
    prepared = []
    for row in mapping:
        candidate_id = row["candidate_id"]
        decision = (
            {"disposition": "covered"}
            if row["status"] == "covered"
            else decisions.get(candidate_id)
        )
        if decision is None:
            return f"Clean candidate_id {candidate_id} before finalizing."
        if (
            decision["disposition"] == "merged"
            and not decision.get("graph_target_id")
            and not decision.get("overlaps_with")
        ):
            return "Merged candidates require an existing target; evidence cannot be dropped."
        prepared.append(
            {
                **deepcopy(row),
                **deepcopy(decision),
                **deepcopy(curated[candidate_id]),
                "disposition": decision["disposition"],
                "rationale": decision.get("reason") or row.get("reasoning", ""),
            }
        )
    fields = {
        "selected_for_insertion": prepared,
        "final_skills": [row["name"] for row in prepared],
        "skill_concepts": None,
    }
    error = _persist_durable_mapping(fields)
    return (
        error
        or f"Finalized {len(prepared)} candidate IDs with covered and merged evidence retained. Ready for Concept Linker."
    )


def _compare_durable_candidates(chapter_title: str) -> str:
    result = _durable_selection_tool()
    if not tool_store.get("curated_skills"):
        return result
    candidates = [
        deepcopy(row)
        for row in tool_store.get("curriculum_mapping") or []
        if row.get("target_chapter") == chapter_title
        and row.get("status") in {"gap", "new_topic_needed"}
    ]
    if not candidates:
        return f"No new candidate IDs mapped to chapter: {chapter_title}"
    try:
        with _neo4j_session() as session:
            rows = _fetch_existing_chapter_skill_rows(
                session, course_id=_require_course_id(), chapter_titles=[chapter_title]
            )
            existing = rows[0]["skills"] if rows else []
        if not existing:
            parsed = {
                "kept": [{"candidate_id": row["candidate_id"]} for row in candidates],
                "dropped": [],
            }
        else:
            prompt = (
                "Compare candidate skills with existing course skills. Keep each candidate_id once in kept or dropped. A drop means merge into the same supported competency, never discard evidence. Each dropped entry must name overlaps_with, graph_target_id and origin from the existing target. Return JSON {kept:[{candidate_id,reason}],dropped:[{candidate_id,overlaps_with,graph_target_id,origin,reason}]}. Candidates: "
                + json.dumps(
                    [
                        {"candidate_id": row["candidate_id"], "name": row["name"]}
                        for row in candidates
                    ]
                )
                + " Existing targets: "
                + json.dumps(existing)
            )
            text = str(
                _get_extraction_llm().invoke(prompt, config={"callbacks": []}).content
            ).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(text)
        ids = [
            str(row.get("candidate_id"))
            for group in ("kept", "dropped")
            for row in parsed.get(group, [])
        ]
        if len(set(ids)) != len(ids) or set(ids) != {
            row["candidate_id"] for row in candidates
        }:
            return "Cleaner must account for each candidate_id exactly once."
        for decision in parsed.get("dropped", []):
            matches = [
                target
                for target in existing
                if str(target.get("graph_target_id"))
                == str(decision.get("graph_target_id"))
                and target.get("origin") == decision.get("origin")
            ]
            if len(matches) != 1:
                return (
                    "Cleaner merge target must be an existing target in this chapter."
                )
            decision["overlaps_with"] = matches[0]["name"]
        cleaned = [
            row
            for row in tool_store.get("_cleaned_results") or []
            if row["chapter"] != chapter_title
        ]
        cleaned.append(
            {
                "chapter": chapter_title,
                "kept": [row["candidate_id"] for row in parsed.get("kept", [])],
                "dropped": [row["candidate_id"] for row in parsed.get("dropped", [])],
                "details": parsed,
            }
        )
        error = _persist_durable_mapping(
            {
                "_cleaned_results": cleaned,
                "selected_for_insertion": None,
                "final_skills": None,
                "skill_concepts": None,
            }
        )
        return (
            error
            or f"Reviewed {len(ids)} candidate IDs for {chapter_title}; all evidence retained."
        )
    except Exception as exc:
        return f"Cleaner unavailable: {type(exc).__name__}. Retry before finalizing."


def _prepare_durable_concepts() -> str:
    from .neo4j_repository import MarketSkillGraphRepository
    from .repository import MarketReviewRepository
    from .review_service import SkillReviewService

    result = _durable_selection_tool()
    if not tool_store.get("curated_skills"):
        return result
    approved = tool_store.get("selected_for_insertion") or []
    if not approved:
        return "Finalize cleaned candidate IDs before preparing the integration review."
    proposals = []
    try:
        for row in approved:
            chapter_title = row.get("target_chapter", "")
            concepts = _fetch_chapter_concepts(chapter_title) if chapter_title else []
            # Only validated candidate passages enter the model context; graph
            # and model work happen before opening an approval transaction.
            snippets = "\n".join(
                ref.get("excerpt") or ref.get("original_phrase", "")
                for ref in row.get("evidence_references", [])
            )
            prompt = _CONCEPT_EXTRACTION_PROMPT.format(
                skill_name=row["name"],
                skill_category=row.get("category", "unknown"),
                chapter_title=chapter_title,
                rationale=row.get("rationale", ""),
                frequency=row.get("job_metrics", {}).get("supporting_posting_count", 0),
                total_jobs=row.get("job_metrics", {}).get("assessed_posting_count", 0),
                demand_pct=row.get("job_metrics", {}).get("percentage"),
                concept_list="\n".join(concepts) or "(no concepts)",
                job_snippets=snippets,
            )
            text = str(
                _get_extraction_llm().invoke(prompt, config={"callbacks": []}).content
            ).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(text)
            concept_rows = [
                {"name": name} if isinstance(name, str) else name
                for name in parsed.get("existing_concepts", [])
            ] + parsed.get("new_concepts", [])
            proposals.append({**deepcopy(row), "concepts": concept_rows})
        error = _persist_durable_mapping(
            {"skill_concepts": {row["candidate_id"]: row for row in proposals}}
        )
        if error:
            return error
        with SessionLocal() as db:
            service = SkillReviewService(MarketReviewRepository(db))
            try:
                review = service.prepare_integration_review(
                    tool_store["course_id"],
                    tool_store["teacher_id"],
                    _review_revision(),
                    proposals,
                    graph=MarketSkillGraphRepository(_get_neo4j_driver()),
                )
            except Exception:
                service.rollback()
                raise
        tool_store["skill_review_change_id"] = str(uuid4())
        return f"Prepared final teacher review for {len(review.integration_review['items'])} candidate IDs. Review targets/evidence and approve explicitly in the teacher panel."
    except Exception as exc:
        return f"Integration review preparation failed: {getattr(exc, 'detail', type(exc).__name__)}. Retry; no skill was published."


def _project_durable_approval() -> str:
    from .neo4j_repository import MarketSkillGraphRepository
    from .projection_service import SkillEvidenceProjector
    from .repository import MarketReviewRepository
    from .review_service import SkillReviewService

    with SessionLocal() as db:
        repo = MarketReviewRepository(db)
        service = SkillReviewService(repo)
        review = service.get_review(tool_store["course_id"], tool_store["teacher_id"])
        if (
            str(review.run_id) != tool_store.get("run_id")
            or not review.approved_references
        ):
            return "Final teacher integration approval through the review API is required before publication. Model tools cannot grant approval."
        revision = review.publication_revision
        repo.rollback()
        status = SkillEvidenceProjector(
            repo, MarketSkillGraphRepository(_get_neo4j_driver())
        ).project(tool_store["course_id"], revision, run_id=UUID(tool_store["run_id"]))
        tool_store["publication_revision"] = revision
        tool_store["insertion_results"] = {"projection_status": status}
        tool_store["skill_review_change_id"] = str(uuid4())
        return f"Approved SQL evidence projection: {status}."


# ═══════════════════════════════════════════════════════════════════
#  Tool Groups (used by each agent)
# ═══════════════════════════════════════════════════════════════════

SUPERVISOR_TOOLS = [
    set_job_search_country,
    save_skills_for_insertion,
    delete_market_skills,
    show_current_state,
    list_chapters,
]

SKILL_FINDER_TOOLS = [
    set_job_search_country,
    fetch_jobs,
    select_jobs_by_group,
    start_extraction,
    get_skills_by_category,
    propose_skill_selection,
    approve_skill_selection,
]

CURRICULUM_MAPPER_TOOLS = [
    list_chapters,
    get_chapter_details,
    check_skills_coverage,
    get_curated_skills,
    save_curriculum_mapping,
]

SKILL_CLEANER_TOOLS = [
    load_mapped_skills,
    load_existing_skills_for_chapters,
    compare_and_clean,
    finalize_cleaned_skills,
]

CONCEPT_LINKER_TOOLS = [
    extract_concepts_for_skills,
    insert_market_skills_to_neo4j,
]

ALL_TOOLS = (
    SUPERVISOR_TOOLS
    + SKILL_FINDER_TOOLS
    + CURRICULUM_MAPPER_TOOLS
    + SKILL_CLEANER_TOOLS
    + CONCEPT_LINKER_TOOLS
)


def owned_sync_tools(tools):
    """Preserve StructuredTool schemas while retaining actual worker execution."""
    adapted = []
    for original in tools:
        if original.coroutine is not None or original.func is None:
            adapted.append(original)
            continue

        adapted.append(
            original.model_copy(
                update={"coroutine": owned_sync_execution(original.func)}
            )
        )
    return adapted
