"""Owned, revision checked assessment persistence against real PostgreSQL."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
from app.modules.marketdemandanalyst.repository import (
    RevisionConflict,
)
from tests.market_priority_fixtures import seed_priority_case


@pytest.fixture
def case(db_session, client, teacher_auth_headers):
    return seed_priority_case(db_session, client, teacher_auth_headers)


def test_legacy_assessments_are_nullable_and_empty_reviews_load():
    from app.modules.marketdemandanalyst.schemas import SkillReview

    assert "priority_assessment" in MarketAnalysisRun.__table__.c
    assert MarketAnalysisRun.__table__.c.priority_assessment.nullable
    assert SkillReview().model_dump(mode="json")["priority_assessment"] is None


def test_assessment_preserves_teacher_decisions(case):
    case.repo.save_priority_assessment(
        case.scope, case.assessment, expected_assessment_id=None
    )
    case.repo.commit()
    assert case.reload().priority_assessment["assessment_id"] == str(
        case.assessment.assessment_id
    )
    assert case.teacher_decisions() == case.before


def test_load_priority_inputs_is_owned_detached_and_has_verified_passages(case):
    inputs = case.repo.load_priority_inputs(case.scope)
    assert inputs["prior_assessment"] is None
    assert inputs["configured_release"] == "31.0"
    assert inputs["thread_id"] == case.thread_id
    assert len(inputs["candidates"]) == 5
    assert inputs["categories"][0].label == "Programming"
    assert set(inputs["posting_hashes"]) == set(case.snapshots)
    assert len(inputs["groups"]) == 1
    assert set(inputs["groups"][0]["posting_ids"]) == set(case.snapshots)
    assert len(inputs["passages"]) == 5
    for passage in inputs["passages"].values():
        snapshot = case.snapshots[passage["snapshot_id"]]
        assert (
            passage["text"]
            == snapshot.description_text[passage["start"] : passage["end"]]
        )
        assert passage["candidate_ids"]
    inputs["candidates"][0].display_name = "Changed only in detached DTO"
    case.repo.rollback()
    assert (
        case.reload().candidate_manifest["candidates"][0]["display_name"]
        == "Competency 1"
    )


@pytest.mark.parametrize("operation", ["load", "save"])
@pytest.mark.parametrize("invalid", ["teacher", "course", "inactive", "revision"])
def test_priority_storage_rejects_foreign_inactive_and_stale_scopes(
    case, db_session, operation, invalid
):
    scope = case.scope
    error = RevisionConflict
    if invalid in {"teacher", "course"}:
        field = f"{invalid}_id"
        scope = scope.model_copy(update={field: getattr(scope, field) + 1000})
        error = LookupError
    elif invalid == "revision":
        scope = scope.model_copy(update={"expected_candidate_revision": 0})
    else:
        thread = db_session.get(MDAThreadState, case.thread_id)
        thread.state_json = {"run_id": str(uuid4())}
        db_session.commit()
    with pytest.raises(error):
        if operation == "load":
            case.repo.load_priority_inputs(scope)
        else:
            case.repo.save_priority_assessment(
                scope, case.assessment, expected_assessment_id=None
            )
    case.repo.rollback()
    assert case.reload().priority_assessment is None
    assert case.teacher_decisions() == case.before


def test_assessment_compare_and_set_rejects_competing_ids(case):
    case.repo.save_priority_assessment(
        case.scope, case.assessment, expected_assessment_id=None
    )
    case.repo.commit()
    competitor = case.assessment.model_copy(update={"assessment_id": uuid4()})
    with pytest.raises(RevisionConflict):
        case.repo.save_priority_assessment(
            case.scope, competitor, expected_assessment_id=None
        )
    case.repo.rollback()
    case.repo.save_priority_assessment(
        case.scope, competitor, expected_assessment_id=case.assessment.assessment_id
    )
    case.repo.commit()
    assert case.reload().priority_assessment["assessment_id"] == str(
        competitor.assessment_id
    )


@pytest.mark.parametrize("changed", ["hash", "purged", "removed_membership"])
def test_assessment_rejects_changed_posting_sources(case, db_session, changed):
    snapshot = next(iter(case.snapshots.values()))
    if changed == "hash":
        snapshot.content_hash = "changed-after-read"
    elif changed == "purged":
        from datetime import UTC, datetime

        snapshot.purged_at = datetime.now(UTC)
    else:
        thread = db_session.get(MDAThreadState, case.thread_id)
        state = deepcopy(thread.state_json)
        state["selected_jobs"] = state["selected_jobs"][1:]
        thread.state_json = state
    db_session.commit()
    with pytest.raises(RevisionConflict):
        case.repo.save_priority_assessment(
            case.scope, case.assessment, expected_assessment_id=None
        )
    case.repo.rollback()
    assert case.reload().priority_assessment is None


def test_group_identity_uses_saved_membership_not_label(case, db_session):
    before = case.repo.load_priority_inputs(case.scope)["groups"][0]["group_id"]
    thread = db_session.get(MDAThreadState, case.thread_id)
    state = deepcopy(thread.state_json)
    state["job_groups"] = {"Different label": state["job_groups"]["Developer"]}
    thread.state_json = state
    db_session.commit()
    after = case.repo.load_priority_inputs(case.scope)["groups"][0]
    assert after["group_id"] == before
    assert after["label"] == "Different label"


def test_provider_tags_and_invalid_offsets_are_not_priority_passages(case, db_session):
    manifest = deepcopy(case.run.candidate_manifest)
    manifest["candidates"][0]["evidence_references"][0]["evidence_kind"] = (
        "provider_tag"
    )
    manifest["candidates"][1]["evidence_references"][0]["excerpt_end"] = 99999
    case.run.candidate_manifest = manifest
    db_session.commit()
    inputs = case.repo.load_priority_inputs(case.scope)
    assert len(inputs["passages"]) == 3


def test_assessment_upgrade_is_idempotent_for_old_table_and_keeps_rows(db_session):
    from main import _ensure_market_priority_assessment

    schema = f"priority_upgrade_{uuid4().hex}"
    with db_session.get_bind().begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        try:
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            connection.execute(
                text("CREATE TABLE market_analysis_runs (id integer PRIMARY KEY)")
            )
            connection.execute(text("INSERT INTO market_analysis_runs (id) VALUES (7)"))
            _ensure_market_priority_assessment(connection)
            _ensure_market_priority_assessment(connection)
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns(
                    "market_analysis_runs", schema=schema
                )
            }
            assert columns["priority_assessment"]["nullable"]
            assert str(columns["priority_assessment"]["type"]) == "JSONB"
            assert connection.execute(
                text("SELECT id, priority_assessment FROM market_analysis_runs")
            ).one() == (7, None)
        finally:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_priority_decision_rejects_model_numbers_and_unknown_association_fields():
    from pydantic import ValidationError

    from app.modules.marketdemandanalyst.schemas import PriorityDecision

    decision = dict(
        candidate_id=uuid4(),
        soc_code="15-1252.00",
        basis="ai_estimate",
        direct_reference_id=None,
        estimate=4,
        associations=[],
        supporting_evidence_ids=[],
        explanation="Evidence-based inference",
        limitations=[],
        unavailable_reason=None,
    )
    for update in (
        {"estimate": True},
        {"estimate": 4.0},
        {"estimate": 6},
        {"official_value": 4.5},
        {
            "associations": [
                {
                    "reference_id": uuid4(),
                    "relation": "related",
                    "rationale": "Anchor",
                    "value": 4.5,
                }
            ]
        },
    ):
        with pytest.raises(ValidationError):
            PriorityDecision(**{**decision, **update})
