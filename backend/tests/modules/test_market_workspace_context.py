"""Owned SQL context resolution and bounded request contracts."""

import json
from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.modules.marketdemandanalyst import schemas
from app.modules.marketdemandanalyst.models import (
    MarketAnalysisRun,
    MarketVacancySnapshot,
)
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from app.modules.marketdemandanalyst.routes import ChatRequest
from app.modules.occupation_reference.models import (
    OnetEvidence,
    OnetOccupation,
    OnetRelease,
)
from app.modules.occupation_reference.repository import OccupationReferenceRepository
from tests.market_skill_fixtures import seed_review


def context(**changes):
    return {
        "kind": "run_review",
        "version": 1,
        "intent": "explain",
        "run_id": str(uuid4()),
        "expected_candidate_revision": 1,
        "expected_selection_revision": 1,
        "view": "overview",
        "focused_candidate_id": None,
        "candidate_ids": [],
        "filters": {"category_ids": [], "search": "", "scope": "all"},
        "occupation_codes": [],
        "metric": "frequency",
        "descriptor_choices": [],
        "insight_kind": None,
        "has_unsaved_changes": False,
        **changes,
    }


def parse(value):
    assert hasattr(schemas, "RunReviewContext"), (
        "strict workspace context contract is missing"
    )
    return schemas.RunReviewContext.model_validate(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown": True},
        {"version": 2},
        {"expected_candidate_revision": -1},
        {"expected_selection_revision": True},
        {"candidate_ids": [str(uuid4()) for _ in range(21)]},
        {"occupation_codes": [f"15-125{i}.00" for i in range(6)]},
        {
            "descriptor_choices": [
                {"candidate_id": str(uuid4()), "evidence_id": str(uuid4())}
                for _ in range(21)
            ]
        },
        {
            "filters": {
                "category_ids": [str(i) for i in range(11)],
                "search": "",
                "scope": "all",
            }
        },
        {"filters": {"category_ids": [], "search": "x" * 121, "scope": "all"}},
        {"filters": {"category_ids": [], "search": "", "scope": "all", "extra": 1}},
        {"metric": "average"},
        {"candidate_ids": ["invalid"]},
        {"has_unsaved_changes": "false"},
    ],
)
def test_context_rejects_untrusted_or_out_of_bound_fields(changes):
    with pytest.raises(ValidationError):
        parse(context(**changes))


@pytest.mark.parametrize(
    "config",
    [
        "sources",
        "evidence_sources",
        "country",
        "location",
        "onet_release",
        "onet_occupation_codes",
    ],
)
def test_context_chat_rejects_configuration_even_if_null(config):
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {"message": "Explain", "workspace_context": context(), config: None}
        )


def test_message_and_utf8_context_budget_are_rejected():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "x" * 8001})
    value = context(
        filters={"category_ids": ["界" * 1000] * 10, "search": "", "scope": "all"}
    )
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "Explain", "workspace_context": value})


def test_reference_contract_forbids_proposals_unknowns_and_bounds():
    assert hasattr(schemas, "OccupationReferenceContext"), (
        "reference context contract is missing"
    )
    value = {
        "kind": "occupation_reference",
        "version": 1,
        "intent": "explain",
        "release": "30.0",
        "occupation_codes": ["15-1252.00"],
        "element_ids": [],
        "metric": "IM",
    }
    for changes in (
        {"intent": "propose_selection"},
        {"element_ids": [str(i) for i in range(21)]},
        {"metric": "frequency"},
        {"unknown": True},
    ):
        with pytest.raises(ValidationError):
            schemas.OccupationReferenceContext.model_validate({**value, **changes})


@pytest.fixture
def owned(db_session, client, teacher_auth_headers):
    course, run, candidates, _, _ = seed_review(
        db_session, client, teacher_auth_headers
    )
    from app.modules.marketdemandanalyst.workspace_service import (
        WorkspaceContextService,
    )

    service = WorkspaceContextService(
        MarketReviewRepository(db_session), OccupationReferenceRepository(db_session)
    )
    return course, run, candidates, service


def resolve(owned, **changes):
    course, run, _, service = owned
    return service.resolve(
        course["id"],
        course["teacher_id"],
        parse(context(**{"run_id": str(run.id), **changes})),
    )


