"""Bounded extraction and candidate provenance contracts (no external calls)."""

import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.modules.marketdemandanalyst.state import bind_tool_store


def test_chunks_cover_tail_and_report_explicit_cap():
    from app.modules.marketdemandanalyst.evidence import make_extraction_chunks

    chunks = make_extraction_chunks("a" * 8100)
    assert [(c["start"], c["end"]) for c in chunks] == [
        (0, 4000),
        (3700, 7700),
        (7400, 8100),
    ]
    capped = make_extraction_chunks("a" * 70000)
    assert len(capped) == 16
    assert capped[-1]["end"] == 59500
    assert capped[-1]["uncovered_chars"] == 10500
    with pytest.raises(ValueError):
        make_extraction_chunks("a", max_chars=300, overlap=300)


def test_evidence_validates_offset_and_does_not_accept_invented_passage():
    from app.modules.marketdemandanalyst.evidence import validated_passage

    assert validated_passage("aaaa Python bbbb", "Python", 4) == {
        "excerpt": "Python",
        "excerpt_start": 5,
        "excerpt_end": 11,
    }
    assert validated_passage("Python", "Java", 0) is None


def test_distinct_demand_metrics_never_count_aliases_or_source_copies_twice():
    from app.modules.marketdemandanalyst.evidence import calculate_job_metrics

    assert calculate_job_metrics(
        ["same", "same"],
        ["same", "same", "other"],
        selected_identities=["same", "other", "failed"],
        coverage_status="partial",
    ) == {
        "supporting_posting_count": 1,
        "assessed_posting_count": 2,
        "selected_posting_count": 3,
        "percentage": 50.0,
        "coverage_status": "partial",
    }
    assert calculate_job_metrics([], [])["percentage"] is None


def observation(name="Explain technical results", identity="a", **kwargs):
    return {
        "name": name,
        "category": "communication",
        "identity_key": kwargs.pop("identity_key", "explain-results"),
        "supporting_identities": [identity],
        "evidence_references": [
            {
                "snapshot_id": str(uuid4()),
                "original_url": f"https://company.test/jobs/{identity}",
                "original_phrase": "explain results",
            }
        ],
        **kwargs,
    }


def test_reconciliation_preserves_ids_exclusions_union_and_ambiguous_decisions():
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates

    old_id = str(uuid4())
    previous = {
        "candidates": [
            {
                "candidate_id": old_id,
                "identity_key": "explain-results",
                "display_name": "Explain results",
                "category_id": "communication",
            }
        ],
        "excluded_candidate_ids": [old_id],
    }
    manifest = reconcile_candidates(
        [observation(), observation(identity="b")], previous
    )
    candidate = manifest["candidates"][0]
    assert candidate["candidate_id"] == old_id
    assert len(candidate["evidence_references"]) == 2
    assert manifest["excluded_candidate_ids"] == [old_id]
    unrelated = reconcile_candidates(
        [
            observation(identity_key="explain-financial-results"),
            observation(identity_key="explain-medical-results"),
        ],
        {},
    )
    assert len(unrelated["candidates"]) == 2
    second_id = str(uuid4())
    previous["candidates"].append(
        {"candidate_id": second_id, "identity_key": "explain-results"}
    )
    previous["selected_candidate_ids"] = [second_id]
    conflicted = reconcile_candidates([observation()], previous)
    assert conflicted["reconciliation_required"]
    assert conflicted["selected_candidate_ids"] == []


def test_removed_excluded_candidate_retry_restores_identity_and_pending_history():
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates

    first = reconcile_candidates([observation()], {})
    candidate_id = first["candidates"][0]["candidate_id"]
    first["excluded_candidate_ids"] = [candidate_id]
    missing = reconcile_candidates([], first)
    repeated = reconcile_candidates([], missing)
    restored = reconcile_candidates([observation()], repeated)
    assert restored["candidates"][0]["candidate_id"] == candidate_id
    assert restored["excluded_candidate_ids"] == [candidate_id]
    assert restored["reconciliation_required"]
    assert restored["reconciliations"] == missing["reconciliations"]
    assert UUID(missing["reconciliations"][0]["reconciliation_id"])


