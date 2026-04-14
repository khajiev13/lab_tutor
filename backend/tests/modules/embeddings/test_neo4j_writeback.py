from __future__ import annotations

from dataclasses import dataclass

from app.modules.document_extraction.neo4j_repository import (
    SET_DOCUMENT_EMBEDDING,
    SET_MENTIONS_EMBEDDINGS,
    DocumentExtractionGraphRepository,
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


def test_sets_document_embedding_and_mentions_embeddings():
    fake = _FakeNeo4jSession()
    repo = DocumentExtractionGraphRepository(fake)  # type: ignore[arg-type]

    repo.set_document_embedding(document_id="doc_1", vector=[0.0, 1.0])
    repo.set_mentions_embeddings(
        document_id="doc_1",
        concept_name="SQL",
        definition_embedding=[0.1, 0.2],
        text_evidence_embedding=[0.3, 0.4],
    )

    assert len(fake.runs) == 2
    (q1, p1), (q2, p2) = fake.runs

    assert q1 == SET_DOCUMENT_EMBEDDING.strip()
    assert p1 == {"document_id": "doc_1", "vector": [0.0, 1.0]}

    assert q2 == SET_MENTIONS_EMBEDDINGS.strip()
    assert p2["document_id"] == "doc_1"
    assert p2["concept_name"] == "sql"  # normalized
    assert p2["definition_embedding"] == [0.1, 0.2]
    assert p2["text_evidence_embedding"] == [0.3, 0.4]
