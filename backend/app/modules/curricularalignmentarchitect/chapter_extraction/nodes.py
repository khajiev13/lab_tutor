"""LangGraph node functions for chapter-level concept extraction.

Ported from the chapter_level_extraction notebook.
Key addition: ``get_stream_writer()`` calls in ``chapter_worker`` to emit
real-time progress events through the outer graph's ``astream()``.
"""

from __future__ import annotations

import json
import logging
import re
import time

import openai
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.types import RetryPolicy

from app.core.settings import settings

from .prompts import (
    CHAPTER_EVALUATION_PROMPT,
    CHAPTER_EXTRACTION_PROMPT,
    CHAPTER_REVISION_PROMPT,
    SKILLS_PROMPT,
    truncate_content,
)
from .schemas import (
    ChapterConceptsResult,
    ChapterExtraction,
    Concept,
    EvaluationVerdict,
    ExtractionFeedback,
    SectionExtraction,
    Skill,
)
from .state import MAX_ITERATIONS, ChapterExtractionState, ChapterWorkerInput

logger = logging.getLogger(__name__)


# ── LLM setup (uses project settings) ─────────────────────────


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=8192,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
    )


def _build_extraction_llm():
    return _build_llm().with_structured_output(
        ChapterConceptsResult, method="json_mode"
    )


def _build_skills_llm():
    return _build_llm().with_structured_output(
        ChapterSkillsResult,
        method="json_mode",  # noqa: F821
    )


def _build_feedback_llm():
    return _build_llm().with_structured_output(ExtractionFeedback, method="json_mode")


# Import needed for _build_skills_llm
from .schemas import ChapterSkillsResult  # noqa: E402

# ── Retry policy ──────────────────────────────────────────────

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


# ── Fallback parser ──────────────────────────────────────────

_CONCEPT_REQUIRED_FIELDS = {
    "name",
    "description",
    "relevance",
    "text_evidence",
    "source_section",
}


def _safe_parse_chapter_concepts(
    raw_json: str, chapter_title: str
) -> ChapterConceptsResult:
    """Parse LLM JSON output with tolerance for malformed concept entries."""
    data = json.loads(raw_json)
    raw_concepts = data.get("concepts", [])

    valid_concepts: list[Concept] = []
    dropped = 0
    for c in raw_concepts:
        if not isinstance(c, dict):
            dropped += 1
            continue
        missing = _CONCEPT_REQUIRED_FIELDS - c.keys()
        if missing:
            dropped += 1
            logger.warning(
                "Dropped malformed concept %r (missing: %s)",
                c.get("name", "???"),
                ", ".join(sorted(missing)),
            )
            continue
        try:
            valid_concepts.append(Concept.model_validate(c))
        except Exception as e:
            dropped += 1
            logger.warning("Dropped concept %r: %s", c.get("name", "???"), e)

    if dropped:
        logger.info(
            "Salvaged %d/%d concepts (%d malformed filtered out)",
            len(valid_concepts),
            len(raw_concepts),
            dropped,
        )

    return ChapterConceptsResult(
        chapter_title=data.get("chapter_title", chapter_title),
        concepts=valid_concepts,
    )


# ── Helpers ───────────────────────────────────────────────────


def _format_section_list(section_titles: list[str]) -> str:
    if not section_titles:
        return "(no sections — chapter body only)"
    return "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(section_titles))


def _format_concepts_for_eval(extraction: ChapterConceptsResult) -> str:
    if not extraction.concepts:
        return "(no concepts extracted)"
    lines = []
    for i, c in enumerate(extraction.concepts, 1):
        lines.append(
            f"  {i}. [{c.relevance.value}] {c.name}: {c.description}"
            f"\n     Section: #{c.source_section}"
            f'\n     Evidence: "{c.text_evidence[:150]}"'
        )
    return "\n".join(lines)