def test_conflicting_merge_keeps_unresolved_record_until_explicit_resolution():
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates

    first_id, second_id = str(uuid4()), str(uuid4())
    previous = {
        "candidates": [
            {"candidate_id": first_id, "identity_key": "explain-results"},
            {"candidate_id": second_id, "identity_key": "explain-results"},
        ],
        "selected_candidate_ids": [first_id],
        "excluded_candidate_ids": [second_id],
    }
    merged = reconcile_candidates([observation()], previous)
    repeated = reconcile_candidates([observation()], merged)
    assert repeated["reconciliation_required"]
    assert repeated["reconciliations"] == merged["reconciliations"]
    assert (
        repeated["candidates"][0]["candidate_id"]
        == merged["candidates"][0]["candidate_id"]
    )
    record = repeated["reconciliations"][0]
    assert UUID(record["reconciliation_id"])
    assert record["previous_selected_candidate_ids"] == [first_id]
    assert record["previous_excluded_candidate_ids"] == [second_id]
    assert record["historical_candidates"][0]["identity_key"] == "explain-results"
    repeated["reconciliations"][0]["resolved"] = True
    assert not reconcile_candidates([observation()], repeated)[
        "reconciliation_required"
    ]


@pytest.mark.parametrize("relation", ["broader", "unmatched"])
def test_onet_broader_and_unmatched_ratings_remain_context_not_candidate_rating(
    relation,
):
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates

    ratings = {"IM": {"value": 4, "status": "reported"}}
    evidence = {
        "id": str(uuid4()),
        "label": "Critical Thinking",
        "soc_code": "15-1252.00",
        "ratings": ratings,
    }
    association = {
        "evidence": evidence,
        "relation": relation,
        "mapping_method": "review",
        "rationale": "context",
    }
    rows = [observation(onet_associations=[association])]
    before = deepcopy(rows)
    result = reconcile_candidates(rows, {})["candidates"][0]
    assert result["onet_associations"][0]["evidence"]["ratings"] == ratings
    assert "onet_rating" not in result
    assert rows == before


def test_real_extract_one_reaches_skill_after_4000_and_rejects_hallucination(
    monkeypatch,
):
    from app.modules.marketdemandanalyst import extractor

    description = "a" * 4300 + " Explain technical results to stakeholders."
    job = {
        "snapshot_id": str(uuid4()),
        "title": "Engineer",
        "description": description,
        "url": "https://company.test/jobs/1",
        "site": "linkedin",
        "demand_identity": "one",
        "retrieved_at": "2026-10-10T00:00:00Z",
        "status": "active",
    }

    class LLM:
        def invoke(self, prompt, **kwargs):
            rows = (
                [
                    {
                        "name": "Explain technical results",
                        "category": "communication",
                        "original_phrase": "Explain technical results to stakeholders",
                        "excerpt": "Explain technical results to stakeholders",
                    }
                ]
                if "stakeholders" in prompt
                else []
            )
            rows.append(
                {
                    "name": "Use Java",
                    "category": "language",
                    "original_phrase": "Java",
                    "excerpt": "Java",
                }
            )
            return SimpleNamespace(content=json.dumps(rows))

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    with bind_tool_store({"run_id": str(uuid4())}):
        result = extractor.extract_one({"job": job})
    assert len(result["skills"]) == 1
    item = result["skills"][0]
    assert item["evidence_references"][0]["excerpt_start"] == 4301
    assert item["evidence_references"][0]["excerpt_end"] == 4342
    assert result["assessments"][0]["status"] == "partial"
    assert result["assessments"][0]["assessed_chunks"] == 2
    assert "2 unsupported extraction rows" in result["assessments"][0]["warnings"][0]


def test_partial_extraction_keeps_success_and_exposes_failed_chunks(monkeypatch):
    from app.modules.marketdemandanalyst import extractor

    class LLM:
        def invoke(self, prompt, **kwargs):
            if "tail" in prompt:
                raise TimeoutError("private detail must not leak")
            return SimpleNamespace(content="[]")

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    with bind_tool_store({"run_id": str(uuid4())}):
        result = extractor.extract_one(
            {
                "job": {
                    "snapshot_id": str(uuid4()),
                    "description": "a" * 4100 + "tail",
                    "demand_identity": "one",
                }
            }
        )
    assert result["assessments"][0]["status"] == "partial"
    assert result["assessments"][0]["assessed_chunks"] == 1
    assert "private detail" not in str(result)


