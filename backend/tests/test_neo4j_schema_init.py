from __future__ import annotations

import logging

from neo4j.exceptions import Neo4jError

from app.core.neo4j import initialize_neo4j_constraints


class _Consumed:
    def consume(self):
        return None


class _FakeNeo4jSession:
    def __init__(self):
        self.statements: list[str] = []

    def run(self, stmt: str):
        s = stmt.strip()
        self.statements.append(s)
        if "FOR ()-[m:MENTIONS]-()" in s and "CREATE VECTOR INDEX" in s:
            raise Neo4jError("relationship vector indexes not supported")
        return _Consumed()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def __init__(self):
        self.session_obj = _FakeNeo4jSession()

    def session(self, *, database: str):
        return self.session_obj


def test_initialize_neo4j_constraints_idempotent_and_relationship_fallback(caplog):
    caplog.set_level(logging.WARNING)

    driver = _FakeDriver()

    initialize_neo4j_constraints(driver)  # type: ignore[arg-type]
    initialize_neo4j_constraints(driver)  # type: ignore[arg-type]

    # Should have attempted node vector index creation.
    assert any(
        s.startswith(
            "CREATE VECTOR INDEX teacher_uploaded_document_embedding_vector_idx"
        )
        for s in driver.session_obj.statements
    )

    # Relationship vector index failures should be swallowed and logged as warnings.
    assert any(
        "relationship vector index" in rec.message.lower() for rec in caplog.records
    )