def test_owned_current_context_is_detached_redacted_and_read_only(owned, db_session):
    course, run, candidates, _ = owned
    before = deepcopy(run.candidate_manifest)
    result = resolve(owned, focused_candidate_id=candidates[0]["candidate_id"])
    assert result.revision.expected_candidate_revision == 1
    assert (
        result.model_bundle["candidates"][0]["candidate_id"]
        == candidates[0]["candidate_id"]
    )
    assert result.history_metadata.matching_count == 1
    assert "Required: Python." in json.dumps(result.model_bundle)
    safe = json.dumps(result.history_metadata.model_dump(mode="json"))
    assert "original_description" not in safe
    assert "Required: Python." not in safe
    assert not db_session.in_transaction()
    assert db_session.get(MarketAnalysisRun, run.id).candidate_manifest == before
    assert course["id"] > 0


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"expected_candidate_revision": 0}, 409),
        ({"expected_selection_revision": 0}, 409),
        ({"candidate_ids": [str(uuid4())]}, 422),
        ({"focused_candidate_id": str(uuid4())}, 422),
        ({"occupation_codes": ["15-1252.00"]}, 422),
        ({"filters": {"category_ids": ["unknown"], "search": "", "scope": "all"}}, 422),
        ({"has_unsaved_changes": True, "intent": "propose_selection"}, 422),
        (
            {
                "has_unsaved_changes": True,
                "filters": {"category_ids": [], "search": "", "scope": "selected"},
            },
            422,
        ),
        (
            {
                "descriptor_choices": [
                    {"candidate_id": str(uuid4()), "evidence_id": str(uuid4())}
                ]
            },
            422,
        ),
    ],
)
def test_context_rejects_invalid_membership_and_dirty_selected_scope(
    owned, changes, status
):
    with pytest.raises(HTTPException) as error:
        resolve(owned, **changes)
    assert error.value.status_code == status
    if status == 409:
        assert error.value.detail["code"] == "context_stale"


def test_foreign_course_run_and_inactive_run_are_inaccessible(owned):
    course, run, _, service = owned
    request = parse(context(run_id=str(run.id)))
    with pytest.raises(HTTPException) as error:
        service.resolve(course["id"], course["teacher_id"] + 1000, request)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        resolve(owned, run_id=str(uuid4()))
    assert error.value.status_code == 404


def test_filters_selected_saved_scope_and_unsaved_notice(owned, db_session):
    _, run, _, _ = owned
    run.selected_candidate_ids = []
    db_session.commit()
    selected = resolve(
        owned, filters={"category_ids": [], "search": "", "scope": "selected"}
    )
    assert selected.history_metadata.matching_count == 0
    assert selected.model_bundle["candidates"] == []
    no_match = resolve(
        owned, filters={"category_ids": [], "search": "absent", "scope": "all"}
    )
    assert no_match.history_metadata.matching_count == 0
    unsaved = resolve(owned, has_unsaved_changes=True)
    assert (
        "Unsaved shortlist changes are not included" in unsaved.history_metadata.notices
    )


def test_purged_postings_never_restore_source_content(owned, db_session):
    _, _, candidates, _ = owned
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        candidates[0]["evidence_references"][0]["snapshot_id"], reason="test"
    )
    repo.commit()
    result = resolve(owned, focused_candidate_id=candidates[0]["candidate_id"])
    assert "Required: Python." not in json.dumps(result.model_bundle)
    assert (
        result.model_bundle["candidates"][0]["postings"][0]["status"] == "unavailable"
    )


@pytest.fixture
def late_skill_passage(owned, db_session):
    _, run, candidates, _ = owned
    candidate = deepcopy(candidates[0])
    ref = candidate["evidence_references"][0]
    snapshot = db_session.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
    passage = "Design SQL ingestion pipelines and query PostgreSQL databases."
    intro = ("General employer introduction. " * 30)[:865]
    snapshot.description_text = intro + passage + " Additional employer information."
    snapshot.original_description = snapshot.description_text
    snapshot.original_url = "https://hh.uz/vacancy/qualified-sql-passage"
    candidate["display_name"] = "Design SQL ingestion pipelines"
    candidate["evidence_references"] = [
        ref,
        {
            **ref,
            "original_url": snapshot.original_url,
            "original_phrase": "SQL ingestion pipelines",
            "evidence_kind": "extracted_text",
            "excerpt": passage,
            "excerpt_start": 865,
            "excerpt_end": 865 + len(passage),
        },
    ]
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    return owned


def test_focused_posting_uses_validated_skill_passage_beyond_intro(late_skill_passage):
    _, _, candidates, _ = late_skill_passage
    result = resolve(
        late_skill_passage, focused_candidate_id=candidates[0]["candidate_id"]
    )
    posting = result.model_bundle["candidates"][0]["postings"][0]
    assert posting["excerpt"] == (
        "Design SQL ingestion pipelines and query PostgreSQL databases."
    )
    assert posting["excerpt_kind"] == "validated_skill_passage"
    assert posting["original_url"] == "https://hh.uz/vacancy/qualified-sql-passage"
    assert result.history_metadata.evidence_included_count == 1
    assert len(posting["excerpt"]) <= 600
    assert (
        len(json.dumps(result.model_bundle, ensure_ascii=False).encode()) <= 24 * 1024
    )