def test_eight_active_calls_bound_across_more_than_eight_postings(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context
    from threading import Event, Lock

    from app.modules.marketdemandanalyst import extractor

    lock, release, eight_started = Lock(), Event(), Event()
    active = maximum = 0

    class LLM:
        def invoke(self, prompt, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                if active == 8:
                    eight_started.set()
            try:
                assert release.wait(8)
                return SimpleNamespace(content="[]")
            finally:
                with lock:
                    active -= 1

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    jobs = [
        {
            "snapshot_id": str(uuid4()),
            "description": "Python " * 20,
            "demand_identity": str(i),
        }
        for i in range(12)
    ]
    with (
        bind_tool_store({"run_id": str(uuid4())}),
        ThreadPoolExecutor(max_workers=12) as pool,
    ):
        futures = [
            pool.submit(copy_context().run, extractor.extract_one, {"job": job})
            for job in jobs
        ]
        try:
            assert eight_started.wait(6)
        finally:
            release.set()
        results = [f.result(timeout=8) for f in futures]
    assert maximum == 8
    assert all(result["assessments"][0]["status"] == "full" for result in results)


def test_software_examples_remain_distinct_under_one_official_descriptor():
    from app.modules.marketdemandanalyst.evidence import (
        onet_candidates,
        reconcile_candidates,
    )

    rows = [
        {
            "id": str(uuid4()),
            "release": "31.0",
            "family": "software",
            "element_id": "2.C.1",
            "label": "Database software",
            "workplace_example": example,
            "ratings": {},
            "flags": {"Hot Technology": True},
        }
        for example in ["PostgreSQL", "MongoDB"]
    ]
    candidates = reconcile_candidates(onet_candidates(rows), {})["candidates"]
    assert {c["display_name"] for c in candidates} == {"PostgreSQL", "MongoDB"}
    assert len(candidates) == 2
    assert all(
        c["onet_associations"][0]["evidence"]["ratings"] == {} for c in candidates
    )


def test_same_name_and_tag_with_different_source_tasks_do_not_merge(monkeypatch):
    from app.modules.marketdemandanalyst import extractor
    from app.modules.marketdemandanalyst.evidence import reconcile_candidates

    class LLM:
        def invoke(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "name": "Use SQL",
                            "category": "database",
                            "original_phrase": "SQL",
                            "excerpt": excerpt,
                        }
                        for excerpt in ["SQL queries", "SQL secure access"]
                    ]
                )
            )

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    with bind_tool_store({"run_id": str(uuid4())}):
        result = extractor.extract_one(
            {
                "job": {
                    "snapshot_id": str(uuid4()),
                    "description": "SQL queries and SQL secure access",
                    "demand_identity": "one",
                    "url": "https://company.test/jobs/one",
                    "site": "linkedin",
                }
            }
        )
    assert len(reconcile_candidates(result["skills"], {})["candidates"]) == 2


def test_invalid_source_rows_are_partial_while_valid_work_is_retained(monkeypatch):
    from app.modules.marketdemandanalyst import extractor

    class LLM:
        def invoke(self, *args, **kwargs):
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {
                            "name": "Develop ETL processes",
                            "original_phrase": "Разрабатывать ETL",
                            "excerpt": "Разрабатывать ETL",
                            "category": "data_processing",
                        },
                        {
                            "name": "Use Spark",
                            "original_phrase": "Spark",
                            "excerpt": "Invented Spark requirement",
                        },
                    ]
                )
            )

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kwargs: LLM())
    with bind_tool_store({"run_id": str(uuid4())}):
        result = extractor.extract_one(
            {
                "job": {
                    "snapshot_id": str(uuid4()),
                    "description": "Разрабатывать ETL. Spark",
                    "demand_identity": "one",
                }
            }
        )
    assert [s["name"] for s in result["skills"]] == ["Develop ETL processes"]
    assessment = result["assessments"][0]
    assert assessment["status"] == "partial"
    assert assessment["assessed_chunks"] == 1
    assert assessment["warnings"]
    assert "Invented Spark requirement" not in str(assessment)
