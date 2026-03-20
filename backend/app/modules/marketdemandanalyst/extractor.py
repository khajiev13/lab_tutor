"""Skill Extractor Subgraph — LangGraph map-reduce (Send API).

Fan-out: one `Send("extract_one", ...)` per job listing.
Fan-in: `synthesize_skills` deduplicates, counts frequency, then
`merge_similar_skills` uses LLM to cluster semantically similar skills.
Finally returns `Command(goto="skill_finder")` in the parent swarm.
"""

import json
import logging
import operator
import os
from collections import Counter
from typing import Annotated, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.types import Command, Send

from .state import tool_store

logger = logging.getLogger(__name__)

# ── State schemas ───────────────────────────────────────────────


class ExtractorState(TypedDict):
    job: dict  # single job dict (populated by Send for each fan-out)
    skills: Annotated[list[dict], operator.add]  # reducer: accumulates across branches


# ── LLM factory ─────────────────────────────────────────────────


def _get_extraction_llm(timeout_seconds: int = 120) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get(
            "LAB_TUTOR_LLM_MODEL",
            os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        ),
        base_url=os.environ.get(
            "LAB_TUTOR_LLM_BASE_URL",
            os.environ.get("OPENAI_BASE_URL"),
        ),
        api_key=os.environ.get(  # type: ignore[arg-type]
            "LAB_TUTOR_LLM_API_KEY",
            os.environ.get("OPENAI_API_KEY", ""),
        ),
        temperature=0,
        timeout=timeout_seconds,
        # Avoid multi-minute stalls from automatic retries during extraction.
        max_retries=0,
    )


# ── Per-job extraction prompt ───────────────────────────────────

_SINGLE_JOB_EXTRACTION_PROMPT = """\
You are a curriculum designer mapping job market demands to teachable competencies.
Extract actionable skills from the single job description below.

DEFINITION OF A SKILL:
A skill is a competency statement describing what a professional CAN DO. \
It must combine an action verb + a task + optionally a technology or context.
  CORRECT: "Implement distributed data pipelines using Apache Spark"
  CORRECT: "Design and query relational databases with SQL"
  CORRECT: "Apply machine learning classification algorithms to structured datasets"
  WRONG:   "Apache Spark"          — tool name only, not a competency
  WRONG:   "SQL knowledge"         — not an actionable statement
  WRONG:   "Good communication"    — soft skill, ignore entirely

RULES:
1. Every skill name MUST start with an action verb: Implement, Apply, Design, Build, \
Write, Analyze, Deploy, Configure, Train, Evaluate, Query, Optimize, Process, etc.
2. Merge synonyms into one canonical skill: \
"k8s" and "Kubernetes" → "Deploy containerized applications using Kubernetes"; \
"Postgres" and "PostgreSQL" → "Query and optimize PostgreSQL databases".
3. Ignore: soft skills, vague requirements ("fast learner", "team player"), \
years-of-experience requirements, and internal company systems.
4. Focus on skills teachable in a university course for entry-level candidates.

For each extracted skill provide:
- name: the competency statement starting with an action verb
- category: the skill domain — one of: language, framework, cloud, database, \
distributed_computing, machine_learning, data_processing, devops, tool, methodology

Return ONLY a valid JSON array. Example:
[
  {{"name": "Implement MapReduce jobs for large-scale data processing", "category": "distributed_computing"}},
  {{"name": "Train and evaluate supervised machine learning models", "category": "machine_learning"}}
]

--- {title} @ {company} ---
{description}

Return ONLY a valid JSON array, nothing else."""


# ── Node: extract skills from one job ───────────────────────────


def extract_one(state: ExtractorState) -> dict:
    """Extract skills from a single job listing via LLM."""
    job = state["job"]
    title = job.get("title", "N/A")
    company = job.get("company", "N/A")
    description = job.get("description", "")[:4000]

    prompt = _SINGLE_JOB_EXTRACTION_PROMPT.format(
        title=title, company=company, description=description
    )

    llm = _get_extraction_llm(timeout_seconds=90)
    response = llm.invoke(prompt, config={"callbacks": []})
    text = str(response.content).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        skills = json.loads(text)
        if isinstance(skills, list):
            # Tag each skill with provenance
            for s in skills:
                s["_source_title"] = title
                s["_source_company"] = company
                s["_source_url"] = job.get("url", "")
            logger.info("extract_one: %s @ %s → %d skills", title, company, len(skills))
            return {"skills": skills}
    except json.JSONDecodeError:
        logger.warning("extract_one: failed to parse JSON for %s @ %s", title, company)

    return {"skills": []}


# ── Conditional edge: fan-out one Send per job ──────────────────


def fan_out(state: ExtractorState) -> list[Send]:
    """Read selected jobs from tool_store and fan out one Send per job."""
    jobs = tool_store.get("selected_jobs", [])
    if not jobs:
        logger.warning("fan_out: no selected_jobs in tool_store")
        return []
    logger.info("fan_out: dispatching %d parallel extraction tasks", len(jobs))
    return [Send("extract_one", {"job": job}) for job in jobs]


