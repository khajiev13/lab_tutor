"""LangGraph workflow for paragraph-level chunking analysis.

Subgraph: extract_pdf → chunk_paragraphs → embed_chunks

The final node persists BookChunk rows (text + 2048-d embedding vectors) to
PostgreSQL so the frontend can visualise and compare them later.

Exports used by routes.py:
    create_run_and_launch()  — create a BookExtractionRun + launch the graph
"""

from __future__ import annotations

import logging
import re
import tempfile
from typing import TypedDict

from fastapi import BackgroundTasks
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.embeddings.embedding_service import EmbeddingService
from app.providers.storage import BlobService

from .chunking_repository import (
    create_run,
    fresh_db,
    get_active_run,
    get_selected_books_with_blobs,
    store_chunks,
    update_run,
)
from .models import BookExtractionRun, ExtractionRunStatus

logger = logging.getLogger(__name__)

# ── Chunking params ─────────────────────────────────────────────
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
SEPARATORS = ["\n\n", "\n", ". "]


# ═══════════════════════════════════════════════════════════════
# State TypedDict
# ═══════════════════════════════════════════════════════════════


class ChunkingState(TypedDict, total=False):
    run_id: int
    course_id: int
    # Per-book data accumulated across nodes
    books: list[dict]  # [{selected_book_id, title, md_text, chunks, chunk_embeddings}]


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
            db, run_id, progress_detail=f"Chunked into {total_chunks} paragraphs"
        )

    return {"books": books}


# ═══════════════════════════════════════════════════════════════
# Node 3: embed_chunks
# ═══════════════════════════════════════════════════════════════


def embed_chunks(state: ChunkingState) -> dict:
    """Embed all book chunks, then persist BookChunk rows to PostgreSQL."""
    run_id = state["run_id"]
    books = state["books"]

    with fresh_db() as db:
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.EMBEDDING,
            progress_detail="Embedding chunks… 0%",
        )

    embedder = EmbeddingService()
    total_chunks = sum(len(b["chunks"]) for b in books)
    embedded_so_far = 0

    for book in books:
        chunks = book["chunks"]
        if not chunks:
            book["chunk_embeddings"] = []
            continue

        batch_size = max(1, int(settings.embedding_batch_size))
        all_vecs: list[list[float]] = []

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vecs = embedder.embed_documents(batch)
            all_vecs.extend(vecs)
            embedded_so_far += len(batch)

            pct = int(embedded_so_far / total_chunks * 100) if total_chunks else 100
            with fresh_db() as db:
                update_run(
                    db,
                    run_id,
                    progress_detail=(
                        f"Embedding chunks… {pct}% ({embedded_so_far}/{total_chunks})"
                    ),
                )

        book["chunk_embeddings"] = all_vecs
        logger.info("Embedded %d chunks for '%s'", len(all_vecs), book["title"])

    # ── Persist to PostgreSQL ───────────────────────────────────
    with fresh_db() as db:
        update_run(db, run_id, progress_detail="Storing chunks in database…")
        total_stored = store_chunks(run_id, books, db)
        update_run(
            db,
            run_id,
            status=ExtractionRunStatus.COMPLETED,
            progress_detail=f"Done — {total_stored} chunks embedded and stored",
        )
        db.commit()

    logger.info("Stored %d chunks for run %d", total_chunks, run_id)
    return {"books": books}


# ═══════════════════════════════════════════════════════════════
# Build the LangGraph subgraph
# ═══════════════════════════════════════════════════════════════


def build_chunking_graph():
    """Build the ChunkingComparison workflow graph."""
    builder = StateGraph(ChunkingState)

    builder.add_node("extract_pdf", extract_pdf)
    builder.add_node("chunk_paragraphs", chunk_paragraphs)
    builder.add_node("embed_chunks", embed_chunks)

    builder.add_edge(START, "extract_pdf")
    builder.add_edge("extract_pdf", "chunk_paragraphs")
    builder.add_edge("chunk_paragraphs", "embed_chunks")
    builder.add_edge("embed_chunks", END)

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
