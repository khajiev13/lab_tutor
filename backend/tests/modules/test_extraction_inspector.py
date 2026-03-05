"""Tests for the extraction inspector endpoints (HITL PDF review).

Covers:
- Auth guards (401 / 403) for all three endpoints
- 404 when run not found
- 409 conflict states (active run, wrong status)
- Extraction preview with chapters/sections data
- Approve extraction flow
- Reuse of existing CHAPTER_EXTRACTED run
"""

from __future__ import annotations

from app.modules.auth.models import User, UserRole
from app.modules.courses.models import Course
from app.modules.curricularalignmentarchitect.models import (
    BookChapter,
    BookExtractionRun,
    BookSection,
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
            email=f"teacher-inspector-{course_id}@test.local",
            hashed_password="!unused",
            first_name="Test",
            last_name="Teacher",
            role=UserRole.TEACHER,
        )
        db_session.add(teacher)
        db_session.flush()
    course = Course(
        id=course_id,
        title=f"Inspector Test Course {course_id}",
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


def _make_chapter(
    db_session,
    run_id: int,
    selected_book_id: int,
    chapter_title: str = "Chapter 1",
    chapter_index: int = 0,
    chapter_text: str = "Full chapter text here.",
) -> BookChapter:
    chapter = BookChapter(
        run_id=run_id,
        selected_book_id=selected_book_id,
        chapter_title=chapter_title,
        chapter_index=chapter_index,
        chapter_text=chapter_text,
    )
    db_session.add(chapter)
    db_session.flush()
    return chapter


def _make_section(
    db_session,
    chapter_id: int,
    section_title: str = "Section 1.1",
    section_index: int = 0,
    section_content: str = "Section content goes here.",
) -> BookSection:
    section = BookSection(
        chapter_id=chapter_id,
        section_title=section_title,
        section_index=section_index,
        section_content=section_content,
    )
    db_session.add(section)
    db_session.flush()
    return section


BASE = "/book-selection/courses"


# ── Extract-only endpoint ───────────────────────────────────────


class TestExtractOnlyAuth:
    def test_requires_auth(self, client):
        resp = client.post(f"{BASE}/1/analysis/extract-only")
        assert resp.status_code == 401

    def test_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            f"{BASE}/1/analysis/extract-only",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


class TestExtractOnlyConflict:
    def test_active_run_returns_409(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        _make_run(db_session, course_id=course_id, status=ExtractionRunStatus.EXTRACTING)
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/extract-only",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"]

    def test_pending_run_returns_409(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        _make_run(db_session, course_id=course_id, status=ExtractionRunStatus.PENDING)
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/extract-only",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409

    def test_reuses_chapter_extracted_run(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/extract-only",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["id"] == run.id
        assert data["status"] == "chapter_extracted"

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Extract-Only Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]


# ── Extraction preview endpoint ─────────────────────────────────


class TestExtractionPreviewAuth:
    def test_requires_auth(self, client):
        resp = client.get(f"{BASE}/1/analysis/1/extraction-preview")
        assert resp.status_code == 401

    def test_requires_teacher(self, client, student_auth_headers):
        resp = client.get(
            f"{BASE}/1/analysis/1/extraction-preview",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


class TestExtractionPreview:
    def test_run_not_found_returns_404(self, client, teacher_auth_headers):
        resp = client.get(
            f"{BASE}/99999/analysis/99999/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_wrong_course_returns_404(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        db_session.commit()

        resp = client.get(
            f"{BASE}/99999/analysis/{run.id}/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_pending_status_returns_409(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.PENDING,
        )
        db_session.commit()

        resp = client.get(
            f"{BASE}/{course_id}/analysis/{run.id}/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409
        assert "not started" in resp.json()["detail"]

    def test_returns_empty_books(self, client, db_session, teacher_auth_headers):
        """Run exists, no books → empty books list."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        db_session.commit()

        resp = client.get(
            f"{BASE}/{course_id}/analysis/{run.id}/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run.id
        assert data["run_status"] == "chapter_extracted"
        assert data["books"] == []

    def test_returns_chapters_and_sections(
        self, client, db_session, teacher_auth_headers
    ):
        """Full preview: book → chapters → sections with content."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        book = _make_selected_book(
            db_session,
            course_id=course_id,
            title="Data Systems",
        )
        ch1 = _make_chapter(
            db_session,
            run_id=run.id,
            selected_book_id=book.id,
            chapter_title="Introduction",
            chapter_index=0,
            chapter_text="Intro chapter text.",
        )
        _make_section(
            db_session,
            chapter_id=ch1.id,
            section_title="Overview",
            section_index=0,
            section_content="This is the overview section.",
        )
        _make_section(
            db_session,
            chapter_id=ch1.id,
            section_title="Motivation",
            section_index=1,
            section_content="",
        )
        ch2 = _make_chapter(
            db_session,
            run_id=run.id,
            selected_book_id=book.id,
            chapter_title="Data Storage",
            chapter_index=1,
            chapter_text="Storage chapter text.",
        )
        _make_section(
            db_session,
            chapter_id=ch2.id,
            section_title="HDFS",
            section_index=0,
            section_content="Hadoop Distributed File System content.",
        )
        db_session.commit()

        resp = client.get(
            f"{BASE}/{course_id}/analysis/{run.id}/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run.id
        assert len(data["books"]) == 1

        bk = data["books"][0]
        assert bk["book_title"] == "Data Systems"
        assert bk["total_chapters"] == 2
        assert bk["total_sections"] == 3

        # First chapter
        intro = bk["chapters"][0]
        assert intro["chapter_title"] == "Introduction"
        assert intro["chapter_index"] == 0
        assert intro["has_content"] is True
        assert intro["section_count"] == 2

        overview = intro["sections"][0]
        assert overview["section_title"] == "Overview"
        assert overview["has_content"] is True
        assert overview["content_length"] > 0

        motivation = intro["sections"][1]
        assert motivation["section_title"] == "Motivation"
        assert motivation["has_content"] is False

        # Second chapter
        storage = bk["chapters"][1]
        assert storage["chapter_title"] == "Data Storage"
        assert storage["section_count"] == 1

    def test_multiple_books(self, client, db_session, teacher_auth_headers):
        """Preview with multiple books returns all."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        _make_selected_book(db_session, course_id=course_id, title="Book A")
        _make_selected_book(db_session, course_id=course_id, title="Book B")
        db_session.commit()

        resp = client.get(
            f"{BASE}/{course_id}/analysis/{run.id}/extraction-preview",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()["books"]) == 2

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Preview Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]


# ── Approve extraction endpoint ─────────────────────────────────


class TestApproveExtractionAuth:
    def test_requires_auth(self, client):
        resp = client.post(f"{BASE}/1/analysis/1/approve-extraction")
        assert resp.status_code == 401

    def test_requires_teacher(self, client, student_auth_headers):
        resp = client.post(
            f"{BASE}/1/analysis/1/approve-extraction",
            headers=student_auth_headers,
        )
        assert resp.status_code == 403


class TestApproveExtraction:
    def test_run_not_found_returns_404(self, client, teacher_auth_headers):
        resp = client.post(
            f"{BASE}/99999/analysis/99999/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_wrong_course_returns_404(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/99999/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 404

    def test_pending_status_returns_409(self, client, db_session, teacher_auth_headers):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.PENDING,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409
        assert "chapter_extracted" in resp.json()["detail"]

    def test_extracting_status_returns_409(
        self, client, db_session, teacher_auth_headers
    ):
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.EXTRACTING,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 409

    def test_approve_chapter_extracted_starts_chunking(
        self, client, db_session, teacher_auth_headers
    ):
        """Approve sets status to CHUNKING and returns run."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.CHAPTER_EXTRACTED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == run.id
        assert data["status"] == "chunking"

    def test_approve_completed_run_allowed(
        self, client, db_session, teacher_auth_headers
    ):
        """COMPLETED status is also approved (re-run chunking)."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.COMPLETED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "chunking"

    def test_approve_book_picked_allowed(
        self, client, db_session, teacher_auth_headers
    ):
        """BOOK_PICKED status is also approved."""
        course_id = self._create_course(client, teacher_auth_headers)
        run = _make_run(
            db_session,
            course_id=course_id,
            status=ExtractionRunStatus.BOOK_PICKED,
        )
        db_session.commit()

        resp = client.post(
            f"{BASE}/{course_id}/analysis/{run.id}/approve-extraction",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "chunking"

    def _create_course(self, client, teacher_auth_headers) -> int:
        resp = client.post(
            "/courses/",
            json={"title": "Approve Test Course", "description": "test"},
            headers=teacher_auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]
