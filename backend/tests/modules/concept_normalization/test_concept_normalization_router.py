from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from neo4j import Session as Neo4jSession

from app.core.neo4j import require_neo4j_session
from app.modules.concept_normalization.schemas import NormalizationStreamEvent
from main import app


@pytest.fixture
def neo4j_session_override() -> Iterator[Neo4jSession]:
    # Any Neo4jSession-like object; our tests monkeypatch downstream usage.
    yield MagicMock(spec=Neo4jSession)


def test_list_course_concepts_requires_teacher(
    client, student_auth_headers, neo4j_session_override
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        res = client.get(
            "/normalization/concepts?course_id=1", headers=student_auth_headers
        )
        assert res.status_code in {401, 403}
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_list_course_concepts_returns_names(
    client, teacher_auth_headers, monkeypatch, neo4j_session_override
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        from app.modules.concept_normalization import routes as normalization_routes

        def _fake_list_concepts_for_course(self, *, course_id: int):
            assert course_id == 123
            return [{"name": "a"}, {"name": "b"}]

        monkeypatch.setattr(
            normalization_routes.ConceptNormalizationRepository,
            "list_concepts_for_course",
            _fake_list_concepts_for_course,
        )

        res = client.get(
            "/normalization/concepts?course_id=123", headers=teacher_auth_headers
        )
        assert res.status_code == 200
        assert res.json() == ["a", "b"]
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_stream_normalization_sse(
    client, teacher_auth_headers, monkeypatch, neo4j_session_override
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        from app.modules.concept_normalization import routes as normalization_routes

        class _FakeService:
            def normalize_concepts_stream(
                self, *, course_id: int, created_by_user_id: int | None = None
            ):
                assert course_id == 5
                assert created_by_user_id is not None
                yield NormalizationStreamEvent(
                    type="update",
                    iteration=1,
                    phase="generation",
                    agent_activity="gen",
                    concepts_count=2,
                    merges_found=1,
                    relationships_found=0,
                    latest_merges=[],
                    latest_relationships=[],
                    total_merges=1,
                    total_relationships=0,
                )
                yield NormalizationStreamEvent(
                    type="complete",
                    iteration=2,
                    phase="complete",
                    agent_activity="done",
                    concepts_count=2,
                    merges_found=0,
                    relationships_found=0,
                    latest_merges=[],
                    latest_relationships=[],
                    total_merges=1,
                    total_relationships=0,
                )

        monkeypatch.setattr(
            normalization_routes,
            "get_concept_normalization_service",
            lambda *, neo4j_session, db: _FakeService(),
        )

        res = client.get(
            "/normalization/stream?course_id=5", headers=teacher_auth_headers
        )
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

        body = res.text
        assert "event: update" in body
        assert "Connected" in body
        assert '"agent_activity":"gen"' in body
        assert "event: complete" in body
        assert '"agent_activity":"done"' in body
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_merge_prompts_format_without_keyerror():
    # This guards against unescaped `{}` in prompt templates (which causes KeyError
    # during `.format_messages()`).
    from app.modules.concept_normalization.prompts import (
        CLUSTER_NORMALIZATION_PROMPT,
        CONCEPT_NORMALIZATION_PROMPT,
        MERGE_VALIDATION_PROMPT,
    )

    messages = CONCEPT_NORMALIZATION_PROMPT.format_messages(
        num_concepts=2,
        concept_list="- a\n- b",
        num_weak=0,
        weak_merges_list="(none yet)",
    )
    assert len(messages) >= 1

    messages = MERGE_VALIDATION_PROMPT.format_messages(
        num_merges=1,
        merges_summary="1. a + b → a\n   Reasoning: same",
        definitions_text="**a**:\n  1. def",
    )
    assert len(messages) >= 1

    messages = CLUSTER_NORMALIZATION_PROMPT.format_messages(
        num_concepts=3,
        concept_list="- a\n- b\n- c",
    )
    assert len(messages) >= 1