def _invoke_extraction_chain(
    prompt, common: dict, chapter_title: str
) -> ChapterConceptsResult:
    """Invoke extraction prompt → structured LLM, with fallback on parse errors."""
    extraction_llm = _build_extraction_llm()
    raw_llm = _build_llm()
    try:
        return (prompt | extraction_llm).invoke(common)
    except OutputParserException:
        logger.warning("Structured parse failed — salvaging valid concepts...")
        raw_response = (prompt | raw_llm).invoke(common)
        raw_text = raw_response.content.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)
        return _safe_parse_chapter_concepts(raw_text, chapter_title)


def _invoke_skills_extraction(
    course_subject: str, book_label: str, ch_title: str, section_summaries: list[str]
) -> ChapterSkillsResult:
    """Chapter-level skills extraction."""
    skills_llm = _build_skills_llm()
    return (SKILLS_PROMPT | skills_llm).invoke(
        {
            "course_subject": course_subject,
            "book_name": book_label,
            "chapter_title": ch_title,
            "all_sections_summary": "\n".join(section_summaries),
        }
    )


def _group_concepts_by_section(
    concepts: list[Concept],
    section_titles: list[str],
    section_contents: list[str] | None = None,
) -> list[SectionExtraction]:
    """Group flat concept list into SectionExtraction objects by source_section index.

    Each concept's ``source_section`` is a **1-based integer** matching the
    numbered section list shown to the LLM.  Grouping is deterministic — no
    fuzzy string matching needed.
    """
    n = len(section_titles)
    grouped: dict[int, list[Concept]] = {i: [] for i in range(n)}
    unmatched: list[Concept] = []

    for concept in concepts:
        idx = concept.source_section - 1  # 1-based → 0-based
        if 0 <= idx < n:
            grouped[idx].append(concept)
        else:
            unmatched.append(concept)

    if unmatched and section_titles:
        logger.info(
            "%d concept(s) had out-of-range source_section — "
            "assigning to section 1 ('%s'): %s",
            len(unmatched),
            section_titles[0],
            [c.name for c in unmatched],
        )
        grouped[0].extend(unmatched)

    contents = section_contents or []
    sections = []
    for i, title in enumerate(section_titles):
        content = contents[i] if i < len(contents) else None
        sections.append(
            SectionExtraction(
                section_title=title,
                section_content=content or None,
                concepts=grouped[i],
            )
        )

    if not section_titles:
        sections.append(
            SectionExtraction(section_title="(chapter body)", concepts=concepts)
        )

    # Log sections that received zero concepts — useful for debugging
    empty = [s.section_title for s in sections if not s.concepts]
    if empty and len(sections) > 1:
        logger.info(
            "%d section(s) received 0 concepts: %s",
            len(empty),
            empty,
        )

    return sections


def _embed_chapter_concepts(chapter_extraction: ChapterExtraction) -> None:
    """Embed concept names and text_evidence for all concepts in a chapter.

    Mutates each Concept in-place, setting ``name_embedding`` and
    ``evidence_embedding`` fields so they can be persisted alongside the
    extraction results.
    """
    from app.modules.embeddings.embedding_service import EmbeddingService

    concepts = chapter_extraction.all_concepts
    if not concepts:
        return

    names = [c.name for c in concepts]
    evidences = [c.text_evidence for c in concepts]
    texts = names + evidences

    embedder = EmbeddingService()
    vectors = embedder.embed_documents(texts)

    n = len(concepts)
    for i, concept in enumerate(concepts):
        concept.name_embedding = vectors[i]
        concept.evidence_embedding = vectors[n + i]


# ═══════════════════════════════════════════════════════════════
# Inner graph nodes: extract → evaluate → (revise | end)
# ═══════════════════════════════════════════════════════════════


