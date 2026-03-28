"""Orchestration service: reads PostgreSQL, writes candidate books to Neo4j.

Writes ALL selected books for a course to the knowledge graph with
CANDIDATE_BOOK relationships.  Yields SSE-friendly progress dicts
so the API layer can stream them.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncGenerator, Generator

from neo4j import Driver
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService

from ..models import (
    BookChapter,
    CourseSelectedBook,
)
from .repository import CurriculumGraphRepository

logger = logging.getLogger(__name__)

repo = CurriculumGraphRepository()


# ── Helpers ─────────────────────────────────────────────────────


@contextlib.contextmanager
def _fresh_db() -> Generator[Session, None, None]:
    """Short-lived DB session for background work."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        with contextlib.suppress(Exception):
            db.rollback()
        raise
    finally:
        with contextlib.suppress(Exception):
            db.close()


def _chapter_id(book_id: str, chapter_index: int) -> str:
    return f"{book_id}_ch_{chapter_index}"


def _section_id(book_id: str, chapter_index: int, section_index: int) -> str:
    return f"{book_id}_ch_{chapter_index}_sec_{section_index}"


def _skill_id(book_id: str, chapter_index: int, skill_index: int) -> str:
    return f"{book_id}_ch_{chapter_index}_sk_{skill_index}"


