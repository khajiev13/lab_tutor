"""Service layer for the book-selection feature."""

from __future__ import annotations

import json
import logging
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.providers.storage import BlobService

from .book_selection.graph import build_workflow
from .models import BookSelectionSession, BookStatus, DownloadStatus, SessionStatus
from .repository import BookSelectionRepository
from .schemas import (
    BookCandidateRead,
    CourseSelectedBookRead,
    ManualUploadResponse,
    SelectedBookManualUploadResponse,
    SessionRead,
    StartSessionRequest,
)

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


CORE_WEIGHT_KEYS = ("C_topic", "C_struc", "C_scope", "C_pub", "C_auth", "C_time")


def _sanitize_error(exc: Exception) -> str:
    """Return a user-friendly error message from an exception.

    Hides raw tracebacks / internal details; keeps short, helpful text.
    """
    raw = str(exc)
    # Connection / database errors
    if "InterfaceError" in raw or "connection is closed" in raw.lower():
        return "Database connection was lost. Please retry."
    if "OperationalError" in raw or "could not connect" in raw.lower():
        return "Database is temporarily unavailable. Please retry in a moment."
    # LLM / JSON parsing errors
    if "JSONDecodeError" in type(exc).__name__ or "json" in raw.lower():
        return "AI response could not be parsed. Please retry."
    if "OutputParserException" in type(exc).__name__:
        return "AI returned an unexpected format. Please retry."
    if "RateLimitError" in type(exc).__name__ or "rate" in raw.lower():
        return "AI rate limit reached. Please wait a moment and retry."
    if "timeout" in raw.lower() or "Timeout" in type(exc).__name__:
        return "Request timed out. Please retry."
    # Generic — truncate to something readable
    if len(raw) > 200:
        return f"An unexpected error occurred: {raw[:150]}…"
    return f"An unexpected error occurred: {raw}"


def _split_weights_payload(payload: dict) -> tuple[dict[str, float], float]:
    """Split persisted payload into core scoring weights and practicality blend."""
    core_weights = {
        key: float(payload[key]) for key in CORE_WEIGHT_KEYS if key in payload
    }
    w_prac = float(payload.get("W_prac", 0.0))
    return core_weights, w_prac


def _can_resume_scoring(status: SessionStatus) -> bool:
    """Check if a session is in a state that allows resuming scoring."""
    return status in (
        SessionStatus.SCORING,
        SessionStatus.DISCOVERING,
        SessionStatus.FAILED,
    )