def extract_chapter_concepts(state: ChapterExtractionState) -> dict:
    """Extract or revise concepts for the entire chapter (1 LLM call)."""
    iteration = state["iteration"]
    feedback = state.get("feedback")
    prev = state.get("extraction")

    chapter_content = truncate_content(state["chapter_content"])
    section_list = _format_section_list(state["section_titles"])

    common = {
        "course_subject": state["course_subject"],
        "book_name": state["book_name"],
        "chapter_title": state["chapter_title"],
        "section_list": section_list,
        "chapter_content": chapter_content,
    }

    if iteration == 0 or feedback is None or prev is None:
        result = _invoke_extraction_chain(
            CHAPTER_EXTRACTION_PROMPT, common, state["chapter_title"]
        )
    else:
        prev_summary = _format_concepts_for_eval(prev)
        all_issues = feedback.issues if feedback.issues else []
        issue_text = (
            "\n".join(f"  - {iss}" for iss in all_issues) if all_issues else "(none)"
        )
        result = _invoke_extraction_chain(
            CHAPTER_REVISION_PROMPT,
            {
                **common,
                "num_prev_concepts": str(len(prev.concepts)),
                "prev_extraction_summary": prev_summary,
                "reflection_issues": issue_text,
            },
            state["chapter_title"],
        )

    return {"extraction": result}


def evaluate_chapter(state: ChapterExtractionState) -> dict:
    """LLM evaluates the quality of the chapter-level extraction."""
    extraction = state["extraction"]
    iteration = state["iteration"]

    concepts_detail = _format_concepts_for_eval(extraction)
    section_list = _format_section_list(state["section_titles"])
    content_preview = state["chapter_content"][:5000]

    eval_vars = {
        "course_subject": state["course_subject"],
        "book_name": state["book_name"],
        "chapter_title": state["chapter_title"],
        "section_list": section_list,
        "chapter_content_preview": content_preview,
        "num_concepts": str(len(extraction.concepts)),
        "concepts_detail": concepts_detail,
    }

    feedback_llm = _build_feedback_llm()
    feedback = (CHAPTER_EVALUATION_PROMPT | feedback_llm).invoke(eval_vars)

    approved = feedback.verdict == EvaluationVerdict.APPROVED
    return {
        "feedback": feedback,
        "approved": approved,
        "iteration": iteration + 1,
    }


def should_continue(state: ChapterExtractionState) -> str:
    """Conditional edge: revise or end."""
    if state["approved"]:
        return "end"
    if state["iteration"] >= state["max_iterations"]:
        return "end"
    return "revise"


# ═══════════════════════════════════════════════════════════════
# Outer graph nodes: assign_chapters + chapter_worker + synthesize
# ═══════════════════════════════════════════════════════════════


def assign_chapters(state):
    """Fan out Send() for each chapter in the book."""
    from langgraph.types import Send

    chapters = state["chapters"]
    sends = []
    for ch in sorted(chapters, key=lambda x: x["chapter_number"]):
        sends.append(
            Send(
                "chapter_worker",
                {
                    "run_id": state["run_id"],
                    "selected_book_id": state["selected_book_id"],
                    "course_subject": state["course_subject"],
                    "book_name": state["book_name"],
                    "book_label": state["book_label"],
                    "chapter_number": ch["chapter_number"],
                    "chapter_title": ch["title"],
                    "section_titles": [s["title"] for s in ch["sections"]],
                    "section_contents": [
                        s.get("content", "") or "" for s in ch["sections"]
                    ],
                    "chapter_content": ch["content"],
                    "total_chapters": state["total_chapters"],
                },
            )
        )
    return sends


