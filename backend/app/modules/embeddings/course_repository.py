from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from .course_models import CourseEmbeddingState, CourseEmbeddingStatus


class CourseEmbeddingStateRepository:
    _db: Session

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, *, course_id: int) -> CourseEmbeddingState | None:
        return self._db.get(CourseEmbeddingState, course_id)

    def mark_in_progress(self, *, course_id: int) -> CourseEmbeddingState:
        state = self.get(course_id=course_id)
        if state is None:
            state = CourseEmbeddingState(course_id=course_id)
            self._db.add(state)

        state.status = CourseEmbeddingStatus.IN_PROGRESS
        state.started_at = datetime.now(UTC)
        state.finished_at = None
        state.last_error = None

        self._db.commit()
        self._db.refresh(state)
        return state

    def mark_completed(self, *, course_id: int) -> CourseEmbeddingState:
        state = self.get(course_id=course_id)
        if state is None:
            state = CourseEmbeddingState(course_id=course_id)
            self._db.add(state)

        state.status = CourseEmbeddingStatus.COMPLETED
        if state.started_at is None:
            state.started_at = datetime.now(UTC)
        state.finished_at = datetime.now(UTC)
        state.last_error = None

        self._db.commit()
        self._db.refresh(state)
        return state

    def mark_failed(self, *, course_id: int, error: str) -> CourseEmbeddingState:
        state = self.get(course_id=course_id)
        if state is None:
            state = CourseEmbeddingState(course_id=course_id)
            self._db.add(state)

        state.status = CourseEmbeddingStatus.FAILED
        if state.started_at is None:
            state.started_at = datetime.now(UTC)
        state.finished_at = datetime.now(UTC)
        state.last_error = (error or "Embedding failed")[:4000]

        self._db.commit()
        self._db.refresh(state)
        return state
