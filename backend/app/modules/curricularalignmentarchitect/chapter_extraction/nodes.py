"""LangGraph node functions for chapter-level skills extraction.

Pipeline per chapter:
  1. Extract skills + inline concepts directly from chapter content (one LLM call).
  2. Karpathy-style LLM judge evaluates quality.
  3. One revision pass if the judge requests it.
  4. Persist to PostgreSQL (BookChapter row) + Neo4j (BOOK_SKILL + CONCEPT nodes).
"""

from __future__ import annotations

import json
import logging
import time

import openai
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.types import RetryPolicy

from app.core.settings import settings

from .prompts import (
    SKILLS_JUDGE_PROMPT,
    SKILLS_PROMPT,
    SKILLS_REVISION_PROMPT,
    truncate_content,
)
from .schemas import ChapterSkillsResult, Skill, SkillsJudgeFeedback, SkillsJudgeVerdict
from .state import MAX_JUDGE_ITERATIONS, ChapterWorkerInput

logger = logging.getLogger(__name__)


# ── LLM setup ─────────────────────────────────────────────────────────────────


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        max_tokens=8192,
        temperature=0,
        timeout=settings.llm_timeout_seconds,
    )


def _skills_llm():
    return _build_llm().with_structured_output(ChapterSkillsResult, method="json_mode")


def _judge_llm():
    return _build_llm().with_structured_output(SkillsJudgeFeedback, method="json_mode")


# ── Retry policy ──────────────────────────────────────────────────────────────

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


# ── Core extraction helpers ────────────────────────────────────────────────────


def _extract_skills(
    course_subject: str,
    book_name: str,
    chapter_title: str,
    chapter_content: str,
) -> ChapterSkillsResult:
    return (SKILLS_PROMPT | _skills_llm()).invoke(
        {
            "course_subject": course_subject,
            "book_name": book_name,
            "chapter_title": chapter_title,
            "chapter_content": truncate_content(chapter_content),
        }
    )


def _judge_skills(
    course_subject: str,
    book_name: str,
    chapter_title: str,
    result: ChapterSkillsResult,
) -> SkillsJudgeFeedback:
    skills_json = json.dumps(
        [s.model_dump() for s in result.skills], indent=2, ensure_ascii=False
    )
    return (SKILLS_JUDGE_PROMPT | _judge_llm()).invoke(
        {
            "course_subject": course_subject,
            "book_name": book_name,
            "chapter_title": chapter_title,
            "skills_json": skills_json,
            "chapter_summary": result.chapter_summary,
        }
    )


def _revise_skills(
    course_subject: str,
    book_name: str,
    chapter_title: str,
    chapter_content: str,
    previous: ChapterSkillsResult,
    issues: list[str],
) -> ChapterSkillsResult:
    previous_json = json.dumps(previous.model_dump(), indent=2, ensure_ascii=False)
    issue_text = (
        "\n".join(f"- {i}" for i in issues) if issues else "(no specific issues)"
    )
    return (SKILLS_REVISION_PROMPT | _skills_llm()).invoke(
        {
            "course_subject": course_subject,
            "book_name": book_name,
            "chapter_title": chapter_title,
            "chapter_content": truncate_content(chapter_content),
            "previous_extraction": previous_json,
            "issues": issue_text,
        }
    )


# ── Neo4j persistence ─────────────────────────────────────────────────────────


def _save_skills_to_neo4j(
    selected_book_id: int,
    chapter_index: int,
    chapter_title: str,
    skills: list[Skill],
) -> None:
    """Write BOOK_SKILL + CONCEPT nodes to Neo4j for one chapter.

    Batch-embeds skill names and descriptions, then creates skill nodes
    with embeddings and links them to a stub BOOK_CHAPTER node.
    """
    from app.core.neo4j import create_neo4j_driver
    from app.core.settings import settings as _settings
    from app.modules.curricularalignmentarchitect.chapter_extraction.repository import (
        fresh_db,
    )
    from app.modules.curricularalignmentarchitect.curriculum_graph.repository import (
        CurriculumGraphRepository,
    )
    from app.modules.curricularalignmentarchitect.models import CourseSelectedBook
    from app.modules.embeddings.embedding_service import EmbeddingService

    driver = create_neo4j_driver()
    if driver is None:
        logger.warning("Neo4j not configured — skipping skill graph write")
        return

    book_neo4j_id = f"book_{selected_book_id}"

    with fresh_db() as db:
        book = db.get(CourseSelectedBook, selected_book_id)
        if not book:
            logger.warning("Book %d not found in psycopg", selected_book_id)
            return
        b_title = book.title
        b_authors = book.authors
        b_publisher = book.publisher
        b_year = book.year
        b_url = book.blob_url
        b_course_id = book.course_id

    repo = CurriculumGraphRepository()
    chapter_id = f"{book_neo4j_id}_ch_{chapter_index}"

    # Batch-embed skill names and descriptions
    name_embeddings: list[list[float] | None]
    desc_embeddings: list[list[float] | None]
    try:
        embedder = EmbeddingService()
        name_embeddings = embedder.embed_documents([s.name for s in skills])
        desc_embeddings = embedder.embed_documents([s.description for s in skills])
    except Exception:
        logger.exception(
            "Skill embedding failed for %s ch %d — writing without embeddings",
            book_neo4j_id,
            chapter_index,
        )
        name_embeddings = [None] * len(skills)
        desc_embeddings = [None] * len(skills)

    try:
        with driver.session(database=_settings.neo4j_database) as session:
            # Ensure BOOK + BOOK_CHAPTER stubs exist and CLASS→CANDIDATE_BOOK link
            session.run(
                """
                MERGE (b:BOOK {id: $book_id})
                SET b.title = $title,
                    b.authors = $authors,
                    b.publisher = $publisher,
                    b.year = $year,
                    b.blob_url = $blob_url
                MERGE (ch:BOOK_CHAPTER {id: $ch_id})
                SET ch.title = $ch_title,
                    ch.chapter_index = $ch_index
                MERGE (b)-[:HAS_CHAPTER]->(ch)
                WITH b
                MATCH (cl:CLASS {id: $course_id})
                MERGE (cl)-[:CANDIDATE_BOOK]->(b)
                """,
                book_id=book_neo4j_id,
                ch_id=chapter_id,
                ch_title=chapter_title,
                ch_index=chapter_index,
                course_id=b_course_id,
                title=b_title,
                authors=b_authors,
                publisher=b_publisher,
                year=b_year,
                blob_url=b_url,
            )

            skill_payloads = [
                {
                    "id": f"{book_neo4j_id}_ch_{chapter_index}_sk_{sk_idx}",
                    "name": skill.name,
                    "description": skill.description,
                    "name_embedding": name_embeddings[sk_idx],
                    "description_embedding": desc_embeddings[sk_idx],
                    "concepts": [c.name for c in skill.concepts],
                }
                for sk_idx, skill in enumerate(skills)
            ]

            if skill_payloads:
                session.execute_write(
                    repo.create_skill_nodes_batch,
                    chapter_id=chapter_id,
                    skills=skill_payloads,
                )
    finally:
        driver.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Outer graph nodes
