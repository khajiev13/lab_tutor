"""LangGraph workflow for paragraph-level chunking analysis.

Graph topology (fan-out / fan-in via Send):

  extract_pdf → chunk_paragraphs ──┬─→ embed_single_book  ──┐
                                   └─→ embed_doc_summaries ──┼─→ score_concepts → END
                                                             │      (fan-in)
                 (parallel Send tasks per book + summaries)──┘

The parallel embedding nodes persist BookChunk rows (text + 2048-d embedding
vectors) to PostgreSQL so the frontend can visualise and compare them later.

Exports used by routes.py:
    create_run_and_launch()  — create a BookExtractionRun + launch the graph
"""

from __future__ import annotations

import json
import logging
import operator
import re
import tempfile
from typing import Annotated, TypedDict

import numpy as np
from fastapi import BackgroundTasks
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from neo4j import GraphDatabase
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService
from app.providers.storage import BlobService

from ..models import AnalysisStrategy, BookExtractionRun, ExtractionRunStatus
from .repository import (
    create_run,
    fresh_db,
    get_active_run,
    get_books_from_stored_chunks,
    get_latest_run,
    get_selected_books_with_blobs,
    run_has_chunks,
    run_has_summaries,
    store_book_analysis_summary,
    store_book_document_summary_scores,
    store_chunks,
    store_course_concept_cache,
    store_document_summary_cache,
    update_run,
)

logger = logging.getLogger(__name__)

# ── Chunking params ─────────────────────────────────────────────
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". "]
NOVEL_THRESHOLD = 0.35
COVERED_THRESHOLD = 0.55


# ═══════════════════════════════════════════════════════════════
# State TypedDict
# ═══════════════════════════════════════════════════════════════


class ChunkingState(TypedDict, total=False):
    run_id: int
    course_id: int
    # Per-book data accumulated across nodes
    books: list[dict]  # [{selected_book_id, title, md_text, chunks, chunk_embeddings}]
    # Reducer fields – populated by parallel embedding nodes (fan-in via Send)
    embedded_books: Annotated[list[dict], operator.add]
    doc_summaries: Annotated[list[dict], operator.add]


# ═══════════════════════════════════════════════════════════════
# Text processing helpers
# ═══════════════════════════════════════════════════════════════


def _strip_book_matter(text: str) -> str:
    """Strip front matter (TOC, preface) and back matter (index, bibliography)."""
    front_patterns = [
        r"(?m)^#{1,4}\s*(chapter|Chapter|CHAPTER)\s+[1iI]\b",
        r"(?m)^(Chapter|CHAPTER)\s+1\b",
        r"(?m)^#{1,4}\s*(Part|PART)\s+[1iI]\b",
        r"(?m)^(Part|PART)\s+[1iI]\b",
        r"(?m)^#{1,4}\s+1[\.\s]",
        r"(?m)^#{1,4}\s+\*\*1\*\*",
        r"(?m)^#{1,4}\s+Introduction\b",
    ]
    content_start = None
    for pat in front_patterns:
        m = re.search(pat, text)
        if m:
            candidate = m.start()
            if content_start is None or candidate < content_start:
                content_start = candidate
            break
    if content_start and content_start < len(text) * 0.25:
        text = text[content_start:]

    back_patterns = [
        r"(?m)^#{1,4}\s+(Index|INDEX)\s*$",
        r"(?m)^#{1,4}\s+(Bibliography|BIBLIOGRAPHY)\s*$",
        r"(?m)^#{1,4}\s+(References|REFERENCES)\s*$",
        r"(?m)^#{1,4}\s+(Glossary|GLOSSARY)\s*$",
        r"(?m)^(Index|INDEX)\s*$",
    ]
    content_end = None
    for pat in back_patterns:
        for m in re.finditer(pat, text):
            candidate = m.start()
            if candidate > len(text) * 0.80:
                content_end = candidate
    if content_end:
        text = text[:content_end]

    return text