def test_focused_invalid_passage_uses_labeled_introductory_context(
    late_skill_passage, db_session
):
    _, run, candidates, _ = late_skill_passage
    rows = deepcopy(run.candidate_manifest["candidates"])
    rows[0]["evidence_references"][1]["excerpt"] = "Invented skill quotation."
    run.candidate_manifest = {**run.candidate_manifest, "candidates": rows}
    db_session.commit()
    result = resolve(
        late_skill_passage, focused_candidate_id=candidates[0]["candidate_id"]
    )
    posting = result.model_bundle["candidates"][0]["postings"][0]
    assert posting.get("excerpt_kind") == "introductory_context"
    assert posting["excerpt"].startswith("General employer introduction.")
    assert "Invented skill quotation." not in json.dumps(result.model_bundle)
    assert len(posting["excerpt"]) <= 600


def test_long_validated_passage_keeps_qualifying_phrase_within_excerpt_cap(
    late_skill_passage, db_session
):
    _, run, candidates, _ = late_skill_passage
    rows = deepcopy(run.candidate_manifest["candidates"])
    ref = rows[0]["evidence_references"][1]
    snapshot = db_session.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
    passage = (
        "Detailed source requirement context. " * 25
        + "Design SQL ingestion pipelines and query PostgreSQL databases."
        + " More required work. " * 20
    )
    snapshot.description_text = snapshot.description_text[:865] + passage
    ref.update(excerpt=passage, excerpt_end=865 + len(passage))
    run.candidate_manifest = {**run.candidate_manifest, "candidates": rows}
    db_session.commit()
    result = resolve(
        late_skill_passage, focused_candidate_id=candidates[0]["candidate_id"]
    )
    posting = result.model_bundle["candidates"][0]["postings"][0]
    assert "SQL ingestion pipelines" in posting["excerpt"]
    assert len(posting["excerpt"]) <= 600
    assert posting["excerpt"] in passage
    assert posting["excerpt_kind"] == "validated_skill_passage"


@pytest.mark.parametrize("phrase_length", [560, 599, 600, 640])
def test_qualifying_phrase_takes_priority_over_left_context(
    late_skill_passage, db_session, phrase_length
):
    _, run, candidates, _ = late_skill_passage
    rows = deepcopy(run.candidate_manifest["candidates"])
    ref = rows[0]["evidence_references"][1]
    snapshot = db_session.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
    phrase = ("SQL ingestion pipelines. " * 30)[:phrase_length]
    passage = (
        "Detailed source requirement context. " * 25
        + phrase
        + " More required work. " * 40
    )
    snapshot.description_text = snapshot.description_text[:865] + passage
    snapshot.original_description = snapshot.description_text
    ref.update(original_phrase=phrase, excerpt=passage, excerpt_end=865 + len(passage))
    run.candidate_manifest = {**run.candidate_manifest, "candidates": rows}
    db_session.commit()

    result = resolve(
        late_skill_passage, focused_candidate_id=candidates[0]["candidate_id"]
    )
    posting = result.model_bundle["candidates"][0]["postings"][0]
    assert phrase[:600] in posting["excerpt"]
    assert len(posting["excerpt"]) <= 600
    assert posting["excerpt"] in passage
    assert posting["excerpt_kind"] == "validated_skill_passage"
    assert posting["original_url"] == "https://hh.uz/vacancy/qualified-sql-passage"


def test_purged_late_passage_is_unavailable_in_focused_bundle(
    late_skill_passage, db_session
):
    _, _, candidates, _ = late_skill_passage
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        candidates[0]["evidence_references"][0]["snapshot_id"], reason="test"
    )
    repo.commit()
    result = resolve(
        late_skill_passage, focused_candidate_id=candidates[0]["candidate_id"]
    )
    posting = result.model_bundle["candidates"][0]["postings"][0]
    assert posting["status"] == "unavailable"
    assert posting["excerpt"] is None
    assert (
        "Design SQL ingestion pipelines and query PostgreSQL databases."
        not in json.dumps(result.model_bundle)
    )


