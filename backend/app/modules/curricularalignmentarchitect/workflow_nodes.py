"""LangGraph node functions for the book-selection workflow V3."""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Send, interrupt
from pydantic import SecretStr

from app.core.settings import settings

from .tools import (
    DOWNLOAD_SEARCH_TOOLS,
    DOWNLOAD_SEARCH_TOOLS_BY_NAME,
    TOOLS,
    TOOLS_BY_NAME,
    download_file_from_url,
    googlebooksqueryrun,
    tavily_search,
)
from .workflow_models import (
    DEFAULT_COURSE_LEVEL,
    VALID_COURSE_LEVELS,
    BookMeritScores,
    CandidateURLList,
    DiscoveredBookList,
    DiscoveryState,
    DownloadState,
    ScoringState,
    SearchQueryBatch,
    WorkflowState,
)
from .workflow_prompts import (
    DOWNLOAD_SEARCH_PROMPT,
    PER_QUERY_EXTRACTION_PROMPT,
    QUERY_GENERATION_PROMPT,
    RESEARCH_PROMPT,
    SCORING_PROMPT_TEMPLATE,
)
from .workflow_utils import (
    compute_finals,
    course_summary,
    exec_tools,
    pick_best_entry,
    syllabus_sequence,
    titles_match,
)

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────
MAX_RESEARCH_ROUNDS = 5
MAX_DOWNLOAD_SEARCH_ROUNDS = 4
MAX_DOWNLOAD_ATTEMPTS = 2
TOP_N_DOWNLOAD = 5


# ═══════════════════════════════════════════════════════════════
# LLM factory helpers
# ═══════════════════════════════════════════════════════════════


def _get_api_key() -> str:
    key = settings.llm_api_key
    if not key:
        raise ValueError("No LLM API key configured.")
    return key


def _make_llm(
    *,
    timeout: int = 120,
    max_tokens: int = 2000,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=SecretStr(_get_api_key()),
        temperature=0,
        timeout=timeout,
        max_completion_tokens=max_tokens,
    )


# ═══════════════════════════════════════════════════════════════
# Phase 1: Discovery nodes (map-reduce)
# ═══════════════════════════════════════════════════════════════


async def generate_queries(state: DiscoveryState) -> dict:
    """Single LLM call: course context → 10-12 search queries (retries up to 3x)."""
    llm = _make_llm(timeout=180, max_tokens=800).with_structured_output(
        SearchQueryBatch,
        method="json_mode",
    )
    ctx = state.get("course_context", {})
    c = ctx.get("course", {})
    user_msg = (
        f"COURSE TITLE: {c.get('title', '')}\n"
        f"DESCRIPTION: {c.get('description', '')}\n\n"
        f"SYLLABUS (lectures with keywords):\n"
        f"{syllabus_sequence(ctx)}\n\n"
        f"Generate 10-12 diverse search queries to discover textbooks for this course. "
        f"Include a brief rationale as a plain text string."
    )

    max_retries = 3
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            result: SearchQueryBatch = await llm.ainvoke(
                [
                    SystemMessage(content=QUERY_GENERATION_PROMPT),
                    HumanMessage(content=user_msg),
                ]
            )
            logger.info("Generated %d search queries", len(result.queries))
            return {
                "search_queries": result.queries,
                "query_rationale": result.rationale,
            }
        except Exception as e:
            last_error = e
            logger.warning(
                "Query generation attempt %d/%d failed: %s",
                attempt + 1,
                max_retries,
                e,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))

    raise RuntimeError(
        f"All {max_retries} query generation attempts failed: {last_error}"
    )


def fan_out_searches(state: DiscoveryState) -> list[Send]:
    """Map phase: dispatch each query to its own search_and_extract node."""
    queries = state.get("search_queries", [])
    ctx = state.get("course_context", {})
    logger.info(
        "Fanning out %d queries to parallel search_and_extract workers", len(queries)
    )
    return [
        Send("search_and_extract", {"query": q, "course_context": ctx}) for q in queries
    ]