def _chunk_paragraphs(text: str) -> list[str]:
    """Paragraph-level chunking with RecursiveCharacterTextSplitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=SEPARATORS,
    )
    return splitter.split_text(text)


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def _build_sim_distribution(max_sims: np.ndarray) -> list[dict]:
    if max_sims.size == 0:
        return []

    buckets: list[dict] = []
    for idx in range(20):
        start = idx * 0.05
        end = start + 0.05
        if idx == 19:
            count = int(np.sum((max_sims >= start) & (max_sims <= end)))
        else:
            count = int(np.sum((max_sims >= start) & (max_sims < end)))
        buckets.append(
            {
                "bucket_start": round(start, 2),
                "bucket_end": round(end, 2),
                "count": count,
            }
        )
    return buckets


def _load_course_concepts(course_id: int) -> list[dict]:
    uri = settings.neo4j_uri
    username = settings.neo4j_username
    password = settings.neo4j_password
    if not (uri and username and password):
        raise ValueError("Neo4j is not configured; cannot score concept coverage")

    query = """
    MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})-[m:MENTIONS]->(c:CONCEPT)
    RETURN
      c.name AS concept_name,
      d.topic AS doc_topic,
      coalesce(m.text_evidence, m.definition, '') AS text_evidence,
      c.embedding AS name_embedding,
      coalesce(m.text_evidence_embedding, m.definition_embedding) AS evidence_embedding
    ORDER BY concept_name ASC
    """

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = session.run(query, {"course_id": course_id}).data()
    finally:
        driver.close()

    by_name: dict[str, dict] = {}
    for row in rows:
        concept_name = (row.get("concept_name") or "").strip()
        name_embedding = row.get("name_embedding")
        if not concept_name or not name_embedding:
            continue

        existing = by_name.get(concept_name)
        candidate = {
            "concept_name": concept_name,
            "doc_topic": row.get("doc_topic"),
            "text_evidence": row.get("text_evidence") or None,
            "name_embedding": [float(v) for v in name_embedding],
            "evidence_embedding": (
                [float(v) for v in row["evidence_embedding"]]
                if row.get("evidence_embedding")
                else None
            ),
        }
        if existing is None:
            by_name[concept_name] = candidate
            continue

        # Prefer entries that include evidence text/topic.
        if not existing.get("text_evidence") and candidate.get("text_evidence"):
            by_name[concept_name] = candidate

    concepts = list(by_name.values())
    if not concepts:
        raise ValueError(f"No embedded course concepts found for course {course_id}")
    return concepts


# ═══════════════════════════════════════════════════════════════
# Node 1: extract_pdf
# ═══════════════════════════════════════════════════════════════


def extract_pdf(state: ChunkingState) -> dict:
    """Download each selected book PDF from Azure Blob and convert to markdown."""
    run_id = state["run_id"]
    course_id = state["course_id"]

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.EXTRACTING,
            progress_detail="Extracting PDF text…",
        )
        selected_books = get_selected_books_with_blobs(course_id, db)
        if not selected_books:
            raise ValueError(f"No selected books with blobs for course {course_id}")

    blob_service = BlobService()
    import pymupdf4llm

    books: list[dict] = []
    for sb in selected_books:
        try:
            pdf_bytes = blob_service.download_file(sb.blob_path)

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                tmp.write(pdf_bytes)
                tmp.flush()
                md_text = pymupdf4llm.to_markdown(tmp.name)

            md_text = _strip_book_matter(md_text)

            books.append(
                {
                    "selected_book_id": sb.id,
                    "title": sb.title,
                    "md_text": md_text,
                    "chunks": [],
                    "chunk_embeddings": [],
                }
            )
            logger.info("Extracted %d chars from '%s'", len(md_text), sb.title)
        except Exception:
            logger.exception("Failed to extract PDF for book %s", sb.title)

    if not books:
        raise ValueError("All PDF extractions failed")

    with fresh_db() as db:
        update_run(db, run_id, progress_detail=f"Extracted {len(books)} book(s)")

    return {"books": books}


# ═══════════════════════════════════════════════════════════════
# Node 2: chunk_paragraphs
# ═══════════════════════════════════════════════════════════════


def chunk_paragraphs(state: ChunkingState) -> dict:
    """Split each book's markdown into paragraph-level chunks."""
    run_id = state["run_id"]
    books = state["books"]

    with fresh_db() as db:
        update_run(db, run_id, progress_detail="Chunking paragraphs…")

    for book in books:
        chunks = _chunk_paragraphs(book["md_text"])
        book["chunks"] = chunks
        # Free the large text now that we have chunks
        book["md_text"] = ""
        logger.info("Book '%s': %d paragraph chunks", book["title"], len(chunks))

    total_chunks = sum(len(b["chunks"]) for b in books)
    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.EMBEDDING,
            progress_detail=f"Chunked {total_chunks} paragraphs — starting parallel embedding…",
        )

    return {"books": books}