def seed_onet(db):
    db.add(OnetRelease(version="30.0", manifest={}, attribution="O*NET", active=True))
    db.flush()
    rows = []
    for code, value in (("15-1252.00", 4.0), ("15-1253.00", 5.0)):
        db.add(
            OnetOccupation(
                release="30.0", soc_code=code, title=code, description="Role"
            )
        )
        db.flush()
        row = OnetEvidence(
            id=uuid4(),
            release="30.0",
            soc_code=code,
            family="transferable",
            element_id="2.B.3",
            label="Programming",
            definition="Reference definition",
            workplace_example=None,
            ratings={
                "IM": {
                    "scale_id": "IM",
                    "value": value,
                    "minimum": 1,
                    "maximum": 5,
                    "status": "reported",
                    "date": None,
                    "quality": {},
                }
            },
            flags={},
            source_rows=[],
            source_key=code,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


@pytest.fixture
def descriptor_context(owned, db_session):
    """Job-backed SQL with deliberately untrusted Programming manifest ratings."""
    _, run, candidates, _ = owned
    rows = seed_onet(db_session)
    for row, value in zip(rows, [3.38, 4.8], strict=True):
        row.ratings = {"IM": {**row.ratings["IM"], "value": value}}
    run.config = {
        **run.config,
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "30.0",
        "selected_onet_occupations": [
            {"soc_code": row.soc_code, "title": "Untrusted title"} for row in rows
        ],
    }
    candidate = {
        **candidates[0],
        "display_name": "SQL",
        "onet_associations": [
            {
                "relation": "related",
                "evidence": {
                    "id": str(row.id),
                    "release": row.release,
                    "soc_code": row.soc_code,
                    "family": row.family,
                    "element_id": row.element_id,
                    "label": "SQL",
                    "ratings": {"IM": {"value": 99}},
                },
            }
            for row in rows
        ],
    }
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    return rows, candidate


@pytest.mark.parametrize(
    "relation,intent",
    [
        ("related", "explain"),
        ("broader", "explain"),
        ("equivalent", "explain"),
        ("equivalent", "propose_selection"),
    ],
)
def test_explain_choices_reach_model_with_canonical_descriptor_facts(
    owned, descriptor_context, db_session, relation, intent
):
    _, run, _, _ = owned
    rows, candidate = descriptor_context
    for association in candidate["onet_associations"]:
        association["relation"] = relation
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    before = deepcopy(
        (
            run.candidate_manifest,
            run.selection_revision,
            run.publication_revision,
            run.selected_candidate_ids,
            run.excluded_candidate_ids,
            run.selection_confirmation,
        )
    )
    choices = [
        {"candidate_id": candidate["candidate_id"], "evidence_id": str(row.id)}
        for row in rows
    ]
    result = resolve(
        owned,
        intent=intent,
        candidate_ids=[candidate["candidate_id"]],
        occupation_codes=[row.soc_code for row in rows],
        metric="IM",
        descriptor_choices=choices,
    )
    assert not db_session.in_transaction()
    bundle = result.model_bundle
    assert bundle["descriptor_choices"] == choices
    assert bundle["occupation_codes"] == ["15-1252.00", "15-1253.00"]
    assert bundle["release"] == "30.0"
    fact = bundle["candidates"][0]
    assert fact["candidate_id"] == candidate["candidate_id"]
    assert fact["display_name"] == "SQL"
    for index, association in enumerate(fact["onet_associations"]):
        assert association["relation"] == relation
        evidence = association["evidence"]
        assert evidence["id"] == choices[index]["evidence_id"]
        assert evidence["label"] == "Programming"
        assert evidence["release"] == "30.0"
        assert evidence["soc_code"] == ["15-1252.00", "15-1253.00"][index]
        assert evidence["occupation_title"] == evidence["soc_code"]
        assert evidence["ratings"]["IM"] == {
            "scale_id": "IM",
            "value": [3.38, 4.8][index],
            "minimum": 1,
            "maximum": 5,
            "status": "reported",
            "date": None,
        }
    if relation != "equivalent":
        assert bundle["patterns"] == []
    assert (
        run.candidate_manifest,
        run.selection_revision,
        run.publication_revision,
        run.selected_candidate_ids,
        run.excluded_candidate_ids,
        run.selection_confirmation,
    ) == before


def test_explain_chosen_descriptor_obeys_utf8_budget_with_explicit_omission(
    owned, descriptor_context, db_session
):
    rows, candidate = descriptor_context
    rows[0].definition = "界" * 9000
    choice = {"candidate_id": candidate["candidate_id"], "evidence_id": str(rows[0].id)}
    db_session.commit()
    result = resolve(
        owned,
        candidate_ids=[candidate["candidate_id"]],
        occupation_codes=["15-1252.00"],
        metric="IM",
        descriptor_choices=[choice],
    )
    bundle = result.model_bundle
    assert len(json.dumps(bundle, ensure_ascii=False).encode()) <= 24 * 1024
    assert bundle["descriptor_choices"] == [choice]
    assert bundle["candidates"] == []
    assert bundle["omitted_count"] == 1
    assert bundle["evidence_omitted_count"] == 2
    assert bundle["notices"] == ["Some context was omitted to fit the evidence budget"]
    assert result.history_metadata.notices == bundle["notices"]


@pytest.mark.parametrize(
    "relation,intent",
    [
        ("related", "propose_selection"),
        ("broader", "propose_selection"),
        ("unmatched", "explain"),
        ("unmatched", "propose_selection"),
    ],
)
def test_descriptor_choices_keep_proposals_equivalent_only_and_unmatched_invalid(
    owned, descriptor_context, db_session, relation, intent
):
    _, run, _, _ = owned
    rows, candidate = descriptor_context
    candidate["onet_associations"][0]["relation"] = relation
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        resolve(
            owned,
            intent=intent,
            occupation_codes=[rows[0].soc_code],
            descriptor_choices=[
                {
                    "candidate_id": candidate["candidate_id"],
                    "evidence_id": str(rows[0].id),
                }
            ],
        )
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "invalid,status",
    [
        ("candidate", 422),
        ("evidence", 404),
        ("occupation", 422),
        ("release", 404),
        ("element", 404),
        ("software", 422),
        ("empty_element", 422),
    ],
)
def test_explain_choices_preserve_catalog_and_actual_descriptor_guards(
    owned, descriptor_context, db_session, invalid, status
):
    _, run, _, _ = owned
    rows, candidate = descriptor_context
    evidence = candidate["onet_associations"][0]["evidence"]
    # Equivalent proves software/empty-element rejection is independent of relation.
    candidate["onet_associations"][0]["relation"] = "equivalent"
    choice = {"candidate_id": candidate["candidate_id"], "evidence_id": str(rows[0].id)}
    codes = [rows[0].soc_code]
    if invalid in {"candidate", "evidence"}:
        choice[f"{invalid}_id"] = str(uuid4())
    elif invalid == "occupation":
        codes = [rows[1].soc_code]
    elif invalid == "release":
        evidence["release"] = "31.0"
    elif invalid == "element":
        evidence["element_id"] = "different"
    elif invalid == "software":
        rows[0].family = evidence["family"] = "software"
        rows[0].workplace_example = "Database application"
        rows[0].flags = {"hot_technology": True}
    else:
        rows[0].element_id = evidence["element_id"] = ""
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        resolve(owned, occupation_codes=codes, descriptor_choices=[choice])
    assert error.value.status_code == status