# ═══════════════════════════════════════════════════════════════════════════════


def assign_chapters(state):
    """Fan out Send() for each pending chapter."""
    from langgraph.types import Send

    from .repository import fresh_db, get_completed_chapter_indices

    with fresh_db() as db:
        completed = get_completed_chapter_indices(
            state["run_id"], state["selected_book_id"], db
        )

    sends = []
    for ch in sorted(state["chapters"], key=lambda x: x["chapter_number"]):
        if ch["chapter_number"] in completed:
            continue
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
                    "chapter_content": ch["content"],
                    "total_chapters": state["total_chapters"],
                },
            )
        )
    return sends


def chapter_worker(state: ChapterWorkerInput) -> dict:
    """Process one chapter: extract skills → judge → (revise once) → persist.

    Emits real-time progress events via get_stream_writer().
    """
    from .repository import save_chapter_skills

    writer = get_stream_writer()
    book_label = state["book_label"]
    course_subject = state["course_subject"]
    ch_title = state["chapter_title"]
    ch_num = state["chapter_number"]
    chapter_content = state["chapter_content"]
    run_id = state["run_id"]
    selected_book_id = state["selected_book_id"]

    t0 = time.time()
    errors: list[dict] = []

    writer(
        {
            "type": "agent_status",
            "book_title": book_label,
            "chapter_title": ch_title,
            "chapter_number": ch_num,
            "total_chapters": state["total_chapters"],
            "step": "extracting_skills",
        }
    )

    try:
        # ── 1. Extract skills ──────────────────────────────────────
        result = _extract_skills(course_subject, book_label, ch_title, chapter_content)

        # ── 2. Judge (Karpathy-style) ──────────────────────────────
        writer(
            {
                "type": "agent_status",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "step": "judging",
                "skill_count": len(result.skills),
            }
        )

        feedback = _judge_skills(course_subject, book_label, ch_title, result)

        if (
            feedback.verdict == SkillsJudgeVerdict.NEEDS_REVISION
            and MAX_JUDGE_ITERATIONS > 0
        ):
            logger.info(
                "Judge requested revision for %s / %s: %s",
                book_label,
                ch_title,
                "; ".join(feedback.issues),
            )
            writer(
                {
                    "type": "agent_status",
                    "book_title": book_label,
                    "chapter_title": ch_title,
                    "chapter_number": ch_num,
                    "total_chapters": state["total_chapters"],
                    "step": "revising",
                }
            )
            result = _revise_skills(
                course_subject,
                book_label,
                ch_title,
                chapter_content,
                result,
                feedback.issues,
            )

        # ── 3. Persist to PostgreSQL ───────────────────────────────
        save_chapter_skills(
            run_id=run_id,
            selected_book_id=selected_book_id,
            chapter_index=ch_num,
            chapter_title=ch_title,
            chapter_summary=result.chapter_summary,
            skills=result.skills,
        )

        # ── 4. Persist to Neo4j ────────────────────────────────────
        try:
            _save_skills_to_neo4j(selected_book_id, ch_num, ch_title, result.skills)
        except Exception:
            logger.exception(
                "Neo4j skill write failed for %s / %s — PostgreSQL save succeeded",
                book_label,
                ch_title,
            )

        elapsed = time.time() - t0
        writer(
            {
                "type": "chapter_completed",
                "book_title": book_label,
                "chapter_title": ch_title,
                "chapter_number": ch_num,
                "total_chapters": state["total_chapters"],
                "skill_count": len(result.skills),
                "concept_count": sum(len(sk.concepts) for sk in result.skills),
                "elapsed_s": round(elapsed, 1),
                "judge_verdict": feedback.verdict.value,
            }
        )

    except Exception as e:
        elapsed = time.time() - t0
        errors.append({"book": book_label, "chapter": ch_title, "error": str(e)})
        logger.exception(
            "Chapter skills extraction failed: %s / %s", book_label, ch_title
        )
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
