from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .models import (
    BookExtractionRun,
    BookSelectionSession,
    BookStatus,
    CourseBook,
    CourseSelectedBook,
    DownloadStatus,
    SessionStatus,
)

logger = logging.getLogger(__name__)


class BookSelectionRepository:
    """Data access layer for book selection sessions and course books."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Session CRUD ────────────────────────────────────────────

    def create_session(
        self,
        course_id: int,
        thread_id: str,
        weights: dict[str, float],
        level: str,
    ) -> BookSelectionSession:
        # Supersede any existing non-terminal sessions for this course
        self.db.query(BookSelectionSession).filter(
            BookSelectionSession.course_id == course_id,
            BookSelectionSession.status.notin_(
                [
                    SessionStatus.COMPLETED,
                    SessionStatus.SUPERSEDED,
                ]
            ),
        ).update(
            {BookSelectionSession.status: SessionStatus.SUPERSEDED},
            synchronize_session="fetch",
        )
        session = BookSelectionSession(
            course_id=course_id,
            thread_id=thread_id,
            weights_json=json.dumps(weights),
            course_level=level,
            status=SessionStatus.CONFIGURING,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int) -> BookSelectionSession | None:
        return self.db.get(BookSelectionSession, session_id)

    def get_session_by_thread(self, thread_id: str) -> BookSelectionSession | None:
        return (
            self.db.query(BookSelectionSession)
            .filter(BookSelectionSession.thread_id == thread_id)
            .first()
        )

    def get_latest_session(self, course_id: int) -> BookSelectionSession | None:
        return (
            self.db.query(BookSelectionSession)
            .filter(BookSelectionSession.course_id == course_id)
            .order_by(BookSelectionSession.created_at.desc())
            .first()
        )

    def update_status(self, session_id: int, status: SessionStatus) -> None:
        session = self.get_session(session_id)
        if session:
            session.status = status
            session.updated_at = datetime.now(UTC)
            self.db.commit()

    def update_progress(
        self,
        session_id: int,
        *,
        status: SessionStatus | None = None,
        progress_scored: int | None = None,
        progress_total: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update session progress fields atomically."""
        session = self.get_session(session_id)
        if session:
            if status is not None:
                session.status = status
            if progress_scored is not None:
                session.progress_scored = progress_scored
            if progress_total is not None:
                session.progress_total = progress_total
            if error_message is not None:
                session.error_message = error_message
            session.updated_at = datetime.now(UTC)
            self.db.commit()

    def save_discovered_books(
        self, session_id: int, discovered_books: list[dict]
    ) -> None:
        """Persist discovered books JSON on the session for resume support."""
        session = self.get_session(session_id)
        if session:
            session.discovered_books_json = json.dumps(
                discovered_books, ensure_ascii=False
            )
            session.updated_at = datetime.now(UTC)
            self.db.commit()

    def load_discovered_books(self, session_id: int) -> list[dict] | None:
        """Load previously persisted discovered books, or None if not saved."""
        session = self.get_session(session_id)
        if session and session.discovered_books_json:
            return json.loads(session.discovered_books_json)
        return None

    # ── Book CRUD ───────────────────────────────────────────────

    def upsert_books(
        self,
        session_id: int,
        course_id: int,
        scored_books: list[dict],
    ) -> list[CourseBook]:
        """Bulk insert CourseBook rows from scoring results."""
        books: list[CourseBook] = []
        for sb in scored_books:
            book = self._make_course_book(session_id, course_id, sb)
            self.db.add(book)
            books.append(book)
        self.db.commit()
        for b in books:
            self.db.refresh(b)
        return books

    def insert_scored_book(
        self,
        session_id: int,
        course_id: int,
        scored_book: dict,
    ) -> CourseBook:
        """Insert a single scored book immediately after scoring."""
        book = self._make_course_book(session_id, course_id, scored_book)
        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)
        return book

    @staticmethod
    def _make_course_book(
        session_id: int,
        course_id: int,
        sb: dict,
    ) -> CourseBook:
        """Build a CourseBook from a scored-book dict, sanitizing fields."""
        raw_year = sb.get("year", "") or ""
        raw_publisher = sb.get("publisher", "") or ""
        # Truncate to column limits: year VARCHAR(10), publisher VARCHAR(255)
        year = raw_year[:10] if len(raw_year) > 10 else raw_year
        publisher = raw_publisher[:255] if len(raw_publisher) > 255 else raw_publisher
        return CourseBook(
            session_id=session_id,
            course_id=course_id,
            title=(sb.get("book_title", "Unknown") or "Unknown")[:500],
            authors=(sb.get("book_authors", "") or "")[:500],
            publisher=publisher,
            year=year,
            s_final=sb.get("S_final"),
            scores_json=json.dumps(sb),
            selected_by_teacher=False,
            download_status=DownloadStatus.PENDING,
        )

    def mark_selected(self, session_id: int, book_ids: list[int]) -> int:
        """Set selected_by_teacher=True for the given book IDs."""
        count = (
            self.db.query(CourseBook)
            .filter(
                CourseBook.session_id == session_id,
                CourseBook.id.in_(book_ids),
            )
            .update(
                {CourseBook.selected_by_teacher: True},
                synchronize_session="fetch",
            )
        )
        self.db.commit()
        return count

    def update_download_result(
        self,
        book_id: int,
        status: DownloadStatus,
        blob_path: str | None = None,
        error: str | None = None,
        source_url: str | None = None,
    ) -> None:
        book = self.db.get(CourseBook, book_id)
        if book:
            book.download_status = status
            if blob_path is not None:
                book.blob_path = blob_path
            if error is not None:
                book.download_error = error
            if source_url is not None:
                book.source_url = source_url
            self.db.commit()

    def get_books(self, session_id: int) -> list[CourseBook]:
        return (
            self.db.query(CourseBook)
            .filter(CourseBook.session_id == session_id)
            .order_by(CourseBook.s_final.desc().nullslast())
            .all()
        )

    def get_selected_books(self, session_id: int) -> list[CourseBook]:
        return (
            self.db.query(CourseBook)
            .filter(
                CourseBook.session_id == session_id,
                CourseBook.selected_by_teacher.is_(True),
            )
            .all()
        )

    def get_course_books(self, course_id: int) -> list[CourseBook]:
        """All books across sessions for the course."""
        return (
            self.db.query(CourseBook)
            .filter(CourseBook.course_id == course_id)
            .order_by(CourseBook.s_final.desc().nullslast())
            .all()
        )

    def get_book(self, book_id: int) -> CourseBook | None:
        return self.db.get(CourseBook, book_id)

    def book_exists_for_course(self, course_id: int, title: str) -> bool:
        """Check if a book with the same title already exists for this course."""
        from sqlalchemy import func

        return (
            self.db.query(CourseBook)
            .filter(
                CourseBook.course_id == course_id,
                func.lower(CourseBook.title) == title.strip().lower(),
            )
            .first()
            is not None
        )

    def create_manual_book(
        self,
        course_id: int,
        session_id: int | None,
        title: str,
        authors: str | None,
        blob_path: str,
    ) -> CourseBook:
        """Create a CourseBook entry for a manually uploaded book."""
        book = CourseBook(
            session_id=session_id,
            course_id=course_id,
            title=title,
            authors=authors,
            download_status=DownloadStatus.MANUAL_UPLOAD,
            blob_path=blob_path,
        )
        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)
        return book

    # ── CourseSelectedBook CRUD ─────────────────────────────────

    def create_selected_book(
        self,
        *,
        course_id: int,
        title: str,
        authors: str | None = None,
        publisher: str | None = None,
        year: str | None = None,
        status: BookStatus,
        blob_path: str | None = None,
        blob_url: str | None = None,
        error_message: str | None = None,
        source_book_id: int | None = None,
    ) -> CourseSelectedBook:
        """Create a CourseSelectedBook entry."""
        book = CourseSelectedBook(
            course_id=course_id,
            source_book_id=source_book_id,
            title=title,
            authors=authors,
            publisher=publisher,
            year=year,
            status=status,
            blob_path=blob_path,
            blob_url=blob_url,
            error_message=error_message,
        )
        self.db.add(book)
        self.db.commit()
        self.db.refresh(book)
        return book

    def get_selected_book(self, selected_book_id: int) -> CourseSelectedBook | None:
        return self.db.get(CourseSelectedBook, selected_book_id)

    def get_selected_book_by_source(
        self, source_book_id: int
    ) -> CourseSelectedBook | None:
        """Find a selected book by its source CourseBook id."""
        return (
            self.db.query(CourseSelectedBook)
            .filter(CourseSelectedBook.source_book_id == source_book_id)
            .first()
        )

    def get_course_selected_books(self, course_id: int) -> list[CourseSelectedBook]:
        """All selected books for a course."""
        return (
            self.db.query(CourseSelectedBook)
            .filter(CourseSelectedBook.course_id == course_id)
            .order_by(CourseSelectedBook.created_at.desc())
            .all()
        )

    def update_selected_book_status(
        self,
        selected_book_id: int,
        status: BookStatus,
        blob_path: str | None = None,
        blob_url: str | None = None,
        error_message: str | None = None,
    ) -> CourseSelectedBook | None:
        book = self.db.get(CourseSelectedBook, selected_book_id)
        if book is None:
            return None
        book.status = status
        if blob_path is not None:
            book.blob_path = blob_path
        if blob_url is not None:
            book.blob_url = blob_url
        if error_message is not None:
            book.error_message = error_message
        self.db.commit()
        self.db.refresh(book)
        return book

    def selected_book_exists_for_course(self, course_id: int, title: str) -> bool:
        """Check if a selected book with the same title already exists."""
        from sqlalchemy import func

        return (
            self.db.query(CourseSelectedBook)
            .filter(
                CourseSelectedBook.course_id == course_id,
                func.lower(CourseSelectedBook.title) == title.strip().lower(),
            )
            .first()
            is not None
        )

    def delete_selected_book(self, selected_book_id: int) -> bool:
        book = self.db.get(CourseSelectedBook, selected_book_id)
        if book is None:
            return False
        self.db.delete(book)
        self.db.commit()
        return True

    def delete_all_selected_books_for_course(
        self, course_id: int
    ) -> list[CourseSelectedBook]:
        """Delete all selected books and their analysis data for a course.

        Deletes BookExtractionRun rows first (which cascade-delete chapters,
        chunks, summaries, etc.), then deletes CourseSelectedBook rows.
        Returns the deleted selected books so callers can clean up blobs.
        """
        selected = self.get_course_selected_books(course_id)
        if not selected:
            return []

        # Load extraction runs into session so ORM cascades fire
        # (bulk .delete() bypasses relationship cascades)
        runs = (
            self.db.query(BookExtractionRun)
            .filter(BookExtractionRun.course_id == course_id)
            .all()
        )
        for run in runs:
            self.db.delete(run)
        self.db.flush()

        # Now safe to delete selected books
        for book in selected:
            self.db.delete(book)
        self.db.flush()

        # Reset candidate CourseBook rows
        self.db.query(CourseBook).filter(
            CourseBook.course_id == course_id,
        ).update(
            {
                CourseBook.selected_by_teacher: False,
                CourseBook.download_status: DownloadStatus.PENDING,
                CourseBook.download_error: None,
                CourseBook.blob_path: None,
                CourseBook.source_url: None,
            },
            synchronize_session="fetch",
        )

        self.db.commit()
        return selected
