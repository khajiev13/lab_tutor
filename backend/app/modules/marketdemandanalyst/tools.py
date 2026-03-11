import json
import logging
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager

import pandas as pd
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.types import Command

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
#  Programmatic helpers — keep heavy data out of the LLM
# ═══════════════════════════════════════════════════════════════════


def _get_extraction_llm() -> ChatOpenAI:
    """Create an LLM instance for skill extraction batches."""
    return ChatOpenAI(
        model=os.environ.get(
            "LAB_TUTOR_LLM_MODEL",
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        ),
        base_url=os.environ.get(
            "LAB_TUTOR_LLM_BASE_URL",
            os.environ.get("OPENAI_BASE_URL"),
        ),
        api_key=os.environ.get(
            "LAB_TUTOR_LLM_API_KEY",
            os.environ.get("OPENAI_API_KEY", ""),
        ),
        temperature=0,
        timeout=120,
    )


_BATCH_EXTRACTION_PROMPT = """\
You are a recruiter analyst. Extract ALL technical skills, tools, \
technologies, and methodologies mentioned in these job descriptions.

For each skill:
- name: canonical name (merge synonyms, e.g. "k8s"="Kubernetes", "Postgres"="PostgreSQL")
- category: a short label for the skill domain (e.g. language, framework, cloud, \
database, tool, methodology, soft_skill — pick the best fit)

Return ONLY a JSON array. Example:
[{{"name": "Python", "category": "language"}}, {{"name": "PCR", "category": "lab_technique"}}]

Job descriptions to analyze:

{descriptions}

Return ONLY a valid JSON array of skill objects, nothing else."""


def _extract_batch(llm: ChatOpenAI, batch: list[dict], batch_num: int) -> list[dict]:
    """Extract skills from a single batch of jobs via LLM."""
    desc_parts = []
    for job in batch:
        desc = job.get("description", "")[:3000]
        desc_parts.append(f"--- {job['title']} @ {job['company']} ---\n{desc}")
    prompt = _BATCH_EXTRACTION_PROMPT.format(descriptions="\n\n".join(desc_parts))

    response = llm.invoke(prompt, config={"callbacks": []})
    text = response.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        skills = json.loads(text)
        if isinstance(skills, list):
            return skills
    except json.JSONDecodeError:
        pass
    return []


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
    """Show a summary of everything collected so far: fetched jobs, selected jobs, extracted skills, graph data, and saved skills."""
    lines = [
        f"All fetched jobs: {len(tool_store.get('fetched_jobs', []))}",
        f"Selected jobs: {len(tool_store.get('selected_jobs', []))}",
        f"Extracted skills: {len(tool_store.get('extracted_skills', []))}",
        f"Graph skills: {len(tool_store.get('existing_graph_skills', []))}",
        f"Graph concepts: {len(tool_store.get('existing_concepts', []))}",
        f"Curriculum mapping: {len(tool_store.get('curriculum_mapping', []))}",
        f"Saved for insertion: {len(tool_store.get('selected_for_insertion', []))}",
    ]
    return " | ".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Job Selector Tools
# ═══════════════════════════════════════════════════════════════════


@tool
def select_jobs_by_group(group_names: str) -> str:
    """Select entire groups from the fetched jobs.
    Accepts group names OR numbers (comma-separated).
    Examples: "1, 2, 5" or "Bioinformatics, Genetics".
    """
    groups = tool_store.get("job_groups", {})
    jobs = tool_store.get("fetched_jobs", [])
    if not groups:
        return "No job groups found. The coordinator needs to fetch jobs first."

    group_list = list(groups.items())  # already sorted by count desc
    requested = [g.strip() for g in group_names.split(",") if g.strip()]

    selected_indices: set[int] = set()
    matched_groups: list[str] = []

    for req in requested:
        # Try as number first
        if req.isdigit():
            idx = int(req) - 1
            if 0 <= idx < len(group_list):
                cat, idxs = group_list[idx]
                selected_indices.update(idxs)
                matched_groups.append(f"{cat} ({len(idxs)})")
            continue
        # Try as substring match on group name
        for cat, idxs in group_list:
            if req.lower() in cat.lower():
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


# ═══════════════════════════════════════════════════════════════════
#  Skill Extraction (programmatic — no LLM agent needed)
# ═══════════════════════════════════════════════════════════════════

