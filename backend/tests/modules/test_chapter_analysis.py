"""Tests for the chapter-level analysis feature (scoring + routes).

Covers:
- ChapterAnalysisScoring — repository-level unit tests (with DB)
- ChapterAnalysisRoutes  — API-level tests via TestClient
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.chapter_extraction.scoring import (
    _save_empty_summary,
    compute_chapter_analysis,
    get_chapter_summaries_for_run,
)
from app.modules.curricularalignmentarchitect.models import (
    BookChapter,
    BookConcept,
    BookExtractionRun,
    BookSection,
    BookStatus,
    ChapterAnalysisSummary,
    ConceptRelevance,
    CourseConceptCache,
    CourseSelectedBook,
    ExtractionRunStatus,
)

# ────────────────────────────────────────────────────────────────
# Shared DB-setup helpers
# ────────────────────────────────────────────────────────────────

# A fixed 2048-d embedding for deterministic tests.  Two "similar" vectors
# and two "different" ones let us control sim_max outcomes.
_DIM = 2048


def _make_vec(index: int, near_index: int | None = None) -> np.ndarray:
    """Create a sparse 2048-d vector with energy concentrated at `index`.

    If `near_index` is given, create a vector that is close to _make_vec(index)
    but slightly offset (high cosine sim).
    """
    v = np.zeros(_DIM, dtype=np.float32)
    if near_index is not None:
        v[near_index] = 0.9
        v[(near_index + 1) % _DIM] = 0.1
    else:
        v[index] = 1.0
    return v


# VEC_A ≈ one-hot at dim 0; VEC_B close to VEC_A (high sim)
# VEC_C ≈ one-hot at dim 1000; VEC_D close to VEC_C (high sim)
_VEC_A = _make_vec(0)
_VEC_B = _make_vec(0, near_index=0)
_VEC_C = _make_vec(1000)
_VEC_D = _make_vec(1000, near_index=1000)


def _norm(v: np.ndarray) -> list[float]:
    """L2-normalise and convert to plain list for pgvector."""
    return (v / np.linalg.norm(v)).tolist()


def _ensure_course(db_session, course_id: int = 1) -> Course:
    existing = db_session.get(Course, course_id)
    if existing:
        return existing
    teacher = db_session.get(User, course_id)
    if not teacher:
        teacher = User(
            id=course_id,
            email=f"teacher-ch-analysis-{course_id}@test.local",
            hashed_password="!unused",
            first_name="Test",
            last_name="Teacher",
            role=UserRole.TEACHER,
        )
        db_session.add(teacher)
        db_session.flush()
    course = Course(
        id=course_id,
        title=f"Chapter Analysis Test Course {course_id}",
        teacher_id=teacher.id,
    )
    db_session.add(course)
    db_session.flush()
    return course


def _make_run(
    db_session,
    course_id: int = 1,
    status=ExtractionRunStatus.COMPLETED,
) -> BookExtractionRun:
    _ensure_course(db_session, course_id)
    run = BookExtractionRun(course_id=course_id, status=status)
    db_session.add(run)
    db_session.flush()
    return run


def _make_selected_book(
    db_session, course_id: int = 1, title: str = "Test Book"
) -> CourseSelectedBook:
    _ensure_course(db_session, course_id)
    book = CourseSelectedBook(
        course_id=course_id,
        title=title,
        authors="Author",
        status=BookStatus.DOWNLOADED,
        blob_path=f"courses/{course_id}/books/test.pdf",
    )
    db_session.add(book)
    db_session.flush()
    return book


def _seed_course_concepts(db_session, run_id: int):
    """Insert 2 course concepts with known embeddings into CourseConceptCache."""
    db_session.add(
        CourseConceptCache(
            run_id=run_id,
            concept_name="Distributed Databases",
            doc_topic="Storage Systems",
            text_evidence="Evidence about distributed databases",
            name_embedding=_norm(_VEC_A),
        )
    )
    db_session.add(
        CourseConceptCache(
            run_id=run_id,
            concept_name="Machine Learning",
            doc_topic="AI",
            text_evidence="Evidence about ML",
            name_embedding=_norm(_VEC_C),
        )
    )
    db_session.flush()


def _seed_book_chapters(db_session, run_id: int, selected_book_id: int):
    """Insert 1 chapter with 2 sections, each with 1 concept."""
    ch = BookChapter(
        run_id=run_id,
        selected_book_id=selected_book_id,
        chapter_index=0,
        chapter_title="Ch 1: Databases",
        chapter_summary="About databases",
        total_concept_count=2,
        skills_json=json.dumps(
            [
                {
                    "name": "SQL Querying",
                    "description": "Write SQL",
                    "concept_names": ["Distributed Databases", "Query Optimization"],
                },
            ]
        ),
    )
    db_session.add(ch)
    db_session.flush()

    sec1 = BookSection(
        chapter_id=ch.id,
        section_index=0,
        section_title="Section 1.1: Intro",
    )
    db_session.add(sec1)
    db_session.flush()

    # Close to course concept "Distributed Databases" (VEC_A → VEC_B, high sim)
    db_session.add(
        BookConcept(
            section_id=sec1.id,
            run_id=run_id,
            name="Distributed DB Systems",
            description="Overview of distributed DB systems",
            relevance=ConceptRelevance.CORE,
            text_evidence="Some evidence",
            name_embedding=_norm(_VEC_B),
        )
    )
    db_session.flush()

    sec2 = BookSection(
        chapter_id=ch.id,
        section_index=1,
        section_title="Section 1.2: Advanced",
    )
    db_session.add(sec2)
    db_session.flush()

    # Close to course concept "Machine Learning" (VEC_C → VEC_D, high sim)
    db_session.add(
        BookConcept(
            section_id=sec2.id,
            run_id=run_id,
            name="Neural Networks",
            description="Deep learning basics",
            relevance=ConceptRelevance.SUPPLEMENTARY,
            text_evidence="Some neural evidence",
            name_embedding=_norm(_VEC_D),
        )
    )
    db_session.flush()


# ────────────────────────────────────────────────────────────────
# Scoring unit tests (DB-backed)
# ────────────────────────────────────────────────────────────────


class TestChapterAnalysisScoring:
    def test_compute_returns_summary_with_correct_counts(self, db_session):
        run = _make_run(db_session, course_id=500)
        book = _make_selected_book(db_session, course_id=500, title="Test DB Book")
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)

        assert isinstance(summary, ChapterAnalysisSummary)
        assert summary.book_title == "Test DB Book"
        assert summary.total_chapters == 1
        assert summary.total_core_concepts == 1
        assert summary.total_supplementary_concepts == 1
        assert summary.total_skills == 1

    def test_compute_coverage_has_correct_length(self, db_session):
        run = _make_run(db_session, course_id=501)
        book = _make_selected_book(db_session, course_id=501)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)
        coverage = json.loads(summary.course_coverage_json)

        # We seeded 2 course concepts
        assert len(coverage) == 2
        for item in coverage:
            assert "concept_name" in item
            assert "sim_max" in item
            assert 0 <= item["sim_max"] <= 1

    def test_compute_similarity_is_high_for_close_vectors(self, db_session):
        """VEC_A → VEC_B and VEC_C → VEC_D should yield high sim_max."""
        run = _make_run(db_session, course_id=502)
        book = _make_selected_book(db_session, course_id=502)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)
        coverage = json.loads(summary.course_coverage_json)

        # Both course concepts should have high sim_max (> 0.9)
        for item in coverage:
            assert item["sim_max"] > 0.9, (
                f"Expected high similarity for {item['concept_name']}, "
                f"got {item['sim_max']}"
            )

    def test_compute_enriches_chapter_details_with_sim_max(self, db_session):
        run = _make_run(db_session, course_id=503)
        book = _make_selected_book(db_session, course_id=503)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)
        chapters = json.loads(summary.chapter_details_json)

        assert len(chapters) == 1
        ch = chapters[0]
        # Both concepts should have sim_max enriched
        for sec in ch["sections"]:
            for concept in sec["concepts"]:
                assert "sim_max" in concept

    def test_compute_populates_topic_scores(self, db_session):
        run = _make_run(db_session, course_id=504)
        book = _make_selected_book(db_session, course_id=504)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)
        topic_scores = json.loads(summary.topic_scores_json)

        # We have 2 topics: "Storage Systems" and "AI"
        assert "Storage Systems" in topic_scores
        assert "AI" in topic_scores
        for score in topic_scores.values():
            assert 0 <= score <= 1

    def test_compute_populates_book_unique_concepts(self, db_session):
        run = _make_run(db_session, course_id=505)
        book = _make_selected_book(db_session, course_id=505)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        summary = compute_chapter_analysis(run.id, book.id, db_session)
        book_unique = json.loads(summary.book_unique_concepts_json)

        # We seeded 2 book concepts (1 core + 1 supplementary)
        assert len(book_unique) == 2
        for item in book_unique:
            assert "name" in item
            assert "sim_max" in item
            assert "best_course_match" in item

    def test_compute_raises_when_no_course_cache(self, db_session):
        run = _make_run(db_session, course_id=506)
        book = _make_selected_book(db_session, course_id=506)
        # No course concept cache seeded → should raise ValueError
        _seed_book_chapters(db_session, run.id, book.id)

        with pytest.raises(ValueError, match="No course concept cache"):
            compute_chapter_analysis(run.id, book.id, db_session)

    def test_compute_returns_empty_when_no_book_concepts(self, db_session):
        run = _make_run(db_session, course_id=507)
        book = _make_selected_book(db_session, course_id=507)
        _seed_course_concepts(db_session, run.id)
        # No book chapters/concepts seeded → should return empty summary

        summary = compute_chapter_analysis(run.id, book.id, db_session)

        assert summary.total_chapters == 0
        assert summary.total_core_concepts == 0
        assert json.loads(summary.chapter_details_json) == []

    def test_save_empty_summary_persists(self, db_session):
        run = _make_run(db_session, course_id=508)
        book = _make_selected_book(db_session, course_id=508)

        summary = _save_empty_summary(run.id, book.id, "Empty Book", db_session)

        assert summary.id is not None
        assert summary.book_title == "Empty Book"
        assert json.loads(summary.chapter_details_json) == []

    def test_get_chapter_summaries_for_run_empty(self, db_session):
        run = _make_run(db_session, course_id=509)
        results = get_chapter_summaries_for_run(run.id, db_session)
        assert results == []

    def test_get_chapter_summaries_for_run_returns_results(self, db_session):
        run = _make_run(db_session, course_id=510)
        book = _make_selected_book(db_session, course_id=510)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        compute_chapter_analysis(run.id, book.id, db_session)
        results = get_chapter_summaries_for_run(run.id, db_session)

        assert len(results) == 1
        assert results[0].book_title == "Test Book"

    def test_re_scoring_replaces_old_summary(self, db_session):
        run = _make_run(db_session, course_id=511)
        book = _make_selected_book(db_session, course_id=511)
        _seed_course_concepts(db_session, run.id)
        _seed_book_chapters(db_session, run.id, book.id)

        s1 = compute_chapter_analysis(run.id, book.id, db_session)
        s2 = compute_chapter_analysis(run.id, book.id, db_session)

        results = get_chapter_summaries_for_run(run.id, db_session)
        assert len(results) == 1
        assert results[0].id == s2.id
        assert results[0].id != s1.id


# ────────────────────────────────────────────────────────────────
# Route tests
# ────────────────────────────────────────────────────────────────

BASE = "/book-selection/courses"


class TestChapterAnalysisRoutes:
    """API-level tests for chapter-scoring and chapter-summaries endpoints."""

    # ── Auth guards ──────────────────────────────────────────────

    def test_chapter_scoring_requires_auth(self, client):
        resp = client.post(f"{BASE}/1/analysis/1/chapter-scoring")
        assert resp.status_code == 401

    def test_chapter_scoring_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            f"{BASE}/1/analysis/1/chapter-scoring", headers=student_auth_headers
        )
        assert resp.status_code == 403

    def test_chapter_summaries_requires_auth(self, client):
        resp = client.get(f"{BASE}/1/analysis/1/chapter-summaries")
        assert resp.status_code == 401

    def test_chapter_summaries_requires_teacher(self, client, student_auth_headers):
        resp = client.get(
            f"{BASE}/1/analysis/1/chapter-summaries",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403

    # ── 404 when run not found ───────────────────────────────────

    def test_chapter_scoring_run_not_found(self, client, teacher_auth_headers):
        resp = client.post(
            f"{BASE}/99999/analysis/99999/chapter-scoring",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_chapter_summaries_run_not_found(self, client, teacher_auth_headers):
        resp = client.get(
            f"{BASE}/99999/analysis/99999/chapter-summaries",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    # ── Summaries endpoint returns data ──────────────────────────

    def test_chapter_summaries_returns_empty_list(
        self,
        client,
        db_session,
        teacher_auth_headers,
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(db_session, course_id=course_id)
        db_session.commit()

        resp = client.get(
            f"{BASE}/{course_id}/analysis/{run.id}/chapter-summaries",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    # ── Helper ───────────────────────────────────────────────────

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Chapter Analysis Route Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]