def _load_and_embed_document_summaries(
    course_id: int,
    run_id: int,
    embedder: EmbeddingService,
) -> list[dict]:
    """Load course document summaries from Neo4j, embed missing ones, cache all."""
    uri = settings.neo4j_uri
    username = settings.neo4j_username
    password = settings.neo4j_password
    if not (uri and username and password):
        logger.warning("Neo4j not configured; skipping document summary embedding")
        return []

    query = """
    MATCH (d:TEACHER_UPLOADED_DOCUMENT {course_id: $course_id})
    WHERE d.summary IS NOT NULL
    RETURN
      d.id AS document_id,
      d.topic AS topic,
      d.summary AS summary_text,
      d.summary_embedding AS summary_embedding
    """

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=settings.neo4j_database) as session:
            rows = session.run(query, {"course_id": course_id}).data()
    finally:
        driver.close()

    if not rows:
        logger.info("No document summaries found for course %d", course_id)
        return []

    # Identify docs needing embedding
    needs_embedding: list[tuple[int, str, str]] = []  # (index, doc_id, summary_text)
    doc_summaries: list[dict] = []

    for idx, row in enumerate(rows):
        doc_id = row["document_id"]
        topic = row.get("topic")
        summary_text = row.get("summary_text") or ""
        existing_emb = row.get("summary_embedding")

        entry: dict = {
            "document_id": doc_id,
            "topic": topic,
            "summary_text": summary_text,
            "summary_embedding": (
                [float(v) for v in existing_emb] if existing_emb else None
            ),
        }
        doc_summaries.append(entry)

        if not existing_emb and summary_text.strip():
            needs_embedding.append((idx, doc_id, summary_text))

    # Embed missing summaries
    if needs_embedding:
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                progress_detail=(
                    f"Embedding {len(needs_embedding)} document summaries…"
                ),
            )

        texts_to_embed = [t for _, _, t in needs_embedding]
        vectors = embedder.embed_documents(texts_to_embed)

        # Write back to Neo4j
        set_query = """
        MATCH (d:TEACHER_UPLOADED_DOCUMENT {id: $document_id})
        SET d.summary_embedding = $vector
        """
        driver = GraphDatabase.driver(uri, auth=(username, password))
        try:
            with driver.session(database=settings.neo4j_database) as session:
                for (_, doc_id, _), vec in zip(needs_embedding, vectors, strict=True):
                    session.run(set_query, {"document_id": doc_id, "vector": vec})
        finally:
            driver.close()

        # Update local entries
        for (orig_idx, _, _), vec in zip(needs_embedding, vectors, strict=True):
            doc_summaries[orig_idx]["summary_embedding"] = vec

        logger.info(
            "Embedded %d document summaries for course %d",
            len(needs_embedding),
            course_id,
        )

    # Cache all summaries in PostgreSQL
    with fresh_db() as db:
        store_document_summary_cache(run_id, doc_summaries, db)
        db.commit()

    logger.info(
        "Cached %d document summaries for run %d", len(doc_summaries), run_id
    )
    return doc_summaries


