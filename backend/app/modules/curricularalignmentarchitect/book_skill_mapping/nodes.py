"""LangGraph node functions for book skill → course chapter mapping.

Pipeline:
  1. load_and_fan_out — reads COURSE_CHAPTERs + BOOK_SKILLs from Neo4j,
     fans out one Send per book chapter.
  2. map_chapter — LLM maps all skills from one book chapter to course chapters.
  3. persist_all — clears old MAPPED_TO edges, batch-writes new ones.
"""

from __future__ import annotations

import json
import logging

import openai
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.types import RetryPolicy, Send

from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings

from .prompts import BOOK_SKILL_MAPPER_PROMPT
from .repository import (
    clear_book_skill_mappings,
    load_book_chapters_with_skills,
    load_course_chapters,
    write_skill_mappings,
)
from .schemas import ChapterMappingResult
from .state import BookSkillMappingState, ChapterMapperInput

logger = logging.getLogger(__name__)


# ── LLM setup ──────────────────────────────────────────────────────────────


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=4096,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
    )


def _mapper_llm():
    return BOOK_SKILL_MAPPER_PROMPT | _build_llm().with_structured_output(
        ChapterMappingResult, method="json_mode"
    )


# ── Retry policy ────────────────────────────────────────────────────────────

RETRYABLE_ERRORS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
    openai.RateLimitError,
    ConnectionError,
    TimeoutError,
)

api_retry_policy = RetryPolicy(
    initial_interval=5.0,
    backoff_factor=2.0,
    max_interval=60.0,
    max_attempts=3,
    retry_on=lambda exc: isinstance(exc, RETRYABLE_ERRORS),
)


# ── Helper: skill name auto-correction ──────────────────────────────────────


def _best_match(llm_name: str, known_names: list[str]) -> str | None:
    """Try to match an LLM-returned skill name back to a known BOOK_SKILL name."""
    # Exact match
    if llm_name in known_names:
        return llm_name
    # Case-insensitive
    lower = llm_name.lower()
    for name in known_names:
        if name.lower() == lower:
            return name
    # Substring match
    for name in known_names:
        if lower in name.lower() or name.lower() in lower:
            return name
    # Word-overlap scoring
    llm_words = set(lower.split())
    best, best_score = None, 0
    for name in known_names:
        words = set(name.lower().split())
        score = len(llm_words & words) / max(len(llm_words | words), 1)
        if score > best_score and score >= 0.5:
            best, best_score = name, score
    return best


# ── Graph nodes ─────────────────────────────────────────────────────────────


def load_and_fan_out(state: BookSkillMappingState) -> list[Send]:
    """Load data from Neo4j and fan out one Send per book chapter."""
    driver = create_neo4j_driver()
    if driver is None:
        logger.warning("Neo4j not configured — skipping book skill mapping.")
        return []

    course_id = state["course_id"]

    course_chapters = load_course_chapters(driver, course_id)
    if not course_chapters:
        logger.warning(
            "Course %d has no COURSE_CHAPTERs — skipping book skill mapping. "
            "Run curriculum planning first.",
            course_id,
        )
        driver.close()
        return []

    book_chapters = load_book_chapters_with_skills(driver, course_id)
    driver.close()

    if not book_chapters:
        logger.warning("Course %d has no BOOK_SKILLs to map.", course_id)
        return []

    logger.info(
        "Course %d: mapping skills from %d book chapters against %d course chapters.",
        course_id,
        len(book_chapters),
        len(course_chapters),
    )

    return [
        Send(
            "map_chapter",
            ChapterMapperInput(
                course_id=course_id,
                book_chapter_id=ch["chapter_id"],
                book_chapter_title=ch["chapter_title"]
                or f"Chapter {ch['chapter_index']}",
                skills=ch["skills"],
                course_chapters=course_chapters,
                mappings=[],
                errors=[],
            ),
        )
        for ch in book_chapters
        if ch.get("skills")
    ]


def map_chapter(state: ChapterMapperInput) -> dict:
    """LLM maps all skills from one book chapter to course chapters."""
    book_chapter_title = state["book_chapter_title"]
    skills = state["skills"]
    course_chapters = state["course_chapters"]
    known_names = [s["name"] for s in skills]

    try:
        result: ChapterMappingResult = _mapper_llm().invoke(
            {
                "course_chapters_json": json.dumps(
                    course_chapters, ensure_ascii=False, indent=2
                ),
                "book_chapter_title": book_chapter_title,
                "book_skills_json": json.dumps(skills, ensure_ascii=False, indent=2),
            }
        )
    except Exception as exc:
        logger.exception("LLM mapping failed for book chapter '%s'", book_chapter_title)
        return {
            "mappings": [],
            "errors": [{"chapter": book_chapter_title, "error": str(exc)}],
        }

    # Auto-correct skill names
    raw_mappings = []
    for m in result.mappings:
        corrected = _best_match(m.skill_name, known_names)
        raw_mappings.append(
            {
                "skill_name": corrected or m.skill_name,
                "target_chapter": m.target_chapter,
                "status": m.status,
                "confidence": m.confidence,
                "reasoning": m.reasoning,
            }
        )

    logger.info(
        "Book chapter '%s': %d skills — %d mapped, %d no_match.",
        book_chapter_title,
        len(raw_mappings),
        sum(1 for m in raw_mappings if m["status"] != "no_match"),
        sum(1 for m in raw_mappings if m["status"] == "no_match"),
    )

    return {"mappings": raw_mappings}


def persist_all(state: BookSkillMappingState) -> dict:
    """Clear old MAPPED_TO edges and batch-write new ones to Neo4j."""
    write = get_stream_writer()
    driver = create_neo4j_driver()
    if driver is None:
        logger.warning("Neo4j not configured — cannot persist skill mappings.")
        return {}

    course_id = state["course_id"]
    all_mappings = state.get("mappings", [])

    write(
        {
            "type": "skill_mapping_progress",
            "message": f"Writing {len(all_mappings)} mappings to Neo4j...",
        }
    )

    deleted = clear_book_skill_mappings(driver, course_id)
    written = write_skill_mappings(driver, course_id, all_mappings)
    driver.close()

    logger.info(
        "Course %d: cleared %d old MAPPED_TO edges, wrote %d new ones.",
        course_id,
        deleted,
        written,
    )

    write(
        {
            "type": "skill_mapping_completed",
            "course_id": course_id,
            "total_mappings": len(all_mappings),
            "written": written,
            "cleared": deleted,
        }
    )

    return {}
