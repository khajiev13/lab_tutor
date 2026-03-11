"""Tests for the book-selection feature (repository, schemas, routes)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.book_selection.utils import (
    compute_finals,
)
from app.modules.curricularalignmentarchitect.models import (
    CourseBook,
    DownloadStatus,
    SessionStatus,
)
from app.modules.curricularalignmentarchitect.repository import (
    BookSelectionRepository,
)
from app.modules.curricularalignmentarchitect.schemas import (
    SelectBooksRequest,
    WeightsConfig,
)
from app.modules.curricularalignmentarchitect.service import BookSelectionService

TEST_WEIGHTS = {
    "C_topic": 0.30,
    "C_struc": 0.20,
    "C_scope": 0.15,
    "C_pub": 0.15,
    "C_auth": 0.10,
    "C_time": 0.10,
    "W_prac": 0.0,
}

# ═══════════════════════════════════════════════════════════════
# WeightsConfig validation tests
# ═══════════════════════════════════════════════════════════════


class TestWeightsConfig:
    def test_explicit_weights_are_valid(self):
        w = WeightsConfig(**TEST_WEIGHTS)
        total = w.C_topic + w.C_struc + w.C_scope + w.C_pub + w.C_auth + w.C_time
        assert abs(total - 1.0) <= 1e-6

    def test_valid_custom_weights(self):
        w = WeightsConfig(
            C_topic=0.25,
            C_struc=0.25,
            C_scope=0.20,
            C_pub=0.10,
            C_auth=0.10,
            C_time=0.10,
            W_prac=0.0,
        )
        assert w.C_topic == 0.25

    def test_invalid_weights_sum_too_low(self):
        with pytest.raises(ValidationError, match="must sum to"):
            WeightsConfig(
                C_topic=0.1,
                C_struc=0.1,
                C_scope=0.1,
                C_pub=0.1,
                C_auth=0.1,
                C_time=0.1,
                W_prac=0.0,
            )

    def test_invalid_weights_sum_too_high(self):
        with pytest.raises(ValidationError, match="must sum to"):
            WeightsConfig(
                C_topic=0.5,
                C_struc=0.5,
                C_scope=0.5,
                C_pub=0.1,
                C_auth=0.1,
                C_time=0.1,
                W_prac=0.0,
            )

    def test_invalid_weights_sum_not_exact(self):
        with pytest.raises(ValidationError, match="must sum to"):
            WeightsConfig(
                C_topic=0.30,
                C_struc=0.20,
                C_scope=0.15,
                C_pub=0.15,
                C_auth=0.10,
                C_time=0.09,
                W_prac=0.0,
            )

    def test_to_weights_dict(self):
        w = WeightsConfig(**TEST_WEIGHTS)
        d = w.to_weights_dict()
        assert set(d.keys()) == {
            "C_topic",
            "C_struc",
            "C_scope",
            "C_pub",
            "C_auth",
            "C_time",
            "W_prac",
        }
        assert d["W_prac"] == 0.0


class TestComputeFinals:
    def test_compute_finals_without_practicality(self):
        scores = {
            "C_topic": 0.8,
            "C_struc": 0.7,
            "C_scope": 0.9,
            "C_pub": 1.0,
            "C_auth": 0.6,
            "C_time": 0.8,
            "C_prac": 0.2,
        }
        s_base, s_with_prac = compute_finals(scores, w_prac=0.0)
        assert s_base == s_with_prac

    def test_compute_finals_with_practicality_blend(self):
        scores = {
            "C_topic": 1.0,
            "C_struc": 1.0,
            "C_scope": 1.0,
            "C_pub": 1.0,
            "C_auth": 1.0,
            "C_time": 1.0,
            "C_prac": 0.5,
        }
        s_base, s_with_prac = compute_finals(scores, w_prac=0.2)
        assert s_base == 1.0
        assert s_with_prac == 0.9


class TestSelectBooksRequest:
    def test_valid_selection(self):
        req = SelectBooksRequest(book_ids=[1, 2, 3])
        assert len(req.book_ids) == 3

    def test_empty_selection_is_valid(self):
        req = SelectBooksRequest(book_ids=[])
        assert len(req.book_ids) == 0

    def test_max_five_books(self):
        req = SelectBooksRequest(book_ids=[1, 2, 3, 4, 5])
        assert len(req.book_ids) == 5

    def test_over_five_books_rejected(self):
        with pytest.raises(ValidationError):
            SelectBooksRequest(book_ids=[1, 2, 3, 4, 5, 6])


# ═══════════════════════════════════════════════════════════════
# BookSelectionRepository tests
# ═══════════════════════════════════════════════════════════════


class TestBookSelectionRepository:
    def _make_repo(self, db_session) -> BookSelectionRepository:
        return BookSelectionRepository(db_session)

    def _ensure_course(self, db_session, course_id: int = 1) -> Course:
        """Create a User + Course row so FK constraints are satisfied."""
        existing = db_session.get(Course, course_id)
        if existing:
            return existing
        # Ensure a teacher user exists
        teacher = db_session.get(User, course_id)
        if not teacher:
            teacher = User(
                id=course_id,
                email=f"teacher-{course_id}@test.local",
                hashed_password="!unused",
                first_name="Test",
                last_name="Teacher",
                role=UserRole.TEACHER,
            )
            db_session.add(teacher)
            db_session.flush()
        course = Course(
            id=course_id,
            title=f"Test Course {course_id}",
            teacher_id=teacher.id,
        )
        db_session.add(course)
        db_session.flush()
        return course

    def test_create_session(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={"C_topic": 0.3},
            level="bachelor",
        )
        assert session.id is not None
        assert session.status == SessionStatus.CONFIGURING
        assert session.course_level == "bachelor"

    def test_get_session(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        created = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="master",
        )
        fetched = repo.get_session(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    def test_get_session_nonexistent(self, db_session):
        repo = self._make_repo(db_session)
        assert repo.get_session(99999) is None

    def test_get_session_by_thread(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        tid = f"test-{uuid.uuid4().hex[:8]}"
        repo.create_session(course_id=1, thread_id=tid, weights={}, level="phd")
        fetched = repo.get_session_by_thread(tid)
        assert fetched is not None
        assert fetched.thread_id == tid

    def test_get_latest_session(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 42)
        repo.create_session(
            course_id=42,
            thread_id=f"t1-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        s2 = repo.create_session(
            course_id=42,
            thread_id=f"t2-{uuid.uuid4().hex[:8]}",
            weights={},
            level="master",
        )
        latest = repo.get_latest_session(42)
        assert latest is not None
        assert latest.id == s2.id

    def test_update_status(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        assert session.status == SessionStatus.CONFIGURING

        repo.update_status(session.id, SessionStatus.DISCOVERING)
        updated = repo.get_session(session.id)
        assert updated is not None
        assert updated.status == SessionStatus.DISCOVERING

    def test_status_transitions(self, db_session):
        """Test the expected session lifecycle transitions."""
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )

        transitions = [
            SessionStatus.DISCOVERING,
            SessionStatus.SCORING,
            SessionStatus.AWAITING_REVIEW,
            SessionStatus.DOWNLOADING,
            SessionStatus.COMPLETED,
        ]
        for new_status in transitions:
            repo.update_status(session.id, new_status)
            s = repo.get_session(session.id)
            assert s is not None
            assert s.status == new_status

    def test_upsert_books(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        scored = [
            {
                "book_title": "Book A",
                "book_authors": "Author A",
                "publisher": "Pub A",
                "year": "2024",
                "S_final": 8.5,
            },
            {
                "book_title": "Book B",
                "book_authors": "Author B",
                "S_final": 7.2,
            },
        ]
        books = repo.upsert_books(session.id, 1, scored)
        assert len(books) == 2
        assert books[0].title == "Book A"
        assert books[0].s_final == 8.5
        assert books[0].download_status == DownloadStatus.PENDING

    def test_mark_selected(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        books = repo.upsert_books(
            session.id,
            1,
            [
                {"book_title": "A", "S_final": 9.0},
                {"book_title": "B", "S_final": 8.0},
                {"book_title": "C", "S_final": 7.0},
            ],
        )
        # Mark first two
        count = repo.mark_selected(session.id, [books[0].id, books[1].id])
        assert count == 2

        selected = repo.get_selected_books(session.id)
        assert len(selected) == 2
        titles = {b.title for b in selected}
        assert titles == {"A", "B"}

    def test_get_books_sorted_by_score(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        repo.upsert_books(
            session.id,
            1,
            [
                {"book_title": "Low", "S_final": 3.0},
                {"book_title": "High", "S_final": 9.0},
                {"book_title": "Mid", "S_final": 6.0},
            ],
        )
        books = repo.get_books(session.id)
        scores = [b.s_final for b in books]
        assert scores == [9.0, 6.0, 3.0], "Books should be sorted descending by score"

    def test_update_download_result(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        books = repo.upsert_books(session.id, 1, [{"book_title": "X", "S_final": 5.0}])
        book_id = books[0].id

        repo.update_download_result(
            book_id,
            DownloadStatus.SUCCESS,
            blob_path="courses/1/books/X.pdf",
            source_url="https://example.com/x.pdf",
        )
        updated = repo.get_book(book_id)
        assert updated is not None
        assert updated.download_status == DownloadStatus.SUCCESS
        assert updated.blob_path == "courses/1/books/X.pdf"
        assert updated.source_url == "https://example.com/x.pdf"

    def test_update_download_result_failure(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        books = repo.upsert_books(session.id, 1, [{"book_title": "Y", "S_final": 4.0}])
        book_id = books[0].id

        repo.update_download_result(
            book_id, DownloadStatus.FAILED, error="404 Not Found"
        )
        updated = repo.get_book(book_id)
        assert updated is not None
        assert updated.download_status == DownloadStatus.FAILED
        assert updated.download_error == "404 Not Found"

    def test_create_manual_book(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 1)
        book = repo.create_manual_book(
            course_id=1,
            session_id=None,
            title="Manual Book",
            authors="Teacher",
            blob_path="courses/1/books/manual.pdf",
        )
        assert book.id is not None
        assert book.download_status == DownloadStatus.MANUAL_UPLOAD
        assert book.title == "Manual Book"

    def test_get_course_books_across_sessions(self, db_session):
        repo = self._make_repo(db_session)
        self._ensure_course(db_session, 7)
        s1 = repo.create_session(
            course_id=7,
            thread_id=f"t1-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        s2 = repo.create_session(
            course_id=7,
            thread_id=f"t2-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        repo.upsert_books(s1.id, 7, [{"book_title": "A", "S_final": 5.0}])
        repo.upsert_books(s2.id, 7, [{"book_title": "B", "S_final": 6.0}])

        all_books = repo.get_course_books(7)
        assert len(all_books) == 2


# ═══════════════════════════════════════════════════════════════
# Route tests (API-level with auth)
# ═══════════════════════════════════════════════════════════════


class TestBookSelectionRoutes:
    def _create_course_via_api(self, client, teacher_auth_headers):
        """Create a course via the API so FK constraints are satisfied."""
        resp = client.post(
            "/courses/",
            json={"title": "Test Course for Book Selection", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), f"Failed to create course: {resp.text}"
        return resp.json()["id"]

    def test_create_session_requires_auth(self, client):
        resp = client.post(
            "/book-selection/sessions",
            params={"course_id": 1},
            json={"course_level": "bachelor", "weights": TEST_WEIGHTS},
        )
        assert resp.status_code == 401

    def test_create_session_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            "/book-selection/sessions",
            params={"course_id": 1},
            json={"course_level": "bachelor", "weights": TEST_WEIGHTS},
            headers=student_auth_headers,
        )
        assert resp.status_code == 403

    def test_create_session_success(self, client, teacher_auth_headers):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        resp = client.post(
            "/book-selection/sessions",
            params={"course_id": course_id},
            json={"course_level": "bachelor", "weights": TEST_WEIGHTS},
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["course_id"] == course_id
        assert data["status"] == "configuring"
        assert "thread_id" in data

    def test_get_session_not_found(self, client, teacher_auth_headers):
        resp = client.get(
            "/book-selection/sessions/99999",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_get_latest_session_none(self, client, teacher_auth_headers):
        resp = client.get(
            "/book-selection/courses/999/session",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() is None

    def test_create_and_get_session(self, client, teacher_auth_headers):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        # Create
        create_resp = client.post(
            "/book-selection/sessions",
            params={"course_id": course_id},
            json={"course_level": "master", "weights": TEST_WEIGHTS},
            headers=teacher_auth_headers,
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["id"]

        # Get
        get_resp = client.get(
            f"/book-selection/sessions/{session_id}",
            headers=teacher_auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == session_id
        assert get_resp.json()["course_level"] == "master"

    def test_get_course_books_empty(self, client, teacher_auth_headers):
        resp = client.get(
            "/book-selection/courses/1/books",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_invalid_weights_rejected(self, client, teacher_auth_headers):
        resp = client.post(
            "/book-selection/sessions",
            params={"course_id": 1},
            json={
                "course_level": "bachelor",
                "weights": {
                    "C_topic": 0.1,
                    "C_struc": 0.1,
                    "C_scope": 0.1,
                    "C_pub": 0.1,
                    "C_auth": 0.1,
                    "C_time": 0.1,
                    "W_prac": 0.0,
                },
            },
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════
# Rediscover endpoint tests
# ═══════════════════════════════════════════════════════════════


class TestRediscoverRoute:
    """Tests for POST /book-selection/sessions/{id}/rediscover."""

    def _create_course_via_api(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Rediscover Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201)
        return resp.json()["id"]

    def _create_session(self, client, teacher_auth_headers, course_id: int) -> int:
        resp = client.post(
            "/book-selection/sessions",
            params={"course_id": course_id},
            json={"course_level": "bachelor", "weights": TEST_WEIGHTS},
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    @patch(
        "app.modules.curricularalignmentarchitect.service.BookSelectionService.rediscover_books",
        new_callable=AsyncMock,
    )
    def test_rediscover_from_awaiting_review(
        self, mock_rediscover, client, teacher_auth_headers, db_session
    ):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        session_id = self._create_session(client, teacher_auth_headers, course_id)

        # Transition session to AWAITING_REVIEW
        repo = BookSelectionRepository(db_session)
        repo.update_status(session_id, SessionStatus.AWAITING_REVIEW)

        resp = client.post(
            f"/book-selection/sessions/{session_id}/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 202
        mock_rediscover.assert_called_once_with(session_id)

    @patch(
        "app.modules.curricularalignmentarchitect.service.BookSelectionService.rediscover_books",
        new_callable=AsyncMock,
    )
    def test_rediscover_from_failed(
        self, mock_rediscover, client, teacher_auth_headers, db_session
    ):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        session_id = self._create_session(client, teacher_auth_headers, course_id)

        repo = BookSelectionRepository(db_session)
        repo.update_status(session_id, SessionStatus.FAILED)

        resp = client.post(
            f"/book-selection/sessions/{session_id}/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 202
        mock_rediscover.assert_called_once_with(session_id)

    def test_rediscover_rejected_from_configuring(
        self, client, teacher_auth_headers, db_session
    ):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        session_id = self._create_session(client, teacher_auth_headers, course_id)

        # Session starts in CONFIGURING — rediscover should be rejected
        resp = client.post(
            f"/book-selection/sessions/{session_id}/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400
        assert "Cannot rediscover" in resp.json()["detail"]

    def test_rediscover_rejected_from_downloading(
        self, client, teacher_auth_headers, db_session
    ):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        session_id = self._create_session(client, teacher_auth_headers, course_id)

        repo = BookSelectionRepository(db_session)
        repo.update_status(session_id, SessionStatus.DOWNLOADING)

        resp = client.post(
            f"/book-selection/sessions/{session_id}/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400
        assert "Cannot rediscover" in resp.json()["detail"]

    def test_rediscover_rejected_from_scoring(
        self, client, teacher_auth_headers, db_session
    ):
        course_id = self._create_course_via_api(client, teacher_auth_headers)
        session_id = self._create_session(client, teacher_auth_headers, course_id)

        repo = BookSelectionRepository(db_session)
        repo.update_status(session_id, SessionStatus.SCORING)

        resp = client.post(
            f"/book-selection/sessions/{session_id}/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 400
        assert "Cannot rediscover" in resp.json()["detail"]

    def test_rediscover_not_found(self, client, teacher_auth_headers):
        resp = client.post(
            "/book-selection/sessions/99999/rediscover",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_rediscover_requires_auth(self, client):
        resp = client.post("/book-selection/sessions/1/rediscover")
        assert resp.status_code == 401

    def test_rediscover_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            "/book-selection/sessions/1/rediscover",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════
# Auto-heal stale downloads
# ═══════════════════════════════════════════════════════════════


class TestAutoHealStaleDownloads(TestBookSelectionRepository):
    """Tests for _auto_heal_stuck_downloading with stale-timeout logic."""

    def _make_service(self, db_session) -> BookSelectionService:
        repo = BookSelectionRepository(db_session)
        blob_service = AsyncMock()
        return BookSelectionService(repo=repo, blob_service=blob_service)

    def _create_session_with_books(
        self, db_session, *, download_statuses: list[DownloadStatus]
    ):
        """Helper: create a DOWNLOADING session with books at given statuses."""
        self._ensure_course(db_session, 1)
        repo = BookSelectionRepository(db_session)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        scored = [
            {"book_title": f"Book {i}", "S_final": 9.0 - i}
            for i in range(len(download_statuses))
        ]
        books = repo.upsert_books(session.id, 1, scored)
        repo.mark_selected(session.id, [b.id for b in books])

        repo.update_progress(session.id, status=SessionStatus.DOWNLOADING)
        for book, status in zip(books, download_statuses):
            repo.update_download_result(book.id, status)

        db_session.refresh(session)
        return session, books

    def test_heals_when_all_terminal(self, db_session):
        """Session completes when all books are already terminal."""
        service = self._make_service(db_session)
        session, _ = self._create_session_with_books(
            db_session,
            download_statuses=[
                DownloadStatus.SUCCESS,
                DownloadStatus.FAILED,
                DownloadStatus.MANUAL_UPLOAD,
            ],
        )
        service._auto_heal_stuck_downloading(session)
        assert session.status == SessionStatus.COMPLETED

    def test_no_heal_when_recent_and_downloading(self, db_session):
        """A recent session with a book still downloading should NOT be healed."""
        service = self._make_service(db_session)
        session, books = self._create_session_with_books(
            db_session,
            download_statuses=[
                DownloadStatus.SUCCESS,
                DownloadStatus.DOWNLOADING,
            ],
        )
        service._auto_heal_stuck_downloading(session)
        assert session.status == SessionStatus.DOWNLOADING

    def test_heals_stale_downloading_books(self, db_session):
        """Books stuck at DOWNLOADING in a stale session get marked FAILED and session completes."""
        service = self._make_service(db_session)
        session, books = self._create_session_with_books(
            db_session,
            download_statuses=[
                DownloadStatus.SUCCESS,
                DownloadStatus.DOWNLOADING,  # will be healed
            ],
        )
        # Bypass SQLAlchemy's onupdate by using a raw UPDATE
        from sqlalchemy import text

        stale_ts = datetime.now(UTC) - timedelta(hours=1)
        db_session.execute(
            text("UPDATE book_selection_sessions SET updated_at = :ts WHERE id = :sid"),
            {"ts": stale_ts, "sid": session.id},
        )
        db_session.commit()
        db_session.refresh(session)

        service._auto_heal_stuck_downloading(session)

        assert session.status == SessionStatus.COMPLETED
        stuck_book = db_session.get(CourseBook, books[1].id)
        assert stuck_book.download_status == DownloadStatus.FAILED
        assert "timed out" in stuck_book.download_error

    def test_no_heal_on_non_downloading_session(self, db_session):
        """Auto-heal should be a no-op for sessions not in DOWNLOADING status."""
        service = self._make_service(db_session)
        self._ensure_course(db_session, 1)
        repo = BookSelectionRepository(db_session)
        session = repo.create_session(
            course_id=1,
            thread_id=f"test-{uuid.uuid4().hex[:8]}",
            weights={},
            level="bachelor",
        )
        repo.update_progress(session.id, status=SessionStatus.AWAITING_REVIEW)
        db_session.refresh(session)

        service._auto_heal_stuck_downloading(session)
        assert session.status == SessionStatus.AWAITING_REVIEW