def _parse_skills_json(raw: str | None) -> list[dict]:
    """Safely parse the skills_json column; returns [] on failure."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ── Service ─────────────────────────────────────────────────────


class CurriculumGraphService:
    """Reads from PostgreSQL, writes to Neo4j, yields SSE progress events."""

    async def build_candidate_books_graph(
        self,
        course_id: int,
        run_id: int,
    ) -> AsyncGenerator[dict, None]:
        """Build knowledge graph for ALL selected books of a course.

        Creates CANDIDATE_BOOK relationships from CLASS to each BOOK,
        with their full chapter/section/concept/skill content.
        """

        # ── 1. Load ALL selected books for this course ─────────
        with _fresh_db() as db:
            from ..models import BookExtractionRun, ExtractionRunStatus

            run = db.get(BookExtractionRun, run_id)
            if run is None or run.course_id != course_id:
                yield {"event": "error", "message": "Analysis run not found."}
                return

            allowed = {
                ExtractionRunStatus.BOOK_PICKED,
                ExtractionRunStatus.AGENTIC_COMPLETED,
            }
            if run.status not in allowed:
                yield {
                    "event": "error",
                    "message": f"Run status must be one of {[s.value for s in allowed]}, "
                    f"got '{run.status.value}'.",
                }
                return

            selected_books = (
                db.query(CourseSelectedBook)
                .filter(CourseSelectedBook.course_id == course_id)
                .all()
            )

            if not selected_books:
                yield {
                    "event": "error",
                    "message": "No selected books found for this course.",
                }
                return

            # Snapshot book metadata
            books_meta = []
            for idx, book in enumerate(selected_books):
                chapters = (
                    db.query(BookChapter)
                    .filter(
                        BookChapter.run_id == run_id,
                        BookChapter.selected_book_id == book.id,
                    )
                    .order_by(BookChapter.chapter_index)
                    .all()
                )

                chapter_data = _snapshot_chapters(chapters) if chapters else []
                books_meta.append(
                    {
                        "selected_book_id": book.id,
                        "book_id": f"book_{book.id}",
                        "title": book.title,
                        "authors": book.authors,
                        "publisher": book.publisher,
                        "year": book.year,
                        "rank": idx + 1,
                        "s_final": 0.0,  # will be populated if score available
                        "chapter_data": chapter_data,
                    }
                )

        total_books = len(books_meta)
        yield {
            "event": "progress",
            "step": "loaded_data",
            "total_books": total_books,
        }

        # ── 2. Connect to Neo4j ─────────────────────────────────
        driver = create_neo4j_driver()
        if driver is None:
            yield {"event": "error", "message": "Neo4j is not configured."}
            return

        try:
            for book_idx, book_meta in enumerate(books_meta):
                book_id = book_meta["book_id"]
                chapter_data = book_meta["chapter_data"]

                yield {
                    "event": "progress",
                    "step": "processing_book",
                    "book_number": book_idx + 1,
                    "total_books": total_books,
                    "book_title": book_meta["title"],
                }

                # ── 2a. Embed chapter summaries ─────────────────
                if chapter_data:
                    yield {
                        "event": "progress",
                        "step": "embedding_chapter_summaries",
                        "book_title": book_meta["title"],
                    }

                    summaries_to_embed = [
                        ch["summary"] or ch["title"] for ch in chapter_data
                    ]

                    try:
                        embedding_svc = EmbeddingService()
                        summary_embeddings = embedding_svc.embed_documents(
                            summaries_to_embed
                        )
                    except Exception as exc:
                        logger.exception(
                            "Failed to embed chapter summaries for book %s",
                            book_meta["title"],
                        )
                        yield {
                            "event": "error",
                            "message": f"Embedding failed for '{book_meta['title']}': {exc}",
                        }
                        continue

                    for i, ch in enumerate(chapter_data):
                        ch["summary_embedding"] = summary_embeddings[i]

                # ── 2b. Write to Neo4j ──────────────────────────
                for event in self._write_book_graph(
                    driver=driver,
                    course_id=course_id,
                    book_id=book_id,
                    book_title=book_meta["title"],
                    book_authors=book_meta["authors"],
                    book_publisher=book_meta["publisher"],
                    book_year=book_meta["year"],
                    rank=book_meta["rank"],
                    s_final=book_meta["s_final"],
                    chapter_data=chapter_data,
                ):
                    yield event

        except Exception as exc:
            logger.exception("Neo4j graph write failed")
            yield {"event": "error", "message": f"Graph write failed: {exc}"}
            return
        finally:
            driver.close()

        yield {
            "event": "complete",
            "total_books": total_books,
        }

    # ── Private: Neo4j write pipeline for a single book ─────────

    def _write_book_graph(
        self,
        *,
        driver: Driver,
        course_id: int,
        book_id: str,
        book_title: str,
        book_authors: str | None,
        book_publisher: str | None,
        book_year: str | None,
        rank: int,
        s_final: float,
        chapter_data: list[dict],
    ) -> Generator[dict, None, None]:
        """Synchronous generator that writes one book's nodes/rels and yields progress."""

        with driver.session(database=settings.neo4j_database) as session:
            # Book node + CANDIDATE_BOOK link to CLASS
            yield {
                "event": "progress",
                "step": "creating_book_node",
                "book_title": book_title,
            }

            session.execute_write(
                repo.create_book_node,
                book_id=book_id,
                title=book_title,
                authors=book_authors,
                publisher=book_publisher,
                year=book_year,
            )
            session.execute_write(
                repo.link_class_to_book,
                course_id=course_id,
                book_id=book_id,
                rank=rank,
                s_final=s_final,
            )

            if not chapter_data:
                yield {
                    "event": "progress",
                    "step": "book_done_no_chapters",
                    "book_title": book_title,
                }
                return

            # Chapter nodes
            yield {
                "event": "progress",
                "step": "creating_chapters",
                "book_title": book_title,
            }

            chapter_payloads = [
                {
                    "id": _chapter_id(book_id, ch["chapter_index"]),
                    "title": ch["title"],
                    "chapter_index": ch["chapter_index"],
                    "content": ch.get("content") or "",
                    "summary": ch["summary"],
                    "summary_embedding": ch["summary_embedding"],
                }
                for ch in chapter_data
            ]
            session.execute_write(
                repo.create_chapter_nodes,
                book_id=book_id,
                chapters=chapter_payloads,
            )
            session.execute_write(
                repo.link_chapters_linked_list,
                book_id=book_id,
            )

            # ── Batch-embed all skills for this book ────────────────
            all_skills_flat: list[dict] = []
            for ch in chapter_data:
                for sk_idx, skill in enumerate(ch["skills"]):
                    all_skills_flat.append(
                        {
                            "name": skill["name"],
                            "description": skill.get("description", ""),
                            "chapter_index": ch["chapter_index"],
                            "sk_idx": sk_idx,
                            "concepts": [c["name"] for c in skill.get("concepts", [])],
                        }
                    )

            if all_skills_flat:
                yield {
                    "event": "progress",
                    "step": "embedding_skills",
                    "book_title": book_title,
                    "skill_count": len(all_skills_flat),
                }

                try:
                    embedding_svc = EmbeddingService()
                    skill_name_embeddings = embedding_svc.embed_documents(
                        [s["name"] for s in all_skills_flat]
                    )
                    skill_desc_embeddings = embedding_svc.embed_documents(
                        [s["description"] for s in all_skills_flat]
                    )
                except Exception as exc:
                    logger.exception("Failed to embed skills for book %s", book_title)
                    yield {
                        "event": "error",
                        "message": f"Skill embedding failed for '{book_title}': {exc}",
                    }
                    # Fall back to writing skills without embeddings
                    skill_name_embeddings = [None] * len(all_skills_flat)
                    skill_desc_embeddings = [None] * len(all_skills_flat)

                for i, s in enumerate(all_skills_flat):
                    s["name_embedding"] = skill_name_embeddings[i]
                    s["description_embedding"] = skill_desc_embeddings[i]

            # ── Write skills per chapter via batch Cypher ──────────
            # Group skills back by chapter_index
            skills_by_chapter: dict[int, list[dict]] = {}
            for s in all_skills_flat:
                skills_by_chapter.setdefault(s["chapter_index"], []).append(s)

            for ch_idx, ch in enumerate(chapter_data):
                ch_id = _chapter_id(book_id, ch["chapter_index"])
                yield {
                    "event": "progress",
                    "step": "processing_chapter",
                    "chapter_index": ch["chapter_index"],
                    "chapter_title": ch["title"],
                    "chapter_number": ch_idx + 1,
                    "total_chapters": len(chapter_data),
                    "book_title": book_title,
                }

                ch_skills = skills_by_chapter.get(ch["chapter_index"], [])
                if ch_skills:
                    skill_payloads = [
                        {
                            "id": _skill_id(book_id, ch["chapter_index"], s["sk_idx"]),
                            "name": s["name"],
                            "description": s["description"],
                            "name_embedding": s["name_embedding"],
                            "description_embedding": s["description_embedding"],
                            "concepts": s["concepts"],
                        }
                        for s in ch_skills
                    ]
                    session.execute_write(
                        repo.create_skill_nodes_batch,
                        chapter_id=ch_id,
                        skills=skill_payloads,
                    )


# ── Data snapshot helper ────────────────────────────────────────


def _snapshot_chapters(chapters: list[BookChapter]) -> list[dict]:
    """Convert ORM objects to plain dicts while still inside the session."""
    return [
        {
            "title": ch.chapter_title,
            "chapter_index": ch.chapter_index,
            "content": ch.chapter_text,
            "summary": ch.chapter_summary,
            "skills": _parse_skills_json(ch.skills_json),
            "summary_embedding": None,  # filled after embedding step
        }
        for ch in chapters
    ]