# ── Node: synthesize all extracted skills ───────────────────────


def synthesize_skills(state: ExtractorState) -> dict:
    """Deduplicate, count frequency, store in tool_store. Routes to merge_similar_skills."""
    all_skills: list[dict] = state.get("skills", [])
    total_jobs = len(tool_store.get("selected_jobs", []))

    skill_counter: Counter[str] = Counter()
    skill_categories: dict[str, str] = {}
    name_map: dict[str, str] = {}  # canonical → original casing
    skill_urls: dict[str, set[str]] = {}  # canonical → set of source job URLs

    for s in all_skills:
        name = s.get("name", "").strip()
        cat = s.get("category", "unknown")
        if not name:
            continue
        canonical = name.lower()
        skill_counter[canonical] += 1
        if canonical not in skill_categories:
            skill_categories[canonical] = cat
            name_map[canonical] = name
        url = s.get("_source_url", "")
        if url:
            skill_urls.setdefault(canonical, set()).add(url)

    results = [
        {
            "name": name_map.get(skill, skill),
            "category": skill_categories.get(skill, "unknown"),
            "frequency": count,
            "pct": round(count / max(total_jobs, 1) * 100, 1),
        }
        for skill, count in skill_counter.most_common()
    ]

    tool_store["_raw_extracted_skills"] = results
    tool_store["_raw_skill_urls"] = {k: list(v) for k, v in skill_urls.items()}
    tool_store["total_jobs_for_extraction"] = total_jobs

    logger.info(
        "synthesize_skills: %d unique skills from %d jobs", len(results), total_jobs
    )

    return {"skills": []}  # clear accumulated skills for merge step


# ── Merge prompt ────────────────────────────────────────────────

_MERGE_PROMPT = """\
You are a curriculum analyst. Below is a list of skills extracted from job postings.
Many skills are semantically identical but phrased differently. Your task:

1. Cluster skills that describe the same competency (e.g. "Deploy on AWS" and \
"Deploy applications using AWS" are the same).
2. For each cluster, pick the BEST original name from the cluster — the one \
that is already a proper competency statement. Do NOT invent a new name.
3. Assign a category to each merged skill.
4. Sum frequencies across merged skills.

CRITICAL — The canonical name MUST be a proper competency statement:
  - Must start with an action verb: Implement, Apply, Design, Build, Write, \
Analyze, Deploy, Configure, Train, Evaluate, Query, Optimize, Process, Extract, etc.
  - Must describe what a professional CAN DO (verb + task + optional technology).
  - CORRECT: "Query and analyze data using SQL"
  - CORRECT: "Deploy containerized applications using Kubernetes"
  - WRONG: "SQL Querying and Analysis"  — not an action-verb competency
  - WRONG: "Python Programming"          — tool name only, no action verb+task
  - WRONG: "Machine Learning Operations (MLOps)" — noun phrase, not a competency

If none of the skills in a cluster is a proper competency statement, construct \
one using the pattern: <ActionVerb> <task description> using <technology>.

Categories (pick one): language, framework, cloud, database, distributed_computing, \
machine_learning, data_processing, devops, tool, methodology

## Skills to merge:
{skill_list}

Return ONLY valid JSON — an array of objects:
[
  {{
    "name": "Canonical Skill Name (proper competency statement)",
    "category": "category",
    "frequency": 5,
    "merged_from": ["original name 1", "original name 2"]
  }}
]
"""


