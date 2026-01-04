from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.core.settings import settings
from app.modules.document_extraction.neo4j_repository import MentionInput
from app.modules.embeddings.models import DocumentEmbeddingState, EmbeddingStatus
from app.modules.embeddings.orchestrator import (
    EmbeddingOrchestrator,
    _compute_embedding_input_hash,
)


@dataclass
class _Consumed:
    def consume(self):
        return None

    def single(self):
        return None


class _FakeNeo4jTx:
    def __init__(self, runs: list[tuple[str, dict]]):
        self._runs = runs

    def run(self, query: str, params: dict):
        self._runs.append((query.strip(), params))
        return _Consumed()


class _FakeNeo4jSession:
    def __init__(self):
        self.runs: list[tuple[str, dict]] = []

    def execute_write(self, fn):
        tx = _FakeNeo4jTx(self.runs)
        return fn(tx)


class _FakeEmbeddingService:
    def __init__(self, *, dims: int, fail: bool = False):
        self.dims = dims
        self.fail = fail
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("boom")
        # deterministic dummy vectors
        return [[0.0] * self.dims for _ in texts]


def _mentions() -> list[MentionInput]:
    return [
        MentionInput(
            name="big data",
            original_name="Big Data",
            definition="a thing",
            text_evidence="the thing",
            source_document="file.txt",
        ),
        MentionInput(
            name="sql",
            original_name="SQL",
            definition="structured query language",
            text_evidence="SELECT 1",
            source_document="file.txt",
        ),
    ]


def test_orchestrator_skips_when_completed_same_hash(db_session):
    fake_neo4j = _FakeNeo4jSession()
    fake_embed = _FakeEmbeddingService(dims=settings.embedding_dims or 3)

    document_text = "hello"
    mentions = _mentions()

    h = _compute_embedding_input_hash(document_text=document_text, mentions=mentions)
    state = DocumentEmbeddingState(
        document_id="doc_1",
        course_id=1,
        content_hash="abc",
        embedding_status=EmbeddingStatus.COMPLETED,
        embedding_input_hash=h,
        embedding_model=settings.embedding_model,
        embedding_dim=settings.embedding_dims,
        embedded_at=datetime.now(UTC),
        last_error=None,
    )
    db_session.add(state)
    db_session.commit()

    orchestrator = EmbeddingOrchestrator(
        db=db_session,
        neo4j_session=fake_neo4j,  # type: ignore[arg-type]
        embedding_service=fake_embed,
    )

    did_embed = orchestrator.embed_document_and_mentions(
        document_id="doc_1",
        course_id=1,
        content_hash="abc",
        document_text=document_text,
        mentions=mentions,
    )

    assert did_embed is False
    assert fake_embed.calls == []
    assert fake_neo4j.runs == []


def test_orchestrator_reruns_when_hash_changes(db_session):
    fake_neo4j = _FakeNeo4jSession()
    fake_embed = _FakeEmbeddingService(dims=settings.embedding_dims or 3)

    # Persist a completed state with a different hash.
    db_session.add(
        DocumentEmbeddingState(
            document_id="doc_2",
            embedding_status=EmbeddingStatus.COMPLETED,
            embedding_input_hash="old",
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dims,
            embedded_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    document_text = "hello2"
    mentions = _mentions()

    orchestrator = EmbeddingOrchestrator(
        db=db_session,
        neo4j_session=fake_neo4j,  # type: ignore[arg-type]
        embedding_service=fake_embed,
    )

    did_embed = orchestrator.embed_document_and_mentions(
        document_id="doc_2",
        course_id=1,
        content_hash="def",
        document_text=document_text,
        mentions=mentions,
    )

    assert did_embed is True
    assert len(fake_embed.calls) == 1

    # 1 doc vector + 2 per mention
    assert len(fake_neo4j.runs) == 1 + len(mentions)

    refreshed = db_session.get(DocumentEmbeddingState, "doc_2")
    assert refreshed is not None
    assert refreshed.embedding_status == EmbeddingStatus.COMPLETED
    assert refreshed.last_error is None


def test_orchestrator_marks_failed_and_raises(db_session):
    fake_neo4j = _FakeNeo4jSession()
    fake_embed = _FakeEmbeddingService(dims=settings.embedding_dims or 3, fail=True)

    orchestrator = EmbeddingOrchestrator(
        db=db_session,
        neo4j_session=fake_neo4j,  # type: ignore[arg-type]
        embedding_service=fake_embed,
    )

    with pytest.raises(RuntimeError):
        orchestrator.embed_document_and_mentions(
            document_id="doc_3",
            course_id=1,
            content_hash="ghi",
            document_text="hello",
            mentions=_mentions(),
        )

    state = db_session.get(DocumentEmbeddingState, "doc_3")
    assert state is not None
    assert state.embedding_status == EmbeddingStatus.FAILED
    assert state.last_error is not None