async def search_and_extract(state: dict) -> dict:
    """Map worker: execute ONE query on both tools → small LLM extract."""
    llm = _make_llm(timeout=60, max_tokens=1000).with_structured_output(
        DiscoveredBookList,
        method="json_mode",
    )
    query = state["query"]
    ctx = state.get("course_context", {})

    async def _search(tool_fn, tool_name: str) -> dict:
        try:
            raw = await asyncio.to_thread(tool_fn.invoke, {"query": query})
            data = json.loads(raw) if isinstance(raw, str) else raw
            return {
                "tool": tool_name,
                "ok": data.get("ok", True),
                "results": data.get("results", []),
            }
        except Exception as e:
            return {"tool": tool_name, "ok": False, "results": [], "error": str(e)}

    gb_result, tv_result = await asyncio.gather(
        _search(googlebooksqueryrun, "googlebooksqueryrun"),
        _search(tavily_search, "tavily_search"),
    )
    ok_results = [r for r in [gb_result, tv_result] if r["ok"] and r["results"]]

    if not ok_results:
        return {"raw_books": []}

    parts: list[str] = []
    for sr in ok_results:
        items_text = json.dumps(sr["results"], ensure_ascii=False)[:3000]
        parts.append(f"[{sr['tool']}]\n{items_text}")

    c = ctx.get("course", {})
    try:
        result: DiscoveredBookList = await llm.ainvoke(
            [
                SystemMessage(content=PER_QUERY_EXTRACTION_PROMPT),
                HumanMessage(
                    content=(
                        f"COURSE: {c.get('title', '')}\n"
                        f'SEARCH QUERY: "{query}"\n\n'
                        f"SEARCH RESULTS:\n\n" + "\n---\n".join(parts)
                    )
                ),
            ]
        )
        books = [b.model_dump() for b in result.books]
    except Exception as e:
        logger.error("Extraction failed for query %s: %s", query[:40], e)
        books = []

    return {"raw_books": books}


def deduplicate_books(state: DiscoveryState) -> dict:
    """Reduce phase: deterministic fuzzy-match dedup on titles."""
    raw = state.get("raw_books", [])
    if not raw:
        return {"discovered_books": []}

    groups: list[list[dict]] = []
    for book in raw:
        title = book.get("title", "")
        matched = False
        for group in groups:
            if titles_match(title, group[0].get("title", "")):
                group.append(book)
                matched = True
                break
        if not matched:
            groups.append([book])

    unique = [pick_best_entry(g) for g in groups]
    logger.info("Deduplicated: %d raw → %d unique", len(raw), len(unique))
    return {"discovered_books": unique}


# ═══════════════════════════════════════════════════════════════
# Phase 2: Scoring nodes (research ReAct + structured scoring)
# ═══════════════════════════════════════════════════════════════


def res_agent(state: ScoringState) -> dict:
    llm = _make_llm(timeout=120, max_tokens=600).bind_tools(TOOLS)
    return {
        "messages": [
            llm.invoke(
                [SystemMessage(content=RESEARCH_PROMPT), *state.get("messages", [])]
            )
        ]
    }


def res_tools(state: ScoringState) -> dict:
    rounds = state.get("tool_rounds", 0) + 1
    if rounds > MAX_RESEARCH_ROUNDS:
        return {
            "messages": [AIMessage(content="Max research rounds reached.")],
            "tool_rounds": rounds,
        }
    return {
        "messages": exec_tools(state["messages"][-1], TOOLS_BY_NAME),
        "tool_rounds": rounds,
    }


