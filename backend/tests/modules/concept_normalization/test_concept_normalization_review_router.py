from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from neo4j import Session as Neo4jSession
from sqlalchemy import select

from app.core.neo4j import require_neo4j_session
from app.modules.concept_normalization.schemas import (
    ApplyReviewResponse,
    MergeProposalDecision,
    NormalizationReview,
)
from app.modules.concept_normalization.review_sql_models import (
    ConceptNormalizationReviewItem,
)
from main import app


@pytest.fixture
def neo4j_session_override() -> Iterator[Neo4jSession]:
    yield MagicMock(spec=Neo4jSession)


def test_get_review_returns_payload(
    client, teacher_auth_headers, monkeypatch, neo4j_session_override, db_session
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        from app.modules.concept_normalization import routes as normalization_routes

        # Insert staged review/proposal in SQL.
        db_session.add(
            ConceptNormalizationReviewItem(
                course_id=5,
                review_id="normrev_1",
                created_by_user_id=1,
                proposal_id="mergeprop_1",
                concept_a="a",
                concept_b="b",
                canonical="a",
                variants_json='["a","b"]',
                r="same",
                decision=MergeProposalDecision.PENDING,
                comment="",
            )
        )
        db_session.commit()

        def _fake_defs(self, *, names, course_id: int):
            assert course_id == 5
            assert "a" in names
            return {"a": ["def a"], "b": ["def b"]}

        monkeypatch.setattr(
            normalization_routes.ConceptNormalizationRepository,
            "get_concept_definitions_for_course",
            _fake_defs,
        )

        res = client.get(
            "/normalization/reviews/normrev_1?course_id=5",
            headers=teacher_auth_headers,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == "normrev_1"
        assert body["course_id"] == 5
        assert body["definitions"]["a"] == ["def a"]
        assert len(body["proposals"]) == 1
        assert body["proposals"][0]["id"] == "mergeprop_1"
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_update_review_decisions(
    client, teacher_auth_headers, monkeypatch, neo4j_session_override, db_session
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        # Insert staged review/proposal in SQL.
        db_session.add(
            ConceptNormalizationReviewItem(
                course_id=5,
                review_id="normrev_1",
                created_by_user_id=1,
                proposal_id="mergeprop_1",
                concept_a="a",
                concept_b="b",
                canonical="a",
                variants_json='["a","b"]',
                r="same",
                decision=MergeProposalDecision.PENDING,
                comment="",
            )
        )
        db_session.commit()

        res = client.post(
            "/normalization/reviews/normrev_1/decisions?course_id=5",
            headers=teacher_auth_headers,
            json={
                "decisions": [
                    {"proposal_id": "mergeprop_1", "decision": "approved", "comment": ""}
                ]
            },
        )
        assert res.status_code == 200
        assert res.json()["updated"] == 1

        row = db_session.scalar(
            select(ConceptNormalizationReviewItem).where(
                ConceptNormalizationReviewItem.review_id == "normrev_1",
                ConceptNormalizationReviewItem.course_id == 5,
                ConceptNormalizationReviewItem.proposal_id == "mergeprop_1",
            )
        )
        assert row is not None
        assert row.decision == MergeProposalDecision.APPROVED
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


def test_apply_review(
    client, teacher_auth_headers, monkeypatch, neo4j_session_override, db_session
):
    app.dependency_overrides[require_neo4j_session] = lambda: neo4j_session_override
    try:
        from app.modules.concept_normalization import routes as normalization_routes

        # Insert staged approved proposal in SQL.
        db_session.add(
            ConceptNormalizationReviewItem(
                course_id=5,
                review_id="normrev_1",
                created_by_user_id=1,
                proposal_id="mergeprop_1",
                concept_a="a",
                concept_b="b",
                canonical="a",
                variants_json='["a","b"]',
                r="same",
                decision=MergeProposalDecision.APPROVED,
                comment="",
            )
        )
        db_session.commit()

        def _fake_merge(self, *, canonical: str, variants: list[str]) -> bool:
            assert canonical
            assert isinstance(variants, list)
            return True

        monkeypatch.setattr(
            normalization_routes.ConceptNormalizationRepository,
            "merge_concepts",
            _fake_merge,
        )

        res = client.post(
            "/normalization/reviews/normrev_1/apply?course_id=5",
            headers=teacher_auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["applied"] == 1

        remaining = db_session.scalars(
            select(ConceptNormalizationReviewItem).where(
                ConceptNormalizationReviewItem.review_id == "normrev_1",
                ConceptNormalizationReviewItem.course_id == 5,
            )
        ).all()
        assert remaining == []
    finally:
        app.dependency_overrides.pop(require_neo4j_session, None)