def test_explain_related_choice_does_not_cross_course_ownership(
    owned, descriptor_context
):
    course, run, _, service = owned
    rows, candidate = descriptor_context
    with pytest.raises(HTTPException) as error:
        service.resolve(
            course["id"],
            course["teacher_id"] + 1000,
            parse(
                context(
                    run_id=str(run.id),
                    occupation_codes=[rows[0].soc_code],
                    descriptor_choices=[
                        {
                            "candidate_id": candidate["candidate_id"],
                            "evidence_id": str(rows[0].id),
                        }
                    ],
                )
            ),
        )
    assert error.value.status_code == 404


def test_explain_related_choices_reject_different_descriptor_across_occupations(
    owned, descriptor_context, db_session
):
    _, run, _, _ = owned
    rows, candidate = descriptor_context
    rows[1].element_id = "2.B.4"
    candidate["onet_associations"][1]["evidence"]["element_id"] = "2.B.4"
    run.candidate_manifest = {**run.candidate_manifest, "candidates": [candidate]}
    db_session.commit()
    with pytest.raises(HTTPException) as error:
        resolve(
            owned,
            occupation_codes=[row.soc_code for row in rows],
            descriptor_choices=[
                {"candidate_id": candidate["candidate_id"], "evidence_id": str(row.id)}
                for row in rows
            ],
        )
    assert error.value.status_code == 422
    assert "same descriptor identity" in error.value.detail["message"]


def test_reference_resolution_does_not_create_run(owned, db_session):
    course, _, _, service = owned
    seed_onet(db_session)
    before = db_session.scalar(select(func.count()).select_from(MarketAnalysisRun))
    assert hasattr(schemas, "OccupationReferenceContext"), (
        "reference context contract is missing"
    )
    request = schemas.OccupationReferenceContext(
        kind="occupation_reference",
        version=1,
        intent="explain",
        release="30.0",
        occupation_codes=["15-1252.00"],
        element_ids=["2.B.3"],
        metric="IM",
    )
    result = service.resolve(course["id"], course["teacher_id"], request)
    assert result.revision is None
    assert result.model_bundle["evidence"][0]["ratings"]["IM"]["value"] == 4
    assert (
        result.model_bundle["evidence"][0].get("level_activity_anchors", "missing")
        is None
    )
    assert (
        db_session.scalar(select(func.count()).select_from(MarketAnalysisRun)) == before
    )
    for patch in (
        {"release": "99.0"},
        {"occupation_codes": ["99-9999.00"]},
        {"element_ids": ["absent"]},
    ):
        with pytest.raises(HTTPException) as error:
            service.resolve(
                course["id"], course["teacher_id"], request.model_copy(update=patch)
            )
        assert error.value.status_code == 422