@contextmanager
def _fresh_db() -> Generator[Session, None, None]:
    """Create a fresh database session for use in async generators.

    This is needed because FastAPI's dependency-injected sessions are closed
    after the route handler returns, but streaming responses continue running.

    The session close is wrapped in a try/except so that a stale-connection
    error during rollback (common with managed Postgres / Azure) does not
    mask the real result — the DB write likely already succeeded.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            # Connection may have been closed server-side (Azure idle timeout).
            # pool_pre_ping will provide a fresh connection on next checkout.
            logger.debug(
                "Suppressed error closing DB session (stale connection)", exc_info=True
            )


class BookSelectionService:
    """Orchestrates the book-selection workflow with HITL."""

    def __init__(
        self,
        repo: BookSelectionRepository,
        blob_service: BlobService,
    ) -> None:
        self.repo = repo
        self.blob_service = blob_service

    # ── Session management ──────────────────────────────────────

    def start_session(
        self,
        course_id: int,
        config: StartSessionRequest,
    ) -> SessionRead:
        """Create a new book-selection session."""
        thread_id = f"bs-{course_id}-{uuid.uuid4().hex[:12]}"
        weights_payload = config.weights.to_weights_dict()
        session = self.repo.create_session(
            course_id=course_id,
            thread_id=thread_id,
            weights=weights_payload,
            level=config.course_level.value,
        )
        return SessionRead.model_validate(session)

    def _auto_heal_stuck_downloading(
        self,
        session: BookSelectionSession,
    ) -> None:
        """If session is stuck at DOWNLOADING but all selected books are resolved, transition to COMPLETED.

        Also detects stale downloads: if the session hasn't been updated
        in >30 minutes, any books still at DOWNLOADING are treated as
        timed-out failures (the background task likely crashed).
        """
        if session.status != SessionStatus.DOWNLOADING:
            return
        selected_books = self.repo.get_selected_books(session.id)
        if not selected_books:
            return

        terminal_statuses = {
            DownloadStatus.SUCCESS,
            DownloadStatus.FAILED,
            DownloadStatus.MANUAL_UPLOAD,
        }

        # Detect stale downloads: if session untouched for >30 min,
        # any book still at DOWNLOADING is a crashed/timed-out download.
        stale_threshold = timedelta(minutes=30)
        now = datetime.now(UTC)
        session_age = now - session.updated_at
        if session_age > stale_threshold:
            for book in selected_books:
                if book.download_status == DownloadStatus.DOWNLOADING:
                    logger.warning(
                        "Auto-healing book %d ('%s'): stuck at DOWNLOADING for %s, marking FAILED",
                        book.id,
                        book.title,
                        session_age,
                    )
                    self.repo.update_download_result(
                        book.id,
                        DownloadStatus.FAILED,
                        error="Download timed out (background task likely crashed).",
                    )
                    book.download_status = DownloadStatus.FAILED

        if all(b.download_status in terminal_statuses for b in selected_books):
            logger.info(
                "Auto-healing session %d: all selected books resolved, transitioning to COMPLETED",
                session.id,
            )
            self.repo.update_progress(
                session.id,
                status=SessionStatus.COMPLETED,
                progress_scored=len(selected_books),
                progress_total=len(selected_books),
            )
            session.status = SessionStatus.COMPLETED

    def get_session(self, session_id: int) -> SessionRead | None:
        session = self.repo.get_session(session_id)
        if session is None:
            return None
        self._auto_heal_stuck_downloading(session)
        return SessionRead.model_validate(session)

    def get_latest_session(self, course_id: int) -> SessionRead | None:
        session = self.repo.get_latest_session(course_id)
        if session is None:
            return None
        self._auto_heal_stuck_downloading(session)
        return SessionRead.model_validate(session)

    def get_session_books(self, session_id: int) -> list[BookCandidateRead]:
        books = self.repo.get_books(session_id)
        return [BookCandidateRead.model_validate(b) for b in books]

    def get_course_books(self, course_id: int) -> list[BookCandidateRead]:
        books = self.repo.get_course_books(course_id)
        return [BookCandidateRead.model_validate(b) for b in books]

    # ── Discovery + Scoring (background task) ─────────────────────

    async def run_discovery_and_scoring(self, session_id: int) -> None:
        """Run LangGraph workflow in a background task, writing progress to DB.

        This replaces the old SSE-generator approach. The frontend polls
        GET /sessions/{id} to read status / progress_scored / progress_total.
        """
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            session = repo.get_session(session_id)
            if session is None:
                return

            weights_payload = (
                json.loads(session.weights_json) if session.weights_json else {}
            )
            core_weights, w_prac = _split_weights_payload(weights_payload)
            thread_id = session.thread_id
            course_id = session.course_id
            course_level = session.course_level

        workflow = await build_workflow()
        thread_config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "course_id": course_id,
            "course_level": course_level,
            "weights": core_weights,
            "w_prac": w_prac,
        }

        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            repo.update_progress(session_id, status=SessionStatus.DISCOVERING)

        try:
            scored_count = 0

            async for event in workflow.astream(
                initial_state, config=thread_config, stream_mode="updates"
            ):
                for node_name, state_update in event.items():
                    logger.info(
                        "Stream event node=%s keys=%s",
                        node_name,
                        list(state_update.keys())
                        if isinstance(state_update, dict)
                        else type(state_update).__name__,
                    )
                    if node_name == "discover_books":
                        discovered = state_update.get("discovered_books", [])
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            repo.save_discovered_books(session_id, discovered)
                            repo.update_progress(
                                session_id,
                                status=SessionStatus.SCORING,
                                progress_total=len(discovered),
                                progress_scored=0,
                            )
                    elif node_name == "score_book":
                        new_scores = state_update.get("scored_books", [])
                        # Insert each book immediately into course_books
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            for sb in new_scores:
                                repo.insert_scored_book(
                                    session_id=session_id,
                                    course_id=course_id,
                                    scored_book=sb,
                                )
                            scored_count += len(new_scores)
                            repo.update_progress(
                                session_id,
                                progress_scored=scored_count,
                            )
                    elif node_name == "__interrupt__":
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            repo.update_progress(
                                session_id,
                                status=SessionStatus.AWAITING_REVIEW,
                                progress_scored=scored_count,
                                progress_total=scored_count,
                            )
                        return

            # Completed without interrupt
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.AWAITING_REVIEW,
                    progress_scored=scored_count,
                    progress_total=scored_count,
                )

        except Exception as e:
            logger.exception("Workflow error in session %d", session_id)
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.FAILED,
                    error_message=_sanitize_error(e),
                )

    # ── Re-discover ────────────────────────────────────────────

    async def rediscover_books(self, session_id: int) -> None:
        """Clear previous results and re-run discovery + scoring from scratch.

        Useful when discovery returned 0 books (e.g. missing API keys) and
        the user wants to try again without creating a brand-new session.
        """
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            session = repo.get_session(session_id)
            if session is None:
                return

            if session.status not in (
                SessionStatus.AWAITING_REVIEW,
                SessionStatus.FAILED,
            ):
                return

            # Clear previous discovered books and scored books
            repo.save_discovered_books(session_id, [])
            from .models import CourseBook

            db.query(CourseBook).filter(
                CourseBook.session_id == session_id,
            ).delete(synchronize_session="fetch")

            # Generate a fresh thread so LangGraph starts clean
            new_thread_id = f"bs-{session.course_id}-rediscover-{uuid.uuid4().hex[:12]}"
            session.thread_id = new_thread_id
            db.commit()

        await self.run_discovery_and_scoring(session_id)

    # ── Selection + Download stream ─────────────────────────────

    async def resume_scoring(self, session_id: int) -> None:
        """Resume a failed/interrupted session from the scoring phase.

        Runs as a background task, writing progress to DB.
        """
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            session = repo.get_session(session_id)
            if session is None:
                return

            if not _can_resume_scoring(session.status):
                return

            discovered_books = repo.load_discovered_books(session_id)
            has_discovered_books = bool(discovered_books)

            weights_payload = (
                json.loads(session.weights_json) if session.weights_json else {}
            )
            core_weights, w_prac = _split_weights_payload(weights_payload)
            course_id = session.course_id
            course_level = session.course_level

        # If no discovered books yet, run the full workflow from scratch.
        if not has_discovered_books:
            await self.run_discovery_and_scoring(session_id)
            return

        # Create a NEW thread for this retry.
        new_thread_id = f"bs-{course_id}-retry-{uuid.uuid4().hex[:12]}"
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            s = repo.get_session(session_id)
            if s:
                s.thread_id = new_thread_id
                db.commit()
            from .models import CourseBook

            db.query(CourseBook).filter(
                CourseBook.session_id == session_id,
                CourseBook.s_final.isnot(None),
            ).delete(synchronize_session="fetch")
            db.commit()

        from .book_selection.nodes import fetch_course as _fc

        await build_workflow()
        thread_config = {"configurable": {"thread_id": new_thread_id}}

        course_ctx_state = _fc(
            {
                "course_id": course_id,
                "course_level": course_level,
            }
        )

        initial_state = {
            "course_id": course_id,
            "course_level": course_ctx_state.get("course_level", course_level),
            "course_context": course_ctx_state.get("course_context", {}),
            "weights": core_weights,
            "w_prac": w_prac,
            "discovered_books": discovered_books,
        }

        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            repo.update_progress(
                session_id,
                status=SessionStatus.SCORING,
                progress_total=len(discovered_books),
                progress_scored=0,
                error_message="",
            )

        try:
            scored_count = 0

            from langgraph.graph import END, START, StateGraph

            from .book_selection.graph import _get_async_checkpointer
            from .book_selection.nodes import (
                download_book_node as _dbn,
            )
            from .book_selection.nodes import (
                fan_out_downloads as _fod,
            )
            from .book_selection.nodes import (
                fan_out_scoring as _fos,
            )
            from .book_selection.nodes import (
                hitl_review as _hr,
            )
            from .book_selection.nodes import (
                score_book_node as _sbn,
            )
            from .book_selection.state import WorkflowState

            async_checkpointer = await _get_async_checkpointer()

            builder = StateGraph(WorkflowState)
            builder.add_node("score_book", _sbn)
            builder.add_node("hitl_review", _hr)
            builder.add_node("download_book", _dbn)
            builder.add_conditional_edges(START, _fos)
            builder.add_edge("score_book", "hitl_review")
            builder.add_conditional_edges("hitl_review", _fod)
            builder.add_edge("download_book", END)

            resume_workflow = builder.compile(checkpointer=async_checkpointer)

            async for event in resume_workflow.astream(
                initial_state, config=thread_config, stream_mode="updates"
            ):
                for node_name, state_update in event.items():
                    logger.info(
                        "Resume stream event node=%s keys=%s",
                        node_name,
                        list(state_update.keys())
                        if isinstance(state_update, dict)
                        else type(state_update).__name__,
                    )
                    if node_name == "score_book":
                        new_scores = state_update.get("scored_books", [])
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            for sb in new_scores:
                                repo.insert_scored_book(
                                    session_id=session_id,
                                    course_id=course_id,
                                    scored_book=sb,
                                )
                            scored_count += len(new_scores)
                            repo.update_progress(
                                session_id,
                                progress_scored=scored_count,
                            )
                    elif node_name == "__interrupt__":
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            repo.update_progress(
                                session_id,
                                status=SessionStatus.AWAITING_REVIEW,
                                progress_scored=scored_count,
                                progress_total=scored_count,
                            )
                        return

            # Completed without interrupt
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.AWAITING_REVIEW,
                    progress_scored=scored_count,
                    progress_total=scored_count,
                )

        except Exception as e:
            logger.exception("Resume scoring error in session %d", session_id)
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.FAILED,
                    error_message=_sanitize_error(e),
                )

    # ── Selection + Download (background task) ───────────────────

    async def run_select_and_download(
        self,
        session_id: int,
        selected_book_ids: list[int],
    ) -> None:
        """Mark selected books, search for PDFs via Serper, stream to Azure.

        For each book:
        1. Query Serper with "<title> <authors> pdf download"
        2. Pick the first organic result whose link ends with .pdf
        3. Stream-download the PDF directly into Azure Blob Storage
        4. Create a CourseSelectedBook record with the blob URL

        If no PDF is found or the download fails, the book is marked FAILED
        with the source URL (if any) so the teacher can download manually.

        Progress is written to DB; frontend polls GET /sessions/{id}.
        """
        from langchain_community.utilities import GoogleSerperAPIWrapper

        from app.core.settings import settings

        # ── Validate & prepare ──────────────────────────────────
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            session = repo.get_session(session_id)
            if session is None:
                return

            if len(selected_book_ids) > 5:
                repo.update_progress(
                    session_id,
                    status=SessionStatus.FAILED,
                    error_message="Cannot select more than 5 books",
                )
                return

            repo.mark_selected(session_id, selected_book_ids)

            selected_rows = [
                b for b in repo.get_books(session_id) if b.id in selected_book_ids
            ]
            books_snapshot = [
                {
                    "id": b.id,
                    "title": b.title,
                    "authors": b.authors or "",
                    "publisher": b.publisher,
                    "year": b.year,
                    "course_id": b.course_id,
                }
                for b in selected_rows
            ]
            course_id = session.course_id

        total = len(books_snapshot)
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            repo.update_progress(
                session_id,
                status=SessionStatus.DOWNLOADING,
                progress_scored=0,
                progress_total=total,
            )
            for book in books_snapshot:
                repo.update_download_result(book["id"], DownloadStatus.DOWNLOADING)

        # ── Process each book sequentially ──────────────────────
        MAX_PDF_ATTEMPTS = 4
        download_count = 0
        serper = GoogleSerperAPIWrapper(
            serper_api_key=settings.serper_api_key,
            k=10,
            type="search",
        )

        try:
            for book in books_snapshot:
                book_id = book["id"]
                title = book["title"]
                authors = book["authors"]
                search_query = f"{title} {authors} pdf download".strip()

                # Search Google via Serper and collect all .pdf links
                pdf_urls: list[str] = []
                try:
                    data: dict = await serper.aresults(search_query)
                    for item in data.get("organic", []):
                        link: str = item.get("link", "")
                        if link.lower().endswith(".pdf"):
                            pdf_urls.append(link)
                except Exception as search_exc:
                    logger.error("Serper search failed for '%s': %s", title, search_exc)

                if not pdf_urls:
                    # No PDF found — mark as failed
                    with _fresh_db() as db:
                        repo = BookSelectionRepository(db)
                        repo.update_download_result(
                            book_id,
                            DownloadStatus.FAILED,
                            error=(
                                "No PDF link found via search. Please upload manually."
                            ),
                        )
                        repo.create_selected_book(
                            course_id=course_id,
                            title=title,
                            authors=authors or None,
                            publisher=book.get("publisher"),
                            year=book.get("year"),
                            status=BookStatus.FAILED,
                            error_message=(
                                "No PDF link found via search. Please upload manually."
                            ),
                            source_book_id=book_id,
                        )
                    download_count += 1
                    with _fresh_db() as db:
                        BookSelectionRepository(db).update_progress(
                            session_id, progress_scored=download_count
                        )
                    continue

                # ── Try up to MAX_PDF_ATTEMPTS URLs ─────────────
                blob_path = f"courses/{course_id}/books/{_safe_filename(title)}.pdf"
                book_downloaded = False
                rejection_log: list[str] = []

                for attempt_idx, pdf_url in enumerate(pdf_urls[:MAX_PDF_ATTEMPTS]):
                    try:
                        import contextlib as _ctxlib
                        import os as _os
                        import tempfile

                        import httpx

                        from .book_selection.tools import validate_pdf

                        tmp_path: str | None = None
                        try:
                            async with httpx.AsyncClient(
                                follow_redirects=True, timeout=120.0
                            ) as client:
                                resp = await client.get(pdf_url)
                                resp.raise_for_status()
                                pdf_bytes = resp.content

                            with tempfile.NamedTemporaryFile(
                                suffix=".pdf", delete=False
                            ) as tmp:
                                tmp.write(pdf_bytes)
                                tmp_path = tmp.name

                            vr = validate_pdf(tmp_path, expected_title=title)
                            if not vr.valid:
                                reason = vr.rejection_reason
                                logger.warning(
                                    "PDF rejected for '%s' (attempt %d/%d) from %s: %s",
                                    title,
                                    attempt_idx + 1,
                                    min(len(pdf_urls), MAX_PDF_ATTEMPTS),
                                    pdf_url,
                                    reason,
                                )
                                rejection_log.append(
                                    f"Attempt {attempt_idx + 1}: {reason} "
                                    f"(source: {pdf_url})"
                                )
                                continue  # try next URL

                            # Valid — upload bytes to Azure
                            blob_url = await self.blob_service.upload_bytes(
                                pdf_bytes, blob_path
                            )
                            logger.info(
                                "PDF validated for '%s' (%d pages) from %s",
                                title,
                                vr.page_count,
                                pdf_url,
                            )
                        finally:
                            if tmp_path:
                                with _ctxlib.suppress(OSError):
                                    _os.remove(tmp_path)

                        # Success — persist to DB
                        with _fresh_db() as db:
                            repo = BookSelectionRepository(db)
                            repo.update_download_result(
                                book_id,
                                DownloadStatus.SUCCESS,
                                blob_path=blob_path,
                                source_url=pdf_url,
                            )
                            repo.create_selected_book(
                                course_id=course_id,
                                title=title,
                                authors=authors or None,
                                publisher=book.get("publisher"),
                                year=book.get("year"),
                                status=BookStatus.DOWNLOADED,
                                blob_path=blob_path,
                                blob_url=blob_url,
                                source_book_id=book_id,
                            )
                        book_downloaded = True
                        break

                    except Exception as dl_exc:
                        logger.warning(
                            "Download attempt %d failed for '%s' from %s: %s",
                            attempt_idx + 1,
                            title,
                            pdf_url,
                            dl_exc,
                        )
                        rejection_log.append(
                            f"Attempt {attempt_idx + 1}: Download error: "
                            f"{dl_exc} (source: {pdf_url})"
                        )

                if not book_downloaded:
                    # All attempts exhausted — mark as failed
                    attempts_tried = min(len(pdf_urls), MAX_PDF_ATTEMPTS)
                    summary = "; ".join(rejection_log) if rejection_log else ""
                    error_msg = (
                        f"Tried {attempts_tried} PDF source(s), "
                        f"none were valid. {summary} "
                        f"Please find and upload a valid PDF manually."
                    )
                    with _fresh_db() as db:
                        repo = BookSelectionRepository(db)
                        repo.update_download_result(
                            book_id,
                            DownloadStatus.FAILED,
                            error=error_msg,
                            source_url=pdf_urls[0] if pdf_urls else None,
                        )
                        repo.create_selected_book(
                            course_id=course_id,
                            title=title,
                            authors=authors or None,
                            publisher=book.get("publisher"),
                            year=book.get("year"),
                            status=BookStatus.FAILED,
                            error_message=error_msg,
                            source_book_id=book_id,
                        )

                download_count += 1
                with _fresh_db() as db:
                    BookSelectionRepository(db).update_progress(
                        session_id, progress_scored=download_count
                    )

            # ── Finalize session ────────────────────────────────
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.COMPLETED,
                    progress_scored=download_count,
                    progress_total=total,
                )

        except Exception as e:
            logger.exception("Download error in session %d", session_id)
            with _fresh_db() as db:
                repo = BookSelectionRepository(db)
                repo.update_progress(
                    session_id,
                    status=SessionStatus.FAILED,
                    error_message=_sanitize_error(e),
                )

    # ── Manual upload ───────────────────────────────────────────

    async def upload_book_manually(
        self,
        session_id: int,
        book_id: int,
        file: UploadFile,
    ) -> ManualUploadResponse:
        """Upload a book file manually for a failed download."""
        book = self.repo.get_book(book_id)
        if book is None:
            raise ValueError(f"Book {book_id} not found")

        blob_path = f"courses/{book.course_id}/books/{_safe_filename(book.title)}.pdf"

        blob_url = await self.blob_service.upload_file(file, blob_path)
        self.repo.update_download_result(
            book_id,
            DownloadStatus.MANUAL_UPLOAD,
            blob_path=blob_path,
        )

        # Update or create the course_selected_books entry
        selected = self.repo.get_selected_book_by_source(book_id)
        if selected:
            self.repo.update_selected_book_status(
                selected.id,
                BookStatus.UPLOADED,
                blob_path=blob_path,
                blob_url=blob_url,
            )
        else:
            self.repo.create_selected_book(
                course_id=book.course_id,
                title=book.title,
                authors=book.authors,
                publisher=book.publisher,
                year=book.year,
                status=BookStatus.UPLOADED,
                blob_path=blob_path,
                blob_url=blob_url,
                source_book_id=book_id,
            )

        return ManualUploadResponse(book_id=book_id, blob_path=blob_path)

    async def upload_custom_book(
        self,
        course_id: int,
        file: UploadFile,
        title: str,
        authors: str | None = None,
    ) -> BookCandidateRead:
        """Upload a book not from the agent (teacher's own choice)."""
        if self.repo.book_exists_for_course(course_id, title):
            raise ValueError(f'A book titled "{title}" already exists for this course.')

        blob_path = f"courses/{course_id}/books/{_safe_filename(title)}.pdf"
        blob_url = await self.blob_service.upload_file(file, blob_path)

        # Get latest session ID if any
        latest = self.repo.get_latest_session(course_id)
        session_id = latest.id if latest else 0

        book = self.repo.create_manual_book(
            course_id=course_id,
            session_id=session_id,
            title=title,
            authors=authors,
            blob_path=blob_path,
        )

        # Also create in course_selected_books
        self.repo.create_selected_book(
            course_id=course_id,
            title=title,
            authors=authors,
            status=BookStatus.UPLOADED,
            blob_path=blob_path,
            blob_url=blob_url,
            source_book_id=book.id,
        )

        return BookCandidateRead.model_validate(book)

    # ── Course Selected Books ───────────────────────────────────

    def get_course_selected_books(self, course_id: int) -> list[CourseSelectedBookRead]:
        """Get all selected books for a course."""
        books = self.repo.get_course_selected_books(course_id)
        return [CourseSelectedBookRead.model_validate(b) for b in books]

    async def reselect_books(self, session_id: int) -> None:
        """Delete all selected books, their analysis data, and blobs.

        Resets the session back to awaiting_review so the teacher can
        re-select books from the scored candidates.
        """
        with _fresh_db() as db:
            repo = BookSelectionRepository(db)
            session = repo.get_session(session_id)
            if session is None:
                return

            course_id = session.course_id

            # Collect blob paths before deleting rows
            deleted_books = repo.delete_all_selected_books_for_course(course_id)
            blob_paths = [b.blob_path for b in deleted_books if b.blob_path]

            # Reset session back to review
            repo.update_status(session_id, SessionStatus.AWAITING_REVIEW)

        # Delete blobs outside the DB transaction
        for path in blob_paths:
            try:
                await self.blob_service.delete_file(path)
            except Exception:
                logger.warning("Failed to delete blob %s", path, exc_info=True)

    def ignore_selected_book(self, selected_book_id: int) -> CourseSelectedBookRead:
        """Mark a selected book as ignored so it is skipped."""
        book = self.repo.get_selected_book(selected_book_id)
        if book is None:
            raise ValueError(f"Selected book {selected_book_id} not found")
        updated = self.repo.update_selected_book_status(
            selected_book_id, BookStatus.IGNORED
        )
        return CourseSelectedBookRead.model_validate(updated)

    async def upload_to_selected_book(
        self,
        selected_book_id: int,
        file: UploadFile,
    ) -> SelectedBookManualUploadResponse:
        """Upload a PDF for a failed selected book."""
        book = self.repo.get_selected_book(selected_book_id)
        if book is None:
            raise ValueError(f"Selected book {selected_book_id} not found")

        blob_path = f"courses/{book.course_id}/books/{_safe_filename(book.title)}.pdf"
        blob_url = await self.blob_service.upload_file(file, blob_path)

        self.repo.update_selected_book_status(
            selected_book_id,
            BookStatus.UPLOADED,
            blob_path=blob_path,
            blob_url=blob_url,
        )

        # Also update the source CourseBook if it exists
        if book.source_book_id:
            self.repo.update_download_result(
                book.source_book_id,
                DownloadStatus.MANUAL_UPLOAD,
                blob_path=blob_path,
            )

        return SelectedBookManualUploadResponse(
            id=selected_book_id,
            blob_path=blob_path,
            blob_url=blob_url,
            status=BookStatus.UPLOADED,
        )

    async def upload_custom_selected_book(
        self,
        course_id: int,
        file: UploadFile,
        title: str,
        authors: str | None = None,
    ) -> CourseSelectedBookRead:
        """Upload a custom book directly to course_selected_books."""
        if self.repo.selected_book_exists_for_course(course_id, title):
            raise ValueError(f'A book titled "{title}" already exists for this course.')

        blob_path = f"courses/{course_id}/books/{_safe_filename(title)}.pdf"
        blob_url = await self.blob_service.upload_file(file, blob_path)

        book = self.repo.create_selected_book(
            course_id=course_id,
            title=title,
            authors=authors,
            status=BookStatus.UPLOADED,
            blob_path=blob_path,
            blob_url=blob_url,
        )

        return CourseSelectedBookRead.model_validate(book)


def _safe_filename(title: str) -> str:
    """Sanitize a book title for use as a filename."""
    safe = re.sub(r"[^\w\s-]", "", title.strip())
    safe = re.sub(r"\s+", "_", safe)[:80] or "book"
    return safe


def get_book_selection_service(db: Session) -> BookSelectionService:
    """Factory: create a BookSelectionService with all dependencies."""
    from app.providers.storage import blob_service

    repo = BookSelectionRepository(db)
    return BookSelectionService(repo=repo, blob_service=blob_service)