# ═══════════════════════════════════════════════════════════════
# Fan-out: parallel embedding via Send
# ═══════════════════════════════════════════════════════════════


def fan_out_embeddings(state: ChunkingState) -> list[Send]:
    """Create parallel Send tasks: one per book + one for document summaries."""
    run_id = state["run_id"]
    course_id = state["course_id"]
    books = state["books"]

    sends = [
        Send(
            "embed_single_book",
            {"run_id": run_id, "course_id": course_id, "book": book},
        )
        for book in books
    ]
    sends.append(
        Send("embed_doc_summaries", {"run_id": run_id, "course_id": course_id})
    )
    return sends


# ═══════════════════════════════════════════════════════════════
# Node 3a: embed_single_book  (one Send per book — runs in parallel)
# ═══════════════════════════════════════════════════════════════


def embed_single_book(state: dict) -> dict:
    """Embed chunks for a single book and persist to PostgreSQL."""
    run_id = state["run_id"]
    book = state["book"]
    chunks = book["chunks"]

    if not chunks:
        book["chunk_embeddings"] = []
        return {"embedded_books": [book]}

    embedder = EmbeddingService()
    all_vecs = embedder.embed_documents(chunks)

    book["chunk_embeddings"] = all_vecs
    logger.info("Embedded %d chunks for '%s'", len(all_vecs), book["title"])

    with fresh_db() as db:
        store_chunks(run_id, [book], db)
        db.commit()

    return {"embedded_books": [book]}


# ═══════════════════════════════════════════════════════════════
# Node 3b: embed_doc_summaries  (single Send — runs parallel to books)
# ═══════════════════════════════════════════════════════════════


def embed_doc_summaries(state: dict) -> dict:
    """Load and embed document summaries from Neo4j."""
    run_id = state["run_id"]
    course_id = state["course_id"]

    try:
        embedder = EmbeddingService()
        summaries = _load_and_embed_document_summaries(course_id, run_id, embedder)
    except Exception:
        logger.exception(
            "Non-fatal: document summary embedding failed for run %d", run_id
        )
        summaries = []

    return {"doc_summaries": summaries}


# ═══════════════════════════════════════════════════════════════
# Node 4: score_concepts
# ═══════════════════════════════════════════════════════════════


