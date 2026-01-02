from __future__ import annotations

from typing import Any

from app.core.neo4j import require_neo4j_session
from app.modules.courses.graph_schemas import CourseGraphResponse, GraphEdge, GraphNode
from main import app


def test_get_course_graph_returns_503_when_neo4j_disabled(client, teacher_auth_headers):
    create_res = client.post(
        "/courses",
        json={"title": "Graph Course", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    res = client.get(f"/courses/{course_id}/graph", headers=teacher_auth_headers)
    assert res.status_code == 503
    assert "Neo4j is not configured" in res.json()["detail"]


def test_get_course_graph_happy_path_with_overrides(
    client, teacher_auth_headers, monkeypatch
):
    # Create a course owned by the teacher.
    create_res = client.post(
        "/courses",
        json={"title": "Graph Course", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    def _override_neo4j_session():
        yield object()

    app.dependency_overrides[require_neo4j_session] = _override_neo4j_session

    def _fake_snapshot(self, *, course_id: int, max_documents: int, max_concepts: int):
        return CourseGraphResponse(
            nodes=[
                GraphNode(
                    id=f"class_{course_id}",
                    kind="class",
                    label="Graph Course",
                    data={"course_id": course_id, "title": "Graph Course"},
                )
            ],
            edges=[],
        )

    def _fake_expand(
        self,
        *,
        course_id: int,
        node_kind: Any,
        node_key: str,
        limit: int,
        max_concepts: int,
    ):
        return CourseGraphResponse(
            nodes=[
                GraphNode(
                    id="concept_test",
                    kind="concept",
                    label="test",
                    data={"name": "test"},
                )
            ],
            edges=[
                GraphEdge(
                    id="mentions_doc_test",
                    kind="mentions",
                    source="document_doc_1",
                    target="concept_test",
                    data=None,
                )
            ],
        )

    monkeypatch.setattr(
        "app.modules.courses.neo4j_repository.CourseGraphRepository.get_course_graph_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(
        "app.modules.courses.neo4j_repository.CourseGraphRepository.expand_course_graph_node",
        _fake_expand,
    )
    try:
        res = client.get(f"/courses/{course_id}/graph", headers=teacher_auth_headers)
        assert res.status_code == 200
        payload = res.json()
        assert "nodes" in payload
        assert payload["nodes"][0]["id"] == f"class_{course_id}"

        res2 = client.get(
            f"/courses/{course_id}/graph/expand?node_kind=concept&node_key=test",
            headers=teacher_auth_headers,
        )
        assert res2.status_code == 200
        payload2 = res2.json()
        assert len(payload2["nodes"]) >= 1
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_get_course_graph_clamps_caps(client, teacher_auth_headers, monkeypatch):
    create_res = client.post(
        "/courses",
        json={"title": "Graph Course", "description": "Desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    def _override_neo4j_session():
        yield object()

    app.dependency_overrides[require_neo4j_session] = _override_neo4j_session

    observed: dict[str, int] = {}

    def _fake_snapshot(self, *, course_id: int, max_documents: int, max_concepts: int):
        observed["max_documents"] = max_documents
        observed["max_concepts"] = max_concepts
        return CourseGraphResponse(nodes=[], edges=[])

    monkeypatch.setattr(
        "app.modules.courses.neo4j_repository.CourseGraphRepository.get_course_graph_snapshot",
        _fake_snapshot,
    )
    try:
        res = client.get(
            f"/courses/{course_id}/graph?max_documents=999999&max_concepts=999999",
            headers=teacher_auth_headers,
        )
        assert res.status_code == 200
        assert observed["max_documents"] == 250
        assert observed["max_concepts"] == 5000
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)
