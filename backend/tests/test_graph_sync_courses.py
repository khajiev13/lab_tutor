from __future__ import annotations

from dataclasses import dataclass

from app.core.neo4j import get_neo4j_session
from app.modules.courses.neo4j_repository import (
    LINK_STUDENT_ENROLLED,
    LINK_TEACHER_TEACHES_CLASS,
    UNLINK_STUDENT_ENROLLED,
    UPSERT_CLASS,
)
from app.modules.document_extraction.neo4j_repository import (
    DELETE_DOCUMENTS_BY_COURSE_AND_ORPHAN_CONCEPTS,
    DocumentExtractionGraphRepository,
)
from main import app


@dataclass
class _Consumed:
    def consume(self):
        return None

    def single(self):
        return None


@dataclass
class _SingleRecord:
    record: dict

    def consume(self):
        return None

    def single(self):
        return self.record


class FakeNeo4jTx:
    def __init__(self, runs: list[tuple[str, dict]]):
        self._runs = runs

    def run(self, query: str, params: dict):
        self._runs.append((query.strip(), params))
        # Some repos use `.consume()` (course graph sync), others use `.single()`
        # (document-extraction deletes). Provide both in a minimal way.
        if "RETURN documents_deleted" in query:
            return _SingleRecord({"documents_deleted": 0, "concepts_deleted": 0})
        return _Consumed()


class FakeNeo4jSession:
    def __init__(self):
        self.runs: list[tuple[str, dict]] = []

    def execute_write(self, fn):
        tx = FakeNeo4jTx(self.runs)
        return fn(tx)


def test_course_create_and_enrollment_sync_to_neo4j(
    client,
    teacher_auth_headers,
    student_auth_headers,
):
    fake_session = FakeNeo4jSession()

    def override_get_neo4j_session():
        yield fake_session

    app.dependency_overrides[get_neo4j_session] = override_get_neo4j_session
    try:
        # Create course (teacher)
        resp = client.post(
            "/courses",
            headers=teacher_auth_headers,
            json={"title": "Neo4j 101", "description": "Intro"},
        )
        assert resp.status_code == 201
        course_id = resp.json()["id"]

        # Join course (student)
        resp = client.post(
            f"/courses/{course_id}/join",
            headers=student_auth_headers,
        )
        assert resp.status_code == 201

        # Leave course (student)
        resp = client.delete(
            f"/courses/{course_id}/leave",
            headers=student_auth_headers,
        )
        assert resp.status_code == 204

        queries = [q for (q, _p) in fake_session.runs]
        assert any(q == UPSERT_CLASS.strip() for q in queries)
        assert any(q == LINK_TEACHER_TEACHES_CLASS.strip() for q in queries)
        assert any(q == LINK_STUDENT_ENROLLED.strip() for q in queries)
        assert any(q == UNLINK_STUDENT_ENROLLED.strip() for q in queries)
    finally:
        app.dependency_overrides.pop(get_neo4j_session, None)


def test_document_extraction_delete_documents_query_keeps_documents_deleted_in_scope():
    """Regression test for Cypher scoping: documents_deleted must be defined + returned."""
    fake_session = FakeNeo4jSession()
    repo = DocumentExtractionGraphRepository(fake_session)  # type: ignore[arg-type]

    # This should execute exactly one write query.
    repo.delete_documents_by_course_and_orphan_concepts(course_id=123)

    assert len(fake_session.runs) == 1
    query, params = fake_session.runs[0]
    assert query == DELETE_DOCUMENTS_BY_COURSE_AND_ORPHAN_CONCEPTS.strip()
    assert params == {"course_id": 123}

    # Sanity: ensure the query defines and returns the variable.
    assert "AS documents_deleted" in query
    assert "RETURN documents_deleted" in query