# Module-level name map for preserving original casing across batches
_extraction_name_map: dict[str, str] = {}


def _run_skill_extraction() -> str:
    """Run parallel LLM extraction on selected jobs and return a summary.

    This is called programmatically by start_analysis_pipeline — it is NOT
    a LangChain tool and is never invoked directly by an LLM.
    """
    jobs = tool_store.get("selected_jobs", [])
    if not jobs:
        return "No selected jobs in store. Fetch and select jobs first."

    total = len(jobs)
    batch_size = 5
    batches = [jobs[i : i + batch_size] for i in range(0, total, batch_size)]
    llm = _get_extraction_llm()

    all_batch_skills: list[list[dict]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(len(batches), 5)) as executor:
        futures = {
            executor.submit(_extract_batch, llm, batch, i): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                all_batch_skills.append(future.result())
            except Exception as e:
                errors.append(f"Batch {batch_num}: {type(e).__name__}: {e}")

    # Fan-in: merge and deduplicate
    skill_counter: Counter[str] = Counter()
    skill_categories: dict[str, str] = {}
    for batch_skills in all_batch_skills:
        seen_in_batch: set[str] = set()
        for s in batch_skills:
            name = s.get("name", "").strip()
            cat = s.get("category", "unknown")
            if not name:
                continue
            canonical = name.lower()
            if canonical not in seen_in_batch:
                seen_in_batch.add(canonical)
                skill_counter[canonical] += 1
                if canonical not in skill_categories:
                    skill_categories[canonical] = cat
                    _extraction_name_map[canonical] = name

    results = [
        {
            "name": _extraction_name_map.get(skill, skill),
            "category": skill_categories.get(skill, "unknown"),
            "frequency": count,
            "pct": round(count / total * 100, 1),
        }
        for skill, count in skill_counter.most_common()
    ]

    tool_store["extracted_skills"] = results
    tool_store["total_jobs_for_extraction"] = total

    lines = [
        f"Extracted {len(results)} unique skills from {total} jobs "
        f"({len(batches)} batches of {batch_size}, {len(errors)} failures)."
    ]
    for s in results[:25]:
        lines.append(
            f"  {s['name']} ({s['category']}) — {s['frequency']}/{total} ({s['pct']}%)"
        )
    if len(results) > 25:
        lines.append(f"  ... and {len(results) - 25} more")
    if errors:
        lines.append(f"Warnings: {'; '.join(errors)}")
    return "\n".join(lines)


@tool
def start_analysis_pipeline() -> Command:
    """Run skill extraction from selected jobs and route directly to
    Curriculum Mapper for analysis. This is a one-shot tool: extraction
    runs programmatically (parallel LLM batches), then the mapper agent
    takes over automatically. No further action needed from the supervisor."""
    logger.info("start_analysis_pipeline: running extraction…")
    t0 = time.perf_counter()
    _run_skill_extraction()
    logger.info(
        "[PERF] start_analysis_pipeline: extraction took %.1fms",
        (time.perf_counter() - t0) * 1000,
    )
    logger.info(
        "start_analysis_pipeline: extraction done, routing to curriculum_mapper"
    )
    return Command(
        goto="curriculum_mapper",
        graph=Command.PARENT,
        update={"active_agent": "curriculum_mapper"},
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
        skill_names: comma-separated skill names to check
            (e.g. "Python, Data Modeling, ETL, Airflow")
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
            - name: skill name
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
                # B: Create MARKET_SKILL node
                session.run(
                    "MERGE (s:MARKET_SKILL {name: $name}) "
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
#  Tool Groups (used by each agent)
# ═══════════════════════════════════════════════════════════════════

SUPERVISOR_TOOLS = [
    fetch_jobs,
    select_jobs_by_group,
    start_analysis_pipeline,
    save_skills_for_insertion,
    delete_market_skills,
    show_current_state,
]

CURRICULUM_MAPPER_TOOLS = [
    list_chapters,
    get_chapter_details,
    get_section_concepts,
    check_skills_coverage,
    get_extracted_skills,
    save_curriculum_mapping,
]

CONCEPT_LINKER_TOOLS = [
    extract_concepts_for_skills,
    insert_market_skills_to_neo4j,
]

ALL_TOOLS = SUPERVISOR_TOOLS + CURRICULUM_MAPPER_TOOLS + CONCEPT_LINKER_TOOLS
