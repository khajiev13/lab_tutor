"""Semantic job grouping through the durable SQL extraction coordinator."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.modules.marketdemandanalyst import associations, extractor
from app.modules.marketdemandanalyst.models import MarketAnalysisRun
from app.modules.marketdemandanalyst.repository import (
    MarketReviewRepository,
    RevisionConflict,
)
from app.modules.marketdemandanalyst.schemas import ProviderVacancy
from app.modules.marketdemandanalyst.service import (
    MarketSourceService,
    available_evidence_omissions,
)


@pytest.fixture
def pipeline(db_session, client, teacher_auth_headers, monkeypatch, request):
    course = client.post(
        "/courses",
        json={"title": "Semantic job evidence"},
        headers=teacher_auth_headers,
    ).json()
    repo = MarketReviewRepository(db_session)
    run = repo.create_run(
        course["id"],
        course["teacher_id"],
        {"sources": ["headhunter"], "evidence_sources": ["jobs"]},
    )
    observations, assessments = [], []
    specifications = [
        (
            "Configure ETL pipelines",
            "Configure and maintain ETL pipelines",
            "semantic-0",
        ),
        (
            "Настраивать ETL-конвейеры",
            "Настраивать и сопровождать ETL-конвейеры",
            "semantic-1",
        ),
    ]
    if getattr(request, "param", None) == "live_etl":
        specifications = [
            ("Create ETL processes", "Create and optimize ETL processes", "131281062"),
            (
                "Develop ETL/ELT processes",
                "Разрабатывать и поддерживать ETL/ELT-процессы",
                "137349578",
            ),
        ]
    elif getattr(request, "param", None) == "inverse_mentoring":
        specifications = [
            (
                "Provide mentoring to junior analysts",
                "Mentor junior analysts",
                "mentor",
            ),
            (
                "Receive mentoring from experienced specialists",
                "Receive mentoring from experienced specialists",
                "mentee",
            ),
        ]
    for name, phrase, native_id in specifications:
        text = f"Required work: {phrase}. Monitor ETL pipeline failures."
        snapshot = repo.upsert_vacancy_snapshot(
            run.id,
            ProviderVacancy(
                provider="headhunter",
                native_id=native_id,
                title="Data engineer",
                original_url=f"https://hh.uz/vacancy/{native_id}"
                + (
                    "?tech_source=api"
                    if getattr(request, "param", None) == "live_etl"
                    else ""
                ),
                original_description=text,
                description_text=text,
            ),
        )
        observations.append(
            {
                "name": name,
                "category": "data_processing",
                "identity_key": f"jobs:{native_id}",
                "evidence_references": [
                    {
                        "snapshot_id": str(snapshot.id),
                        "provider": snapshot.provider,
                        "original_url": snapshot.original_url,
                        "original_phrase": phrase,
                        "evidence_kind": "extracted_text",
                        "excerpt": text,
                        "excerpt_start": 0,
                        "excerpt_end": len(text),
                    }
                ],
            }
        )
        assessments.append(
            {
                "snapshot_id": str(snapshot.id),
                "demand_identity": snapshot.demand_identity,
                "status": "full",
                "total_chunks": 1,
                "assessed_chunks": 1,
                "warnings": [],
            }
        )
    db_session.commit()
    sessions, calls = [], []

    def session_factory():
        session = Session(bind=db_session.get_bind())
        sessions.append(session)
        return session

    fixture = SimpleNamespace(
        config={
            "run_id": str(run.id),
            "course_id": course["id"],
            "teacher_id": course["teacher_id"],
        },
        observations=observations,
        assessments=assessments,
        service=MarketSourceService(session_factory=session_factory),
        calls=calls,
        handler=lambda payload: [],
        repo=repo,
        run=run,
        db=db_session,
    )

    class GroupingLLM:
        def invoke(self, prompt, **kwargs):
            assert all(not session.in_transaction() for session in sessions)
            payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
            calls.append(payload)
            return SimpleNamespace(content=json.dumps(fixture.handler(payload)))

    monkeypatch.setattr(
        extractor, "_get_extraction_llm", lambda **kwargs: GroupingLLM()
    )
    monkeypatch.setattr(
        associations,
        "_get_extraction_llm",
        lambda **kwargs: SimpleNamespace(
            invoke=lambda *args, **kw: SimpleNamespace(content="[]")
        ),
    )
    return fixture


def all_equivalent(payload):
    ids = [row["observation_id"] for row in payload["observations"]]
    return [{"canonical_id": ids[0], "member_ids": ids}]


def confirm_prior_equivalence(payload):
    groups = all_equivalent(payload)
    groups[0]["prior_candidate_id"] = payload["prior_candidates"][0]["candidate_id"]
    return groups


def save(pipeline, observations=None):
    return pipeline.service.save_extraction(
        pipeline.config,
        pipeline.observations if observations is None else observations,
        pipeline.assessments,
    )


def stored(pipeline):
    pipeline.db.expire_all()
    return pipeline.db.get(MarketAnalysisRun, UUID(pipeline.config["run_id"]))


def draft(pipeline, selected, excluded):
    run = stored(pipeline)
    pipeline.repo.save_draft(
        run.id,
        run.course_id,
        run.teacher_id,
        expected_candidate_revision=run.candidate_revision,
        expected_selection_revision=run.selection_revision,
        selected_candidate_ids=selected,
        excluded_candidate_ids=excluded,
    )
    pipeline.db.commit()


def test_equivalent_translations_union_exact_sources_and_unique_job_metrics(pipeline):
    pipeline.handler = all_equivalent
    originals = deepcopy(pipeline.observations)
    # Multiple chunk hits for one posting are evidence, not additional demand.
    result = save(pipeline, [*originals, deepcopy(originals[0])])
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["display_name"] == "Configure ETL pipelines"
    assert set(candidate["original_labels"]) == {row["name"] for row in originals}
    assert "Настраивать ETL-конвейеры" in candidate["aliases"]
    assert candidate["qualifying_posting_links"] == [
        "https://hh.uz/vacancy/semantic-0",
        "https://hh.uz/vacancy/semantic-1",
    ]
    assert candidate["evidence_references"] == [
        row["evidence_references"][0] for row in originals
    ]
    assert candidate["job_metrics"]["supporting_posting_count"] == 2
    assert candidate["job_metrics"]["percentage"] == 100.0
    assert len(candidate["supporting_identities"]) == 2
    assert stored(pipeline).candidate_manifest["candidates"] == result["candidates"]
    assert originals == pipeline.observations


@pytest.mark.parametrize("pipeline", ["live_etl"], indirect=True)
def test_create_and_develop_etl_keep_the_supplied_original_hh_phrases(pipeline):
    pipeline.handler = all_equivalent
    result = save(pipeline)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["display_name"] == "Create ETL processes"
    assert candidate["aliases"] == ["Develop ETL/ELT processes"]
    assert set(candidate["supporting_identities"]) == {
        "headhunter:id:131281062",
        "headhunter:id:137349578",
    }
    assert candidate["qualifying_posting_links"] == [
        "https://hh.uz/vacancy/131281062?tech_source=api",
        "https://hh.uz/vacancy/137349578?tech_source=api",
    ]
    assert {ref["original_phrase"] for ref in candidate["evidence_references"]} == {
        "Create and optimize ETL processes",
        "Разрабатывать и поддерживать ETL/ELT-процессы",
    }
    assert candidate["job_metrics"]["supporting_posting_count"] == 2


def test_omitted_task_stays_separate_instead_of_disappearing(pipeline):
    other = deepcopy(pipeline.observations[0])
    other.update(name="Monitor pipeline failures", identity_key="jobs:monitor")
    other["evidence_references"][0]["original_phrase"] = "Monitor ETL pipeline failures"

    def groups(payload):
        ids = [row["observation_id"] for row in payload["observations"][:2]]
        return [{"canonical_id": ids[0], "member_ids": ids}]

    pipeline.handler = groups
    result = save(pipeline, [*pipeline.observations, other])
    assert {row["display_name"] for row in result["candidates"]} == {
        "Configure ETL pipelines",
        "Monitor pipeline failures",
    }
    assert (
        result["extraction_coverage"]["semantic_grouping"]["omitted_observations"] == 1
    )
    assert (
        result["extraction_coverage"]["semantic_grouping"]["warnings"][0]
        in result["extraction_coverage"]["warnings"]
    )


def test_related_tasks_using_the_same_technology_remain_distinct(pipeline):
    other = deepcopy(pipeline.observations[0])
    other.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    other["evidence_references"][0]["original_phrase"] = other["name"]
    pipeline.handler = lambda payload: [
        {"canonical_id": row["observation_id"], "member_ids": [row["observation_id"]]}
        for row in payload["observations"]
    ]
    result = save(pipeline, [pipeline.observations[0], other])
    assert {row["display_name"] for row in result["candidates"]} == {
        "Configure ETL pipelines",
        "Monitor ETL pipeline failures",
    }
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"


def _enable_onet(pipeline):
    from app.modules.occupation_reference.importer import parse_release
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )

    catalog = OccupationReferenceRepository(pipeline.db)
    catalog.import_release(
        parse_release(Path(__file__).parents[1] / "fixtures/onet/31.0", "31.0"),
        activate=True,
    )
    run = stored(pipeline)
    run.config = {
        **run.config,
        "evidence_sources": ["jobs", "onet"],
        "onet_release": "31.0",
        "onet_selection_confirmed": True,
        "selected_onet_occupations": [{"soc_code": "15-2051.00"}],
    }
    pipeline.repo.save_configuration_snapshot(
        f"mda-{run.teacher_id}-course-{run.course_id}", {"run_id": str(run.id)}
    )
    pipeline.db.commit()


def test_shared_occupation_descriptor_is_context_not_a_job_grouping_key(
    pipeline, monkeypatch
):
    _enable_onet(pipeline)
    other = deepcopy(pipeline.observations[0])
    other.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    other["evidence_references"][0]["original_phrase"] = other["name"]
    pipeline.handler = lambda payload: [
        {"canonical_id": row["observation_id"], "member_ids": [row["observation_id"]]}
        for row in payload["observations"]
    ]

    class ContextLLM:
        def invoke(self, prompt, **kwargs):
            payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
            descriptor = next(
                row
                for row in payload["catalog"]
                if row["label"] == "Reading Comprehension"
            )
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "observation_index": row["observation_index"],
                            "evidence_id": descriptor["id"],
                            "relation": "related",
                            "rationale": "Context only; interpreting instructions supports both tasks.",
                        }
                        for row in payload["observations"]
                    ]
                )
            )

    monkeypatch.setattr(
        associations, "_get_extraction_llm", lambda **kwargs: ContextLLM()
    )
    result = save(pipeline, [pipeline.observations[0], other])
    jobs = [
        row for row in result["candidates"] if row["identity_key"].startswith("jobs:")
    ]
    assert len(jobs) == 2
    official = jobs[0]["onet_associations"][0]["evidence"]
    assert jobs[1]["onet_associations"][0]["evidence"] == official
    assert official["release"] == "31.0" and official["soc_code"] == "15-2051.00"
    assert official["ratings"]["IM"]["value"] == 4.2
    assert official["ratings"]["LV"]["status"] == "missing"
    reference = next(
        row
        for row in result["candidates"]
        if row["identity_key"].startswith("onet:")
        and row["display_name"] == official["label"]
    )
    assert reference["job_metrics"]["supporting_posting_count"] == 0
    assert reference["evidence_references"] == []


@pytest.mark.parametrize(
    "invalid", ["unknown", "repeated", "overlap", "canonical", "fabricated"]
)
def test_invalid_model_membership_preserves_original_evidence(pipeline, invalid):
    def groups(payload):
        ids = [row["observation_id"] for row in payload["observations"]]
        group = {"canonical_id": ids[0], "member_ids": ids}
        if invalid == "unknown":
            group["member_ids"] = [*ids, "invented-member"]
        elif invalid == "repeated":
            group["member_ids"] = [*ids, ids[0]]
        elif invalid == "overlap":
            return [group, {"canonical_id": ids[0], "member_ids": [ids[0]]}]
        elif invalid == "canonical":
            group["canonical_id"] = "invented-member"
        else:
            group["original_url"] = "https://fabricated.test/posting"
        return [group]

    pipeline.handler = groups
    result = save(pipeline)
    assert len(pipeline.calls) == 2
    assert len(result["candidates"]) == 2
    refs = [ref for row in result["candidates"] for ref in row["evidence_references"]]
    assert refs == [row["evidence_references"][0] for row in pipeline.observations]
    assert "fabricated.test" not in json.dumps(result)
    status = result["extraction_coverage"]["semantic_grouping"]
    assert status["status"] == "error"
    assert status["warnings"]


def test_model_failure_retains_sources_and_does_not_repeat_assessed_sample(pipeline):
    def fail(payload):
        raise TimeoutError("private provider detail")

    pipeline.handler = fail
    result = save(pipeline)
    assert len(pipeline.calls) == 1
    assert len(result["candidates"]) == 2
    assert result["extraction_coverage"]["status"] == "full"
    status = result["extraction_coverage"]["semantic_grouping"]
    assert status["status"] == "error"
    assert status["warnings"] and "private provider detail" not in json.dumps(result)
    assert set(status["warnings"]) <= set(result["extraction_coverage"]["warnings"])
    jobs = [{"snapshot_id": row["snapshot_id"]} for row in pipeline.assessments]
    assert pipeline.service.extraction_is_complete(pipeline.config, jobs)
    pipeline.service.require_available_evidence(pipeline.config)


def test_grouping_advisory_does_not_repeat_fixed_bounds_or_add_source_omissions(
    pipeline, monkeypatch
):
    _enable_onet(pipeline)
    monkeypatch.setattr(associations, "MAX_MAPPING_OBSERVATIONS", 1)
    monkeypatch.setattr(associations, "MAX_MAPPING_CATALOG_ROWS", 1)
    pipeline.handler = lambda payload: []
    result = save(pipeline)
    coverage = result["extraction_coverage"]
    assert coverage["status"] == "partial"
    advisory = set(coverage["semantic_grouping"]["warnings"])
    assert advisory and advisory <= set(coverage["warnings"])
    jobs = [{"snapshot_id": row["snapshot_id"]} for row in pipeline.assessments]
    assert pipeline.service.extraction_is_complete(pipeline.config, jobs)
    assert advisory.isdisjoint(available_evidence_omissions(stored(pipeline)))


def test_real_failed_posting_still_requires_retry_or_source_acknowledgment(pipeline):
    pipeline.assessments[0].update(
        status="failed", assessed_chunks=0, warnings=["Posting chunk failed; retry."]
    )
    result = save(pipeline)
    assert result["extraction_coverage"]["status"] == "partial"
    jobs = [{"snapshot_id": row["snapshot_id"]} for row in pipeline.assessments]
    assert not pipeline.service.extraction_is_complete(pipeline.config, jobs)
    with pytest.raises(ValueError, match="acknowledge"):
        pipeline.service.require_available_evidence(pipeline.config)


def test_selected_canonical_survives_new_equivalent_group_and_failed_rerun(pipeline):
    initial = save(pipeline)["candidates"]
    selected_id = initial[0]["candidate_id"]
    draft(pipeline, [selected_id], [])

    def choose_translation(payload):
        ids = [row["observation_id"] for row in payload["observations"]]
        return [{"canonical_id": ids[-1], "member_ids": ids}]

    pipeline.handler = choose_translation
    merged = save(pipeline)
    assert len(merged["candidates"]) == 1
    assert merged["candidates"][0]["candidate_id"] == selected_id
    assert merged["candidates"][0]["display_name"] == "Configure ETL pipelines"
    assert stored(pipeline).selected_candidate_ids == [selected_id]
    pipeline.handler = lambda payload: pytest.fail(
        "Known equivalence should reuse its registry"
    )
    repeated = save(pipeline, list(reversed(pipeline.observations)))
    assert repeated["candidates"][0]["candidate_id"] == selected_id
    assert stored(pipeline).selected_candidate_ids == [selected_id]


def test_local_handles_round_trip_full_identities_and_prior_candidate_uuid(pipeline):
    for index, item in enumerate(pipeline.observations):
        item["identity_key"] = "jobs:" + ("a" if index == 0 else "b") * 64

    def grouping(payload):
        assert [row["observation_id"] for row in payload["observations"]] == [
            "o0",
            "o1",
        ]
        assert all(
            item["identity_key"] not in json.dumps(payload)
            for item in pipeline.observations
        )
        return all_equivalent(payload)

    pipeline.handler = grouping
    first = save(pipeline)["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    changed = deepcopy(pipeline.observations)
    for index, item in enumerate(changed):
        item.update(
            name="Set up ETL pipelines",
            identity_key="jobs:" + ("c" if index == 0 else "d") * 64,
        )

    def confirmation(payload):
        assert payload["prior_candidates"][0]["candidate_id"] == "p0"
        assert first["candidate_id"] not in json.dumps(payload)
        return confirm_prior_equivalence(payload)

    pipeline.handler = confirmation
    repeated = save(pipeline, changed)
    assert repeated["candidates"][0]["candidate_id"] == first["candidate_id"]
    assert set(repeated["candidates"][0]["semantic_identity_keys"]) == {
        item["identity_key"] for item in [*pipeline.observations, *changed]
    }
    assert repeated["candidates"][0]["job_metrics"]["supporting_posting_count"] == 2


def test_changed_display_names_reuse_the_same_validated_claim_and_saved_selection(
    pipeline,
):
    pipeline.handler = all_equivalent
    first = save(pipeline)["candidates"][0]
    selected_id = first["candidate_id"]
    draft(pipeline, [selected_id], [])
    changed = deepcopy(pipeline.observations)
    for index, item in enumerate(changed):
        item["name"] = ["Set up ETL pipelines", "Настроить ETL-конвейеры"][index]
        item["identity_key"] = f"jobs:changed-label-{index}"
    calls_before = len(pipeline.calls)
    pipeline.handler = confirm_prior_equivalence
    repeated = save(pipeline, changed)
    assert len(repeated["candidates"]) == 1
    candidate = repeated["candidates"][0]
    assert candidate["candidate_id"] == selected_id
    assert candidate["display_name"] == "Configure ETL pipelines"
    assert set(candidate["original_labels"]) == {
        "Configure ETL pipelines",
        "Настраивать ETL-конвейеры",
        "Set up ETL pipelines",
        "Настроить ETL-конвейеры",
    }
    assert set(candidate["aliases"]) == set(candidate["original_labels"]) - {
        candidate["display_name"]
    }
    assert candidate["evidence_references"] == first["evidence_references"]
    assert stored(pipeline).selected_candidate_ids == [selected_id]
    assert len(pipeline.calls) == calls_before + 1


def test_official_context_claim_cannot_block_the_job_canonical_on_a_changed_label(
    pipeline,
):
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    _enable_onet(pipeline)
    text = "Reading Comprehension is required for the work."
    for index, item in enumerate(pipeline.observations):
        item["name"] = ["Reading Comprehension", "Comprehend written information"][
            index
        ]
        ref = item["evidence_references"][0]
        row = pipeline.db.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
        row.description_text = row.original_description = text
        ref.update(
            original_phrase="Reading Comprehension", excerpt=text, excerpt_end=len(text)
        )
    pipeline.db.commit()
    pipeline.handler = all_equivalent
    first = next(
        row
        for row in save(pipeline)["candidates"]
        if row["identity_key"].startswith("jobs:")
    )
    draft(pipeline, [first["candidate_id"]], [])
    changed = deepcopy(pipeline.observations)
    for index, item in enumerate(changed):
        item.update(
            name="Understand written information",
            identity_key=f"jobs:changed-reading-{index}",
        )
    pipeline.handler = confirm_prior_equivalence
    repeated = save(pipeline, changed)
    jobs = [
        row for row in repeated["candidates"] if row["identity_key"].startswith("jobs:")
    ]
    assert len(jobs) == 1
    assert jobs[0]["candidate_id"] == first["candidate_id"]
    assert stored(pipeline).selected_candidate_ids == [first["candidate_id"]]


def test_a_different_claim_in_the_same_posting_does_not_reuse_the_selected_identity(
    pipeline,
):
    pipeline.handler = all_equivalent
    first = save(pipeline)["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    other = deepcopy(pipeline.observations[0])
    other.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    other["evidence_references"][0]["original_phrase"] = other["name"]
    result = save(pipeline, [other])
    assert result["candidates"][0]["candidate_id"] != first["candidate_id"]
    assert result["candidates"][0]["display_name"] == other["name"]
    assert stored(pipeline).selected_candidate_ids == []
    assert stored(pipeline).candidate_manifest["reconciliation_required"]


def compound_configure_claim(pipeline):
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    item = deepcopy(pipeline.observations[0])
    text = "Configure ETL pipelines and monitor ETL pipeline failures."
    ref = item["evidence_references"][0]
    row = pipeline.db.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
    row.description_text = row.original_description = text
    ref.update(original_phrase=text, excerpt=text, excerpt_end=len(text))
    pipeline.db.commit()
    return item


@pytest.mark.parametrize("decision", ["distinct", "omitted", "failure"])
def test_same_compound_quote_does_not_transfer_configure_selection_to_monitor(
    pipeline, decision
):
    from app.modules.marketdemandanalyst.evidence import reference_fingerprint

    configure = compound_configure_claim(pipeline)
    first = save(pipeline, [configure])["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    monitor = deepcopy(configure)
    monitor.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    assert reference_fingerprint(
        configure["evidence_references"][0]
    ) == reference_fingerprint(monitor["evidence_references"][0])

    def response(payload):
        assert payload["prior_candidates"][0]["name"] == "Configure ETL pipelines"
        if decision == "failure":
            raise TimeoutError("private classification detail")
        return all_equivalent(payload) if decision == "distinct" else []

    pipeline.handler = response
    result = save(pipeline, [monitor])
    candidate = result["candidates"][0]
    assert candidate["display_name"] == "Monitor ETL pipeline failures"
    assert candidate["candidate_id"] != first["candidate_id"]
    assert candidate["evidence_references"] == monitor["evidence_references"]
    assert stored(pipeline).selected_candidate_ids == []
    record = stored(pipeline).candidate_manifest["reconciliations"][0]
    assert record["reason"] == "candidate_no_longer_observed"
    assert record["previous_selected_candidate_ids"] == [first["candidate_id"]]
    assert len(pipeline.calls) == 1


@pytest.mark.parametrize(
    "invalid", ["unknown_prior", "prior_as_member", "repeated_prior", "split_known"]
)
def test_invalid_historical_confirmation_cannot_transfer_teacher_choices(
    pipeline, invalid
):
    configure = compound_configure_claim(pipeline)
    first = save(pipeline, [configure])["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    monitor = deepcopy(configure)
    monitor.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    current = [monitor]
    if invalid == "repeated_prior":
        setup = deepcopy(configure)
        setup.update(name="Set up ETL pipelines", identity_key="jobs:setup")
        current.append(setup)
    elif invalid == "split_known":
        current.append(configure)

    def response(payload):
        prior_handle = payload["prior_candidates"][0]["candidate_id"]
        groups = [
            {
                "canonical_id": row["observation_id"],
                "member_ids": [row["observation_id"]],
                "prior_candidate_id": prior_handle,
            }
            for row in payload["observations"]
        ]
        if invalid == "unknown_prior":
            groups[0]["prior_candidate_id"] = "fabricated-prior"
        elif invalid == "prior_as_member":
            groups[0]["member_ids"].append(prior_handle)
        elif invalid == "split_known":
            groups[1].pop("prior_candidate_id")
        return groups

    pipeline.handler = response
    result = save(pipeline, current)
    assert {row["display_name"] for row in result["candidates"]} == {
        row["name"] for row in current
    }
    assert stored(pipeline).selected_candidate_ids == (
        [first["candidate_id"]] if invalid == "split_known" else []
    )
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "error"


def test_configure_and_monitor_in_the_same_quote_remain_two_current_tasks(pipeline):
    configure = compound_configure_claim(pipeline)
    first = save(pipeline, [configure])["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    monitor = deepcopy(configure)
    monitor.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    pipeline.handler = lambda payload: [
        {"canonical_id": row["observation_id"], "member_ids": [row["observation_id"]]}
        for row in payload["observations"]
    ]
    result = save(pipeline, [configure, monitor])
    assert {row["display_name"] for row in result["candidates"]} == {
        "Configure ETL pipelines",
        "Monitor ETL pipeline failures",
    }
    assert stored(pipeline).selected_candidate_ids == [first["candidate_id"]]


def test_selected_and_excluded_equivalent_members_require_explicit_reconciliation(
    pipeline,
):
    initial = save(pipeline)["candidates"]
    selected_id, excluded_id = [row["candidate_id"] for row in initial]
    draft(pipeline, [selected_id], [excluded_id])
    pipeline.handler = all_equivalent
    result = save(pipeline)
    assert len(result["candidates"]) == 1
    run = stored(pipeline)
    assert run.selected_candidate_ids == []
    assert run.excluded_candidate_ids == [result["candidates"][0]["candidate_id"]]
    assert run.candidate_manifest["reconciliation_required"]
    record = run.candidate_manifest["reconciliations"][0]
    assert record["reason"] == "conflicting_teacher_decisions"
    assert record["previous_selected_candidate_ids"] == [selected_id]
    assert record["previous_excluded_candidate_ids"] == [excluded_id]
    assert not record["resolved"]
    repeated = save(pipeline)
    assert (
        repeated["candidates"][0]["candidate_id"]
        == result["candidates"][0]["candidate_id"]
    )
    assert stored(pipeline).excluded_candidate_ids == [
        repeated["candidates"][0]["candidate_id"]
    ]
    assert stored(pipeline).candidate_manifest["reconciliations"] == [record]


def renamed_setup_observations(pipeline):
    changed = deepcopy(pipeline.observations)
    for index, item in enumerate(changed):
        item.update(
            name=["Set up ETL pipelines", "Настроить ETL-конвейеры"][index],
            identity_key=f"jobs:renamed-setup-{index}",
        )
    return changed


@pytest.mark.parametrize("protected", [False, True], ids=["unselected", "conflict"])
def test_both_renamed_equivalents_preserve_all_confirmed_prior_labels_and_choices(
    pipeline, protected
):
    initial = save(pipeline)["candidates"]
    selected_id, excluded_id = [row["candidate_id"] for row in initial]
    if protected:
        draft(pipeline, [selected_id], [excluded_id])
    changed = renamed_setup_observations(pipeline)

    def confirmation(payload):
        groups = all_equivalent(payload)
        groups[0]["prior_candidate_ids"] = [
            row["candidate_id"] for row in payload["prior_candidates"]
        ]
        return groups

    pipeline.handler = confirmation
    result = save(pipeline, changed)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert set(candidate["original_labels"]) == {
        "Configure ETL pipelines",
        "Настраивать ETL-конвейеры",
        "Set up ETL pipelines",
        "Настроить ETL-конвейеры",
    }
    assert set(candidate["aliases"]) == set(candidate["original_labels"]) - {
        candidate["display_name"]
    }
    assert candidate["evidence_references"] == [
        row["evidence_references"][0] for row in changed
    ]
    assert candidate["job_metrics"]["supporting_posting_count"] == 2
    run = stored(pipeline)
    assert run.selected_candidate_ids == []
    if protected:
        assert run.excluded_candidate_ids == [candidate["candidate_id"]]
        assert run.candidate_manifest["reconciliation_required"]
        record = run.candidate_manifest["reconciliations"][0]
        assert record["reason"] == "conflicting_teacher_decisions"
        assert record["previous_selected_candidate_ids"] == [selected_id]
        assert record["previous_excluded_candidate_ids"] == [excluded_id]
        assert not record["resolved"]
    else:
        assert run.excluded_candidate_ids == []
        assert candidate["candidate_id"] in {selected_id, excluded_id}
        assert not run.candidate_manifest["reconciliation_required"]


@pytest.mark.parametrize("field", ["prior_candidate_id", "prior_candidate_ids"])
def test_incomplete_renamed_confirmation_cannot_drop_an_excluded_equivalent(
    pipeline, field
):
    initial = save(pipeline)["candidates"]
    selected_id, excluded_id = [row["candidate_id"] for row in initial]
    draft(pipeline, [selected_id], [excluded_id])
    changed = renamed_setup_observations(pipeline)

    def incomplete_confirmation(payload):
        groups = all_equivalent(payload)
        selected_handle = next(
            row["candidate_id"]
            for row in payload["prior_candidates"]
            if row["name"] == "Configure ETL pipelines"
        )
        groups[0][field] = (
            selected_handle if field == "prior_candidate_id" else [selected_handle]
        )
        return groups

    pipeline.handler = incomplete_confirmation
    result = save(pipeline, changed)
    assert stored(pipeline).selected_candidate_ids == []
    assert {row["display_name"] for row in result["candidates"]} == {
        "Set up ETL pipelines",
        "Настроить ETL-конвейеры",
    }
    assert [
        ref for row in result["candidates"] for ref in row["evidence_references"]
    ] == [row["evidence_references"][0] for row in changed]
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "error"
    records = stored(pipeline).candidate_manifest["reconciliations"]
    assert any(
        excluded_id in record["previous_excluded_candidate_ids"]
        and not record["resolved"]
        for record in records
    )


@pytest.mark.parametrize("invalid", ["duplicate", "unknown", "not_list", "unrelated"])
def test_historical_confirmation_list_rejects_invalid_or_unrelated_members(
    pipeline, invalid
):
    initial = save(pipeline)["candidates"]
    draft(
        pipeline,
        [initial[0]["candidate_id"]],
        [initial[1]["candidate_id"]],
    )
    changed = renamed_setup_observations(pipeline)

    def response(payload):
        groups = all_equivalent(payload)
        prior_ids = [row["candidate_id"] for row in payload["prior_candidates"]]
        groups[0]["prior_candidate_ids"] = prior_ids
        if invalid == "duplicate":
            groups[0]["prior_candidate_ids"].append(prior_ids[0])
        elif invalid == "unknown":
            groups[0]["prior_candidate_ids"].append("fabricated-prior")
        elif invalid == "not_list":
            groups[0]["prior_candidate_ids"] = prior_ids[0]
        else:
            groups = [
                {
                    "canonical_id": row["observation_id"],
                    "member_ids": [row["observation_id"]],
                    "prior_candidate_ids": prior_ids,
                }
                for row in payload["observations"]
            ]
        return groups

    pipeline.handler = response
    result = save(pipeline, changed)
    assert len(result["candidates"]) == 2
    assert stored(pipeline).selected_candidate_ids == []
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "error"
    assert [
        ref for row in result["candidates"] for ref in row["evidence_references"]
    ] == [row["evidence_references"][0] for row in changed]


def test_separate_known_excluded_task_is_accounted_for_during_prior_confirmation(
    pipeline,
):
    configure = compound_configure_claim(pipeline)
    monitor = deepcopy(configure)
    monitor.update(name="Monitor ETL pipeline failures", identity_key="jobs:monitor")
    pipeline.handler = lambda payload: [
        {"canonical_id": row["observation_id"], "member_ids": [row["observation_id"]]}
        for row in payload["observations"]
    ]
    initial = save(pipeline, [configure, monitor])["candidates"]
    selected_id, excluded_id = [row["candidate_id"] for row in initial]
    draft(pipeline, [selected_id], [excluded_id])
    setup = deepcopy(configure)
    setup.update(name="Set up ETL pipelines", identity_key="jobs:setup")

    def response(payload):
        prior_id = next(
            row["candidate_id"]
            for row in payload["prior_candidates"]
            if row["name"] == "Configure ETL pipelines"
        )
        return [
            {
                "canonical_id": row["observation_id"],
                "member_ids": [row["observation_id"]],
                **(
                    {"prior_candidate_ids": [prior_id]}
                    if row["name"] == "Set up ETL pipelines"
                    else {}
                ),
            }
            for row in payload["observations"]
        ]

    pipeline.handler = response
    result = save(pipeline, [setup, monitor])
    assert len(result["candidates"]) == 2
    assert stored(pipeline).selected_candidate_ids == [selected_id]
    assert stored(pipeline).excluded_candidate_ids == [excluded_id]
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"
    assert not stored(pipeline).candidate_manifest["reconciliation_required"]
    selected = next(
        row for row in result["candidates"] if row["candidate_id"] == selected_id
    )
    assert selected["aliases"] == ["Set up ETL pipelines"]


@pytest.mark.parametrize("changed", ["candidate_revision", "selection_revision"])
def test_revision_change_during_grouping_cannot_overwrite_teacher_state(
    pipeline, changed
):
    before = deepcopy(stored(pipeline).candidate_manifest)

    def concurrent_change(payload):
        run = stored(pipeline)
        setattr(run, changed, getattr(run, changed) + 1)
        pipeline.db.commit()
        return all_equivalent(payload)

    pipeline.handler = concurrent_change
    with pytest.raises(RevisionConflict):
        save(pipeline)
    assert stored(pipeline).candidate_manifest == before


def test_foreign_teacher_cannot_send_owned_postings_for_grouping(pipeline):
    pipeline.config["teacher_id"] += 1
    with pytest.raises(LookupError):
        save(pipeline)
    assert pipeline.calls == []


@pytest.mark.parametrize("old_version", [None, 1])
def test_corrected_extraction_can_replace_obsolete_assessment_once(
    pipeline, old_version
):
    save(pipeline)
    jobs = [{"snapshot_id": item["snapshot_id"]} for item in pipeline.assessments]
    assert pipeline.service.extraction_is_complete(pipeline.config, jobs)
    run = stored(pipeline)
    coverage = deepcopy(run.extraction_coverage)
    coverage["extraction_version"] = old_version
    run.extraction_coverage = coverage
    pipeline.db.commit()
    assert not pipeline.service.extraction_is_complete(pipeline.config, jobs)
    save(pipeline)
    assert pipeline.service.extraction_is_complete(pipeline.config, jobs)


def test_shorter_validated_quote_can_confirm_same_task_without_losing_choice(pipeline):
    pipeline.handler = all_equivalent
    first = save(pipeline)["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    changed = deepcopy(pipeline.observations)
    for index, item in enumerate(changed):
        item.update(name="Set up ETL pipelines", identity_key=f"jobs:shorter-{index}")
        ref = item["evidence_references"][0]
        quote = ref["original_phrase"]
        offset = ref["excerpt"].index(quote)
        ref.update(excerpt=quote, excerpt_start=offset, excerpt_end=offset + len(quote))
    pipeline.handler = confirm_prior_equivalence
    result = save(pipeline, changed)
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["candidate_id"] == first["candidate_id"]
    assert stored(pipeline).selected_candidate_ids == [first["candidate_id"]]
    assert candidate["evidence_references"] == [
        c["evidence_references"][0] for c in changed
    ]
    assert candidate["job_metrics"]["supporting_posting_count"] == 2


def test_long_source_sample_137_can_group_without_discarding_stored_text(pipeline):
    from app.modules.marketdemandanalyst.models import MarketVacancySnapshot

    for item in pipeline.observations:
        ref = item["evidence_references"][0]
        text = "Context. " * 90 + ref["original_phrase"] + ". End."
        row = pipeline.db.get(MarketVacancySnapshot, UUID(ref["snapshot_id"]))
        row.original_description = row.description_text = text
        ref.update(excerpt=text, excerpt_end=len(text))
    pipeline.db.commit()
    many = []
    for index in range(137):
        item = deepcopy(pipeline.observations[index % 2])
        item.update(
            name=f"Configure ETL pipelines variant {index}",
            identity_key=f"jobs:variant-{index}",
        )
        many.append(item)

    def groups(payload):
        assert (
            len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
            < 64 * 1024
        )
        assert all(row["passages"] for row in payload["observations"])
        assert all(
            "ETL" in json.dumps(row["passages"]) for row in payload["observations"]
        )
        return all_equivalent(payload)

    pipeline.handler = groups
    result = save(pipeline, many)
    assert len(result["candidates"]) == 1
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"
    assert result["candidates"][0]["job_metrics"]["supporting_posting_count"] == 2
    assert all(
        len(ref["excerpt"]) > 800
        for ref in result["candidates"][0]["evidence_references"]
    )


@pytest.mark.parametrize("count", [180, 250])
def test_complete_large_sample_groups_in_one_bounded_request_without_losing_sources(
    pipeline, monkeypatch, count
):
    observations = []
    for index in range(count):
        item = deepcopy(pipeline.observations[index % 2])
        item.update(
            name=f"Perform distinct competency {index}", identity_key=f"jobs:{index}"
        )
        ref = item["evidence_references"][0]
        ref["original_phrase"] = ref["excerpt"] = "Exact saved work evidence. " * 18
        ref["excerpt_end"] = len(ref["excerpt"])
        observations.append(item)
    original = deepcopy(observations)
    calls = []
    timeouts = []

    class Model:
        def invoke(self, prompt, **kwargs):
            payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
            calls.append((payload, kwargs))
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "canonical_id": row["observation_id"],
                            "member_ids": [row["observation_id"]],
                        }
                        for row in payload["observations"]
                    ]
                ),
                response_metadata={},
            )

    def factory(*, timeout_seconds):
        timeouts.append(timeout_seconds)
        return Model()

    monkeypatch.setattr(extractor, "_get_extraction_llm", factory)
    result, coverage = extractor.merge_evidenced_skills(observations, {})

    assert coverage["status"] == "full"
    assert coverage["input_competencies"] == coverage["output_competencies"] == count
    assert coverage["omitted_observations"] == 0
    assert len(calls) == 1
    payload, options = calls[0]
    assert (
        64 * 1024
        < len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
        <= 128 * 1024
    )
    assert [item["name"] for item in result] == [item["name"] for item in original]
    assert [item["evidence_references"] for item in result] == [
        item["evidence_references"] for item in original
    ]
    assert observations == original
    assert 45 * count <= options["max_tokens"] <= 12_000
    assert options["config"]["tags"] == ["nostream"]
    assert timeouts == [90]


@pytest.mark.parametrize("bound", ["count", "bytes"])
def test_semantic_input_above_new_bound_keeps_all_original_observations(
    pipeline, bound
):
    observations = []
    for index in range(251 if bound == "count" else 2):
        item = deepcopy(pipeline.observations[index % 2])
        item.update(
            name=("x" * (70 * 1024) if bound == "bytes" else "Task") + str(index),
            identity_key=f"jobs:limit-{index}",
        )
        observations.append(item)
    pipeline.handler = lambda payload: pytest.fail(
        "Oversized input must not reach model"
    )
    result, coverage = extractor.merge_evidenced_skills(observations, {})
    assert len(result) == len(observations)
    assert [item["evidence_references"] for item in result] == [
        item["evidence_references"] for item in observations
    ]
    assert coverage["status"] == "partial"
    assert coverage["omitted_observations"] == len(observations)
    assert not pipeline.calls


def test_truncated_grouping_prefix_is_corrected_before_accepting_partial_membership(
    pipeline, monkeypatch
):
    calls = []

    class Model:
        def invoke(self, prompt, **kwargs):
            payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
            calls.append(payload)
            groups = all_equivalent(payload)
            if len(calls) == 1:
                groups[0]["member_ids"] = groups[0]["member_ids"][:1]
            return SimpleNamespace(
                content=json.dumps(groups),
                response_metadata={
                    "finish_reason": "length" if len(calls) == 1 else "stop"
                },
            )

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: Model())
    result, coverage = extractor.merge_evidenced_skills(pipeline.observations, {})
    assert len(calls) == 2
    assert coverage["status"] == "full"
    assert len(result) == 1
    assert result[0]["evidence_references"] == [
        item["evidence_references"][0] for item in pipeline.observations
    ]


@pytest.mark.parametrize("count", [1, 2])
def test_failed_changed_quote_pass_can_recover_explicit_historical_teacher_choice(
    pipeline, count
):
    pipeline.handler = all_equivalent
    first = save(pipeline)["candidates"][0]
    draft(pipeline, [first["candidate_id"]], [])
    changed = deepcopy(pipeline.observations[:count])
    for index, item in enumerate(changed):
        item.update(name="Set up ETL pipelines", identity_key=f"jobs:recovery-{index}")
        ref = item["evidence_references"][0]
        quote = ref["original_phrase"]
        offset = ref["excerpt"].index(quote)
        ref.update(excerpt=quote, excerpt_start=offset, excerpt_end=offset + len(quote))

    def fail(payload):
        raise TimeoutError("Grouping temporarily unavailable")

    pipeline.handler = fail
    save(pipeline, changed)
    assert stored(pipeline).selected_candidate_ids == []
    # Existing production history predates retained passage references.
    run = stored(pipeline)
    manifest = deepcopy(run.candidate_manifest)
    for candidate in manifest["candidate_history"]:
        if candidate["candidate_id"] == first["candidate_id"]:
            candidate.pop("evidence_references", None)
    run.candidate_manifest = manifest
    pipeline.db.commit()

    def confirm(payload):
        assert len(payload["prior_candidates"]) == 1
        assert payload["prior_candidates"][0]["name"] == "Configure ETL pipelines"
        return confirm_prior_equivalence(payload)

    pipeline.handler = confirm
    result = save(pipeline, changed)
    assert result["candidates"][0]["candidate_id"] == first["candidate_id"]
    assert stored(pipeline).selected_candidate_ids == [first["candidate_id"]]
    assert result["candidates"][0]["evidence_references"] == [
        i["evidence_references"][0] for i in changed
    ]
    assert not stored(pipeline).candidate_manifest["reconciliation_required"]


def test_current_known_sample_does_not_duplicate_137_prior_labels(pipeline):
    many = []
    for index in range(137):
        item = deepcopy(pipeline.observations[index % 2])
        item.update(
            name=f"Configure ETL pipelines variant {index}",
            identity_key=f"jobs:known-{index}",
        )
        many.append(item)
    pipeline.handler = lambda payload: []
    save(pipeline, many)

    def groups(payload):
        assert len(payload["observations"]) == 137
        assert payload["prior_candidates"] == []
        return all_equivalent(payload)

    pipeline.handler = groups
    result = save(pipeline, many)
    assert len(result["candidates"]) == 1
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"


def test_unrelated_missing_choice_does_not_force_historical_confirmation(pipeline):
    configure = deepcopy(pipeline.observations[0])
    monitor = deepcopy(configure)
    monitor.update(
        name="Monitor ETL pipeline failures", identity_key="jobs:missing-monitor"
    )
    ref = monitor["evidence_references"][0]
    quote = "Monitor ETL pipeline failures"
    start = ref["excerpt"].index(quote)
    ref.update(
        original_phrase=quote,
        excerpt=quote,
        excerpt_start=start,
        excerpt_end=start + len(quote),
    )
    pipeline.handler = lambda payload: [
        {"canonical_id": row["observation_id"], "member_ids": [row["observation_id"]]}
        for row in payload["observations"]
    ]
    initial = save(pipeline, [configure, monitor])["candidates"]
    selected, missing = [c["candidate_id"] for c in initial]
    draft(pipeline, [selected, missing], [])
    current = deepcopy(configure)
    current.update(name="Set up ETL pipelines", identity_key="jobs:recovered-setup")
    ref = current["evidence_references"][0]
    quote = ref["original_phrase"]
    start = ref["excerpt"].index(quote)
    ref.update(excerpt=quote, excerpt_start=start, excerpt_end=start + len(quote))
    pipeline.handler = lambda payload: []
    save(pipeline, [current])

    def confirm(payload):
        prior = next(
            row["candidate_id"]
            for row in payload["prior_candidates"]
            if row["name"] == configure["name"]
        )
        return [
            {"canonical_id": "o0", "member_ids": ["o0"], "prior_candidate_ids": [prior]}
        ]

    pipeline.handler = confirm
    result = save(pipeline, [current])
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"
    assert stored(pipeline).selected_candidate_ids == [selected]
    assert result["candidates"][0]["candidate_id"] != missing
    assert any(
        not r["resolved"] and r["previous_candidate_ids"] == [missing]
        for r in stored(pipeline).candidate_manifest["reconciliations"]
    )


def test_one_correction_attempt_repairs_invalid_partition_without_losing_refs(pipeline):
    def groups(payload):
        group = all_equivalent(payload)
        if len(pipeline.calls) == 1:
            group[0]["member_ids"].append(group[0]["member_ids"][0])
        return group

    pipeline.handler = groups
    result = save(pipeline)
    assert len(pipeline.calls) == 2
    assert pipeline.calls[0] == pipeline.calls[1]
    assert len(result["candidates"]) == 1
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "full"
    assert result["candidates"][0]["evidence_references"] == [
        i["evidence_references"][0] for i in pipeline.observations
    ]


def test_large_historical_comparison_set_keeps_teacher_choices_without_duplicate_noise(
    pipeline,
):
    from uuid import uuid4

    previous = {"candidate_history": []}
    for index in range(60):
        previous["candidate_history"].append(
            {
                "candidate_id": str(uuid4()),
                "identity_key": f"jobs:historical-{index}",
                "display_name": "Configure ETL pipelines",
                "category_id": "data_processing",
                "selected": index == 0,
                "excluded": index == 1,
                "evidence_references": deepcopy(
                    pipeline.observations[0]["evidence_references"]
                ),
            }
        )
    old = deepcopy(previous)

    def confirm(payload):
        assert len(payload["prior_candidates"]) == 2
        result = all_equivalent(payload)
        result[0]["prior_candidate_ids"] = [
            row["candidate_id"] for row in payload["prior_candidates"]
        ]
        return result

    pipeline.handler = confirm
    result, coverage = extractor.merge_evidenced_skills(pipeline.observations, previous)
    assert len(result) == 1
    assert coverage["status"] == "full"
    assert previous == old
    assert set(result[0]["_confirmed_prior_candidate_ids"]) == {
        candidate["candidate_id"] for candidate in previous["candidate_history"][:2]
    }
    assert coverage["historical_comparisons_omitted"] == 58


@pytest.mark.parametrize("pipeline", ["inverse_mentoring"], indirect=True)
def test_opposite_mentoring_roles_cannot_merge_even_with_valid_model_ids(pipeline):
    pipeline.handler = all_equivalent
    result = save(pipeline)
    assert {c["display_name"] for c in result["candidates"]} == {
        item["name"] for item in pipeline.observations
    }
    assert all(len(c["qualifying_posting_links"]) == 1 for c in result["candidates"])
    assert all(
        c["job_metrics"]["supporting_posting_count"] == 1 for c in result["candidates"]
    )
    assert result["extraction_coverage"]["semantic_grouping"]["status"] == "partial"


@pytest.mark.parametrize("pipeline", ["inverse_mentoring"], indirect=True)
@pytest.mark.parametrize("changed_key", [False, True])
def test_saved_inverse_membership_repairs_without_reassigning_mentor_choice(
    pipeline, changed_key
):
    from app.modules.marketdemandanalyst.evidence import (
        merge_observation_group,
        reconcile_candidates,
    )

    # Seed a durable group made by the old implementation, without the new guard.
    combined = merge_observation_group(pipeline.observations, pipeline.observations[0])
    previous = reconcile_candidates([combined], {})
    mentor_id = previous["candidates"][0]["candidate_id"]
    run = stored(pipeline)
    run.candidate_manifest = previous
    pipeline.db.commit()
    draft(pipeline, [mentor_id], [])
    current = deepcopy(pipeline.observations)
    if changed_key:
        current[1]["identity_key"] = "jobs:changed-mentee"

    pipeline.handler = lambda payload: [
        {"canonical_id": r["observation_id"], "member_ids": [r["observation_id"]]}
        for r in payload["observations"]
    ]
    result = save(pipeline, current)
    candidates = result["candidates"]
    assert len(candidates) == len({c["candidate_id"] for c in candidates}) == 2
    mentor = next(c for c in candidates if c["display_name"] == current[0]["name"])
    mentee = next(c for c in candidates if c["display_name"] == current[1]["name"])
    assert mentor["candidate_id"] == mentor_id != mentee["candidate_id"]
    assert stored(pipeline).selected_candidate_ids == [mentor_id]
    assert current[1]["name"] not in mentor["aliases"]
    assert (
        pipeline.observations[1]["identity_key"] not in mentor["semantic_identity_keys"]
    )
    assert current[1]["identity_key"] not in mentor["semantic_identity_keys"]
    assert mentor["qualifying_posting_links"] == ["https://hh.uz/vacancy/mentor"]
    assert mentee["qualifying_posting_links"] == ["https://hh.uz/vacancy/mentee"]
    manifest = stored(pipeline).candidate_manifest
    assert not manifest["reconciliation_required"]
    assert any(
        r["reason"] == "incompatible_task_roles_repaired"
        and r["resolved"]
        and current[1]["name"] in r["historical_candidates"][0]["aliases"]
        for r in manifest["reconciliations"]
    )
    repeated = save(pipeline, list(reversed(current)))
    assert {c["candidate_id"] for c in repeated["candidates"]} == {
        c["candidate_id"] for c in candidates
    }
    assert stored(pipeline).selected_candidate_ids == [mentor_id]
