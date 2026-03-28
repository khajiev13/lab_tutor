"""Chapter-level scoring: compute concept-to-concept similarity and persist summaries.

Reads skill concepts directly from skills_json (no BookSection/BookConcept tables).
Embeds concept names on-the-fly and compares against CourseConceptCache embeddings.
"""

from __future__ import annotations

import contextlib
import json
import logging

import numpy as np
from sqlalchemy.orm import Session

from app.modules.embeddings.embedding_service import EmbeddingService

from ..chunking_analysis.state import COVERED_THRESHOLD, NOVEL_THRESHOLD
from ..chunking_analysis.utils import build_sim_distribution, l2_normalize
from ..models import (
    BookChapter,
    BookExtractionRun,
    ChapterAnalysisSummary,
    CourseConceptCache,
    CourseDocumentSummaryCache,
    CourseSelectedBook,
)

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────


def _load_course_concept_cache(run_id: int, db: Session) -> list[dict]:
    """Load cached course concept embeddings for a run."""
    rows = (
        db.query(CourseConceptCache).filter(CourseConceptCache.run_id == run_id).all()
    )
    results: list[dict] = []
    for r in rows:
        emb = r.name_embedding
        if emb is None:
            continue
        entry: dict = {
            "concept_name": r.concept_name,
            "doc_topic": r.doc_topic,
            "text_evidence": r.text_evidence,
            "name_embedding": [float(v) for v in emb],
        }
        if r.evidence_embedding is not None:
            entry["evidence_embedding"] = [float(v) for v in r.evidence_embedding]
        results.append(entry)
    return results


def _load_document_summary_cache(run_id: int, db: Session) -> list[dict]:
    """Load cached course document summary embeddings for a run."""
    rows = (
        db.query(CourseDocumentSummaryCache)
        .filter(CourseDocumentSummaryCache.run_id == run_id)
        .all()
    )
    results: list[dict] = []
    for r in rows:
        emb = r.summary_embedding
        if emb is None:
            continue
        results.append(
            {
                "document_neo4j_id": r.document_neo4j_id,
                "topic": r.topic,
                "summary_text": r.summary_text or "",
                "summary_embedding": [float(v) for v in emb],
            }
        )
    return results


def _load_book_concepts_structured(
    run_id: int, selected_book_id: int, db: Session
) -> tuple[list[dict], list[dict]]:
    """Load all chapters → skills → concepts for a book.

    Returns (chapters_data, flat_concepts) where:
    - chapters_data: chapter dicts with nested skills (each skill has its concepts)
    - flat_concepts: flattened list of all skill concepts (no embeddings yet)
    """
    chapters = (
        db.query(BookChapter)
        .filter(
            BookChapter.run_id == run_id,
            BookChapter.selected_book_id == selected_book_id,
        )
        .order_by(BookChapter.chapter_index)
        .all()
    )

    chapters_data: list[dict] = []
    flat_concepts: list[dict] = []

    for ch in chapters:
        skills: list[dict] = []
        if ch.skills_json:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                skills = json.loads(ch.skills_json)

        chapters_data.append(
            {
                "chapter_title": ch.chapter_title,
                "chapter_index": ch.chapter_index,
                "chapter_summary": ch.chapter_summary,
                "skill_count": len(skills),
                "concept_count": sum(len(sk.get("concepts", [])) for sk in skills),
                "skills": [
                    {
                        "name": sk["name"],
                        "description": sk.get("description", ""),
                        "concepts": sk.get("concepts", []),
                    }
                    for sk in skills
                ],
            }
        )

        for skill in skills:
            for concept in skill.get("concepts", []):
                flat_concepts.append(
                    {
                        "name": concept["name"],
                        "description": concept.get("description", ""),
                        "chapter_title": ch.chapter_title,
                        "chapter_index": ch.chapter_index,
                        "skill_name": skill["name"],
                    }
                )

    return chapters_data, flat_concepts


# ── Main scoring function ───────────────────────────────────────


