"""Tests for curriculum graph construction (repository + service + API route).

Covers:
- CurriculumGraphRepository — Cypher execution against a mock Neo4j session
- CurriculumGraphService    — orchestration, data snapshot, SSE event stream
- Build-curriculum route    — auth guards (401/403), validation (404, wrong status)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.curriculum_graph.repository import (
    CurriculumGraphRepository,
)
from app.modules.curricularalignmentarchitect.curriculum_graph.service import (
    CurriculumGraphService,
    _parse_skills_json,
    _snapshot_chapters,
)
from app.modules.curricularalignmentarchitect.models import (
    BookChapter,
    BookConcept,
    BookExtractionRun,
    BookSection,
    BookStatus,
    ConceptRelevance,
    CourseSelectedBook,
    ExtractionRunStatus,
)

# ── Shared helpers ──────────────────────────────────────────────


def _ensure_course(db_session, course_id: int = 1) -> Course:
    existing = db_session.get(Course, course_id)
    if existing:
        return existing
    teacher = db_session.get(User, course_id)
    if not teacher:
        teacher = User(
            id=course_id,
            email=f"teacher-curriculum-{course_id}@test.local",
            hashed_password="!unused",
            first_name="Test",
            last_name="Teacher",
            role=UserRole.TEACHER,
        )
        db_session.add(teacher)
        db_session.flush()
    course = Course(
        id=course_id,
        title=f"Curriculum Test Course {course_id}",
        teacher_id=teacher.id,
    )
    db_session.add(course)
    db_session.flush()
    return course


def _make_run(
    db_session,
    course_id: int = 1,
    status: ExtractionRunStatus = ExtractionRunStatus.AGENTIC_COMPLETED,
) -> BookExtractionRun:
    _ensure_course(db_session, course_id)
    run = BookExtractionRun(course_id=course_id, status=status)
    db_session.add(run)
    db_session.flush()
    return run


def _make_selected_book(
    db_session,
    course_id: int = 1,
    title: str = "Test Book",
) -> CourseSelectedBook:
    _ensure_course(db_session, course_id)
    book = CourseSelectedBook(
        course_id=course_id,
        title=title,
        authors="Author One",
        status=BookStatus.DOWNLOADED,
        blob_path=f"courses/{course_id}/books/test.pdf",
    )
    db_session.add(book)
    db_session.flush()
    return book


def _make_chapter_with_sections(
    db_session,
    run_id: int,
    selected_book_id: int,
    chapter_index: int = 0,
    chapter_title: str = "Chapter 1",
    chapter_summary: str = "A summary.",
    skills_json: str | None = None,
) -> BookChapter:
    chapter = BookChapter(
        run_id=run_id,
        selected_book_id=selected_book_id,
        chapter_title=chapter_title,
        chapter_index=chapter_index,
        chapter_summary=chapter_summary,
        skills_json=skills_json,
    )
    db_session.add(chapter)
    db_session.flush()

    section = BookSection(
        chapter_id=chapter.id,
        section_title="Section 1.1",
        section_index=0,
    )
    db_session.add(section)
    db_session.flush()

    concept = BookConcept(
        section_id=section.id,
        run_id=run_id,
        name="MapReduce",
        description="A parallel computing framework",
        text_evidence="MapReduce is used for batch processing",
        relevance=ConceptRelevance.CORE,
    )
    db_session.add(concept)
    db_session.flush()

    return chapter


BASE = "/book-selection/courses"


# ────────────────────────────────────────────────────────────────────────────
# 1. Repository unit tests (mock Neo4j session)
# ────────────────────────────────────────────────────────────────────────────


class _Consumed:
    def consume(self):
        return None


class _FakeTx:
    """Mock Neo4j transaction that records executed queries."""

    def __init__(self):
        self.queries: list[tuple[str, dict]] = []

    def run(self, query: str, **kwargs):
        self.queries.append((query.strip(), kwargs))
        return _Consumed()


class TestCurriculumGraphRepository:
    def test_create_curriculum_node(self):
        tx = _FakeTx()
        CurriculumGraphRepository.create_curriculum_node(
            tx, curriculum_id="cur_1", book_title="Test", authors="Auth", course_id=1
        )
        assert len(tx.queries) == 1
        q, params = tx.queries[0]
        assert "MERGE (cur:CURRICULUM" in q
        assert params["id"] == "cur_1"
        assert params["book_title"] == "Test"

    def test_link_curriculum_to_class(self):
        tx = _FakeTx()
        CurriculumGraphRepository.link_curriculum_to_class(
            tx, course_id=1, curriculum_id="cur_1"
        )
        assert len(tx.queries) == 1
        q, _ = tx.queries[0]
        assert "HAS_CURRICULUM" in q

    def test_create_chapter_nodes(self):
        tx = _FakeTx()
        chapters = [
            {
                "id": "cur_1_ch_0",
                "title": "Ch 1",
                "chapter_index": 0,
                "summary": "A summary",
                "summary_embedding": [0.1] * 10,
            }
        ]
        CurriculumGraphRepository.create_chapter_nodes(
            tx, curriculum_id="cur_1", chapters=chapters
        )
        assert len(tx.queries) == 1
        q, params = tx.queries[0]
        assert "BOOK_CHAPTER" in q
        assert params["curriculum_id"] == "cur_1"
        assert len(params["chapters"]) == 1

    def test_link_chapters_linked_list(self):
        tx = _FakeTx()
        CurriculumGraphRepository.link_chapters_linked_list(tx, curriculum_id="cur_1")
        assert len(tx.queries) == 1
        q, _ = tx.queries[0]
        assert "NEXT_CHAPTER" in q

    def test_create_section_nodes(self):
        tx = _FakeTx()
        sections = [{"id": "cur_1_ch_0_sec_0", "title": "Sec 1", "section_index": 0}]
        CurriculumGraphRepository.create_section_nodes(
            tx, chapter_id="cur_1_ch_0", sections=sections
        )
        assert len(tx.queries) == 1
        q, _ = tx.queries[0]
        assert "BOOK_SECTION" in q

    def test_merge_concept_node(self):
        tx = _FakeTx()
        CurriculumGraphRepository.merge_concept_node(
            tx, name="MapReduce", embedding=[0.1] * 5, description="desc"
        )
        assert len(tx.queries) == 1
        q, params = tx.queries[0]
        assert "MERGE (c:CONCEPT" in q
        assert "toLower($name)" in q
        assert params["name"] == "MapReduce"

    def test_create_covers_concept_rel(self):
        tx = _FakeTx()
        CurriculumGraphRepository.create_covers_concept_rel(
            tx,
            section_id="cur_1_ch_0_sec_0",
            concept_name="MapReduce",
            relevance="core",
            text_evidence="some evidence",
        )
        assert len(tx.queries) == 1
        q, _ = tx.queries[0]
        assert "COVERS_CONCEPT" in q

    def test_create_skill_node(self):
        tx = _FakeTx()
        CurriculumGraphRepository.create_skill_node(
            tx, skill_id="cur_1_ch_0_sk_0", name="Data Processing", description="desc"
        )
        q, params = tx.queries[0]
        assert "BOOK_SKILL" in q
        assert params["skill_id"] == "cur_1_ch_0_sk_0"

    def test_link_skill_to_chapter(self):
        tx = _FakeTx()
        CurriculumGraphRepository.link_skill_to_chapter(
            tx, chapter_id="cur_1_ch_0", skill_id="cur_1_ch_0_sk_0"
        )
        q, _ = tx.queries[0]
        assert "HAS_SKILL" in q

    def test_link_skill_requires_concept(self):
        tx = _FakeTx()
        CurriculumGraphRepository.link_skill_requires_concept(
            tx, skill_id="cur_1_ch_0_sk_0", concept_name="MapReduce"
        )
        q, _ = tx.queries[0]
        assert "REQUIRES_CONCEPT" in q


# ────────────────────────────────────────────────────────────────────────────
# 2. Service unit tests
# ────────────────────────────────────────────────────────────────────────────


class TestParseSkillsJson:
    def test_valid_json(self):
        raw = json.dumps(
            [{"name": "Analysis", "description": "d", "concept_names": ["x"]}]
        )
        result = _parse_skills_json(raw)
        assert len(result) == 1
        assert result[0]["name"] == "Analysis"

    def test_empty_string(self):
        assert _parse_skills_json("") == []

    def test_none(self):
        assert _parse_skills_json(None) == []

    def test_invalid_json(self):
        assert _parse_skills_json("{bad") == []

    def test_non_list(self):
        assert _parse_skills_json('"just a string"') == []


class TestSnapshotChapters:
    def test_snapshot_converts_orm_objects(self, db_session):
        run = _make_run(db_session)
        book = _make_selected_book(db_session)
        skills = [
            {
                "name": "Batch Processing",
                "description": "desc",
                "concept_names": ["MapReduce"],
            }
        ]
        ch = _make_chapter_with_sections(
            db_session,
            run_id=run.id,
            selected_book_id=book.id,
            skills_json=json.dumps(skills),
        )
        db_session.commit()
        db_session.refresh(ch)

        snapshot = _snapshot_chapters([ch])

        assert len(snapshot) == 1
        assert snapshot[0]["title"] == "Chapter 1"
        assert snapshot[0]["chapter_index"] == 0
        assert snapshot[0]["summary"] == "A summary."
        assert len(snapshot[0]["sections"]) == 1
        assert snapshot[0]["sections"][0]["title"] == "Section 1.1"
        assert len(snapshot[0]["sections"][0]["concepts"]) == 1
        assert snapshot[0]["sections"][0]["concepts"][0]["name"] == "MapReduce"
        assert snapshot[0]["sections"][0]["concepts"][0]["relevance"] == "core"
        assert len(snapshot[0]["skills"]) == 1
        assert snapshot[0]["skills"][0]["name"] == "Batch Processing"
        assert snapshot[0]["summary_embedding"] is None  # filled later


class TestCurriculumGraphServiceValidation:
    """Test that the service yields error events for invalid inputs."""

    def _collect_events(self, async_gen) -> list[dict]:
        """Run an async generator to completion and collect all yielded dicts."""
        loop = asyncio.new_event_loop()
        events = []
        try:

            async def _drain():
                async for evt in async_gen:
                    events.append(evt)

            loop.run_until_complete(_drain())
        finally:
            loop.close()
        return events

    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service._fresh_db"
    )
    def test_run_not_found(self, mock_fresh_db, db_session):
        """Yields error when run_id doesn't exist."""
        mock_fresh_db.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_fresh_db.return_value.__exit__ = MagicMock(return_value=False)

        service = CurriculumGraphService()
        events = self._collect_events(
            service.build_curriculum(course_id=999, run_id=999, selected_book_id=999)
        )

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "not found" in events[0]["message"].lower()

    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service._fresh_db"
    )
    def test_wrong_status(self, mock_fresh_db, db_session):
        """Yields error when run status is PENDING (not allowed)."""
        run = _make_run(db_session, status=ExtractionRunStatus.PENDING)
        book = _make_selected_book(db_session)
        db_session.commit()

        mock_fresh_db.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_fresh_db.return_value.__exit__ = MagicMock(return_value=False)

        service = CurriculumGraphService()
        events = self._collect_events(
            service.build_curriculum(
                course_id=run.course_id,
                run_id=run.id,
                selected_book_id=book.id,
            )
        )

        assert len(events) == 1
        assert events[0]["event"] == "error"
        assert "status" in events[0]["message"].lower()

    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service._fresh_db"
    )
    def test_no_chapters_yields_error(self, mock_fresh_db, db_session):
        """Yields error when there are no chapters for the selected book."""
        run = _make_run(db_session, status=ExtractionRunStatus.AGENTIC_COMPLETED)
        book = _make_selected_book(db_session)
        db_session.commit()

        mock_fresh_db.return_value.__enter__ = MagicMock(return_value=db_session)
        mock_fresh_db.return_value.__exit__ = MagicMock(return_value=False)

        service = CurriculumGraphService()
        events = self._collect_events(
            service.build_curriculum(
                course_id=run.course_id,
                run_id=run.id,
                selected_book_id=book.id,
            )
        )

        assert any(e["event"] == "error" for e in events)
        assert "no chapters" in events[-1]["message"].lower()

    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service.create_neo4j_driver"
    )
    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service.EmbeddingService"
    )
    @patch(
        "app.modules.curricularalignmentarchitect.curriculum_graph.service._fresh_db"
    )
    def test_happy_path_events(
        self, mock_fresh_db, mock_embedding_cls, mock_neo4j_driver, db_session
    ):
        """On valid input, the service yields progress + complete events."""
        run = _make_run(db_session, status=ExtractionRunStatus.AGENTIC_COMPLETED)
        book = _make_selected_book(db_session)
        _make_chapter_with_sections(db_session, run_id=run.id, selected_book_id=book.id)
        db_session.commit()

        # Mock _fresh_db to return our test session
        from contextlib import contextmanager

        @contextmanager
        def _fake_fresh_db():
            yield db_session

        mock_fresh_db.side_effect = _fake_fresh_db

        # Mock EmbeddingService
        mock_emb_instance = MagicMock()
        mock_emb_instance.embed_documents.return_value = [[0.1] * 2048]
        mock_embedding_cls.return_value = mock_emb_instance

        # Mock Neo4j driver with a session that records but doesn't execute
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute_write = MagicMock(return_value=None)
        mock_session.execute_read = MagicMock(return_value=[])
        mock_session.run = MagicMock(
            return_value=MagicMock(single=MagicMock(return_value=None))
        )

        mock_driver_instance = MagicMock()
        mock_driver_instance.session.return_value = mock_session
        mock_neo4j_driver.return_value = mock_driver_instance

        service = CurriculumGraphService()
        events = self._collect_events(
            service.build_curriculum(
                course_id=run.course_id,
                run_id=run.id,
                selected_book_id=book.id,
            )
        )

        event_types = [e["event"] for e in events]
        # Should have progress events and end with complete
        assert "progress" in event_types
        assert event_types[-1] == "complete"

        # Should include key progress steps
        steps = [e.get("step") for e in events if e["event"] == "progress"]
        assert "loaded_data" in steps
        assert "embedding_chapter_summaries" in steps
        assert "embedding_done" in steps
        assert "creating_curriculum_node" in steps
        assert "creating_chapters" in steps
        assert "processing_chapter" in steps
        assert "merging_similar_concepts" in steps

        # Complete event should have curriculum_id
        complete_evt = events[-1]
        assert complete_evt["curriculum_id"] == f"cur_{book.id}"
        assert complete_evt["total_chapters"] == 1

        # Embedding service should have been called with the chapter summary
        mock_emb_instance.embed_documents.assert_called_once()

        # Run status should be CURRICULUM_BUILT
        db_session.refresh(run)
        assert run.status == ExtractionRunStatus.CURRICULUM_BUILT


