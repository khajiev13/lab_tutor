"""Book Gap Analysis recommendation agent.

Uses pre-computed ChapterAnalysisSummary data + Neo4j teacher documents
to generate actionable recommendations via a streaming DeepSeek LLM call
(proxied through Silra API).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Generator
from dataclasses import asdict

from langchain_openai import ChatOpenAI

from app.core.settings import settings

from ..prompts import (
    BOOK_GAP_ANALYSIS_SYSTEM,
    BOOK_GAP_ANALYSIS_USER,
    format_novel_concepts,
    format_overlap_concepts,
    format_skills,
    format_teacher_documents,
)
from ..repository import RecommendationData
from ..schemas import RecommendationReport

logger = logging.getLogger(__name__)

# DeepSeek sometimes returns markdown-fenced JSON even with json_object mode.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)

# Field-name mapping: DeepSeek occasionally uses its own names instead of the
# ones specified in the prompt.  We normalise before Pydantic validation.
_ITEM_FIELD_ALIASES: dict[str, str] = {
    "type": "category",
    "book_reference": "book_evidence",
    "suggested_document": "affected_teacher_document",
    "related_skills": "suggested_action",
}

# Category value aliases: DeepSeek may invent its own category names.
_CATEGORY_ALIASES: dict[str, str] = {
    "weak_coverage": "insufficient_coverage",
    "missing": "missing_concept",
    "skill": "suggested_skill",
    "structure": "structural",
}


def _build_llm() -> ChatOpenAI:
    """Build the DeepSeek LLM client (via Silra proxy) with JSON-object mode."""
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=8192,
        temperature=0.1,
        timeout=settings.llm_timeout_seconds,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that DeepSeek may add."""
    m = _FENCE_RE.match(text)
    return m.group(1) if m else text


def _normalise_item(item: dict) -> dict:
    """Map DeepSeek field-name variants to the canonical schema names."""
    for alt, canonical in _ITEM_FIELD_ALIASES.items():
        if alt in item and canonical not in item:
            val = item.pop(alt)
            # DeepSeek may return book_reference as a string — wrap it
            if canonical == "book_evidence" and isinstance(val, str):
                val = {"text_evidence": val}
            # DeepSeek may return related_skills as a list — join into action
            if canonical == "suggested_action" and isinstance(val, list):
                val = "; ".join(str(s) for s in val) if val else ""
            item[canonical] = val

    # Normalise category value aliases (e.g. "weak_coverage" → "insufficient_coverage")
    cat = item.get("category")
    if isinstance(cat, str):
        item["category"] = _CATEGORY_ALIASES.get(cat.lower(), cat.lower())

    return item


def _prepare_prompt_data(data: RecommendationData) -> dict:
    """Convert repository data into prompt-friendly dicts."""
    novel_dicts = [asdict(c) for c in data.novel_concepts]
    overlap_dicts = [asdict(c) for c in data.overlap_concepts]
    teacher_dicts = [asdict(d) for d in data.teacher_documents]
    skill_dicts = [asdict(s) for s in data.skills]

    return {
        "novel_concepts_text": format_novel_concepts(novel_dicts),
        "overlap_concepts_text": format_overlap_concepts(overlap_dicts),
        "teacher_documents_text": format_teacher_documents(teacher_dicts),
        "skills_text": format_skills(skill_dicts),
    }


def _build_messages(data: RecommendationData) -> list[dict]:
    """Build the chat messages for the DeepSeek LLM call."""
    prompt_data = _prepare_prompt_data(data)
    user_message = BOOK_GAP_ANALYSIS_USER.format(
        book_title=data.book_title,
        **prompt_data,
    )
    return [
        {"role": "system", "content": BOOK_GAP_ANALYSIS_SYSTEM},
        {"role": "user", "content": user_message},
    ]


def stream_book_gap_analysis(
    data: RecommendationData,
    course_id: int,
) -> Generator[tuple[str, dict], None, None]:
    """Stream the book gap analysis, yielding (event_type, data) tuples.

    Uses DeepSeek (via Silra API) in streaming mode so the frontend can
    display tokens as they arrive.

    Events emitted:
      token  — partial text chunk from the LLM
      report — final validated RecommendationReport as JSON
      error  — parsing / validation failure
    """
    total_gaps = len(data.novel_concepts) + len(data.overlap_concepts)
    logger.info(
        "Book gap analysis: %d novel + %d overlap concepts, %d teacher docs, %d skills",
        len(data.novel_concepts),
        len(data.overlap_concepts),
        len(data.teacher_documents),
        len(data.skills),
    )

    if total_gaps == 0 and not data.skills:
        report = RecommendationReport(
            source="book_gap_analysis",
            course_id=course_id,
            book_title=data.book_title,
            summary="No significant gaps found between the book and teacher materials.",
            recommendations=[],
        )
        yield "report", report.model_dump()
        return

    llm = _build_llm()
    messages = _build_messages(data)

    # Stream token-by-token from DeepSeek
    accumulated = ""
    for chunk in llm.stream(messages):
        token = chunk.content
        if token:
            accumulated += token
            yield "token", {"text": token}

    # Parse accumulated JSON into the validated Pydantic model.
    # DeepSeek may wrap output in ```json fences or use non-standard field names.
    try:
        cleaned = _strip_markdown_fences(accumulated.strip())
        raw = json.loads(cleaned)

        # Normalise recommendation items (field-name aliases)
        if "recommendations" in raw and isinstance(raw["recommendations"], list):
            raw["recommendations"] = [
                _normalise_item(r) for r in raw["recommendations"]
            ]

        # Inject metadata fields that the LLM doesn't produce
        raw["source"] = "book_gap_analysis"
        raw["course_id"] = course_id
        raw["book_title"] = data.book_title

        report = RecommendationReport.model_validate(raw)
        yield "report", report.model_dump()
        logger.info(
            "Book gap analysis produced %d recommendations for '%s'",
            len(report.recommendations),
            data.book_title,
        )
    except (json.JSONDecodeError, Exception) as exc:
        logger.exception("Failed to parse book gap analysis response")
        logger.debug("Raw LLM output (first 500 chars): %s", accumulated[:500])
        yield "error", {"message": f"Failed to parse LLM response: {exc!s}"}
