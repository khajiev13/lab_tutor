import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

import pandas as pd
from langchain.tools import tool
from langgraph.types import Command

from .extractor import _get_extraction_llm
from .state import tool_store

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
    """Fetch course + book + chapter summaries for a given teacher from Neo4j.

    If teacher_email is None, defaults to the first teacher in the DB.
    Returns a compact text block suitable for embedding in a system prompt.
    """
    try:
        t0 = time.perf_counter()
        with _neo4j_session() as session:
            # Find teacher node
            if teacher_email:
                teacher_result = session.run(
                    "MATCH (t:USER:TEACHER) WHERE toLower(t.email) = toLower($email) RETURN t.first_name AS first, t.last_name AS last, t.email AS email, t.id AS id LIMIT 1",
                    {"email": teacher_email},
                )
            else:
                teacher_result = session.run(
                    "MATCH (t:USER:TEACHER) RETURN t.first_name AS first, t.last_name AS last, t.email AS email, t.id AS id LIMIT 1"
                )
            teacher_row = teacher_result.single()
            if not teacher_row:
                teacher_name = "(Unknown Teacher)"
                teacher_email_val = ""
            else:
                teacher_name = f"{teacher_row['first']} {teacher_row['last']}".strip()
                teacher_email_val = teacher_row["email"]

            # Find their class and curriculum
            class_result = session.run(
                "MATCH (t:USER:TEACHER)-[:TEACHES_CLASS]->(cl:CLASS)-[:USES_BOOK]->(b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER) "
                "OPTIONAL MATCH (ch)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
                "WHERE toLower(t.email) = toLower($email) OR $email IS NULL "
                "WITH cl, b, ch, collect(sk.name) AS skills "
                "ORDER BY ch.chapter_index "
                "RETURN cl.title AS course, cl.description AS course_desc, "
                "       b.title AS book, b.authors AS authors, b.year AS year, "
                "       ch.chapter_index AS idx, ch.title AS ch_title, "
                "       ch.summary AS ch_summary, skills",
                {"email": teacher_email_val} if teacher_email_val else {"email": None},
            )
            rows = [dict(r) for r in class_result]
        neo4j_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[PERF] load_curriculum_context Neo4j queries took %.1fms (%d rows)",
            neo4j_ms,
            len(rows),
        )
    except Exception:
        return "(Curriculum data unavailable — Neo4j not reachable)"

    if not rows:
        return "(No curriculum data found for this teacher in the knowledge graph)"

    r0 = rows[0]
    lines = [
        f"Teacher: {teacher_name}",
        f"Course: {r0['course']}",
    ]
    if r0["course_desc"]:
        lines.append(f"Description: {r0['course_desc']}")
    lines.append(f"Textbook: {r0['book']} ({r0['authors']}, {r0['year']})")
    lines.append(f"Chapters: {len(rows)}")
    lines.append("")

    for r in rows:
        skills_str = ", ".join(r["skills"]) if r["skills"] else "(none yet)"
        lines.append(f"Ch {r['idx']}: {r['ch_title']}")
        if r["ch_summary"]:
            lines.append(f"  Summary: {r['ch_summary']}")
        lines.append(f"  Skills: {skills_str}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Coordinator Tools
# ═══════════════════════════════════════════════════════════════════


@tool
def fetch_jobs(
    search_terms: str,
    location: str = "San Francisco, CA",
    results_per_site: int = 15,
) -> str:
    """Fetch real job postings from Indeed and LinkedIn.
    search_terms: comma-separated queries (e.g. "Bioinformatics Researcher, Lab Technician").
    Scrapes all terms, deduplicates by title+company.
    IMPORTANT: Always use ONE call with all search terms. Never call this tool multiple times."""
    from jobspy import scrape_jobs

    terms = [t.strip() for t in search_terms.split(",") if t.strip()]
    sites = ["indeed", "linkedin"]
    all_results: list[pd.DataFrame] = []
    errors: list[str] = []

    def _scrape_one(term: str, site: str) -> pd.DataFrame | None:
        df = scrape_jobs(
            site_name=[site],
            search_term=term,
            location=location,
            results_wanted=results_per_site,
            hours_old=72,
            country_indeed="USA",
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
            }
        )

    if not jobs_list:
        return "Scraped jobs but none had usable descriptions."

    # Store raw jobs and track which search term found each one
    tool_store["fetched_jobs"] = jobs_list

    # ── Group by normalized job title ──
    # Strip seniority prefixes so "Senior Data Engineer" and "Data Engineer" group together
    _SENIORITY_RE = re.compile(
        r"^(senior|sr\.?|junior|jr\.?|lead|principal|staff|entry[- ]level|mid[- ]level)\s+",
        re.IGNORECASE,
    )

    def _normalize_title(title: str) -> str:
        t = _SENIORITY_RE.sub("", title.strip())
        return t.strip().title()

    groups: dict[str, list[int]] = {}
    for i, job in enumerate(jobs_list):
        group = _normalize_title(job.get("title", "Other"))
        groups.setdefault(group, []).append(i)

    # Sort by count descending and assign stable numbers
    sorted_groups = sorted(groups.items(), key=lambda x: -len(x[1]))
    tool_store["job_groups"] = {cat: idxs for cat, idxs in sorted_groups}

    # Build grouped summary (this is all the LLM sees)
    lines = [
        f"Fetched {len(jobs_list)} unique jobs in {len(groups)} title-based groups:"
    ]
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
    """Show a summary of everything collected so far: fetched jobs, selected jobs, extracted skills, curated skills, mapped skills, final skills, and saved skills."""
    lines = [
        f"All fetched jobs: {len(tool_store.get('fetched_jobs', []))}",
        f"Selected jobs: {len(tool_store.get('selected_jobs', []))}",
        f"Extracted skills: {len(tool_store.get('extracted_skills', []))}",
        f"Curated skills: {len(tool_store.get('curated_skills', []))}",
        f"Curriculum mapping: {len(tool_store.get('curriculum_mapping', []))}",
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
    Accepts group names, numbers, or "all" intents (comma-separated).
    Examples: "1, 2, 5", "Bioinformatics, Genetics", or "all".
    """
    groups = tool_store.get("job_groups", {})
    jobs = tool_store.get("fetched_jobs", [])
    if not groups:
        return "No job groups found. The coordinator needs to fetch jobs first."

    group_list = list(groups.items())  # already sorted by count desc
    requested = [g.strip() for g in group_names.split(",") if g.strip()]

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
def start_extraction() -> Command | str:
    """Start parallel skill extraction from selected job groups.
    Fans out one LLM call per job, merges duplicates, then returns
    control back to Skill Finder for teacher skill selection."""
    # Guard: if extraction already ran, do NOT re-run.
    existing = tool_store.get("extracted_skills", [])
    if existing:
        count = len(existing)
        return (
            f"⚠️ Extraction already complete: {count} merged skills are ready. "
            "Call get_skills_by_category to review them. "
            "Do NOT call select_jobs_by_group or start_extraction again."
        )
    jobs = tool_store.get("selected_jobs", [])
    if not jobs:
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update={"active_agent": "skill_finder"},
        )
    logger.info("start_extraction: routing to skill_extractor (%d jobs)", len(jobs))
    return Command(
        goto="skill_extractor",
        graph=Command.PARENT,
        # Keep active_agent as skill_finder — skill_extractor is a temporary
        # subgraph detour, not a real swarm agent. This ensures the checkpoint
        # never stores "skill_extractor" as active_agent, preventing KeyError
        # on __start__ routing when a new message arrives mid-extraction.
        update={"active_agent": "skill_finder"},
    )


# ═══════════════════════════════════════════════════════════════════
#  Curriculum Mapper Tools (hierarchical graph exploration)
# ═══════════════════════════════════════════════════════════════════


@tool
def list_chapters() -> str:
    """List all chapters in the curriculum knowledge graph.
    Returns chapter titles, indices, section counts, and existing skill counts.
    Call this first to get an overview of the course structure."""
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (b:BOOK)-[:HAS_CHAPTER]->(ch:BOOK_CHAPTER) "
                "OPTIONAL MATCH (ch)-[:HAS_SECTION]->(s:BOOK_SECTION) "
                "OPTIONAL MATCH (ch)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
                "OPTIONAL MATCH (ch)-[:HAS_SKILL]->(ms:MARKET_SKILL) "
                "WITH ch, count(DISTINCT s) AS sections, "
                "     count(DISTINCT sk) AS book_skills, "
                "     count(DISTINCT ms) AS market_skills "
                "RETURN ch.title AS title, ch.chapter_index AS idx, sections, "
                "       book_skills, market_skills "
                "ORDER BY ch.chapter_index"
            )
            chapters = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        logger.info(
            "[PERF] list_chapters Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j unavailable: {e}"
    except AuthError as e:
        return f"Neo4j auth failed: {e}"
    logger.info(
        "[PERF] list_chapters Neo4j took %.1fms (%d chapters)",
        (time.perf_counter() - t0) * 1000,
        len(chapters),
    )

    if not chapters:
        return "No chapters found in the knowledge graph."

    tool_store["chapters"] = chapters
    lines = [f"Course has {len(chapters)} chapters:"]
    for ch in chapters:
        ms = ch["market_skills"]
        ms_str = f", {ms} market skills" if ms else ""
        lines.append(
            f"  [{ch['idx']}] {ch['title']} — "
            f"{ch['sections']} sections, {ch['book_skills']} book skills{ms_str}"
        )
    lines.append("\nUse get_chapter_details with chapter numbers to drill deeper.")
    return "\n".join(lines)


@tool
def get_chapter_details(chapter_indices: str) -> str:
    """Get sections and existing BOOK_SKILL nodes for specific chapters.
    Args:
        chapter_indices: comma-separated chapter numbers (e.g. "1, 2, 4")
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    indices = [
        int(x.strip()) for x in chapter_indices.split(",") if x.strip().isdigit()
    ]
    if not indices:
        return "Please provide valid chapter numbers (e.g. '1, 2, 4')."

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            sections_result = session.run(
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SECTION]->(s:BOOK_SECTION) "
                "WHERE ch.chapter_index IN $indices "
                "OPTIONAL MATCH (s)-[:MENTIONS]->(c:CONCEPT) "
                "WITH ch, s, count(c) AS concept_count "
                "RETURN ch.chapter_index AS ch_idx, ch.title AS ch_title, "
                "       s.title AS section_title, s.section_index AS s_idx, concept_count "
                "ORDER BY ch.chapter_index, s.section_index",
                {"indices": indices},
            )
            sections = [dict(r) for r in sections_result]

            skills_result = session.run(
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
                "WHERE ch.chapter_index IN $indices "
                "OPTIONAL MATCH (sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) "
                "WITH ch, sk, collect(c.name) AS concepts "
                "RETURN ch.chapter_index AS ch_idx, sk.name AS skill, "
                "       sk.description AS description, concepts, "
                "       'book' AS skill_type "
                "ORDER BY ch.chapter_index, sk.name",
                {"indices": indices},
            )
            skills = [dict(r) for r in skills_result]

            market_skills_result = session.run(
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SKILL]->(ms:MARKET_SKILL) "
                "WHERE ch.chapter_index IN $indices "
                "OPTIONAL MATCH (ms)-[:REQUIRES_CONCEPT]->(c:CONCEPT) "
                "WITH ch, ms, collect(c.name) AS concepts "
                "RETURN ch.chapter_index AS ch_idx, ms.name AS skill, "
                "       ms.status AS status, ms.demand_pct AS demand_pct, "
                "       ms.category AS category, concepts, "
                "       'market' AS skill_type "
                "ORDER BY ch.chapter_index, ms.name",
                {"indices": indices},
            )
            market_skills = [dict(r) for r in market_skills_result]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        logger.info(
            "[PERF] get_chapter_details Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j unavailable: {e}"
    except AuthError as e:
        return f"Neo4j auth failed: {e}"
    logger.info(
        "[PERF] get_chapter_details Neo4j took %.1fms (%d sections, %d book skills, %d market skills)",
        (time.perf_counter() - t0) * 1000,
        len(sections),
        len(skills),
        len(market_skills),
    )

    # Group by chapter
    ch_sections: dict[int, list] = {}
    ch_skills: dict[int, list] = {}
    ch_market_skills: dict[int, list] = {}
    ch_titles: dict[int, str] = {}

    for s in sections:
        ch_sections.setdefault(s["ch_idx"], []).append(s)
        ch_titles[s["ch_idx"]] = s["ch_title"]
    for sk in skills:
        ch_skills.setdefault(sk["ch_idx"], []).append(sk)
    for ms in market_skills:
        ch_market_skills.setdefault(ms["ch_idx"], []).append(ms)

    lines = []
    all_idx = sorted(
        set(
            list(ch_sections.keys())
            + list(ch_skills.keys())
            + list(ch_market_skills.keys())
        )
    )
    for idx in all_idx:
        title = ch_titles.get(idx, f"Chapter {idx}")
        lines.append(f"\n{'=' * 60}")
        lines.append(f"[{idx}] {title}")
        lines.append(f"{'=' * 60}")

        secs = ch_sections.get(idx, [])
        if secs:
            lines.append("  Sections:")
            for s in secs:
                prefix = s["section_title"].split(" ")[0]
                lines.append(
                    f"    [{prefix}] {s['section_title']} ({s['concept_count']} concepts)"
                )

        sks = ch_skills.get(idx, [])
        if sks:
            lines.append("  Book Skills:")
            for sk in sks:
                concepts_flat = []
                for c in sk["concepts"]:
                    if isinstance(c, list):
                        concepts_flat.extend(c)
                    else:
                        concepts_flat.append(c)
                concepts_str = ", ".join(concepts_flat[:5])
                if len(concepts_flat) > 5:
                    concepts_str += f" (+{len(concepts_flat) - 5} more)"
                lines.append(f"    • {sk['skill']}")
                if concepts_str:
                    lines.append(f"      requires: {concepts_str}")

        mks = ch_market_skills.get(idx, [])
        if mks:
            lines.append("  Market Skills (already in graph):")
            for ms in mks:
                demand = ms.get("demand_pct", "?")
                status = ms.get("status", "?")
                lines.append(f"    ★ {ms['skill']} [{status}] (demand: {demand}%)")

    lines.append("\nUse get_section_concepts to drill into specific sections.")
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

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "UNWIND $refs AS ref "
                "MATCH (s:BOOK_SECTION) WHERE s.title STARTS WITH ref "
                "OPTIONAL MATCH (s)-[m:MENTIONS]->(c:CONCEPT) "
                "RETURN s.title AS section, c.name AS concept, m.definition AS definition "
                "ORDER BY s.title, c.name",
                {"refs": refs},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        logger.info(
            "[PERF] get_section_concepts Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j unavailable: {e}"
    except AuthError as e:
        return f"Neo4j auth failed: {e}"
    logger.info(
        "[PERF] get_section_concepts Neo4j took %.1fms (%d rows)",
        (time.perf_counter() - t0) * 1000,
        len(rows),
    )

    if not rows:
        return f"No sections found matching: {section_refs}"

    by_section: dict[str, list] = {}
    for r in rows:
        by_section.setdefault(r["section"], []).append(r)

    lines = []
    for section, concepts in by_section.items():
        lines.append(f"\n[{section}]")
        valid = [c for c in concepts if c.get("concept")]
        if valid:
            for c in valid:
                defn = c.get("definition", "")
                if defn:
                    defn = defn[:100] + "..." if len(defn) > 100 else defn
                    lines.append(f"  • {c['concept']}: {defn}")
                else:
                    lines.append(f"  • {c['concept']}")
        else:
            lines.append("  (no concepts)")

    return "\n".join(lines)


@tool
def check_skills_coverage(skill_names: str) -> str:
    """Check if market-extracted skills already exist in the knowledge graph.
    Searches both BOOK_SKILL nodes and CONCEPT nodes for matches.
    Args:
        skill_names: comma-separated EXACT skill names as returned by get_extracted_skills.
            Use the full competency statements — do NOT simplify to bare technology keywords.
            CORRECT: "Query and analyze data using SQL, Deploy containerized applications using Kubernetes"
            WRONG:   "SQL, Kubernetes"
    """
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    names = [n.strip() for n in skill_names.split(",") if n.strip()]
    if not names:
        return "Please provide skill names to check."

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "UNWIND $names AS skill_name "
                "CALL { "
                "  WITH skill_name "
                "  MATCH (sk:BOOK_SKILL) "
                "  WHERE toLower(toString(sk.name)) CONTAINS toLower(skill_name) "
                "  RETURN collect(DISTINCT sk.name) AS matching_skills "
                "} "
                "CALL { "
                "  WITH skill_name "
                "  MATCH (ms:MARKET_SKILL) "
                "  WHERE toLower(ms.name) CONTAINS toLower(skill_name) "
                "     OR toLower(skill_name) CONTAINS toLower(ms.name) "
                "  RETURN collect(DISTINCT ms.name) AS matching_market_skills "
                "} "
                "CALL { "
                "  WITH skill_name "
                "  MATCH (c:CONCEPT) "
                "  WITH c, skill_name, "
                "    CASE WHEN valueType(c.name) STARTS WITH 'STRING' "
                "         THEN c.name ELSE head(c.name) END AS cname "
                "  WHERE toLower(cname) = toLower(skill_name) "
                "  RETURN collect(DISTINCT cname) AS exact_concepts "
                "} "
                "CALL { "
                "  WITH skill_name "
                "  MATCH (c2:CONCEPT) "
                "  WITH c2, skill_name, "
                "    CASE WHEN valueType(c2.name) STARTS WITH 'STRING' "
                "         THEN c2.name ELSE head(c2.name) END AS cname "
                "  WHERE toLower(cname) CONTAINS toLower(skill_name) "
                "    AND toLower(cname) <> toLower(skill_name) "
                "  RETURN collect(DISTINCT cname)[0..5] AS related_concepts "
                "} "
                "RETURN skill_name, matching_skills, matching_market_skills, "
                "       exact_concepts, related_concepts",
                {"names": names},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        logger.info(
            "[PERF] check_skills_coverage Neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j unavailable: {e}"
    except AuthError as e:
        return f"Neo4j auth failed: {e}"
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
        f"{covered} covered by book, {partial} partial, {new} new"
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
def save_curriculum_mapping(mapping_json: str) -> str:
    """Save the curriculum mapping analysis results.
    Args:
        mapping_json: JSON array of objects with keys:
            - name: EXACT skill name from get_extracted_skills (e.g.
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

    tool_store["curriculum_mapping"] = mapping

    covered = [m for m in mapping if m.get("status") == "covered"]
    gaps = [m for m in mapping if m.get("status") == "gap"]
    new_topics = [m for m in mapping if m.get("status") == "new_topic_needed"]

    lines = [
        f"Curriculum mapping saved: {len(covered)} covered, "
        f"{len(gaps)} gaps, {len(new_topics)} new topics needed.",
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
    lines.append("\nTransfer to Job Analyst for teacher discussion.")
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
    """Fetch all concept names for a chapter from Neo4j."""
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SECTION]->(s:BOOK_SECTION)"
                "-[:MENTIONS]->(c:CONCEPT) "
                "WHERE ch.title = $title "
                "WITH c, CASE WHEN valueType(c.name) STARTS WITH 'STRING' "
                "  THEN c.name ELSE head(c.name) END AS cname "
                "RETURN DISTINCT cname ORDER BY cname",
                {"title": chapter_title},
            )
            return [r["cname"] for r in result]
    except (ServiceUnavailable, SessionExpired, OSError):
        _get_neo4j_driver(force_new=True)
        try:
            with _neo4j_session() as session:
                result = session.run(
                    "MATCH (ch:BOOK_CHAPTER)-[:HAS_SECTION]->(s:BOOK_SECTION)"
                    "-[:MENTIONS]->(c:CONCEPT) "
                    "WHERE ch.title = $title "
                    "WITH c, CASE WHEN valueType(c.name) STARTS WITH 'STRING' "
                    "  THEN c.name ELSE head(c.name) END AS cname "
                    "RETURN DISTINCT cname ORDER BY cname",
                    {"title": chapter_title},
                )
                return [r["cname"] for r in result]
        except Exception:
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
    approved = tool_store.get("selected_for_insertion", [])
    if not approved:
        return "No approved skills found. Teacher must approve skills first."

    t0 = time.perf_counter()
    mapping_list = tool_store.get("curriculum_mapping", [])
    mapping_lookup = {m["name"].lower(): m for m in mapping_list}

    skills_list = tool_store.get("extracted_skills", [])
    skills_lookup = {s["name"].lower(): s for s in skills_list}

    jobs = tool_store.get("selected_jobs", [])
    total_jobs = tool_store.get("total_jobs_for_extraction", len(jobs))

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
        source_job_urls = [
            j["url"]
            for j in jobs
            if re.search(re.escape(skill_name), j.get("description", ""), re.IGNORECASE)
        ]

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
    RELEVANT_TO_CHAPTER, SOURCED_FROM, and REQUIRES_CONCEPT relationships."""
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
    }

    try:
        with _neo4j_session() as session:
            # Step A: Create JOB_POSTING nodes
            for job in jobs:
                if not job.get("url"):
                    continue
                session.run(
                    "MERGE (j:JOB_POSTING {url: $url}) "
                    "SET j.title = $title, j.company = $company, "
                    "    j.site = $site, j.search_term = $search_term",
                    {
                        "url": job["url"],
                        "title": job.get("title", ""),
                        "company": job.get("company", ""),
                        "site": job.get("site", ""),
                        "search_term": job.get("search_term", ""),
                    },
                )
                stats["job_postings"] += 1

            # Steps B-E: For each skill, create node + relationships
            for skill_name, data in skill_concepts.items():
                # B: Create MARKET_SKILL node (with shared :SKILL label)
                session.run(
                    "MERGE (s:MARKET_SKILL:SKILL {name: $name}) "
                    "SET s.category = $category, "
                    "    s.frequency = $frequency, "
                    "    s.demand_pct = $demand_pct, "
                    "    s.priority = $priority, "
                    "    s.status = $status, "
                    "    s.target_chapter = $target_chapter, "
                    "    s.rationale = $rationale, "
                    "    s.reasoning = $reasoning, "
                    "    s.source = 'market_demand', "
                    "    s.created_at = datetime()",
                    {
                        "name": skill_name,
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

                # C: Link chapter -> skill (reuses HAS_SKILL pattern)
                chapter = data.get("chapter_title")
                if chapter:
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (ch:BOOK_CHAPTER {title: $chapter}) "
                        "MERGE (ch)-[:HAS_SKILL]->(s)",
                        {"name": skill_name, "chapter": chapter},
                    )
                    stats["chapter_links"] += 1

                # D: Link to job postings
                for url in data.get("source_job_urls", []):
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (j:JOB_POSTING {url: $url}) "
                        "MERGE (s)-[:SOURCED_FROM]->(j)",
                        {"name": skill_name, "url": url},
                    )
                    stats["sourced_from"] += 1

                # E: Link to existing concepts
                for concept_name in data.get("existing_concepts", []):
                    session.run(
                        "MATCH (s:MARKET_SKILL {name: $name}) "
                        "MATCH (c:CONCEPT) WHERE c.name = $cname "
                        "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                        {"name": skill_name, "cname": concept_name},
                    )
                    stats["existing_concept_links"] += 1

                # E: Create new concepts and link
                for new_concept in data.get("new_concepts", []):
                    session.run(
                        "MERGE (c:CONCEPT {name: $cname}) "
                        "SET c.description = $desc "
                        "WITH c "
                        "MATCH (s:MARKET_SKILL {name: $sname}) "
                        "MERGE (s)-[:REQUIRES_CONCEPT]->(c)",
                        {
                            "cname": new_concept["name"],
                            "desc": new_concept.get("description", ""),
                            "sname": skill_name,
                        },
                    )
                    stats["new_concepts"] += 1

    except (ServiceUnavailable, SessionExpired, OSError) as e:
        _get_neo4j_driver(force_new=True)
        logger.info(
            "[PERF] insert_market_skills_to_neo4j FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j write failed: {e}. Connection was reset — try again."

    logger.info(
        "[PERF] insert_market_skills_to_neo4j took %.1fms (stats=%s)",
        (time.perf_counter() - t0) * 1000,
        stats,
    )
    tool_store["insertion_results"] = stats

    return (
        f"✅ Neo4j write complete!\n"
        f"  MARKET_SKILL nodes created: {stats['skills']}\n"
        f"  JOB_POSTING nodes created: {stats['job_postings']}\n"
        f"  HAS_SKILL links: {stats['chapter_links']}\n"
        f"  SOURCED_FROM links: {stats['sourced_from']}\n"
        f"  Existing concept links: {stats['existing_concept_links']}\n"
        f"  New concepts created: {stats['new_concepts']}"
    )


@tool
def delete_market_skills(skill_names: str) -> str:
    """Delete MARKET_SKILL nodes and their relationships from Neo4j.
    Also removes orphaned JOB_POSTING nodes (those with no remaining SOURCED_FROM links).
    Args:
        skill_names: comma-separated MARKET_SKILL names to delete,
            or "all" to delete every MARKET_SKILL node.
    """
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    names = [n.strip() for n in skill_names.split(",") if n.strip()]
    delete_all = len(names) == 1 and names[0].lower() == "all"

    try:
        with _neo4j_session() as session:
            if delete_all:
                result = session.run(
                    "MATCH (s:MARKET_SKILL) DETACH DELETE s RETURN count(s) AS deleted"
                )
                deleted = result.single()["deleted"]
            else:
                result = session.run(
                    "UNWIND $names AS name "
                    "MATCH (s:MARKET_SKILL) WHERE toLower(s.name) = toLower(name) "
                    "DETACH DELETE s "
                    "RETURN count(s) AS deleted",
                    {"names": names},
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

    except (ServiceUnavailable, SessionExpired, OSError) as e:
        _get_neo4j_driver(force_new=True)
        return f"Neo4j unavailable: {e}. Connection was reset — try again."

    scope = "all" if delete_all else f"matching {skill_names}"
    return (
        f"Deleted {deleted} MARKET_SKILL node(s) ({scope}).\n"
        f"Cleaned up {orphans} orphaned JOB_POSTING node(s)."
    )


# ═══════════════════════════════════════════════════════════════════
#  Skill Finder Tools (NEW)
# ═══════════════════════════════════════════════════════════════════


@tool
def get_skills_by_category() -> str:
    """Return extracted skills grouped by category with frequency counts.
    Call this after extraction completes to present skills to the teacher."""
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


@tool
def approve_skill_selection(selection_json: str) -> str:
    """Save the teacher's curated skill selection for downstream processing.
    Args:
        selection_json: JSON array of skill names the teacher wants to keep.
            Example: ["Query data using SQL", "Deploy apps using Kubernetes"]
            Or a JSON object with category-based selection:
            {"categories": ["cloud", "database"], "specific": ["Train ML models"], "top_n_per_category": 3}
    """
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
    mapped = tool_store.get("mapped_skills")
    if not mapped:
        # Fall back to curriculum_mapping if mapped_skills not set
        mapping = tool_store.get("curriculum_mapping", [])
        if not mapping:
            return "No mapped skills found. Curriculum Mapper must run first."

        # Build mapped_skills from curriculum_mapping
        mapped = {}
        for m in mapping:
            if m.get("status") in ("gap", "new_topic_needed"):
                chapter = m.get("target_chapter", "unassigned")
                mapped.setdefault(chapter, []).append(m["name"])
        tool_store["mapped_skills"] = mapped

    lines = [f"Mapped skills across {len(mapped)} chapters:"]
    for chapter, skills in mapped.items():
        lines.append(f"\n  {chapter}: {len(skills)} skills")
        for s in skills:
            lines.append(f"    • {s}")
    return "\n".join(lines)


@tool
def load_book_skills_for_chapters(chapter_titles: str) -> str:
    """Query Neo4j for existing BOOK_SKILL nodes linked to the given chapters.
    Args:
        chapter_titles: comma-separated chapter titles to check.
    Returns per-chapter book skill lists."""
    from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

    titles = [t.strip() for t in chapter_titles.split(",") if t.strip()]
    if not titles:
        return "Please provide chapter titles."

    t0 = time.perf_counter()
    try:
        with _neo4j_session() as session:
            result = session.run(
                "UNWIND $titles AS title "
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
                "WHERE ch.title = title "
                "OPTIONAL MATCH (sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) "
                "WITH ch.title AS chapter, sk.name AS skill, "
                "     sk.description AS description, "
                "     collect(DISTINCT c.name) AS concepts "
                "RETURN chapter, skill, description, concepts "
                "ORDER BY chapter, skill",
                {"titles": titles},
            )
            rows = [dict(r) for r in result]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        logger.info(
            "[PERF] load_book_skills_for_chapters FAILED in %.1fms",
            (time.perf_counter() - t0) * 1000,
        )
        return f"Neo4j unavailable: {e}"
    except AuthError as e:
        return f"Neo4j auth failed: {e}"
    logger.info(
        "[PERF] load_book_skills_for_chapters took %.1fms (%d rows)",
        (time.perf_counter() - t0) * 1000,
        len(rows),
    )

    if not rows:
        return f"No book skills found for chapters: {chapter_titles}"

    by_chapter: dict[str, list[dict]] = {}
    for r in rows:
        by_chapter.setdefault(r["chapter"], []).append(r)

    lines = [f"Book skills for {len(by_chapter)} chapters:"]
    for chapter, skills in by_chapter.items():
        lines.append(f"\n  {chapter} ({len(skills)} book skills):")
        for sk in skills:
            desc = sk.get("description", "")
            desc_str = f" — {desc[:80]}" if desc else ""
            lines.append(f"    • {sk['skill']}{desc_str}")
    return "\n".join(lines)


@tool
def compare_and_clean(chapter_title: str) -> str:
    """Compare mapped market skills vs existing book skills for one chapter.
    Uses LLM to decide which market skills are redundant.
    Args:
        chapter_title: the chapter to clean.
    Returns kept/dropped skill lists with reasoning."""
    mapped = tool_store.get("mapped_skills", {})
    market_skills = mapped.get(chapter_title, [])
    if not market_skills:
        return f"No mapped market skills for chapter: {chapter_title}"

    # Fetch book skills for this chapter
    from neo4j.exceptions import ServiceUnavailable, SessionExpired

    book_skills: list[str] = []
    try:
        with _neo4j_session() as session:
            result = session.run(
                "MATCH (ch:BOOK_CHAPTER)-[:HAS_SKILL]->(sk:BOOK_SKILL) "
                "WHERE ch.title = $title "
                "RETURN sk.name AS name, sk.description AS description",
                {"title": chapter_title},
            )
            book_skills_data = [dict(r) for r in result]
            book_skills = [
                f"{s['name']}: {s.get('description', '')}" for s in book_skills_data
            ]
    except (ServiceUnavailable, SessionExpired, OSError) as e:
        _get_neo4j_driver(force_new=True)
        return f"Neo4j unavailable: {e}"

    if not book_skills:
        # No book skills to compare against — keep all market skills
        result_data = {
            "chapter": chapter_title,
            "kept": market_skills,
            "dropped": [],
        }
        _update_cleaned_results(result_data)
        return (
            f"Chapter '{chapter_title}': No book skills to compare against. "
            f"Keeping all {len(market_skills)} market skills."
        )

    # LLM comparison
    llm = _get_extraction_llm()
    prompt = (
        "You are a curriculum deduplication expert. Compare market skills against "
        "existing book skills for redundancy.\n\n"
        f"## Chapter: {chapter_title}\n\n"
        "## Existing Book Skills:\n"
        + "\n".join(f"- {s}" for s in book_skills)
        + "\n\n## New Market Skills to evaluate:\n"
        + "\n".join(f"- {s}" for s in market_skills)
        + "\n\n"
        "For each market skill, decide: KEEP or DROP.\n"
        "DROP only if a book skill teaches essentially the same competency.\n"
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


# ═══════════════════════════════════════════════════════════════════
#  Tool Groups (used by each agent)
# ═══════════════════════════════════════════════════════════════════

SUPERVISOR_TOOLS = [
    save_skills_for_insertion,
    delete_market_skills,
    show_current_state,
]

SKILL_FINDER_TOOLS = [
    fetch_jobs,
    select_jobs_by_group,
    start_extraction,
    get_skills_by_category,
    approve_skill_selection,
]

CURRICULUM_MAPPER_TOOLS = [
    list_chapters,
    get_chapter_details,
    get_section_concepts,
    check_skills_coverage,
    get_extracted_skills,
    save_curriculum_mapping,
]

SKILL_CLEANER_TOOLS = [
    load_mapped_skills,
    load_book_skills_for_chapters,
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