def test_per_occupation_evidence_ids_share_descriptor_identity_and_fresh_facts(
    owned, db_session
):
    _, run, candidates, _ = owned
    rows = seed_onet(db_session)
    run.config = {
        **run.config,
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "30.0",
        "selected_onet_occupations": [
            {"soc_code": row.soc_code, "title": row.soc_code} for row in rows
        ],
    }
    associations = [
        {
            "relation": "equivalent",
            "evidence": {
                "id": str(row.id),
                "release": row.release,
                "soc_code": row.soc_code,
                "family": row.family,
                "element_id": row.element_id,
                "ratings": {"IM": {"value": 1}},
            },
        }
        for row in rows
    ]
    associations.append(deepcopy(associations[0]))
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidates": [{**candidates[0], "onet_associations": associations}],
    }
    db_session.commit()
    result = resolve(
        owned,
        occupation_codes=[row.soc_code for row in rows],
        descriptor_choices=[
            {"candidate_id": candidates[0]["candidate_id"], "evidence_id": str(row.id)}
            for row in rows
        ],
        insight_kind="occupation_difference",
    )
    assert len(result.model_bundle["candidates"][0]["onet_associations"]) == 2
    assert result.model_bundle["patterns"][0]["kind"] == "occupation_difference"
    assert [v["value"] for v in result.model_bundle["patterns"][0]["values"]] == [4, 5]
    current = resolve(owned, focused_candidate_id=candidates[0]["candidate_id"])
    assert current.model_bundle["occupation_codes"] == []
    assert all(
        candidate["onet_associations"] == []
        for candidate in current.model_bundle["candidates"]
    )
    with pytest.raises(HTTPException) as error:
        resolve(
            owned,
            descriptor_choices=[
                {
                    "candidate_id": candidates[0]["candidate_id"],
                    "evidence_id": str(uuid4()),
                }
            ],
        )
    assert error.value.status_code == 404


def test_boolean_version_and_unknown_outer_context_fields_are_rejected():
    with pytest.raises(ValidationError):
        parse(context(version=True))


def test_unknown_outer_context_fields_are_rejected():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Explain",
                "workspace_context": context(),
                "chart_values": [100],
            }
        )


def test_oversized_multibyte_evidence_is_omitted_as_complete_json(owned, db_session):
    _, run, candidates, _ = owned
    records = []
    for index in range(25):
        records.append(
            {
                **candidates[0],
                "candidate_id": str(uuid4()),
                "display_name": "界" * 700 + str(index),
                "evidence_references": [],
            }
        )
    run.candidate_manifest = {**run.candidate_manifest, "candidates": records}
    db_session.commit()
    result = resolve(owned)
    encoded = json.dumps(result.model_bundle, ensure_ascii=False).encode()
    assert len(encoded) <= 24 * 1024
    assert json.loads(encoded)["candidates"] == result.model_bundle["candidates"]
    metadata = result.history_metadata
    assert 0 < metadata.included_count < 20
    assert metadata.included_count + metadata.omitted_count == 25
    assert metadata.notices


def test_duplicate_posting_reference_does_not_consume_excerpt_slots(owned, db_session):
    _, run, candidates, _ = owned
    repo = MarketReviewRepository(db_session)
    extra = repo.upsert_vacancy_snapshot(
        run.id,
        schemas.ProviderVacancy(
            provider="headhunter",
            native_id=str(uuid4()),
            title="Other developer",
            original_url="https://hh.uz/vacancy/other",
            original_description="X" * 800,
            description_text="X" * 800,
        ),
    )
    first = candidates[0]["evidence_references"][0]
    second = {**first, "snapshot_id": str(extra.id)}
    # Repeated references can precede another immutable posting in the manifest.
    smaller, larger = sorted([first, second], key=lambda ref: ref["snapshot_id"])
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidates": [
            {**candidates[0], "evidence_references": [smaller, smaller, larger]}
        ],
    }
    db_session.commit()
    result = resolve(owned, focused_candidate_id=candidates[0]["candidate_id"])
    postings = result.model_bundle["candidates"][0]["postings"]
    assert len(postings) == 2
    assert all(len(row["excerpt"]) <= 600 for row in postings)
    assert result.history_metadata.evidence_included_count == 2


def test_same_owner_nonactive_run_is_rejected(owned, db_session):
    course, _, _, service = owned
    repo = MarketReviewRepository(db_session)
    inactive = repo.create_run(
        course["id"], course["teacher_id"], {"sources": ["headhunter"]}
    )
    repo.commit()
    with pytest.raises(HTTPException) as error:
        service.resolve(
            course["id"],
            course["teacher_id"],
            parse(
                context(
                    run_id=str(inactive.id),
                    expected_candidate_revision=0,
                    expected_selection_revision=0,
                )
            ),
        )
    assert error.value.status_code == 404