def _build_skill_job_urls(
    skills: list[dict], raw_urls: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Map each canonical skill name (lowercased) to its source job URLs.

    For merged skills, unions URLs from all `merged_from` originals plus the
    canonical name itself.  For raw (non-merged) skills, uses the name directly.
    """
    result: dict[str, list[str]] = {}
    for item in skills:
        urls: set[str] = set()
        for orig in item.get("merged_from", []):
            urls.update(raw_urls.get(orig.lower(), []))
        urls.update(raw_urls.get(item["name"].lower(), []))
        result[item["name"].lower()] = list(urls)
    return result


def merge_similar_skills(state: ExtractorState) -> Command:
    """LLM-based semantic deduplication of extracted skills.

    Clusters similar skills, picks canonical names, sums frequencies,
    then routes to skill_finder in the parent swarm.
    """
    raw_skills = tool_store.get("_raw_extracted_skills", [])
    raw_urls: dict[str, list[str]] = tool_store.get("_raw_skill_urls", {})
    total_jobs = tool_store.get("total_jobs_for_extraction", 1)

    if not raw_skills:
        logger.warning("merge_similar_skills: no raw skills to merge")
        tool_store["extracted_skills"] = []
        tool_store["skill_job_urls"] = {}
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update={"active_agent": "skill_finder"},
        )

    # If few enough skills, skip LLM merge
    if len(raw_skills) <= 10:
        tool_store["extracted_skills"] = raw_skills
        tool_store["skill_job_urls"] = _build_skill_job_urls(raw_skills, raw_urls)
        logger.info(
            "merge_similar_skills: %d skills (skipped merge, too few)", len(raw_skills)
        )
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update={"active_agent": "skill_finder"},
        )

    # Guardrail: very large skill sets can make the merge prompt too big and
    # stall the SSE stream for minutes if the provider times out.
    if len(raw_skills) > 150:
        tool_store["extracted_skills"] = raw_skills
        tool_store["skill_job_urls"] = _build_skill_job_urls(raw_skills, raw_urls)
        logger.warning(
            "merge_similar_skills: %d skills (skipped merge, too many for safe LLM merge)",
            len(raw_skills),
        )
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update={"active_agent": "skill_finder"},
        )

    skill_list = "\n".join(
        f"- {s['name']} (category: {s['category']}, frequency: {s['frequency']})"
        for s in raw_skills
    )

    llm = _get_extraction_llm(timeout_seconds=45)
    prompt = _MERGE_PROMPT.format(skill_list=skill_list)

    try:
        response = llm.invoke(prompt, config={"callbacks": []})
        text = str(response.content).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        merged = json.loads(text)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("merge_similar_skills: LLM parse error, using raw skills: %s", e)
        tool_store["extracted_skills"] = raw_skills
        tool_store["skill_job_urls"] = _build_skill_job_urls(raw_skills, raw_urls)
        return Command(
            goto="skill_finder",
            graph=Command.PARENT,
            update={"active_agent": "skill_finder"},
        )

    # Post-merge validation: ensure every name is a proper competency statement
    # (starts with an action verb). If the LLM still produced a noun phrase,
    # fall back to the best original from merged_from.
    _ACTION_VERBS = {
        "implement",
        "apply",
        "design",
        "build",
        "write",
        "analyze",
        "analyse",
        "deploy",
        "configure",
        "train",
        "evaluate",
        "query",
        "optimize",
        "process",
        "processes",
        "extract",
        "transform",
        "load",
        "develop",
        "create",
        "manage",
        "orchestrate",
        "integrate",
        "monitor",
        "debug",
        "test",
        "automate",
        "schedule",
        "stream",
        "ingest",
        "model",
        "visualize",
        "visualise",
        "run",
        "use",
        "work",
        "perform",
        "construct",
        "compute",
        "calculate",
        "identify",
        "detect",
        "classify",
        "predict",
        "generate",
        "migrate",
        "scale",
        "tune",
        "profile",
        "benchmark",
        "building",
        "implementing",
        "developing",
        "designing",
        "applying",
        "deploying",
        "writing",
        "analyzing",
        "training",
        "evaluating",
        "querying",
        "optimizing",
        "processing",
        "extracting",
        "transforming",
        "managing",
        "orchestrating",
        "integrating",
        "monitoring",
        "debugging",
        "testing",
        "automating",
        "scheduling",
        "streaming",
        "ingesting",
        "modeling",
        "visualizing",
    }
    # Build a lookup of raw skill names for fallback
    raw_name_set: dict[str, dict] = {s["name"]: s for s in raw_skills}

    for item in merged:
        name = item.get("name", "")
        first_word = name.split()[0].lower() if name else ""
        if first_word not in _ACTION_VERBS:
            # Try to find a good original from merged_from
            originals = item.get("merged_from", [])
            best_original = None
            for orig in originals:
                orig_first = orig.split()[0].lower().rstrip("s") if orig else ""
                if orig_first in _ACTION_VERBS:
                    best_original = orig
                    break
            if best_original:
                logger.info(
                    "merge validation: replaced non-competency '%s' → '%s'",
                    name,
                    best_original,
                )
                item["name"] = best_original
            else:
                # Last resort: use the highest-frequency original
                best_by_freq = max(
                    (raw_name_set.get(o, {}) for o in originals),
                    key=lambda s: s.get("frequency", 0),
                    default={},
                )
                if best_by_freq.get("name"):
                    logger.info(
                        "merge validation: no action-verb original for '%s', using '%s' (highest freq)",
                        name,
                        best_by_freq["name"],
                    )
                    item["name"] = best_by_freq["name"]

    # Recalculate pct from merged frequencies
    for s in merged:
        s["pct"] = round(s.get("frequency", 0) / max(total_jobs, 1) * 100, 1)

    # Sort by frequency descending
    merged.sort(key=lambda x: -x.get("frequency", 0))

    tool_store["extracted_skills"] = merged
    tool_store["skill_job_urls"] = _build_skill_job_urls(merged, raw_urls)
    logger.info(
        "merge_similar_skills: %d raw → %d merged skills",
        len(raw_skills),
        len(merged),
    )

    return Command(
        goto="skill_finder",
        graph=Command.PARENT,
        update={"active_agent": "skill_finder"},
    )


# ── Assemble the subgraph ──────────────────────────────────────

_builder = StateGraph(ExtractorState)
_builder.add_node("extract_one", extract_one)
_builder.add_node("synthesize_skills", synthesize_skills)
_builder.add_node("merge_similar_skills", merge_similar_skills)
_builder.add_conditional_edges(START, fan_out, ["extract_one"])
_builder.add_edge("extract_one", "synthesize_skills")
_builder.add_edge("synthesize_skills", "merge_similar_skills")

skill_extractor_subgraph = _builder.compile()