def compute_chapter_analysis(
    run_id: int,
    selected_book_id: int,
    db: Session,
) -> ChapterAnalysisSummary:
    """Compute concept-to-concept similarity and persist a ChapterAnalysisSummary.

    1. Load course concept embeddings from CourseConceptCache
    2. Load book skills + inline concepts from BookChapter.skills_json
    3. Embed concept names on-the-fly
    4. Compute cosine similarity matrix (course × book-concept)
    5. Derive: course_coverage, book_unique_concepts, topic_scores, sim_distribution
    6. Enrich chapter skills with per-concept sim_max
    7. Persist and return the summary
    """
    book = db.get(CourseSelectedBook, selected_book_id)
    book_title = book.title if book else "Unknown"

    # Load course concepts
    course_concepts = _load_course_concept_cache(run_id, db)
    if not course_concepts:
        raise ValueError(
            f"No course concept cache for run {run_id}. "
            "Run chunking analysis first to populate the cache."
        )

    # Load book chapters → skills → concepts (no embeddings yet)
    chapters_data, flat_book_concepts = _load_book_concepts_structured(
        run_id, selected_book_id, db
    )
    if not flat_book_concepts:
        logger.warning(
            "No skill concepts for book %d in run %d", selected_book_id, run_id
        )
        return _save_empty_summary(run_id, selected_book_id, book_title, db)

    # Embed concept names on the fly (batch call)
    concept_names = [c["name"] for c in flat_book_concepts]
    embedder = EmbeddingService()
    concept_vectors = embedder.embed_documents(concept_names)
    for fc, vec in zip(flat_book_concepts, concept_vectors, strict=True):
        fc["name_embedding"] = vec

    # Build embedding matrices
    course_names = [c["concept_name"] for c in course_concepts]
    course_topics = [c.get("doc_topic") for c in course_concepts]
    course_matrix = l2_normalize(
        np.array([c["name_embedding"] for c in course_concepts], dtype=np.float32)
    )
    book_matrix = l2_normalize(
        np.array([c["name_embedding"] for c in flat_book_concepts], dtype=np.float32)
    )

    # ── Course → Book similarity ─────────────────────────────────
    sim_matrix = course_matrix @ book_matrix.T  # (n_course, n_book)
    max_sims = sim_matrix.max(axis=1)
    best_idx = sim_matrix.argmax(axis=1)

    course_evidences = [c.get("text_evidence") or "" for c in course_concepts]

    course_coverage: list[dict] = []
    topic_values: dict[str, list[float]] = {}
    for idx, concept_name in enumerate(course_names):
        sim_max = float(max_sims[idx])
        bi = int(best_idx[idx])
        matched = flat_book_concepts[bi] if 0 <= bi < len(flat_book_concepts) else {}
        best_match = matched.get("name", "")
        topic = course_topics[idx]

        course_coverage.append(
            {
                "concept_name": concept_name,
                "doc_topic": topic,
                "sim_max": round(sim_max, 4),
                "sim_evidence": round(sim_max, 4),
                "sim_weighted": round(sim_max, 4),
                "best_match": best_match,
                "course_text_evidence": course_evidences[idx][:1200],
                "book_chapter_title": matched.get("chapter_title", ""),
                "book_skill_name": matched.get("skill_name", ""),
            }
        )
        if topic:
            topic_values.setdefault(topic, []).append(sim_max)

    topic_scores = {
        topic: round(float(sum(vals) / len(vals)), 4)
        for topic, vals in topic_values.items()
        if vals
    }
    sim_distribution = build_sim_distribution(max_sims)

    novel_count = int(np.sum(max_sims < NOVEL_THRESHOLD))
    overlap_count = int(
        np.sum((max_sims >= NOVEL_THRESHOLD) & (max_sims < COVERED_THRESHOLD))
    )
    covered_count = int(np.sum(max_sims >= COVERED_THRESHOLD))
    s_final_name = float(max_sims.mean()) if max_sims.size else 0.0

    # ── Strategy ③: chapter_summary ←→ doc summary_embedding ───
    doc_summaries = _load_document_summary_cache(run_id, db)
    s_chapter_lecture = 0.0
    if doc_summaries and chapters_data:
        ch_texts = [
            ch.get("chapter_summary") or ch["chapter_title"] for ch in chapters_data
        ]
        ch_vectors = embedder.embed_documents(ch_texts)
        ch_matrix = l2_normalize(np.array(ch_vectors, dtype=np.float32))
        doc_matrix = l2_normalize(
            np.array(
                [d["summary_embedding"] for d in doc_summaries],
                dtype=np.float32,
            )
        )
        ch_doc_sim = ch_matrix @ doc_matrix.T
        ch_max_sims = ch_doc_sim.max(axis=1)
        s_chapter_lecture = float(ch_max_sims.mean())
    else:
        logger.debug(
            "Skipping chapter-lecture alignment: %d doc summaries, %d chapters",
            len(doc_summaries) if doc_summaries else 0,
            len(chapters_data),
        )

    # ── Book → Course direction (novelty) ───────────────────────
    rev_sim_matrix = book_matrix @ course_matrix.T  # (n_book, n_course)
    rev_max_sims = rev_sim_matrix.max(axis=1)
    rev_best_idx = rev_sim_matrix.argmax(axis=1)

    book_unique_concepts: list[dict] = []
    for idx, bc in enumerate(flat_book_concepts):
        ci = int(rev_best_idx[idx])
        best_course = course_names[ci] if 0 <= ci < len(course_names) else ""
        book_unique_concepts.append(
            {
                "name": bc["name"],
                "description": bc["description"],
                "skill_name": bc["skill_name"],
                "chapter_title": bc["chapter_title"],
                "sim_max": round(float(rev_max_sims[idx]), 4),
                "best_course_match": best_course,
            }
        )

    # ── Enrich chapter_details: add sim_max per skill concept ───
    book_concept_lookup: dict[tuple[str, str, str], dict] = {}
    for idx, bc in enumerate(flat_book_concepts):
        key = (bc["chapter_title"], bc["skill_name"], bc["name"])
        book_concept_lookup[key] = {
            "sim_max": round(float(rev_max_sims[idx]), 4),
            "best_course_match": (
                course_names[int(rev_best_idx[idx])]
                if 0 <= int(rev_best_idx[idx]) < len(course_names)
                else ""
            ),
        }

    for chapter in chapters_data:
        for skill in chapter["skills"]:
            for concept in skill["concepts"]:
                key = (chapter["chapter_title"], skill["name"], concept["name"])
                match = book_concept_lookup.get(key)
                if match:
                    concept["sim_max"] = match["sim_max"]
                    concept["best_course_match"] = match["best_course_match"]

    # ── Scalar aggregates ───────────────────────────────────────
    total_skills = sum(ch["skill_count"] for ch in chapters_data)
    total_concepts = sum(ch["concept_count"] for ch in chapters_data)

    # ── Persist ─────────────────────────────────────────────────
    (
        db.query(ChapterAnalysisSummary)
        .filter(
            ChapterAnalysisSummary.run_id == run_id,
            ChapterAnalysisSummary.selected_book_id == selected_book_id,
        )
        .delete(synchronize_session=False)
    )

    summary = ChapterAnalysisSummary(
        run_id=run_id,
        selected_book_id=selected_book_id,
        book_title=book_title,
        total_core_concepts=0,
        total_supplementary_concepts=total_concepts,  # repurposed: total inline concepts
        total_skills=total_skills,
        total_chapters=len(chapters_data),
        s_final_name=round(s_final_name, 4),
        s_final_evidence=round(s_final_name, 4),
        s_final_weighted=round(s_final_name, 4),
        s_chapter_lecture=round(s_chapter_lecture, 4),
        novel_count_default=novel_count,
        overlap_count_default=overlap_count,
        covered_count_default=covered_count,
        chapter_details_json=json.dumps(chapters_data),
        course_coverage_json=json.dumps(course_coverage),
        book_unique_concepts_json=json.dumps(book_unique_concepts),
        topic_scores_json=json.dumps(topic_scores),
        sim_distribution_json=json.dumps(sim_distribution),
    )
    db.add(summary)
    db.flush()

    logger.info(
        "Saved chapter analysis for book '%s' (run=%d): "
        "%d skills, %d concepts, s_final=%.4f",
        book_title,
        run_id,
        total_skills,
        total_concepts,
        s_final_name,
    )
    return summary