def test_descriptor_duplicate_choice_is_invalid_and_suppressed_value_redacted(
    owned, db_session
):
    _, run, candidates, _ = owned
    rows = seed_onet(db_session)
    rows[0].ratings = {
        "IM": {
            "scale_id": "IM",
            "value": 4.5,
            "minimum": 1,
            "maximum": 5,
            "status": "suppressed",
        }
    }
    run.config = {
        **run.config,
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "30.0",
        "selected_onet_occupations": [
            {"soc_code": row.soc_code, "title": row.soc_code} for row in rows
        ],
    }
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidates": [
            {
                **candidates[0],
                "onet_associations": [
                    {
                        "relation": "equivalent",
                        "evidence": {
                            "id": str(row.id),
                            "release": row.release,
                            "soc_code": row.soc_code,
                            "family": row.family,
                            "element_id": row.element_id,
                        },
                    }
                    for row in rows
                ],
            }
        ],
    }
    db_session.commit()
    choice = {
        "candidate_id": candidates[0]["candidate_id"],
        "evidence_id": str(rows[0].id),
    }
    with pytest.raises(HTTPException) as error:
        resolve(
            owned,
            occupation_codes=[rows[0].soc_code],
            descriptor_choices=[choice, choice],
        )
    assert error.value.status_code == 422
    result = resolve(owned, occupation_codes=[row.soc_code for row in rows])
    assert (
        result.model_bundle["candidates"][0]["onet_associations"][0]["evidence"][
            "ratings"
        ]["IM"]["value"]
        is None
    )
    assert result.model_bundle["patterns"] == []
    assert all(
        row["kind"] != "occupation_difference"
        for row in result.model_bundle["patterns"]
    )


def test_legacy_workflow_still_ignores_unknown_fields():
    request = ChatRequest.model_validate(
        {"message": "Review", "legacy_client_hint": "ok"}
    )
    assert request.message == "Review"
    assert request.workspace_context is None


