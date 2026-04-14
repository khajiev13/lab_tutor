"""Tests for the agentic chapter extraction endpoint (route guards + validation).

Covers:
- Auth guards (401 / 403)
- 404 when run not found
- 409 when run status is not allowed
- 400 when no selected books exist
"""

from __future__ import annotations

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.models import (
    BookExtractionRun,
    BookStatus,
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
            email=f"teacher-agentic-{course_id}@test.local",
            hashed_password="!unused",
            first_name="Test",
            last_name="Teacher",
            role=UserRole.TEACHER,
        )
        db_session.add(teacher)
        db_session.flush()
    course = Course(
        id=course_id,
        title=f"Agentic Test Course {course_id}",
        teacher_id=teacher.id,
    )
    db_session.add(course)
    db_session.flush()
    return course


def _make_run(
    db_session,
    course_id: int = 1,
    status: ExtractionRunStatus = ExtractionRunStatus.COMPLETED,
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
    blob_path: str | None = "courses/1/books/test.pdf",
) -> CourseSelectedBook:
    _ensure_course(db_session, course_id)
    book = CourseSelectedBook(
        course_id=course_id,
        title=title,
        authors="Author",
        status=BookStatus.DOWNLOADED,
        blob_path=blob_path,
    )
    db_session.add(book)
    db_session.flush()
    return book


BASE = "/book-selection/courses"


# ── Auth guard tests ────────────────────────────────────────────


class TestAgenticAnalysisAuth:
    def test_requires_auth(self, client):
        resp = client.post(f"{BASE}/1/analysis/1/agentic")
        assert resp.status_code == 401

    def test_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            f"{BASE}/1/analysis/1/agentic",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


# ── Validation tests ────────────────────────────────────────────


class TestAgenticAnalysisValidation:
    def test_run_not_found_returns_404(self, client, teacher_auth_headers):
        resp = client.post(
            f"{BASE}/99999/analysis/99999/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_wrong_course_returns_404(self, client, db_session, teacher_auth_headers):
        """Run exists but belongs to a different course → 404."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(db_session, course_id=course_id)
        db_session.commit()

        resp = client.post(
            f"{BASE}/99999/analysis/{run.id}/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_wrong_status_returns_409(self, client, db_session, teacher_auth_headers):
        """Run in 'pending' status → 409 Conflict."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.PENDING,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409

    def test_extracting_status_returns_409(
        self, client, db_session, teacher_auth_headers
    ):
        """Run in 'extracting' status → 409 Conflict."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.EXTRACTING,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409

    def test_no_selected_books_returns_400(
        self, client, db_session, teacher_auth_headers
    ):
        """Run is COMPLETED but no selected books with blob_path → 400."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.COMPLETED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400

    def test_books_without_blob_path_returns_400(
        self, client, db_session, teacher_auth_headers
    ):
        """Selected books exist but blob_path is None → 400."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.COMPLETED,
        )
        _make_selected_book(
            db_session,
            course_id=course_id,
            blob_path=None,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/agentic",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400

    # ── Helper ───────────────────────────────────────────────

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Agentic Route Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]
