"""Node functions for chunking analysis workflow."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from neo4j import GraphDatabase

from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService

from ..models import (
    AnalysisStrategy,
    BookChapter,
    BookStatus,
    CourseSelectedBook,
    ExtractionRunStatus,
)
from ..pdf_extraction import extract_book_chapters, validate_extracted_chapters
from .repository import (
    fresh_db,
    get_books_from_stored_chunks,
    get_cached_document_summaries,
    get_chapters_for_book,
    get_embedded_chunk_indices,
    get_selected_books_with_blobs,
    store_book_analysis_summary,
    store_book_document_summary_scores,
    store_chapters,
    store_chunks_bare,
    store_course_concept_cache,
    store_document_summary_cache,
    update_chunk_embeddings,
    update_run,
)
from .state import COVERED_THRESHOLD, NOVEL_THRESHOLD, ChunkingState
from .utils import (
    build_sim_distribution,
    chunk_paragraphs_text,
    l2_normalize,
    load_course_concepts,
)

logger = logging.getLogger(__name__)


def extract_pdf(state: ChunkingState) -> dict:
    """Download each selected book PDF, extract chapters, store in SQL.

    Uses the shared pdf_extraction module — single extraction for the
    entire application. Chapters are stored as BookChapter rows so
    both the chunking and agentic pipelines can read them.
    """
    run_id = state["run_id"]
    course_id = state["course_id"]

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.EXTRACTING,
            progress_detail="Extracting PDF text… 0%",
        )
        selected_books = get_selected_books_with_blobs(course_id, db)
        if not selected_books:
            raise ValueError(f"No selected books with blobs for course {course_id}")

    total = len(selected_books)
    books: list[dict] = []
    for idx, sb in enumerate(selected_books):
        book_label = f"Book {idx + 1}/{total} '{sb.title}'"

        def _progress(msg: str, _label: str = book_label) -> None:
            with fresh_db() as _db:
                update_run(
                    _db,
                    run_id,
                    progress_detail=f"{_label} — {msg}",
                )

        try:
            chapters = extract_book_chapters(sb.blob_path, on_progress=_progress)

            # ── Validate chapter quality before chunking ───────
            is_valid, reason = validate_extracted_chapters(chapters)
            if not is_valid:
                logger.warning(
                    "Corrupted PDF for '%s': %s — skipping", sb.title, reason
                )
                with fresh_db() as db:
                    book_row = db.get(CourseSelectedBook, sb.id)
                    if book_row:
                        book_row.status = BookStatus.CORRUPTED_PDF
                        book_row.error_message = reason
                        db.commit()
                    update_run(
                        db,
                        run_id,
                        progress_detail=(
                            f"{book_label} — SKIPPED (corrupted PDF: {reason})"
                        ),
                    )
                continue

            # Store chapters in SQL
            with fresh_db() as db:
                store_chapters(run_id, sb.id, chapters, db)
                db.commit()

            # Build combined markdown from chapters for chunking state
            md_text = "\n\n".join(ch["content"] for ch in chapters)

            books.append(
                {
                    "selected_book_id": sb.id,
                    "title": sb.title,
                    "md_text": md_text,
                    "chunks": [],
                    "chunk_embeddings": [],
                }
            )
            logger.info(
                "Extracted %d chapters (%d chars) from '%s'",
                len(chapters),
                len(md_text),
                sb.title,
            )
        except Exception:
            logger.exception("Failed to extract PDF for book %s", sb.title)

    if not books:
        raise ValueError("All PDF extractions failed or were corrupted")

    skipped = total - len(books)
    detail = f"Extracted {len(books)}/{total} book(s)"
    if skipped:
        detail += f" ({skipped} skipped — corrupted PDF)"
    detail += " — 100%"

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
            progress_detail=detail,
        )

    return {"books": books}


def chunk_paragraphs(state: ChunkingState) -> dict:
    """Split each book's chapters into paragraph-level chunks.

    Reads chapters from SQL (stored during extract_pdf) and chunks each
    chapter separately for better semantic boundaries — no cross-chapter
    chunks.
    """
    run_id = state["run_id"]
    books = state.get("books", [])

    # On resume the graph may not carry in-memory books; reconstruct from SQL.
    if not books:
        with fresh_db() as db:
            all_chapters = (
                db.query(BookChapter)
                .filter(BookChapter.run_id == run_id)
                .order_by(
                    BookChapter.selected_book_id.asc(),
                    BookChapter.chapter_index.asc(),
                )
                .all()
            )
            by_book: dict[int, dict] = {}
            for ch in all_chapters:
                if ch.selected_book_id not in by_book:
                    sb = db.get(CourseSelectedBook, ch.selected_book_id)
                    by_book[ch.selected_book_id] = {
                        "selected_book_id": ch.selected_book_id,
                        "title": sb.title if sb else f"Book {ch.selected_book_id}",
                        "md_text": "",
                        "chunks": [],
                        "chunk_embeddings": [],
                    }
            books = list(by_book.values())
        if not books:
            raise ValueError("No books or chapters to chunk")

    total = len(books)

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.CHUNKING,
            progress_detail="Chunking paragraphs… 0%",
        )

    for idx, book in enumerate(books):
        # Read chapters from SQL and chunk each one separately
        with fresh_db() as db:
            chapters = get_chapters_for_book(run_id, book["selected_book_id"], db)

        all_chunks: list[str] = []
        if chapters:
            for chapter in chapters:
                if chapter.chapter_text:
                    chapter_chunks = chunk_paragraphs_text(chapter.chapter_text)
                    all_chunks.extend(chapter_chunks)
        else:
            # Fallback: chunk the combined md_text if no chapters in SQL
            if book.get("md_text"):
                all_chunks = chunk_paragraphs_text(book["md_text"])

        book["chunks"] = all_chunks
        book["md_text"] = ""
        logger.info(
            "Book '%s': %d paragraph chunks (from %d chapters)",
            book["title"],
            len(all_chunks),
            len(chapters),
        )

        pct = int((idx + 1) / total * 100)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                progress_detail=(
                    f"Chunking paragraphs… {pct}% ({idx + 1}/{total}) — {book['title']}"
                ),
            )

    total_chunks = sum(len(b["chunks"]) for b in books)

    # Persist all chunks to SQL immediately with embedding=None so they survive
    # any crash or timeout that occurs during the embedding stage.
    with fresh_db() as db:
        store_chunks_bare(run_id, books, db)
        db.commit()
    logger.info("Stored %d bare chunks for run %d", total_chunks, run_id)

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.EMBEDDING,
            progress_detail=f"Chunked {total_chunks} paragraphs — starting parallel embedding…",
        )

    return {"books": books}


def embed_books(state: ChunkingState) -> dict:
    """Embed all books sequentially; within each book embed batches in parallel.

    Each batch: read chunk texts from state -> call embedding API -> write
    vectors back to SQL immediately.  The SSE progress endpoint polls the
    SQL table, so the UI updates in real time as rows are committed.

    Workers default to ``settings.embedding_parallel_workers`` (5).
    """
    run_id = state["run_id"]
    books = state.get("books", [])

    logger.info(
        "[run %d] embed_books ENTERED (in-memory books: %d)", run_id, len(books)
    )

    # On resume the graph may not carry in-memory books; reload from SQL.
    if not books:
        with fresh_db() as db:
            books = get_books_from_stored_chunks(run_id, db)
        if not books:
            raise ValueError("No stored chunks to embed")
        logger.info("[run %d] Loaded %d book(s) from SQL", run_id, len(books))

    embedder = EmbeddingService()
    batch_size = max(1, int(settings.embedding_batch_size))
    workers = max(1, int(settings.embedding_parallel_workers))
    logger.info(
        "[run %d] Embedding config: batch_size=%d, workers=%d",
        run_id,
        batch_size,
        workers,
    )

    for book in books:
        chunks = book["chunks"]
        if not chunks:
            book["chunk_embeddings"] = []
            continue

        selected_book_id = book["selected_book_id"]
        n = len(chunks)
        all_vecs: list[list[float] | None] = [None] * n

        # Skip chunks that already have embeddings (resume-safe).
        with fresh_db() as db:
            done = get_embedded_chunk_indices(run_id, selected_book_id, db)
        if len(done) == n:
            logger.info(
                "Skipping '%s' — all %d chunks already embedded",
                book["title"],
                n,
            )
            book["chunk_embeddings"] = book.get("chunk_embeddings") or [None] * n
            continue
        if done:
            logger.info(
                "Resuming '%s': %d/%d chunks already embedded",
                book["title"],
                len(done),
                n,
            )

        # Build batches only for un-embedded index ranges.
        batches: list[tuple[int, list[str]]] = []
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            if all(i in done for i in range(start, end)):
                continue
            batches.append((start, chunks[start:end]))

        logger.info(
            "[run %d] '%s': %d batches to embed (%d chunks, %d already done)",
            run_id,
            book["title"],
            len(batches),
            n,
            len(done),
        )

        embedded_count = 0

        def _embed_batch(
            args: tuple[int, list[str]],
            _book_id: int = selected_book_id,
        ) -> tuple[int, list[list[float]]]:
            start, texts = args
            logger.info(
                "[run %d] Embedding batch start=%d, size=%d for book %d",
                run_id,
                start,
                len(texts),
                _book_id,
            )
            vecs = embedder.embed_documents(texts)
            update_chunk_embeddings(run_id, _book_id, start, vecs)
            logger.info(
                "[run %d] Batch start=%d DONE (%d vecs written) for book %d",
                run_id,
                start,
                len(vecs),
                _book_id,
            )
            return start, vecs

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_embed_batch, b): b for b in batches}
            for future in as_completed(futures):
                start, vecs = future.result()
                for i, vec in enumerate(vecs):
                    all_vecs[start + i] = vec
                embedded_count += 1
                if embedded_count % 10 == 0 or embedded_count == len(batches):
                    logger.info(
                        "[run %d] '%s': %d/%d batches complete",
                        run_id,
                        book["title"],
                        embedded_count,
                        len(batches),
                    )

        book["chunk_embeddings"] = all_vecs  # type: ignore[assignment]
        logger.info("Embedded %d new batches for '%s'", len(batches), book["title"])

    return {"books": books}


def score_concepts(state: ChunkingState) -> dict:
    """Score book chunks against course concepts and persist summaries."""
    run_id = state["run_id"]
    course_id = state["course_id"]

    # Always load from SQL — single source of truth after embed step.
    with fresh_db() as db:
        books = get_books_from_stored_chunks(run_id, db)
    if not books:
        raise ValueError(
            "No books/chunks available to score. Run extraction+embedding first."
        )
    logger.info("Run %d: scoring %d book(s)", run_id, len(books))

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.SCORING,
            progress_detail="Scoring concept coverage…",
        )

    concepts = load_course_concepts(course_id)
    concept_names = [c["concept_name"] for c in concepts]
    concept_topics = [c.get("doc_topic") for c in concepts]
    concept_matrix = l2_normalize(
        np.array([c["name_embedding"] for c in concepts], dtype=np.float32)
    )

    with fresh_db() as db:
        cached_count = store_course_concept_cache(run_id, concepts, db)
        db.commit()
    logger.info("Cached %d concepts for run %d", cached_count, run_id)

    # Load document summaries from SQL cache (embedded during a prior run)
    doc_summaries: list[dict] = []
    try:
        with fresh_db() as db:
            doc_summaries = get_cached_document_summaries(run_id, db)
        if not doc_summaries:
            embedder = EmbeddingService()
            doc_summaries = _load_and_embed_document_summaries(
                course_id,
                run_id,
                embedder,
            )
    except Exception:
        logger.exception(
            "Non-fatal: document summary loading failed for run %d",
            run_id,
        )

    doc_summary_matrix = None
    valid_doc_sums: list[dict] = []
    if doc_summaries:
        valid_doc_sums = [ds for ds in doc_summaries if ds.get("summary_embedding")]
        if valid_doc_sums:
            doc_summary_matrix = l2_normalize(
                np.array(
                    [ds["summary_embedding"] for ds in valid_doc_sums],
                    dtype=np.float32,
                )
            )

    total_books = len(books)
    summary_count = 0

    for book_idx, book in enumerate(books):
        chunks = book.get("chunks", [])
        chunk_embeddings = book.get("chunk_embeddings", [])
        if not chunks or not chunk_embeddings:
            continue

        chunk_matrix = l2_normalize(np.array(chunk_embeddings, dtype=np.float32))

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
        sim_distribution = build_sim_distribution(max_sims)

        novel_count = int(np.sum(max_sims < NOVEL_THRESHOLD))
        overlap_count = int(
            np.sum((max_sims >= NOVEL_THRESHOLD) & (max_sims < COVERED_THRESHOLD))
        )
        covered_count = int(np.sum(max_sims >= COVERED_THRESHOLD))

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
                store_book_document_summary_scores(summary.id, doc_summary_scores, db)
            db.commit()

        summary_count += 1
        pct = int((book_idx + 1) / total_books * 100)
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                progress_detail=(
                    f"Scoring concept coverage… {pct}% "
                    f"({book_idx + 1}/{total_books} books)"
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
    return {}


# ── Helpers (not graph nodes) ───────────────────────────────────


def _load_and_embed_document_summaries(
    course_id: int,
    run_id: int,
    embedder: EmbeddingService,
) -> list[dict]:
    """Load course document summaries from Neo4j, embed missing ones, cache."""
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

    needs_embedding: list[tuple[int, str, str]] = []
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

    if needs_embedding:
        with fresh_db() as db:
            update_run(
                db,
                run_id,
                progress_detail=(
                    f"Embedding {len(needs_embedding)} document summaries…"
                ),
            )

        texts_to_embed = [text for _, _, text in needs_embedding]
        vectors = embedder.embed_documents(texts_to_embed)

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

        for (orig_idx, _, _), vec in zip(needs_embedding, vectors, strict=True):
            doc_summaries[orig_idx]["summary_embedding"] = vec

        logger.info(
            "Embedded %d document summaries for course %d",
            len(needs_embedding),
            course_id,
        )

    with fresh_db() as db:
        store_document_summary_cache(run_id, doc_summaries, db)
        db.commit()

    logger.info("Cached %d document summaries for run %d", len(doc_summaries), run_id)
    return doc_summaries


__all__ = [
    "extract_pdf",
    "chunk_paragraphs",
    "embed_books",
    "score_concepts",
]
