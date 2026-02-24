"""Tests for the chunking-analysis feature (repository + routes).

Covers:
- ChunkingAnalysisRepository — pure DB-layer unit tests (no HTTP)
- AnalysisRoutes            — API-level tests via TestClient
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.chunking_analysis.repository import (
    create_run,
    get_active_run,
    get_latest_run,
    get_summaries_for_run,
    pick_book,
    recover_orphaned_runs,
    update_run,
)
from app.modules.curricularalignmentarchitect.models import (
    BookExtractionRun,
    BookStatus,
    CourseSelectedBook,
    ExtractionRunStatus,
)

# ────────────────────────────────────────────────────────────────────────────
# Shared DB-setup helpers
# ────────────────────────────────────────────────────────────────────────────


def _ensure_course(db_session, course_id: int = 1) -> Course:
    """Create a User + Course row to satisfy FK constraints."""
    existing = db_session.get(Course, course_id)
    if existing:
        return existing
    teacher = db_session.get(User, course_id)
    if not teacher:
        teacher = User(
            id=course_id,
            email=f"teacher-analysis-{course_id}@test.local",
            hashed_password="!unused",
            first_name="Test",
            last_name="Teacher",
            role=UserRole.TEACHER,
        )
        db_session.add(teacher)
        db_session.flush()
    course = Course(
        id=course_id,
        title=f"Analysis Test Course {course_id}",
        teacher_id=teacher.id,
    )
    db_session.add(course)
    db_session.flush()
    return course


def _make_run(
    db_session,
    course_id: int = 1,
    status: ExtractionRunStatus = ExtractionRunStatus.PENDING,
) -> BookExtractionRun:
    """Insert a BookExtractionRun and return it."""
    _ensure_course(db_session, course_id)
    return create_run(db_session, course_id=course_id, status=status)


def _make_selected_book(db_session, course_id: int = 1) -> CourseSelectedBook:
    """Create a CourseSelectedBook row (used by pick_book route tests)."""
    _ensure_course(db_session, course_id)
    book = CourseSelectedBook(
        course_id=course_id,
        title="Analysis Test Book",
        authors="Test Author",
        status=BookStatus.DOWNLOADED,
        blob_path=f"courses/{course_id}/books/test.pdf",
    )
    db_session.add(book)
    db_session.flush()
    return book


# ────────────────────────────────────────────────────────────────────────────
# Repository unit tests
# ────────────────────────────────────────────────────────────────────────────


class TestChunkingAnalysisRepository:
    def test_create_run_defaults(self, db_session):
        run = _make_run(db_session, course_id=1)
        assert run.id is not None
        assert run.status == ExtractionRunStatus.PENDING
        assert run.course_id == 1
        assert run.error_message is None

    def test_get_latest_run_none(self, db_session):
        result = get_latest_run(99999, db_session)
        assert result is None

    def test_get_latest_run_returns_most_recent(self, db_session):
        _make_run(db_session, course_id=10, status=ExtractionRunStatus.COMPLETED)
        run2 = _make_run(db_session, course_id=10, status=ExtractionRunStatus.PENDING)
        latest = get_latest_run(10, db_session)
        assert latest is not None
        assert latest.id == run2.id

    def test_get_active_run_returns_pending(self, db_session):
        run = _make_run(db_session, course_id=20, status=ExtractionRunStatus.PENDING)
        active = get_active_run(20, db_session)
        assert active is not None
        assert active.id == run.id

    def test_get_active_run_returns_embedding(self, db_session):
        run = _make_run(db_session, course_id=21, status=ExtractionRunStatus.EMBEDDING)
        active = get_active_run(21, db_session)
        assert active is not None
        assert active.id == run.id

    def test_get_active_run_none_when_completed(self, db_session):
        _make_run(db_session, course_id=22, status=ExtractionRunStatus.COMPLETED)
        active = get_active_run(22, db_session)
        assert active is None

    def test_get_active_run_none_when_failed(self, db_session):
        _make_run(db_session, course_id=23, status=ExtractionRunStatus.FAILED)
        active = get_active_run(23, db_session)
        assert active is None

    def test_pick_book_success(self, db_session):
        run = _make_run(db_session, course_id=30, status=ExtractionRunStatus.COMPLETED)
        sb = _make_selected_book(db_session, course_id=30)
        updated = pick_book(run.id, sb.id, db_session)
        assert updated.status == ExtractionRunStatus.BOOK_PICKED

    def test_pick_book_already_picked_is_idempotent(self, db_session):
        run = _make_run(
            db_session, course_id=31, status=ExtractionRunStatus.BOOK_PICKED
        )
        sb = _make_selected_book(db_session, course_id=31)
        updated = pick_book(run.id, sb.id, db_session)
        assert updated.status == ExtractionRunStatus.BOOK_PICKED

    def test_pick_book_wrong_status_raises(self, db_session):
        run = _make_run(db_session, course_id=32, status=ExtractionRunStatus.PENDING)
        sb = _make_selected_book(db_session, course_id=32)
        with pytest.raises(ValueError, match="COMPLETED"):
            pick_book(run.id, sb.id, db_session)

    def test_pick_book_not_found_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            pick_book(99999, 1, db_session)

    def test_recover_orphaned_runs(self, db_session):
        run1 = _make_run(db_session, course_id=40, status=ExtractionRunStatus.PENDING)
        run2 = _make_run(db_session, course_id=40, status=ExtractionRunStatus.EMBEDDING)
        _make_run(db_session, course_id=40, status=ExtractionRunStatus.COMPLETED)

        recovered = recover_orphaned_runs(db_session)
        assert recovered == 2

        db_session.refresh(run1)
        db_session.refresh(run2)
        assert run1.status == ExtractionRunStatus.FAILED
        assert run2.status == ExtractionRunStatus.FAILED

    def test_update_run_fields(self, db_session):
        run = _make_run(db_session, course_id=50)
        update_run(db_session, run.id, error_message="something went wrong")
        db_session.refresh(run)
        assert run.error_message == "something went wrong"

    def test_update_run_nonexistent_is_noop(self, db_session):
        # Should not raise
        update_run(db_session, 99999, error_message="noop")

    def test_get_summaries_for_run_empty(self, db_session):
        run = _make_run(db_session, course_id=60, status=ExtractionRunStatus.COMPLETED)
        summaries = get_summaries_for_run(run.id, db_session)
        assert summaries == []


# ────────────────────────────────────────────────────────────────────────────
# Route-level tests
# ────────────────────────────────────────────────────────────────────────────


class TestAnalysisRoutes:
    """API-level tests for /book-selection/courses/{course_id}/analysis/* endpoints."""

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Analysis Route Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]

    # ── Auth guards ──────────────────────────────────────────────────────────

    def test_trigger_analysis_requires_auth(self, client):
        resp = client.post("/book-selection/courses/1/analysis")
        assert resp.status_code == 401

    def test_trigger_analysis_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            "/book-selection/courses/1/analysis", headers=student_auth_headers
        )
        assert resp.status_code == 403

    def test_get_latest_analysis_requires_auth(self, client):
        resp = client.get("/book-selection/courses/1/analysis/latest")
        assert resp.status_code == 401

    def test_get_latest_analysis_requires_teacher(self, client, student_auth_headers):
        resp = client.get(
            "/book-selection/courses/1/analysis/latest", headers=student_auth_headers
        )
        assert resp.status_code == 403

    def test_get_summaries_requires_auth(self, client):
        resp = client.get("/book-selection/courses/1/analysis/1/summaries")
        assert resp.status_code == 401

    def test_get_summaries_requires_teacher(self, client, student_auth_headers):
        resp = client.get(
            "/book-selection/courses/1/analysis/1/summaries",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403

    def test_pick_book_requires_auth(self, client):
        resp = client.post("/book-selection/courses/1/analysis/1/pick/1")
        assert resp.status_code == 401

    def test_pick_book_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            "/book-selection/courses/1/analysis/1/pick/1",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403

    # ── get_latest_analysis ──────────────────────────────────────────────────

    def test_get_latest_analysis_none(self, client, teacher_auth_headers):
        resp = client.get(
            "/book-selection/courses/99999/analysis/latest",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() is None

    def test_get_latest_analysis_returns_run(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        # Seed a run via repo directly (avoids triggering the LangGraph workflow)
        run = create_run(
            db_session, course_id=course_id, status=ExtractionRunStatus.COMPLETED
        )
        db_session.commit()

        resp = client.get(
            f"/book-selection/courses/{course_id}/analysis/latest",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data is not None
        assert data["id"] == run.id
        assert data["status"] == "completed"

    # ── get_analysis_summaries ───────────────────────────────────────────────

    def test_get_summaries_not_found(self, client, teacher_auth_headers):
        resp = client.get(
            "/book-selection/courses/1/analysis/99999/summaries",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_get_summaries_wrong_course_is_404(
        self, client, db_session, teacher_auth_headers
    ):
        """A run that exists but belongs to a different course returns 404."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = create_run(
            db_session, course_id=course_id, status=ExtractionRunStatus.COMPLETED
        )
        db_session.commit()

        wrong_course_id = course_id + 9999
        resp = client.get(
            f"/book-selection/courses/{wrong_course_id}/analysis/{run.id}/summaries",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_get_summaries_empty_for_completed_run(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = create_run(
            db_session, course_id=course_id, status=ExtractionRunStatus.COMPLETED
        )
        db_session.commit()

        resp = client.get(
            f"/book-selection/courses/{course_id}/analysis/{run.id}/summaries",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    # ── pick_analysis_book ───────────────────────────────────────────────────

    def test_pick_book_run_not_found_returns_400(self, client, teacher_auth_headers):
        resp = client.post(
            "/book-selection/courses/1/analysis/99999/pick/1",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400

    def test_pick_book_pending_run_returns_400(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = create_run(
            db_session, course_id=course_id, status=ExtractionRunStatus.PENDING
        )
        db_session.commit()

        resp = client.post(
            f"/book-selection/courses/{course_id}/analysis/{run.id}/pick/1",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400
        assert "COMPLETED" in resp.json()["detail"]

    def test_pick_book_completed_run_succeeds(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = create_run(
            db_session, course_id=course_id, status=ExtractionRunStatus.COMPLETED
        )
        # The route only updates the run status; it does not require a valid selected_book_id FK
        # (pick_book() doesn't validate it against the DB). Any int is fine here.
        db_session.commit()

        resp = client.post(
            f"/book-selection/courses/{course_id}/analysis/{run.id}/pick/1",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "book_picked"

    # ── trigger_analysis (409 conflict) ─────────────────────────────────────

    def test_trigger_analysis_conflict_when_active_run_exists(
        self, client, db_session, teacher_auth_headers, monkeypatch
    ):
        """POST /analysis returns 409 when create_run_and_launch raises ValueError."""
        course_id = self._create_course(client, teacher_auth_headers)

        # Patch the workflow launcher so no LangGraph or background task runs.
        # The mock raises ValueError to simulate an already-active run guard.
        mock_launcher = MagicMock(
            side_effect=ValueError(
                "An active analysis run already exists for this course."
            )
        )
        monkeypatch.setattr(
            "app.modules.curricularalignmentarchitect.api_routes.analysis.create_run_and_launch",
            mock_launcher,
        )

        resp = client.post(
            f"/book-selection/courses/{course_id}/analysis",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]