def chapter_worker(state: ChapterWorkerInput) -> dict:
    """Process one chapter: extract → evaluate/revise → skills.

    Uses ``get_stream_writer()`` to emit real-time progress events.
    """
    from .graph import build_chapter_extraction_graph
    from .repository import save_chapter_extraction
    from .state import CHAPTER_GRAPH_MAX_CONCURRENCY, CHAPTER_GRAPH_RECURSION_LIMIT

    writer = get_stream_writer()
    book_label = state["book_label"]
    course_subject = state["course_subject"]
    ch_title = state["chapter_title"]
    ch_num = state["chapter_number"]
    section_titles = state["section_titles"]
    section_contents = state.get("section_contents", [])
    chapter_content = state["chapter_content"]

    t0 = time.time()
    errors: list[dict] = []

    # Emit: started
    writer(
        {
            "type": "agent_status",
            "book_title": book_label,
            "chapter_title": ch_title,
            "chapter_number": ch_num,
            "total_chapters": state["total_chapters"],
            "step": "extracting",
            "iteration": 0,
        }
    )

    try:
        chapter_graph = build_chapter_extraction_graph()
        final = chapter_graph.invoke(
            {
                "course_subject": course_subject,
                "book_name": book_label,
                "chapter_title": ch_title,
                "section_titles": section_titles,
                "chapter_content": chapter_content,
                "extraction": None,
                "feedback": None,
                "iteration": 0,
                "max_iterations": MAX_ITERATIONS,
                "approved": False,
            },
            config={
                "max_concurrency": CHAPTER_GRAPH_MAX_CONCURRENCY,
                "recursion_limit": CHAPTER_GRAPH_RECURSION_LIMIT,
            },
        )

        extraction_result: ChapterConceptsResult = final["extraction"]
        approved = final["approved"]
        iterations = final["iteration"]

        # Emit: evaluating done
        writer(
            {
                "type": "agent_status",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "step": "evaluated",
                "iteration": iterations,
                "concept_count": len(extraction_result.concepts),
                "approved": approved,
            }
        )

        section_extractions = _group_concepts_by_section(
            extraction_result.concepts, section_titles, section_contents
        )

        all_concept_names = {c.name for c in extraction_result.concepts}
        section_summaries = []
        for se in section_extractions:
            cs = ", ".join(c.name for c in se.concepts) if se.concepts else "(none)"
            section_summaries.append(f"  {se.section_title}: {cs}")

        # Emit: skills extraction
        writer(
            {
                "type": "agent_status",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "step": "skills",
                "iteration": iterations,
            }
        )

        try:
            skills_result = _invoke_skills_extraction(
                course_subject, book_label, ch_title, section_summaries
            )
            chapter_summary = skills_result.chapter_summary
            skills: list[Skill] = []
            for skill in skills_result.skills:
                skill.concept_names = [
                    n for n in skill.concept_names if n in all_concept_names
                ]
                skills.append(skill)
        except Exception:
            logger.exception(
                "Skills extraction failed for %s / %s", book_label, ch_title
            )
            chapter_summary = ""
            skills = []

        chapter_extraction = ChapterExtraction(
            chapter_title=ch_title,
            chapter_summary=chapter_summary,
            sections=section_extractions,
            skills=skills,
        )

        # ── Embed concept names + text_evidence ──
        writer(
            {
                "type": "agent_status",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "step": "embedding",
                "iteration": iterations,
            }
        )

        try:
            _embed_chapter_concepts(chapter_extraction)
        except Exception:
            logger.exception(
                "Embedding failed for %s / %s — saving without embeddings",
                book_label,
                ch_title,
            )

        elapsed = time.time() - t0

        # Save to database
        save_chapter_extraction(
            run_id=state["run_id"],
            selected_book_id=state["selected_book_id"],
            chapter_extraction=chapter_extraction,
            chapter_index=ch_num,
            chapter_text=chapter_content,
        )

        # Emit: completed
        writer(
            {
                "type": "chapter_completed",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "concept_count": chapter_extraction.total_concept_count,
                "skill_count": len(skills),
                "elapsed_s": round(elapsed, 1),
                "approved": approved,
                "iterations": iterations,
            }
        )

    except Exception as e:
        elapsed = time.time() - t0
        errors.append(
            {
                "book": book_label,
                "chapter": ch_title,
                "error": str(e),
            }
        )
        logger.exception("Chapter extraction failed: %s / %s", book_label, ch_title)

        # Emit: error
        writer(
            {
                "type": "chapter_error",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "error": str(e)[:200],
            }
        )

    return {
        "completed_chapters": [
            {
                "book_name": state["book_name"],
                "chapter_number": ch_num,
                "chapter_title": ch_title,
            }
        ],
        "errors": errors,
    }


def synthesize_results(state) -> dict:
    """Collect all completed chapter results. Final node."""
    completed = state.get("completed_chapters") or []
    errors = state.get("errors") or []
    logger.info(
        "Synthesize: %d chapters completed, %d errors",
        len(completed),
        len(errors),
    )
    return {}
