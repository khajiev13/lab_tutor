"""Production mixed collection/extraction associations, real imported SQL evidence."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.marketdemandanalyst import associations, extractor
from app.modules.marketdemandanalyst.job_sources import JobSourceService
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from app.modules.marketdemandanalyst.review_service import SkillReviewService
from app.modules.marketdemandanalyst.service import MarketSourceService
from app.modules.marketdemandanalyst.state import bind_tool_store
from app.modules.occupation_reference.importer import parse_release
from app.modules.occupation_reference.repository import OccupationReferenceRepository


@pytest.fixture
def mixed_pipeline(db_session, client, teacher_auth_headers, monkeypatch, request):
    catalog = OccupationReferenceRepository(db_session)
    parsed = parse_release(Path(__file__).parents[1] / "fixtures/onet/31.0", "31.0")
    codes = ["15-2051.00"]
    if getattr(request, "param", None) == "multiple":
        codes.append("15-1252.00")
        parsed = replace(
            parsed,
            evidence=[
                *parsed.evidence,
                *[
                    replace(
                        row,
                        id=str(uuid4()),
                        soc_code="15-1252.00",
                        source_key=row.source_key.replace(
                            '"15-2051.00"', '"15-1252.00"'
                        ),
                        source_rows=[
                            {**source, "O*NET-SOC Code": "15-1252.00"}
                            for source in row.source_rows
                        ],
                    )
                    for row in parsed.evidence
                ],
            ],
        )
    catalog.import_release(
        parsed,
        activate=True,
    )
    course = client.post(
        "/courses", json={"title": "Mixed associations"}, headers=teacher_auth_headers
    ).json()
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"],
        course["teacher_id"],
        {
            "country": "Uzbekistan",
            "sources": ["linkedin"],
            "evidence_sources": ["jobs", "onet"],
            "onet_release": "31.0",
            "onet_selection_confirmed": True,
            "selected_onet_occupations": [{"soc_code": code} for code in codes],
        },
    )
    repo.save_configuration_snapshot(
        SkillReviewService.thread_id(course["id"], course["teacher_id"]),
        {"run_id": str(run.id)},
    )
    db_session.commit()
    description = (
        "Reading Comprehension is required. Explain technical results to colleagues. "
        "Query relational databases with PostgreSQL."
    )
    jobs = JobSourceService(
        jobspy_scraper=lambda **kwargs: pd.DataFrame(
            [
                {
                    "id": "association-1",
                    "title": "Data scientist",
                    "company": "Fixture company",
                    "description": description,
                    "job_url": "https://www.linkedin.com/jobs/view/association-1",
                }
            ]
        )
    )
    service = MarketSourceService(
        jobs=jobs, session_factory=lambda: Session(bind=db_session.get_bind())
    )
    config = {
        "run_id": str(run.id),
        "course_id": course["id"],
        "teacher_id": course["teacher_id"],
        **run.config,
    }
    collected = service.collect_sources(config, ["Data scientist"])

    class ExtractionLLM:
        def invoke(self, prompt, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "name": name,
                            "category": category,
                            "original_phrase": phrase,
                            "excerpt": phrase,
                            "evidence_kind": "extracted_text",
                        }
                        for name, category, phrase in [
                            (
                                "Reading Comprehension",
                                "essential",
                                "Reading Comprehension",
                            ),
                            (
                                "Explain technical results",
                                "communication",
                                "Explain technical results to colleagues",
                            ),
                            (
                                "Query relational databases",
                                "database",
                                "Query relational databases with PostgreSQL",
                            ),
                        ]
                    ]
                )
            )

    monkeypatch.setattr(
        extractor, "_get_extraction_llm", lambda **kwargs: ExtractionLLM()
    )
    monkeypatch.setattr(
        associations,
        "_get_extraction_llm",
        lambda **kwargs: SimpleNamespace(
            invoke=lambda *args, **kw: SimpleNamespace(content="[]")
        ),
    )
    with bind_tool_store({"run_id": str(run.id)}):
        extracted = extractor.extract_one({"job": collected["jobs"][0]})
    return SimpleNamespace(
        service=service,
        config=config,
        extracted=extracted,
        course=course,
        run=run,
        jobs=collected["jobs"],
        catalog=collected["onet_evidence"],
        repo=repo,
    )


def test_actual_mixed_pipeline_creates_exact_association_and_reference_support(
    mixed_pipeline,
):
    p = mixed_pipeline
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    jobs = [c for c in result["candidates"] if c["identity_key"].startswith("jobs:")]
    reading = next(c for c in jobs if c["display_name"] == "Reading Comprehension")
    assert reading["onet_associations"], (
        "production save must create the cross-source association"
    )
    evidence = reading["onet_associations"][0]["evidence"]
    assert evidence["ratings"]["IM"]["value"] == 4.2
    assert evidence["ratings"]["LV"]["value"] is None
    assert evidence["ratings"]["LV"]["status"] == "missing"
    assert evidence == next(row for row in p.catalog if row["family"] == "essential")
    reference = next(
        c
        for c in result["candidates"]
        if c["identity_key"].startswith("onet:")
        and c["display_name"] == "Reading Comprehension"
    )
    assert reference["candidate_id"] != reading["candidate_id"]
    assert reference["qualifying_posting_links"] == [
        "https://www.linkedin.com/jobs/view/association-1"
    ]
    assert reference["job_metrics"]["supporting_posting_count"] == 1


def scripted_mapping(monkeypatch, handler):
    class MappingLLM:
        def invoke(self, prompt, **kwargs):
            payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
            return SimpleNamespace(content=json.dumps(handler(payload)))

    monkeypatch.setattr(
        associations, "_get_extraction_llm", lambda **kwargs: MappingLLM()
    )


@pytest.mark.parametrize("relation", ["equivalent", "broader", "related", "unmatched"])
def test_inference_is_immutable_context_without_lending_reference_support(
    mixed_pipeline, monkeypatch, relation
):
    p = mixed_pipeline

    def mapping(payload):
        observation = next(
            o
            for o in payload["observations"]
            if o["name"] == "Explain technical results"
        )
        row = next(
            r for r in payload["catalog"] if r["label"] == "Social Perceptiveness"
        )
        return [
            {
                "observation_index": observation["observation_index"],
                "evidence_id": row["id"],
                "relation": relation,
                "rationale": "Scripted external context inference.",
            }
        ]

    scripted_mapping(monkeypatch, mapping)
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    job = next(
        c
        for c in result["candidates"]
        if c["display_name"] == "Explain technical results"
    )
    association = job["onet_associations"][0]
    assert association["relation"] == relation
    assert association["mapping_method"] == "model_context"
    assert association["evidence"] == next(
        r for r in p.catalog if r["label"] == "Social Perceptiveness"
    )
    assert association["evidence"]["ratings"]["IM"]["status"] == "suppressed"
    assert association["evidence"]["ratings"]["LV"]["status"] == "not_relevant"
    reference = next(
        c for c in result["candidates"] if c["display_name"] == "Social Perceptiveness"
    )
    assert reference["posting_support"] == "missing"
    assert reference["evidence_references"] == []
    assert reference["job_metrics"]["supporting_posting_count"] == 0
    assert job["qualifying_posting_links"] == [
        "https://www.linkedin.com/jobs/view/association-1"
    ]
    assert "onet_rating" not in job


def test_exact_reference_approval_readback_retains_original_job_link_and_ratings(
    mixed_pipeline, db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.schemas import (
        SkillReviewDraft,
        SkillReviewRevision,
    )
    from tests.market_skill_fixtures import prepare
    from tests.modules.test_market_skill_approval import approve

    p = mixed_pipeline
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    db_session.expire_all()
    run = p.repo.get_run(p.run.id, p.course["id"], p.course["teacher_id"])
    reference = next(
        c
        for c in result["candidates"]
        if c["identity_key"].startswith("onet:")
        and c["display_name"] == "Reading Comprehension"
    )
    service = SkillReviewService(p.repo)
    draft = SkillReviewDraft(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
        selected_candidate_ids=[reference["candidate_id"]],
        excluded_candidate_ids=[],
    )
    service.save_draft(p.course["id"], p.course["teacher_id"], draft)
    revision = SkillReviewRevision(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
    )
    service.confirm_selection(p.course["id"], p.course["teacher_id"], revision)
    review = prepare(service, p.course, revision, [reference])
    response = approve(
        client, teacher_auth_headers, p.course, run, review, [reference["candidate_id"]]
    )
    assert response.status_code == 200, response.text
    assert response.json()["review"]["approved_references"][0][
        "qualifying_posting_links"
    ] == ["https://www.linkedin.com/jobs/view/association-1"]
    db_session.expire_all()
    from app.modules.marketdemandanalyst.models import MarketSkillApproval

    approval = db_session.scalar(
        select(MarketSkillApproval).where(MarketSkillApproval.run_id == run.id)
    )
    assert (
        approval.items[0]["onet_bindings"][0]["evidence"]["ratings"]["IM"]["value"]
        == 4.2
    )


def test_unbacked_reference_and_broader_final_target_are_refused(
    mixed_pipeline, db_session, client, teacher_auth_headers
):
    from app.modules.marketdemandanalyst.schemas import (
        SkillReviewDraft,
        SkillReviewRevision,
    )
    from tests.market_skill_fixtures import prepare
    from tests.modules.test_market_skill_approval import approve

    p = mixed_pipeline
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    db_session.expire_all()
    run = p.repo.get_run(p.run.id, p.course["id"], p.course["teacher_id"])
    reference = next(
        c for c in result["candidates"] if c["display_name"] == "Social Perceptiveness"
    )
    service = SkillReviewService(p.repo)
    service.save_draft(
        p.course["id"],
        p.course["teacher_id"],
        SkillReviewDraft(
            run_id=run.id,
            expected_candidate_revision=run.candidate_revision,
            expected_selection_revision=run.selection_revision,
            selected_candidate_ids=[reference["candidate_id"]],
            excluded_candidate_ids=[],
        ),
    )
    revision = SkillReviewRevision(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
    )
    service.confirm_selection(p.course["id"], p.course["teacher_id"], revision)
    review = prepare(service, p.course, revision, [reference])
    response = approve(
        client, teacher_auth_headers, p.course, run, review, [reference["candidate_id"]]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "missing_job_evidence"
    supported = next(
        c
        for c in result["candidates"]
        if c["display_name"] == "Reading Comprehension"
        and c["identity_key"].startswith("jobs:")
    )
    service.save_draft(
        p.course["id"],
        p.course["teacher_id"],
        SkillReviewDraft(
            run_id=run.id,
            expected_candidate_revision=run.candidate_revision,
            expected_selection_revision=run.selection_revision,
            selected_candidate_ids=[supported["candidate_id"]],
            excluded_candidate_ids=[],
        ),
    )
    revision = SkillReviewRevision(
        run_id=run.id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
    )
    service.confirm_selection(p.course["id"], p.course["teacher_id"], revision)
    review = prepare(
        service,
        p.course,
        revision,
        [supported],
        target_label="Reading Comprehension for medical reports",
    )
    response = approve(
        client, teacher_auth_headers, p.course, run, review, [supported["candidate_id"]]
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "missing_job_evidence"


def test_repeated_extraction_preserves_reference_id_exclusion_and_pending_history(
    mixed_pipeline, db_session
):
    p = mixed_pipeline
    first = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    db_session.expire_all()
    run = p.repo.get_run(p.run.id, p.course["id"], p.course["teacher_id"])
    reference = next(
        c
        for c in first["candidates"]
        if c["display_name"] == "Reading Comprehension"
        and c["identity_key"].startswith("onet:")
    )
    p.repo.save_draft(
        run.id,
        run.course_id,
        run.teacher_id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
        selected_candidate_ids=[],
        excluded_candidate_ids=[reference["candidate_id"]],
    )
    db_session.commit()
    p.service.save_extraction(
        p.config, p.extracted["skills"][1:], p.extracted["assessments"]
    )
    restored = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    db_session.expire_all()
    run = p.repo.get_run(run.id, run.course_id, run.teacher_id)
    assert reference["candidate_id"] in run.excluded_candidate_ids
    assert (
        next(
            c
            for c in restored["candidates"]
            if c["identity_key"] == reference["identity_key"]
        )["candidate_id"]
        == reference["candidate_id"]
    )
    assert run.candidate_manifest["reconciliation_required"]
    assert any(
        r["reason"] == "candidate_no_longer_observed" and not r["resolved"]
        for r in run.candidate_manifest["reconciliations"]
    )


@pytest.mark.parametrize("change", ["config", "revision", "active_run", "purge"])
def test_post_model_revalidation_refuses_stale_run_or_discards_purged_proof(
    mixed_pipeline, db_session, monkeypatch, change
):
    from copy import deepcopy
    from datetime import UTC, datetime

    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot
    from app.modules.marketdemandanalyst.repository import RevisionConflict

    p = mixed_pipeline

    def change_during_external_call(payload):
        # A separate real SQL transaction proves no model call holds run/lifecycle locks.
        with Session(bind=db_session.get_bind()) as db:
            repo = MarketReviewRepository(db)
            repo.lock_vacancy_lifecycle()
            run = repo.get_run(
                p.run.id, p.course["id"], p.course["teacher_id"], for_update=True
            )
            if change == "config":
                run.config = {
                    **deepcopy(run.config),
                    "selected_onet_occupations": [{"soc_code": "15-1252.00"}],
                }
            elif change == "revision":
                run.candidate_revision += 1
            elif change == "active_run":
                repo.save_configuration_snapshot(
                    SkillReviewService.thread_id(run.course_id, run.teacher_id),
                    {"run_id": None},
                )
            else:
                snapshot = db.get(
                    MarketVacancySnapshot,
                    p.extracted["skills"][0]["evidence_references"][0]["snapshot_id"],
                )
                snapshot.purged_at = datetime.now(UTC)
                snapshot.status = "purged"
            db.commit()
        return []

    scripted_mapping(monkeypatch, change_during_external_call)
    if change == "purge":
        result = p.service.save_extraction(
            p.config, p.extracted["skills"], p.extracted["assessments"]
        )
        assert all(c["posting_support"] == "missing" for c in result["candidates"])
        assert result["extraction_coverage"]["status"] == "partial"
        assert "removed" in " ".join(result["extraction_coverage"]["warnings"])
    else:
        with pytest.raises(RevisionConflict):
            p.service.save_extraction(
                p.config, p.extracted["skills"], p.extracted["assessments"]
            )


def test_unselected_onet_never_retains_caller_association_or_calls_mapping(
    mixed_pipeline, db_session, monkeypatch
):
    from copy import deepcopy

    p = mixed_pipeline
    run = p.repo.get_run(p.run.id, p.course["id"], p.course["teacher_id"])
    run.config = {**deepcopy(run.config), "evidence_sources": ["jobs"]}
    db_session.commit()
    p.extracted["skills"][0]["onet_associations"] = [
        {"evidence": p.catalog[0], "relation": "equivalent"}
    ]

    def forbidden(**kwargs):
        raise AssertionError("Unselected source must not run")

    monkeypatch.setattr(associations, "_get_extraction_llm", forbidden)
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    assert all(
        c["identity_key"].startswith("jobs:") and not c["onet_associations"]
        for c in result["candidates"]
    )
    assert "association_coverage" not in result["extraction_coverage"]


@pytest.mark.parametrize("mixed_pipeline", ["multiple"], indirect=True)
def test_exact_association_preserves_each_selected_occupation_context(mixed_pipeline):
    p = mixed_pipeline
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    reading = next(
        c
        for c in result["candidates"]
        if c["display_name"] == "Reading Comprehension"
        and c["identity_key"].startswith("jobs:")
    )
    assert {a["evidence"]["soc_code"] for a in reading["onet_associations"]} == {
        "15-2051.00",
        "15-1252.00",
    }
    assert {
        a["evidence"]["occupation_title"] for a in reading["onet_associations"]
    } == {"Data Scientists", "Software Developers"}
    assert all(
        a["evidence"]["ratings"]["IM"]["value"] == 4.2
        and a["evidence"]["ratings"]["LV"]["value"] is None
        for a in reading["onet_associations"]
    )
    assert len({a["evidence"]["id"] for a in reading["onet_associations"]}) == 2


def test_inference_caps_are_visible_and_exact_matches_cover_rows_outside_caps(
    mixed_pipeline, monkeypatch
):
    from copy import deepcopy

    p = mixed_pipeline
    prototype = next(row for row in p.catalog if row["family"] == "software")
    rows = [
        {**deepcopy(prototype), "id": str(uuid4()), "workplace_example": f"Tool {i}"}
        for i in range(249)
    ]
    rare = {
        **deepcopy(p.catalog[0]),
        "id": str(uuid4()),
        "family": "essential",
        "soc_code": "99-9999.00",
        "label": "Rare context",
    }
    rows.append(rare)
    observations = [
        {**deepcopy(p.extracted["skills"][0]), "name": f"Action {i}"} for i in range(20)
    ]
    observations[-1]["name"] = "Tool 248"
    scripted_mapping(
        monkeypatch,
        lambda payload: [
            {
                "observation_index": payload["observations"][0]["observation_index"],
                "evidence_id": row["id"],
                "relation": "related",
                "rationale": "Other occupation context retained.",
            }
            for row in payload["catalog"]
            if row["id"] == rare["id"]
        ],
    )
    decisions, coverage = associations.map_associations(observations, rows)
    enriched = associations.enrich_observations(observations, rows, decisions)
    assert (
        enriched[-1]["onet_associations"][0]["evidence"]["workplace_example"]
        == "Tool 248"
    )
    assert (
        enriched[-1]["onet_associations"][0]["mapping_method"]
        == "exact_competency_identity"
    )
    assert any(
        a["evidence"]["soc_code"] == "99-9999.00"
        for a in enriched[0]["onet_associations"]
    )
    assert coverage["status"] == "partial"
    assert coverage["omitted_observations"] == 4
    assert coverage["omitted_catalog_rows"] == 50
    assert coverage["assessed_pairs"] == 3200
    assert coverage["failed_calls"] == 0
    assert len(coverage["warnings"]) == 2


def test_exact_provider_tag_supports_reference_without_broadening_specific_job_competency(
    mixed_pipeline, db_session
):
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    p = mixed_pipeline
    item = p.extracted["skills"][2]
    snapshot = db_session.get(
        MarketVacancySnapshot, item["evidence_references"][0]["snapshot_id"]
    )
    snapshot.skill_tags = ["PostgreSQL"]
    db_session.commit()
    item["evidence_references"][0].update(
        evidence_kind="provider_tag",
        original_phrase="PostgreSQL",
        excerpt=None,
        excerpt_start=None,
        excerpt_end=None,
    )
    result = p.service.save_extraction(p.config, [item], p.extracted["assessments"])
    reference = next(
        c for c in result["candidates"] if c["display_name"] == "PostgreSQL"
    )
    other = next(c for c in result["candidates"] if c["display_name"] == "MySQL")
    assert reference["job_metrics"]["supporting_posting_count"] == 1
    assert reference["onet_associations"][0]["evidence"]["ratings"] == {}
    assert other["posting_support"] == "missing"


def test_invalid_nested_or_foreign_mapping_cannot_create_source_proof(
    mixed_pipeline, monkeypatch
):
    p = mixed_pipeline
    p.extracted["skills"][1]["onet_associations"] = [
        {"evidence": p.catalog[0], "relation": "equivalent"}
    ]
    scripted_mapping(
        monkeypatch,
        lambda payload: [
            {
                "observation_index": 1,
                "evidence_id": "foreign-row",
                "relation": "equivalent",
                "rationale": "foreign",
            },
            {
                "observation_index": 1,
                "evidence_id": payload["catalog"][0]["id"],
                "relation": "equivalent",
                "rationale": "nested",
                "evidence": {"ratings": {"IM": 5}},
            },
        ],
    )
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    candidate = next(
        c
        for c in result["candidates"]
        if c["display_name"] == "Explain technical results"
    )
    assert candidate["onet_associations"] == []
    coverage = result["extraction_coverage"]
    assert coverage["status"] == "partial"
    assert coverage["assessed_postings"] == 1
    assert coverage["association_coverage"]["rejected_mappings"] == 2


def test_failed_mapping_keeps_exact_matches_and_requires_omission_acknowledgement(
    mixed_pipeline, monkeypatch
):
    p = mixed_pipeline

    def fail(*args, **kwargs):
        raise TimeoutError("external model failed")

    monkeypatch.setattr(associations, "_get_extraction_llm", fail)
    result = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    assert result["extraction_coverage"]["status"] == "partial"
    assert result["extraction_coverage"]["assessed_postings"] == 1
    assert result["extraction_coverage"]["association_coverage"]["failed_calls"] == 1
    assert next(
        c
        for c in result["candidates"]
        if c["identity_key"].startswith("jobs:")
        and c["display_name"] == "Reading Comprehension"
    )["onet_associations"]
    with pytest.raises(ValueError, match="acknowledge"):
        p.service.require_available_evidence(p.config)


@pytest.mark.parametrize("bounded", [False, True])
def test_completed_sample_stops_automatic_reextraction(
    mixed_pipeline, db_session, monkeypatch, bounded
):
    from langgraph.types import Command

    from app.modules.marketdemandanalyst import tools

    p = mixed_pipeline
    if bounded:
        monkeypatch.setattr(associations, "MAX_MAPPING_OBSERVATIONS", 1)
        monkeypatch.setattr(associations, "MAX_MAPPING_CATALOG_ROWS", 1)
    saved = p.service.save_extraction(
        p.config, p.extracted["skills"], p.extracted["assessments"]
    )
    coverage = saved["extraction_coverage"]
    assert coverage["assessed_postings"] == coverage["selected_postings"] == 1
    assert coverage["assessed_chunks"] == coverage["total_chunks"] == 1
    assert coverage["status"] == ("partial" if bounded else "full")
    assert coverage["association_coverage"]["failed_calls"] == 0
    monkeypatch.setattr(tools, "get_market_source_service", lambda: p.service)
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    state = {
        **p.config,
        "selected_jobs": p.jobs,
        "extracted_skills": [],
        "extraction_coverage": {"status": "pending"},
    }
    with bind_tool_store(state):
        result = tools.start_extraction.invoke({})
        assert not isinstance(result, Command), "Completed evidence was extracted again"
        review = json.loads(tools.get_skills_by_category.invoke({}))
    assert review["candidate_revision"] == saved["candidate_revision"]
    assert review["extraction_coverage"]["status"] == coverage["status"]
    if bounded:
        assert review["extraction_coverage"]["acknowledged"] is False
        with pytest.raises(ValueError, match="Continue"):
            p.service.require_available_evidence(p.config)
    db_session.refresh(p.run)
    assert p.run.candidate_revision == saved["candidate_revision"]
    assert not p.run.candidate_manifest.get("acknowledged_omissions")


@pytest.mark.parametrize("retry_reason", ["posting", "association", "refetch"])
def test_real_failure_or_provider_refetch_keeps_extraction_retry_available(
    mixed_pipeline, monkeypatch, retry_reason
):
    from copy import deepcopy

    from langgraph.types import Command

    from app.modules.marketdemandanalyst import tools

    p = mixed_pipeline
    assessments = deepcopy(p.extracted["assessments"])
    if retry_reason == "posting":
        assessments[0].update(status="partial", total_chunks=2, assessed_chunks=1)
    elif retry_reason == "association":

        def failed_model(**kwargs):
            raise TimeoutError("model failed")

        monkeypatch.setattr(associations, "_get_extraction_llm", failed_model)
    saved = p.service.save_extraction(p.config, p.extracted["skills"], assessments)
    if retry_reason == "refetch":
        p.service.collect_sources(p.config, ["Data scientist"])
    monkeypatch.setattr(tools, "get_market_source_service", lambda: p.service)
    state = {
        **p.config,
        "selected_jobs": p.jobs,
        "extracted_skills": saved["candidates"],
        "extraction_coverage": saved["extraction_coverage"],
    }
    with bind_tool_store(state):
        result = tools.start_extraction.invoke({})
    assert isinstance(result, Command) and result.goto == "skill_extractor"