# ────────────────────────────────────────────────────────────────────────────
# 3. API route tests
# ────────────────────────────────────────────────────────────────────────────


class TestBuildCurriculumRouteAuth:
    """Auth guard tests for the build-curriculum endpoint."""

    def test_requires_auth(self, client):
        resp = client.post(f"{BASE}/1/analysis/1/build-curriculum/1")
        assert resp.status_code == 401

    def test_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            f"{BASE}/1/analysis/1/build-curriculum/1",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


class TestBuildCurriculumRouteValidation:
    """Validation tests — the endpoint streams SSE events, so we check the
    first event for error conditions."""

    def _read_first_sse_event(self, response) -> dict | None:
        """Parse the first SSE data frame from a streaming response."""
        for line in response.iter_lines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return None

    def test_run_not_found_returns_error_event(
        self, client, db_session, teacher_auth_headers
    ):
        resp = client.post(
            f"{BASE}/1/analysis/99999/build-curriculum/99999",
            headers=teacher_auth_headers,
        )
        # SSE endpoint always returns 200 — errors come as events
        assert resp.status_code == 200
        event = self._read_first_sse_event(resp)
        assert event is not None
        assert event["event"] == "error"

    def test_wrong_run_status_returns_error_event(
        self, client, db_session, teacher_auth_headers
    ):
        run = _make_run(db_session, status=ExtractionRunStatus.PENDING)
        book = _make_selected_book(db_session)
        db_session.commit()

        resp = client.post(
            f"{BASE}/{run.course_id}/analysis/{run.id}/build-curriculum/{book.id}",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        event = self._read_first_sse_event(resp)
        assert event is not None
        assert event["event"] == "error"
        assert "status" in event["message"].lower()