def _save_empty_summary(
    run_id: int,
    selected_book_id: int,
    book_title: str,
    db: Session,
) -> ChapterAnalysisSummary:
    """Create an empty (zeroed) summary when no concepts are available."""
    (
        db.query(ChapterAnalysisSummary)
        .filter(
            ChapterAnalysisSummary.run_id == run_id,
            ChapterAnalysisSummary.selected_book_id == selected_book_id,
        )
        .delete(synchronize_session=False)
    )

    summary = ChapterAnalysisSummary(
        run_id=run_id,
        selected_book_id=selected_book_id,
        book_title=book_title,
        chapter_details_json=json.dumps([]),
        course_coverage_json=json.dumps([]),
        book_unique_concepts_json=json.dumps([]),
        topic_scores_json=json.dumps({}),
        sim_distribution_json=json.dumps([]),
    )
    db.add(summary)
    db.flush()
    return summary


def get_chapter_summaries_for_run(
    run_id: int, db: Session
) -> list[ChapterAnalysisSummary]:
    """Return all chapter analysis summaries for the given run."""
    return (
        db.query(ChapterAnalysisSummary)
        .filter(ChapterAnalysisSummary.run_id == run_id)
        .order_by(
            ChapterAnalysisSummary.s_final_name.desc(),
            ChapterAnalysisSummary.id.asc(),
        )
        .all()
    )


def compute_all_books_chapter_analysis(
    run_id: int, db: Session
) -> list[ChapterAnalysisSummary]:
    """Compute chapter analysis for every selected book in a run."""
    run = db.get(BookExtractionRun, run_id)
    if not run:
        raise ValueError(f"Run {run_id} not found")

    # Find all selected books that have chapters in this run
    book_ids = (
        db.query(BookChapter.selected_book_id)
        .filter(BookChapter.run_id == run_id)
        .distinct()
        .all()
    )
    book_ids = [b[0] for b in book_ids]

    summaries: list[ChapterAnalysisSummary] = []
    for book_id in book_ids:
        try:
            summary = compute_chapter_analysis(run_id, book_id, db)
            summaries.append(summary)
        except Exception:
            logger.exception(
                "Failed to compute chapter analysis for book %d in run %d",
                book_id,
                run_id,
            )
    db.commit()
    return summaries