def score_concepts(state: ChunkingState) -> dict:
    """Score book chunks against course concepts and persist summaries."""
    run_id = state["run_id"]
    course_id = state["course_id"]
    books = state.get("embedded_books", [])
    doc_summaries = state.get("doc_summaries", [])

    if not books:
        with fresh_db() as db:
            books = get_books_from_stored_chunks(run_id, db)
        if books:
            logger.info(
                "Run %d: loaded %d book(s) from stored chunks for scoring-only pass",
                run_id,
                len(books),
            )
        else:
            raise ValueError(
                "No books/chunks available to score. Run extraction+embedding first."
            )

    # For scoring-only pass, load doc summaries from Neo4j if not in state
    if not doc_summaries:
        try:
            embedder = EmbeddingService()
            doc_summaries = _load_and_embed_document_summaries(
                course_id, run_id, embedder
            )
        except Exception:
            logger.exception(
                "Non-fatal: document summary loading failed for run %d", run_id
            )

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.SCORING,
            progress_detail="Scoring concept coverage…",
        )

    concepts = _load_course_concepts(course_id)
    concept_names = [c["concept_name"] for c in concepts]
    concept_topics = [c.get("doc_topic") for c in concepts]
    concept_matrix = np.array([c["name_embedding"] for c in concepts], dtype=np.float32)
    concept_matrix = _l2_normalize(concept_matrix)

    with fresh_db() as db:
        cached_count = store_course_concept_cache(run_id, concepts, db)
        db.commit()
    logger.info("Cached %d concepts for run %d", cached_count, run_id)

    # Build document summary embedding matrix for per-book scoring
    doc_summary_matrix = None
    if doc_summaries:
        valid_doc_sums = [
            ds for ds in doc_summaries if ds.get("summary_embedding")
        ]
        if valid_doc_sums:
            doc_summary_matrix = np.array(
                [ds["summary_embedding"] for ds in valid_doc_sums],
                dtype=np.float32,
            )
            doc_summary_matrix = _l2_normalize(doc_summary_matrix)
        else:
            valid_doc_sums = []
    else:
        valid_doc_sums = []

    total_books = len(books)
    completed_books = 0
    summary_count = 0

    for book in books:
        chunks = book.get("chunks", [])
        chunk_embeddings = book.get("chunk_embeddings", [])
        if not chunks or not chunk_embeddings:
            continue

        chunk_matrix = np.array(chunk_embeddings, dtype=np.float32)
        chunk_matrix = _l2_normalize(chunk_matrix)

        sim_matrix = concept_matrix @ chunk_matrix.T
        max_sims = sim_matrix.max(axis=1)
        best_idx = sim_matrix.argmax(axis=1)

        course_coverage: list[dict] = []
        topic_values: dict[str, list[float]] = {}
        for idx, concept_name in enumerate(concept_names):
            sim_max = float(max_sims[idx])
            chunk_idx = int(best_idx[idx])
            best_match = chunks[chunk_idx] if 0 <= chunk_idx < len(chunks) else ""
            topic = concept_topics[idx]

            course_coverage.append(
                {
                    "concept_name": concept_name,
                    "doc_topic": topic,
                    "sim_max": sim_max,
                    "best_match": best_match[:1200],
                }
            )

            if topic:
                topic_values.setdefault(topic, []).append(sim_max)

        topic_scores = {
            topic: float(sum(values) / len(values))
            for topic, values in topic_values.items()
            if values
        }
        sim_distribution = _build_sim_distribution(max_sims)

        novel_count = int(np.sum(max_sims < NOVEL_THRESHOLD))
        overlap_count = int(
            np.sum((max_sims >= NOVEL_THRESHOLD) & (max_sims < COVERED_THRESHOLD))
        )
        covered_count = int(np.sum(max_sims >= COVERED_THRESHOLD))

        # Score document summaries against this book's chunks
        doc_summary_scores: list[dict] = []
        if doc_summary_matrix is not None and valid_doc_sums:
            doc_sim = doc_summary_matrix @ chunk_matrix.T
            doc_max_sims = doc_sim.max(axis=1)
            for di, ds in enumerate(valid_doc_sums):
                doc_summary_scores.append(
                    {
                        "document_id": ds["document_id"],
                        "topic": ds.get("topic"),
                        "summary_text": (ds.get("summary_text") or "")[:2000],
                        "sim_score": round(float(doc_max_sims[di]), 4),
                    }
                )
            doc_summary_scores.sort(key=lambda x: x["sim_score"], reverse=True)

        with fresh_db() as db:
            summary = store_book_analysis_summary(
                run_id=run_id,
                selected_book_id=book["selected_book_id"],
                strategy=AnalysisStrategy.CHUNKING,
                payload={
                    "book_title": book["title"],
                    "s_final_name": float(max_sims.mean()) if max_sims.size else 0.0,
                    "s_final_evidence": (
                        float(max_sims.mean()) if max_sims.size else 0.0
                    ),
                    "total_book_concepts": len(course_coverage),
                    "chapter_count": 0,
                    "novel_count_default": novel_count,
                    "overlap_count_default": overlap_count,
                    "covered_count_default": covered_count,
                    "book_unique_concepts_json": json.dumps([]),
                    "course_coverage_json": json.dumps(course_coverage),
                    "topic_scores_json": json.dumps(topic_scores),
                    "sim_distribution_json": json.dumps(sim_distribution),
                },
                db=db,
            )
            if doc_summary_scores:
                store_book_document_summary_scores(
                    summary.id, doc_summary_scores, db
                )
            db.commit()

        summary_count += 1
        completed_books += 1
        pct = int(completed_books / total_books * 100) if total_books else 100
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                progress_detail=(
                    f"Scoring concept coverage… {pct}% "
                    f"({completed_books}/{total_books} books)"
                ),
            )

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.COMPLETED,
            progress_detail=(
                f"Done — {summary_count} book summary(ies) scored "
                f"against {len(concepts)} course concepts"
            ),
        )

    logger.info(
        "Scoring completed for run %d: %d summaries, %d concepts",
        run_id,
        summary_count,
        len(concepts),
    )
    return {"books": books}