async def score_node(state: ScoringState) -> dict:
    """Collect research evidence and produce structured BookMeritScores.

    Retries up to 3 times on JSON parsing / validation errors (common with
    LLM-generated structured output).
    """
    llm = _make_llm(timeout=90, max_tokens=1200).with_structured_output(
        BookMeritScores,
        method="json_mode",
    )
    book = state["book"]
    ctx = state["course_context"]
    course_level = state.get("course_level", DEFAULT_COURSE_LEVEL)
    scoring_prompt = SCORING_PROMPT_TEMPLATE.format(course_level=course_level)

    evidence: list[str] = []
    for m in state.get("messages", []):
        if isinstance(m, ToolMessage):
            evidence.append(m.content[:800])
        elif (
            isinstance(m, AIMessage)
            and m.content
            and not getattr(m, "tool_calls", None)
        ):
            evidence.append(m.content[:500])

    user_prompt = (
        f"COURSE:\n{course_summary(ctx, course_level=course_level)}\n\n"
        f"SYLLABUS SEQUENCE:\n{syllabus_sequence(ctx)}\n\n"
        f"BOOK: {book.get('title', '')}\n"
        f"Authors: {book.get('authors', '')} | "
        f"Publisher: {book.get('publisher', '')} | "
        f"Year: {book.get('year', '')}\n"
        f"Reason: {book.get('reason', '')}\n\n"
        f"EVIDENCE:\n" + "\n---\n".join(evidence[-10:])
    )

    max_retries = 3
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            scores: BookMeritScores = await llm.ainvoke(
                [
                    SystemMessage(content=scoring_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )

            result = scores.to_flat_dict()
            sf_base, sf_with_prac = compute_finals(
                result,
                weights=state.get("weights"),
                w_prac=state.get("w_prac"),
            )
            w_prac = float(state.get("w_prac", 0.0) or 0.0)
            result["S_final_base"] = sf_base
            result["S_final_with_prac"] = sf_with_prac
            result["S_final"] = sf_with_prac if w_prac > 0 else sf_base
            result["book_title"] = book.get("title", "")
            result["book_authors"] = book.get("authors", "")
            result["publisher"] = book.get("publisher", "")
            result["year"] = book.get("year", "")

            return {"final_scores": result}
        except Exception as e:
            last_error = e
            logger.warning(
                "Scoring attempt %d/%d failed for '%s': %s",
                attempt + 1,
                max_retries,
                book.get("title", "?")[:50],
                e,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))  # back-off

    # All retries exhausted — return a zero-score fallback so the workflow
    # continues instead of crashing the entire session.
    logger.error(
        "All %d scoring attempts failed for '%s': %s",
        max_retries,
        book.get("title", "?")[:50],
        last_error,
    )
    fallback = {
        "C_topic": 0,
        "C_topic_rationale": f"Scoring failed: {last_error}",
        "C_struc": 0,
        "C_struc_rationale": "",
        "C_scope": 0,
        "C_scope_rationale": "",
        "C_pub": 0,
        "C_pub_rationale": "",
        "C_auth": 0,
        "C_auth_rationale": "",
        "C_time": 0,
        "C_time_rationale": "",
        "C_prac": 0,
        "C_prac_rationale": "",
        "S_final": 0,
        "S_final_with_prac": 0,
        "book_title": book.get("title", ""),
        "book_authors": book.get("authors", ""),
        "scoring_error": str(last_error),
    }
    return {"final_scores": fallback}


def res_route(state: ScoringState) -> str:
    if state.get("tool_rounds", 0) >= MAX_RESEARCH_ROUNDS:
        return "score"
    last = (state.get("messages") or [None])[-1]
    return "tools" if last and getattr(last, "tool_calls", None) else "score"


# ═══════════════════════════════════════════════════════════════
# Phase 3: Download nodes
# ═══════════════════════════════════════════════════════════════


def dl_search_agent(state: DownloadState) -> dict:
    llm = _make_llm(timeout=120, max_tokens=600).bind_tools(DOWNLOAD_SEARCH_TOOLS)
    return {
        "messages": [
            llm.invoke(
                [
                    SystemMessage(content=DOWNLOAD_SEARCH_PROMPT),
                    *state.get("messages", []),
                ]
            )
        ]
    }


def dl_search_tools(state: DownloadState) -> dict:
    rounds = state.get("tool_rounds", 0) + 1
    if rounds > MAX_DOWNLOAD_SEARCH_ROUNDS:
        return {
            "messages": [
                AIMessage(
                    content="Max download search rounds reached. Proceeding to URL extraction."
                )
            ],
            "tool_rounds": rounds,
        }
    return {
        "messages": exec_tools(state["messages"][-1], DOWNLOAD_SEARCH_TOOLS_BY_NAME),
        "tool_rounds": rounds,
    }


def dl_search_route(state: DownloadState) -> str:
    if state.get("tool_rounds", 0) >= MAX_DOWNLOAD_SEARCH_ROUNDS:
        return "extract_urls"
    last = (state.get("messages") or [None])[-1]
    return "dl_tools" if last and getattr(last, "tool_calls", None) else "extract_urls"


async def dl_extract_urls(state: DownloadState) -> dict:
    """LLM extracts candidate download URLs from all search evidence."""
    llm = _make_llm(timeout=60, max_tokens=1500).with_structured_output(
        CandidateURLList,
        method="json_mode",
    )
    book = state["book"]

    evidence: list[str] = []
    for m in state.get("messages", []):
        if isinstance(m, ToolMessage):
            evidence.append(m.content[:1200])
        elif (
            isinstance(m, AIMessage)
            and m.content
            and not getattr(m, "tool_calls", None)
        ):
            evidence.append(m.content[:600])

    user_prompt = (
        f"Extract ALL candidate download URLs from the search results below.\n\n"
        f"BOOK: {book.get('title', '')} by {book.get('authors', '')} "
        f"({book.get('year', '')})\n"
        f"Publisher: {book.get('publisher', '')}\n\n"
        f"SEARCH EVIDENCE:\n"
        + "\n---\n".join(evidence[-12:])
        + "\n\nExtract every URL that could be a direct download link. "
        "Rate each URL's confidence. If you found NO usable URLs, return an empty list."
    )

    result: CandidateURLList = await llm.ainvoke(
        [
            SystemMessage(
                content=(
                    "Extract candidate download URLs from the search evidence. "
                    "Include ONLY URLs that actually appeared in the search results. "
                    "Rate confidence: 1.0 = URL ends in .pdf/.epub (direct link), "
                    "0.8 = download page on archive.org or similar, "
                    "0.5 = book page that might have a download option, "
                    "0.2 = tangential reference."
                )
            ),
            HumanMessage(content=user_prompt),
        ]
    )

    urls = [u.model_dump() for u in result.urls]
    urls.sort(key=lambda u: u.get("confidence", 0), reverse=True)
    logger.info(
        "Found %d candidate URLs for %s", len(urls), book.get("title", "?")[:50]
    )
    return {"candidate_urls": urls}


async def dl_attempt_download(state: DownloadState) -> dict:
    """Try downloading from top candidate URLs."""
    book = state["book"]
    urls = state.get("candidate_urls", [])
    title = book.get("title", "unknown")

    safe_fn = _re.sub(r"[^\w\s-]", "", title.strip())
    safe_fn = _re.sub(r"\s+", "_", safe_fn)[:80] or "book"

    if not urls:
        return {
            "download_result": {
                "book_title": title,
                "status": "no_urls",
                "error": "No candidate download URLs found.",
            }
        }

    tried_urls: list[str] = []
    for _i, candidate in enumerate(urls[:MAX_DOWNLOAD_ATTEMPTS]):
        url = candidate.get("url", "")
        if not url or not url.startswith("http"):
            continue
        tried_urls.append(url)
        try:
            raw_result = await asyncio.to_thread(
                download_file_from_url.invoke,
                {"url": url, "filename": safe_fn},
            )
            result_data = (
                json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            )
            if result_data.get("ok"):
                results = result_data.get("results", [])
                dl_info = results[0] if results else {}
                return {
                    "download_result": {
                        "book_title": title,
                        "book_authors": book.get("authors", ""),
                        "status": "success",
                        "file_path": dl_info.get("url", ""),
                        "file_info": dl_info.get("snippet", ""),
                        "source_url": url,
                    }
                }
        except Exception as e:
            logger.warning("Download attempt failed for %s: %s", url[:60], e)

    remaining_urls = [
        u.get("url", "") for u in urls if u.get("url", "") not in tried_urls
    ]
    return {
        "download_result": {
            "book_title": title,
            "status": "failed",
            "error": f"Tried {len(tried_urls)} URL(s), all failed.",
            "tried_urls": tried_urls,
            "manual_urls": remaining_urls[:5],
        }
    }


# ═══════════════════════════════════════════════════════════════
# Main orchestrator nodes
# ═══════════════════════════════════════════════════════════════


def fetch_course(state: WorkflowState) -> dict:
    """Load course context from Neo4j."""
    from neo4j import GraphDatabase

    course_id = state.get("course_id", 1)
    level = state.get("course_level", DEFAULT_COURSE_LEVEL)
    if level not in VALID_COURSE_LEVELS:
        level = DEFAULT_COURSE_LEVEL

    uri = settings.neo4j_uri
    usr = settings.neo4j_username or "neo4j"
    pwd = settings.neo4j_password
    db = settings.neo4j_database

    if not (uri and usr and pwd):
        raise ValueError("Neo4j not configured.")

    query = """
    MATCH (c:CLASS {id: $cid})
    OPTIONAL MATCH (d:TEACHER_UPLOADED_DOCUMENT) WHERE d.course_id = $cid
    WITH c, d ORDER BY d.source_filename ASC
    WITH c, collect(CASE WHEN d IS NULL THEN NULL ELSE {
      title: coalesce(d.topic, ""),
      keywords: coalesce(d.keywords, []),
      summary: coalesce(d.summary, ""),
      source_filename: coalesce(d.source_filename, "")
    } END) AS docs
    RETURN c.title AS t, c.description AS desc,
           [x IN docs WHERE x IS NOT NULL] AS docs
    """
    drv = GraphDatabase.driver(uri, auth=(usr, pwd))
    try:
        with drv.session(database=db) as s:
            r = s.run(query, {"cid": course_id}).single()
            if not r:
                raise ValueError(f"Course {course_id} not found in Neo4j.")
            ctx = {
                "course": {
                    "id": course_id,
                    "title": r["t"] or "",
                    "description": r["desc"] or "",
                },
                "documents": [
                    {
                        "title": d["title"],
                        "keywords": [str(k) for k in d["keywords"] if k],
                        "summary": d["summary"],
                        "source_filename": d["source_filename"],
                    }
                    for d in r["docs"]
                ],
            }
    finally:
        drv.close()

    return {"course_context": ctx, "course_level": level}


async def discover_books(state: WorkflowState) -> dict:
    """Run the discovery sub-graph."""
    from .workflow import build_discovery_graph

    discovery_graph = build_discovery_graph()
    result = await discovery_graph.ainvoke({"course_context": state["course_context"]})
    return {"discovered_books": result.get("discovered_books", [])}


def fan_out_scoring(state: WorkflowState) -> list[Send]:
    """Fan out: one Send per discovered book → score_book node."""
    books = state.get("discovered_books", [])
    ctx = state.get("course_context", {})
    level = state.get("course_level", DEFAULT_COURSE_LEVEL)
    weights = state.get("weights", {})
    w_prac = state.get("w_prac", 0.0)
    sends: list[Send] = []
    for book in books:
        sends.append(
            Send(
                "score_book",
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                f"Research and gather evidence about this book:\n"
                                f"Title: {book.get('title', '')}\n"
                                f"Authors: {book.get('authors', '')}\n"
                                f"Publisher: {book.get('publisher', '')}\n"
                                f"Year: {book.get('year', '')}\n"
                                f"Reason: {book.get('reason', '')}"
                            )
                        )
                    ],
                    "book": book,
                    "course_context": ctx,
                    "course_level": level,
                    "weights": weights,
                    "w_prac": w_prac,
                },
            )
        )
    return sends


