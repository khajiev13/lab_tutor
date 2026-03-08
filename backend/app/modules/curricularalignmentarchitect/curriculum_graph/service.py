"""Orchestration service: reads PostgreSQL, writes curriculum graph to Neo4j.

Yields SSE-friendly progress dicts so the API layer can stream them.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncGenerator, Generator

from neo4j import Driver
from sqlalchemy.orm import Session, joinedload

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService

from ..models import (
    BookChapter,
    BookExtractionRun,
    BookSection,
    CourseSelectedBook,
    ExtractionRunStatus,
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

    async def build_curriculum(
        self,
        course_id: int,
        run_id: int,
        selected_book_id: int,
    ) -> AsyncGenerator[dict, None]:
        """Generator that streams progress events while building the graph."""

        # ── 1. Validate & load data from PostgreSQL ─────────────
        with _fresh_db() as db:
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

            book = db.get(CourseSelectedBook, selected_book_id)
            if book is None or book.course_id != course_id:
                yield {"event": "error", "message": "Selected book not found."}
                return

            chapters = (
                db.query(BookChapter)
                .options(
                    joinedload(BookChapter.sections).joinedload(BookSection.concepts)
                )
                .filter(
                    BookChapter.run_id == run_id,
                    BookChapter.selected_book_id == selected_book_id,
                )
                .order_by(BookChapter.chapter_index)
                .all()
            )

            if not chapters:
                yield {"event": "error", "message": "No chapters found for this book."}
                return

            # Snapshot the data we need before leaving the session scope.
            chapter_data = _snapshot_chapters(chapters)
            book_title = book.title
            book_authors = book.authors
            book_publisher = book.publisher
            book_year = book.year
            book_id = f"book_{selected_book_id}"

        total_chapters = len(chapter_data)

        yield {
            "event": "progress",
            "step": "loaded_data",
            "total_chapters": total_chapters,
        }

        # ── 2. Embed chapter summaries ──────────────────────────
        yield {"event": "progress", "step": "embedding_chapter_summaries"}

        summaries_to_embed = [ch["summary"] or ch["title"] for ch in chapter_data]

        try:
            embedding_svc = EmbeddingService()
            summary_embeddings = embedding_svc.embed_documents(summaries_to_embed)
        except Exception as exc:
            logger.exception("Failed to embed chapter summaries")
            yield {"event": "error", "message": f"Embedding failed: {exc}"}
            return

        for i, ch in enumerate(chapter_data):
            ch["summary_embedding"] = summary_embeddings[i]

        yield {"event": "progress", "step": "embedding_done"}

        # ── 3. Write to Neo4j ───────────────────────────────────
        driver = create_neo4j_driver()
        if driver is None:
            yield {"event": "error", "message": "Neo4j is not configured."}
            return

        try:
            for event in self._write_graph(
                driver=driver,
                course_id=course_id,
                book_id=book_id,
                book_title=book_title,
                book_authors=book_authors,
                book_publisher=book_publisher,
                book_year=book_year,
                chapter_data=chapter_data,
            ):
                yield event
        except Exception as exc:
            logger.exception("Neo4j graph write failed")
            yield {"event": "error", "message": f"Graph write failed: {exc}"}
            return
        finally:
            driver.close()

        # ── 4. Update run status in PostgreSQL ──────────────────
        # Persist status *before* yielding the final event so it
        # survives even if the SSE connection drops.
        with _fresh_db() as db:
            run = db.get(BookExtractionRun, run_id)
            if run:
                run.status = ExtractionRunStatus.CURRICULUM_BUILT
                db.commit()
                logger.info("Run %d status set to CURRICULUM_BUILT", run_id)

        yield {
            "event": "complete",
            "book_id": book_id,
            "total_chapters": total_chapters,
        }

    # ── Private: Neo4j write pipeline ───────────────────────────

    def _write_graph(
        self,
        *,
        driver: Driver,
        course_id: int,
        book_id: str,
        book_title: str,
        book_authors: str | None,
        book_publisher: str | None,
        book_year: str | None,
        chapter_data: list[dict],
    ) -> Generator[dict, None, None]:
        """Synchronous generator that writes nodes/rels and yields progress."""

        with driver.session(database=settings.neo4j_database) as session:
            # Book node + link to CLASS
            yield {"event": "progress", "step": "creating_book_node"}

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
            )

            # Chapter nodes
            yield {"event": "progress", "step": "creating_chapters"}

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

            # Per-chapter: sections, concepts, skills
            concepts_seen: set[str] = set()

            for ch_idx, ch in enumerate(chapter_data):
                ch_id = _chapter_id(book_id, ch["chapter_index"])
                yield {
                    "event": "progress",
                    "step": "processing_chapter",
                    "chapter_index": ch["chapter_index"],
                    "chapter_title": ch["title"],
                    "chapter_number": ch_idx + 1,
                    "total_chapters": len(chapter_data),
                }

                # Sections
                section_payloads = [
                    {
                        "id": _section_id(
                            book_id, ch["chapter_index"], sec["section_index"]
                        ),
                        "title": sec["title"],
                        "section_index": sec["section_index"],
                        "theory": sec.get("content") or "",
                    }
                    for sec in ch["sections"]
                ]
                if section_payloads:
                    session.execute_write(
                        repo.create_section_nodes,
                        chapter_id=ch_id,
                        sections=section_payloads,
                    )
                    session.execute_write(
                        repo.link_sections_linked_list,
                        chapter_id=ch_id,
                    )

                # Concepts per section
                for sec in ch["sections"]:
                    sec_id = _section_id(
                        book_id, ch["chapter_index"], sec["section_index"]
                    )
                    for concept in sec["concepts"]:
                        concept_lower = concept["name"].lower()
                        session.execute_write(
                            repo.merge_concept_node,
                            name=concept["name"],
                            embedding=concept.get("name_embedding"),
                            description=concept.get("description"),
                        )
                        session.execute_write(
                            repo.create_mentions_rel,
                            section_id=sec_id,
                            concept_name=concept["name"],
                            relevance=concept["relevance"],
                            text_evidence=concept.get("text_evidence"),
                        )
                        concepts_seen.add(concept_lower)

                # Skills
                for sk_idx, skill in enumerate(ch["skills"]):
                    sk_id = _skill_id(book_id, ch["chapter_index"], sk_idx)
                    session.execute_write(
                        repo.create_skill_node,
                        skill_id=sk_id,
                        name=skill["name"],
                        description=skill.get("description", ""),
                    )
                    session.execute_write(
                        repo.link_skill_to_chapter,
                        chapter_id=ch_id,
                        skill_id=sk_id,
                    )
                    for concept_name in skill.get("concept_names", []):
                        if concept_name.lower() in concepts_seen:
                            session.execute_write(
                                repo.link_skill_requires_concept,
                                skill_id=sk_id,
                                concept_name=concept_name,
                            )

            # ── Concept similarity merging pass ─────────────────
            yield {"event": "progress", "step": "merging_similar_concepts"}

            # Guard: only run if the vector index is online
            index_ready = session.execute_read(
                repo.vector_index_exists,
            )
            if index_ready:
                merged_count = self._merge_similar_concepts(session, concepts_seen)
            else:
                logger.warning("Skipping concept merge: vector index not online yet")
                merged_count = 0

            yield {
                "event": "progress",
                "step": "merging_done",
                "merged_count": merged_count,
            }

    def _merge_similar_concepts(
        self,
        session,
        concepts_seen: set[str],
    ) -> int:
        """Run a single pass of vector-similarity concept merging."""
        merged = 0
        already_merged: set[str] = set()

        for concept_name in concepts_seen:
            if concept_name in already_merged:
                continue

            # Fetch embedding for this concept
            result = session.run(
                "MATCH (c:CONCEPT {name: toLower($name)}) RETURN c.embedding AS emb",
                name=concept_name,
            ).single()

            if result is None or result["emb"] is None:
                continue

            embedding = result["emb"]

            similars = session.execute_read(
                repo.find_similar_concepts,
                concept_name=concept_name,
                embedding=embedding,
                threshold=0.92,
                top_k=5,
            )

            for sim in similars:
                sim_name = sim["name"]
                if sim_name in already_merged:
                    continue
                try:
                    session.execute_write(
                        repo.merge_similar_concepts,
                        keep_name=concept_name,
                        merge_name=sim_name,
                    )
                    already_merged.add(sim_name)
                    merged += 1
                    logger.info("Merged concept '%s' into '%s'", sim_name, concept_name)
                except Exception:
                    logger.warning(
                        "Failed to merge '%s' into '%s'",
                        sim_name,
                        concept_name,
                        exc_info=True,
                    )

        return merged


# ── Data snapshot helper ────────────────────────────────────────


def _snapshot_chapters(chapters: list[BookChapter]) -> list[dict]:
    """Convert ORM objects to plain dicts while still inside the session."""
    result = []
    for ch in chapters:
        sections = []
        for sec in sorted(ch.sections, key=lambda s: s.section_index):
            concepts = []
            for c in sec.concepts:
                concepts.append(
                    {
                        "name": c.name,
                        "description": c.description,
                        "relevance": c.relevance.value,
                        "text_evidence": c.text_evidence,
                        "name_embedding": (
                            list(c.name_embedding)
                            if c.name_embedding is not None
                            else None
                        ),
                    }
                )
            sections.append(
                {
                    "title": sec.section_title,
                    "section_index": sec.section_index,
                    "content": sec.section_content,
                    "concepts": concepts,
                }
            )
        result.append(
            {
                "title": ch.chapter_title,
                "chapter_index": ch.chapter_index,
                "content": ch.chapter_text,
                "summary": ch.chapter_summary,
                "skills": _parse_skills_json(ch.skills_json),
                "sections": sections,
                "summary_embedding": None,  # filled after embedding step
            }
        )
    return result
