from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DocumentEmbeddingState, EmbeddingStatus


class DocumentEmbeddingStateRepository:
    _db: Session

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, *, document_id: str) -> DocumentEmbeddingState | None:
        return self._db.get(DocumentEmbeddingState, document_id)

    def upsert_in_progress(
        self,
        *,
        document_id: str,
        course_id: int | None,
        content_hash: str | None,
        embedding_input_hash: str,
        embedding_model: str,
        embedding_dim: int | None,
    ) -> DocumentEmbeddingState:
        state = self.get(document_id=document_id)
        if state is None:
            state = DocumentEmbeddingState(document_id=document_id)
            self._db.add(state)

        state.course_id = course_id
        state.content_hash = content_hash
        state.embedding_status = EmbeddingStatus.IN_PROGRESS
        state.embedding_input_hash = embedding_input_hash
        state.embedding_model = embedding_model
        state.embedding_dim = embedding_dim
        state.embedded_at = None
        state.last_error = None

        self._db.commit()
        self._db.refresh(state)
        return state

    def mark_completed(
        self,
        *,
        document_id: str,
        embedding_dim: int,
        embedded_at: datetime | None = None,
    ) -> DocumentEmbeddingState:
        state = self.get(document_id=document_id)
        if state is None:
            state = DocumentEmbeddingState(document_id=document_id)
            self._db.add(state)

        state.embedding_status = EmbeddingStatus.COMPLETED
        state.embedding_dim = embedding_dim
        state.embedded_at = embedded_at or datetime.now(UTC)
        state.last_error = None

        self._db.commit()
        self._db.refresh(state)
        return state

    def mark_failed(self, *, document_id: str, error: str) -> DocumentEmbeddingState:
        state = self.get(document_id=document_id)
        if state is None:
            state = DocumentEmbeddingState(document_id=document_id)
            self._db.add(state)

        state.embedding_status = EmbeddingStatus.FAILED
        state.last_error = (error or "Embedding failed")[:4000]

        self._db.commit()
        self._db.refresh(state)
        return state

    def should_skip(
        self,
        *,
        document_id: str,
        embedding_input_hash: str,
        embedding_model: str,
        expected_dim: int | None,
    ) -> bool:
        state = self.get(document_id=document_id)
        if state is None:
            return False

        return (
            state.embedding_status == EmbeddingStatus.COMPLETED
            and (state.embedding_input_hash or "") == embedding_input_hash
            and (state.embedding_model or "") == embedding_model
            and (expected_dim is None or state.embedding_dim == expected_dim)
        )

    def list_by_course_id(self, *, course_id: int) -> list[DocumentEmbeddingState]:
        return list(
            self._db.scalars(
                select(DocumentEmbeddingState).where(
                    DocumentEmbeddingState.course_id == course_id
                )
            ).all()
        )