async def score_book_node(state: ScoringState) -> dict:
    """Run the scoring sub-graph for a single book."""
    from .workflow import build_scoring_graph

    scoring_graph = build_scoring_graph()
    result = await scoring_graph.ainvoke(state)
    scores = result.get("final_scores", {})
    return {"scored_books": [scores]}


def select_top_books(state: WorkflowState) -> dict:
    """Sort scored books by S_final and select top N for download."""
    scored = state.get("scored_books", [])
    ranked = sorted(scored, key=lambda x: x.get("S_final", 0), reverse=True)
    top = ranked[:TOP_N_DOWNLOAD]
    logger.info("Selected top %d books for download", len(top))
    return {"top_books": top}


def hitl_review(state: WorkflowState) -> dict:
    """HITL interrupt: pause workflow so the teacher can review scored books.

    Returns the scored books list as the interrupt value.
    The teacher's response (selected book titles) will be received via Command(resume=...).
    """
    scored = state.get("scored_books", [])
    ranked = sorted(scored, key=lambda x: x.get("S_final", 0), reverse=True)

    # interrupt() suspends the workflow and returns the data to the caller
    selected = interrupt(
        {
            "type": "book_review",
            "books": ranked,
            "message": "Please review the scored books and select up to 5 for download.",
        }
    )

    # When resumed, selected can be:
    # - list of indices (legacy)
    # - list of book titles (preferred)
    if isinstance(selected, list) and selected:
        if isinstance(selected[0], str):
            # Match by title
            selected_titles = set(selected)
            top = [b for b in ranked if b.get("book_title", "") in selected_titles][
                :TOP_N_DOWNLOAD
            ]
        else:
            # Legacy: match by index
            selected_set = set(selected)
            top = [b for i, b in enumerate(ranked) if i in selected_set][
                :TOP_N_DOWNLOAD
            ]
    else:
        top = ranked[:TOP_N_DOWNLOAD]

    return {"top_books": top}


def fan_out_downloads(state: WorkflowState) -> list[Send]:
    """Fan out: one Send per top book → download_book node."""
    top = state.get("top_books", [])
    sends: list[Send] = []
    for book_scores in top:
        book = {
            "title": book_scores.get("book_title", ""),
            "authors": book_scores.get("book_authors", ""),
            "year": book_scores.get("year", ""),
            "publisher": book_scores.get("publisher", ""),
            "S_final": book_scores.get("S_final", 0),
        }
        sends.append(
            Send(
                "download_book",
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                f"Find download links for this book:\n"
                                f"Title: {book['title']}\n"
                                f"Authors: {book['authors']}\n"
                                f"Year: {book['year']}\n"
                                f"Publisher: {book['publisher']}"
                            )
                        )
                    ],
                    "book": book,
                },
            )
        )
    return sends


async def download_book_node(state: DownloadState) -> dict:
    """Run the download sub-graph for a single book."""
    from .workflow import build_download_graph

    download_graph = build_download_graph()
    result = await download_graph.ainvoke(state)
    dl_result = result.get("download_result", {})
    return {"download_results": [dl_result]}