# ═══════════════════════════════════════════════════════════════
# Build the LangGraph subgraph
# ═══════════════════════════════════════════════════════════════


def build_chunking_graph():
    """Build the ChunkingComparison workflow graph.

    Graph topology:
      extract_pdf → chunk_paragraphs ──┬─→ embed_single_book ──┬─→ score_concepts → END
                                       └─→ embed_doc_summaries─┘
                    (fan-out via Send)        (parallel)       (fan-in)
    """
    builder = StateGraph(ChunkingState)

    builder.add_node("extract_pdf", extract_pdf)
    builder.add_node("chunk_paragraphs", chunk_paragraphs)
    builder.add_node("embed_single_book", embed_single_book)
    builder.add_node("embed_doc_summaries", embed_doc_summaries)
    builder.add_node("score_concepts", score_concepts)

    builder.add_edge(START, "extract_pdf")
    builder.add_edge("extract_pdf", "chunk_paragraphs")
    builder.add_conditional_edges(
        "chunk_paragraphs",
        fan_out_embeddings,
        ["embed_single_book", "embed_doc_summaries"],
    )
    builder.add_edge("embed_single_book", "score_concepts")
    builder.add_edge("embed_doc_summaries", "score_concepts")
    builder.add_edge("score_concepts", END)

    return builder.compile()


# ═══════════════════════════════════════════════════════════════
# Public API (called by routes.py)
# ═══════════════════════════════════════════════════════════════


def create_run_and_launch(
    course_id: int,
    db: Session,
    background_tasks: BackgroundTasks,
) -> BookExtractionRun:
    """Create a new BookExtractionRun and enqueue the workflow via BackgroundTasks.

    Raises ValueError if a run is already in progress for this course.
    """
    active = get_active_run(course_id, db)
    if active:
        raise ValueError(
            f"An analysis run is already in progress (run {active.id}, "
            f"status={active.status.value})"
        )

    latest = get_latest_run(course_id, db)
    if (
        latest
        and latest.status
        in (ExtractionRunStatus.COMPLETED, ExtractionRunStatus.BOOK_PICKED)
        and run_has_chunks(latest.id, db)
        and not run_has_summaries(latest.id, db)
    ):
        update_run(
            db,
            latest.id,
            status=ExtractionRunStatus.SCORING,
            progress_detail="Queued scoring from stored chunk embeddings",
            error_message=None,
        )
        background_tasks.add_task(_run_scoring_only, latest.id, course_id)
        db.refresh(latest)
        return latest

    run = create_run(
        db,
        course_id=course_id,
        status=ExtractionRunStatus.PENDING,
        embedding_model=settings.embedding_model,
        embedding_dims=settings.embedding_dims or 2048,
        progress_detail="Queued",
    )

    background_tasks.add_task(_run_workflow, run.id, course_id)
    return run


def _run_workflow(run_id: int, course_id: int) -> None:
    """Execute the chunking workflow (called by BackgroundTasks)."""
    try:
        graph = build_chunking_graph()
        graph.invoke({"run_id": run_id, "course_id": course_id})
    except Exception as exc:
        logger.exception("Chunking workflow failed for run %d", run_id)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Failed",
            )


def _run_scoring_only(run_id: int, course_id: int) -> None:
    """Execute only scoring for a run that already has persisted chunk embeddings."""
    try:
        score_concepts({"run_id": run_id, "course_id": course_id})
    except Exception as exc:
        logger.exception("Scoring-only workflow failed for run %d", run_id)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                status=ExtractionRunStatus.FAILED,
                error_message=str(exc)[:2000],
                progress_detail="Failed",
            )