def test_context_http_rejections_precede_external_graph_calls(
    client, teacher_auth_headers, monkeypatch
):
    calls = []

    def unexpected_graph(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Model boundary must remain untouched")

    monkeypatch.setattr(
        "app.modules.marketdemandanalyst.routes.get_graph", unexpected_graph
    )
    for body in (
        {
            "message": "Explain",
            "workspace_context": context(),
            "sources": ["headhunter"],
        },
        {
            "message": "Explain",
            "workspace_context": context(
                filters={"category_ids": [], "search": "x" * 121, "scope": "all"}
            ),
        },
    ):
        response = client.post(
            "/courses/1/market-demand/chat", json=body, headers=teacher_auth_headers
        )
        assert response.status_code == 422
    assert calls == []


def test_reference_only_course_with_no_run_stays_runless(
    db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.workspace_service import (
        WorkspaceContextService,
    )

    course = client.post(
        "/courses", json={"title": "Reference only"}, headers=teacher_auth_headers
    ).json()
    seed_onet(db_session)
    service = WorkspaceContextService(
        MarketReviewRepository(db_session), OccupationReferenceRepository(db_session)
    )
    request = schemas.OccupationReferenceContext(
        kind="occupation_reference",
        version=1,
        intent="explain",
        release="30.0",
        occupation_codes=["15-1252.00"],
        element_ids=[],
        metric="LV",
    )
    result = service.resolve(course["id"], course["teacher_id"], request)
    assert result.history_metadata.matching_count == 1
    assert result.revision is None
    assert result.history_metadata.run_id is None
    assert db_session.scalar(select(func.count()).select_from(MarketAnalysisRun)) == 0


def test_utf8_context_is_accepted_at_exact_byte_limit_and_rejected_above_it():
    value = context()
    baseline = len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    )
    remaining = 16 * 1024 - baseline - 2
    value["filters"]["category_ids"] = ["界" * (remaining // 3) + "x" * (remaining % 3)]
    assert (
        len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        == 16 * 1024
    )
    parsed = parse(value)
    assert parsed.filters.category_ids == value["filters"]["category_ids"]
    value["filters"]["category_ids"][0] += "x"
    with pytest.raises(ValidationError):
        parse(value)


def test_all_matching_small_facts_fit_without_a_hidden_twenty_row_limit(
    owned, db_session
):
    _, run, candidates, _ = owned
    records = [
        {
            **candidates[0],
            "candidate_id": str(uuid4()),
            "display_name": f"Skill {index}",
            "evidence_references": [],
        }
        for index in range(25)
    ]
    run.candidate_manifest = {**run.candidate_manifest, "candidates": records}
    db_session.commit()
    result = resolve(owned)
    assert result.history_metadata.matching_count == 25
    assert result.history_metadata.included_count == 25
    assert result.history_metadata.omitted_count == 0


def test_reference_resolution_does_not_invent_missing_declared_scales(
    owned, db_session
):
    course, _, _, service = owned
    rows = seed_onet(db_session)
    rows[0].ratings = {"IM": {"status": "reported", "value": 4}}
    db_session.commit()
    request = schemas.OccupationReferenceContext(
        kind="occupation_reference",
        version=1,
        intent="explain",
        release="30.0",
        occupation_codes=["15-1252.00"],
        element_ids=[],
        metric="IM",
    )
    result = service.resolve(course["id"], course["teacher_id"], request)
    assert result.model_bundle["evidence"][0]["ratings"]["IM"] == {
        "status": "reported",
        "value": 4,
    }


@pytest.mark.parametrize(
    "changed_fact", ["rating", "occupation_title", "release_attribution"]
)
def test_reference_refreshes_preloaded_catalog_facts_after_another_session_commits(
    owned, db_session, changed_fact
):
    """A real read must replace stale identity-map attributes, not just issue SQL."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    course, _, _, service = owned
    rows = seed_onet(db_session)
    repository = OccupationReferenceRepository(db_session)
    # Strong references retain the precise stale instances throughout resolution.
    release = repository.get_release("30.0")
    occupations = repository.get_occupations("30.0", ["15-1252.00"])
    evidence = repository.get_evidence("30.0", ["15-1252.00"])
    assert evidence[0] is rows[0]
    assert evidence[0].ratings["IM"]["status"] == "reported"
    assert release.attribution == "O*NET"
    assert occupations[0].title == "15-1252.00"
    with Session(db_session.get_bind()) as writer:
        if changed_fact == "rating":
            writer.execute(
                update(OnetEvidence)
                .where(OnetEvidence.id == evidence[0].id)
                .values(
                    ratings={
                        "IM": {
                            "scale_id": "IM",
                            "value": 4,
                            "minimum": 1,
                            "maximum": 5,
                            "status": "suppressed",
                        }
                    }
                )
            )
        elif changed_fact == "occupation_title":
            writer.execute(
                update(OnetOccupation)
                .where(
                    OnetOccupation.release == "30.0",
                    OnetOccupation.soc_code == "15-1252.00",
                )
                .values(title="Updated occupation")
            )
        else:
            writer.execute(
                update(OnetRelease)
                .where(OnetRelease.version == "30.0")
                .values(attribution="Updated official attribution")
            )
        writer.commit()
    # Session A still holds stale reported data until the repository read refreshes it.
    assert evidence[0].ratings["IM"]["status"] == "reported"
    request = schemas.OccupationReferenceContext(
        kind="occupation_reference",
        version=1,
        intent="explain",
        release="30.0",
        occupation_codes=["15-1252.00"],
        element_ids=["2.B.3"],
        metric="IM",
    )
    result = service.resolve(course["id"], course["teacher_id"], request)
    model_fact = result.model_bundle["evidence"][0]
    history_fact = result.history_metadata.facts[0]
    if changed_fact == "rating":
        assert model_fact["ratings"]["IM"]["status"] == "suppressed"
        assert model_fact["ratings"]["IM"]["value"] is None
        assert history_fact["ratings"]["IM"]["value"] is None
    elif changed_fact == "occupation_title":
        assert model_fact["occupation_title"] == "Updated occupation"
        assert history_fact["occupation_title"] == "Updated occupation"
        assert result.history_metadata.occupations[0].title == "Updated occupation"
    else:
        assert model_fact["attribution"] == "Updated official attribution"
        assert history_fact["attribution"] == "Updated official attribution"
    assert not db_session.in_transaction()


@pytest.mark.parametrize(
    "label,aliases,original_labels,search,expected_count",
    [
        ("Ｐｙｔｈｏｎ", [], [], "python", 1),
        ("Competency", ["ＳＱＬ"], [], "sql", 1),
        ("Competency", [], ["ＳＱＬ"], "sql", 1),
        ("Machine  Learning", [], [], "machine  learning", 1),
        ("Machine", ["Learning"], [], "machine learning", 0),
    ],
)
def test_sql_context_search_matches_the_same_normalized_per_label_scope(
    owned, db_session, label, aliases, original_labels, search, expected_count
):
    _, run, candidates, _ = owned
    run.candidate_manifest = {
        **run.candidate_manifest,
        "candidates": [
            {
                **candidates[0],
                "display_name": label,
                "aliases": aliases,
                "original_labels": original_labels,
            }
        ],
    }
    db_session.commit()
    result = resolve(
        owned, filters={"category_ids": [], "search": search, "scope": "all"}
    )
    assert result.history_metadata.matching_count == expected_count
    assert result.history_metadata.included_count == expected_count
    assert len(result.model_bundle["candidates"]) == expected_count
    if expected_count:
        fact = result.model_bundle["candidates"][0]
        assert fact["candidate_id"] == candidates[0]["candidate_id"]
        assert fact["display_name"] == label
        assert fact["job_metrics"]["assessed_posting_count"] == 1
        assert (
            result.history_metadata.facts[0]["candidate_id"]
            == candidates[0]["candidate_id"]
        )
    else:
        assert result.history_metadata.facts == []
