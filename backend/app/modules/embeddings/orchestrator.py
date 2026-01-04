from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from neo4j import Session as Neo4jSession
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.modules.document_extraction.neo4j_repository import (
    DocumentExtractionGraphRepository,
    MentionInput,
)

from .embedding_service import EmbeddingService
from .repository import DocumentEmbeddingStateRepository

logger = logging.getLogger(__name__)


def _compute_embedding_input_hash(
    *, document_text: str, mentions: Sequence[MentionInput]
) -> str:
    mention_items: list[tuple[str, str, str]] = []
    for m in mentions:
        concept = (m.name or "").strip().casefold()
        mention_items.append((concept, "definition", m.definition or ""))
        mention_items.append((concept, "text_evidence", m.text_evidence or ""))

    mention_items.sort(key=lambda t: (t[0], t[1]))

    payload = {
        "document_text": document_text or "",
        "mentions": mention_items,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


class EmbeddingOrchestrator:
    _db: Session
    _neo4j_session: Neo4jSession
    _state_repo: DocumentEmbeddingStateRepository
    _graph_repo: DocumentExtractionGraphRepository
    _embedding_service: EmbeddingService | None

    def __init__(
        self,
        *,
        db: Session,
        neo4j_session: Neo4jSession,
        state_repo: DocumentEmbeddingStateRepository | None = None,
        graph_repo: DocumentExtractionGraphRepository | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._db = db
        self._neo4j_session = neo4j_session
        self._state_repo = state_repo or DocumentEmbeddingStateRepository(db)
        self._graph_repo = graph_repo or DocumentExtractionGraphRepository(
            neo4j_session
        )
        self._embedding_service = embedding_service

    def embed_document_and_mentions(
        self,
        *,
        document_id: str,
        course_id: int | None,
        content_hash: str | None,
        document_text: str,
        mentions: Sequence[MentionInput],
    ) -> bool:
        """Returns True when embeddings were generated+written, False when skipped."""

        embedding_input_hash = _compute_embedding_input_hash(
            document_text=document_text, mentions=mentions
        )
        expected_dim = settings.embedding_dims
        model = settings.embedding_model

        if self._state_repo.should_skip(
            document_id=document_id,
            embedding_input_hash=embedding_input_hash,
            embedding_model=model,
            expected_dim=expected_dim,
        ):
            return False

        # Mark state before doing any remote work.
        self._state_repo.upsert_in_progress(
            document_id=document_id,
            course_id=course_id,
            content_hash=content_hash,
            embedding_input_hash=embedding_input_hash,
            embedding_model=model,
            embedding_dim=expected_dim,
        )

        try:
            vectors, actual_dim = self._embed_all(
                document_text=document_text, mentions=mentions
            )

            self._graph_repo.set_document_embedding(
                document_id=document_id, vector=vectors[0]
            )

            offset = 1
            for m in mentions:
                concept_name = (m.name or "").strip().casefold()
                def_vec = vectors[offset]
                ev_vec = vectors[offset + 1]
                offset += 2

                self._graph_repo.set_mentions_embeddings(
                    document_id=document_id,
                    concept_name=concept_name,
                    definition_embedding=def_vec,
                    text_evidence_embedding=ev_vec,
                )

            self._state_repo.mark_completed(
                document_id=document_id,
                embedding_dim=actual_dim,
                embedded_at=datetime.now(UTC),
            )
            return True

        except Exception as e:
            logger.exception(
                "Embedding orchestration failed for document %s (course_id=%s)",
                document_id,
                course_id,
            )
            try:
                self._state_repo.mark_failed(document_id=document_id, error=str(e))
            except Exception:
                logger.exception(
                    "Failed to persist embedding failure state for document %s",
                    document_id,
                )
            raise

    def _embed_all(
        self, *, document_text: str, mentions: Sequence[MentionInput]
    ) -> tuple[list[list[float]], int]:
        texts: list[str] = [document_text or ""]
        for m in mentions:
            texts.append(m.definition or "")
            texts.append(m.text_evidence or "")

        embedding_service = self._embedding_service or EmbeddingService()
        vectors = embedding_service.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ValueError(
                f"Embedding count mismatch: expected {len(texts)}, got {len(vectors)}"
            )

        dim = len(vectors[0]) if vectors else 0
        for v in vectors:
            if len(v) != dim:
                raise ValueError("Embedding vectors have inconsistent dimensions")

        expected_dim = settings.embedding_dims
        if expected_dim is not None and dim != expected_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {expected_dim}, got {dim}"
            )

        return vectors, dim
