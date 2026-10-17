"""Release criteria cannot pass by dropping difficult or unsupported cases."""

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

CASES = Path(__file__).parents[1] / "fixtures/skill_priority/evaluation.json"


def fixture_document():
    return json.loads(CASES.read_text())


def runner():
    return importlib.import_module("tests.acceptance.skill_priority_evaluation")


def observations(cases):
    return [
        {
            "case_id": case["id"],
            "basis": "unavailable" if case["kind"] == "weak_control" else "ai_estimate",
            "value": None
            if case["kind"] == "weak_control"
            else round(case["expected_value"]),
            "provided_reference_ids": ["anchor"],
            "cited_reference_ids": [] if case["kind"] == "weak_control" else ["anchor"],
        }
        for case in cases
    ]


def test_twenty_source_derived_cases_cover_three_occupations_and_five_controls():
    cases = runner().validate_cases(fixture_document())
    assert len(cases) == 20
    assert len({case["soc_code"] for case in cases}) == 3
    assert sum(case["kind"] == "weak_control" for case in cases) == 5


@pytest.mark.parametrize(
    "defect",
    ["few_cases", "few_roles", "few_controls", "missing_provenance", "duplicate_id"],
)
def test_rejects_insufficient_or_unsourced_evaluation(defect):
    doc = fixture_document()
    if defect == "few_cases":
        doc["cases"].pop()
    elif defect == "few_roles":
        for case in doc["cases"]:
            case["soc_code"] = "15-2051.00"
    elif defect == "few_controls":
        weak = next(case for case in doc["cases"] if case["kind"] == "weak_control")
        weak.update(deepcopy(doc["cases"][0]), id="extra-target")
    elif defect == "missing_provenance":
        doc["cases"][0]["target_provenance"] = {}
    else:
        doc["cases"][1]["id"] = doc["cases"][0]["id"]
    with pytest.raises(ValueError):
        runner().validate_cases(doc)


def test_exact_eighty_percent_thresholds_use_every_target_and_control():
    cases = runner().validate_cases(fixture_document())
    rows = observations(cases)
    targets = [row for row in rows if row["basis"] == "ai_estimate"]
    for row in targets[:3]:
        row.update(basis="unavailable", value=None)
    controls = [row for row in rows if row["case_id"].startswith("weak-")]
    controls[0].update(basis="ai_estimate", value=3)
    report = runner().summarize_evaluation(cases, rows, elapsed_seconds=4.5)
    assert report["within_one_point_rate"] == 0.8
    assert report["abstention_rate"] == 0.8
    assert report["quality_gate_passed"] is True
    assert report["elapsed_seconds"] == 4.5


@pytest.mark.parametrize(
    "defect",
    [
        "missed_target",
        "false_control",
        "fabrication",
        "official_label",
        "boolean_value",
    ],
)
def test_quality_gate_rejects_failures_instead_of_inflating_coverage(defect):
    cases = runner().validate_cases(fixture_document())
    rows = observations(cases)
    if defect == "missed_target":
        for row in rows[:4]:
            row.update(basis="unavailable", value=None)
    elif defect == "false_control":
        for row in rows[-2:]:
            row.update(basis="ai_estimate", value=3)
    elif defect == "fabrication":
        rows[0]["cited_reference_ids"].append("invented")
    elif defect == "official_label":
        rows[0]["basis"] = "onet"
    else:
        rows[0]["value"] = True
    report = runner().summarize_evaluation(cases, rows)
    assert report["quality_gate_passed"] is False
    if defect == "missed_target":
        assert report["within_one_point_rate"] == 11 / 15
    if defect == "fabrication":
        assert report["fabricated_reference_count"] == 1
    if defect == "official_label":
        assert report["mislabeled_estimate_count"] == 1


def test_rejects_leaked_targets_and_missing_duplicate_or_foreign_results():
    cases = runner().validate_cases(fixture_document())
    rows = observations(cases)
    bad = deepcopy(rows)
    bad[0]["provided_reference_ids"].append(cases[0]["held_out_reference_id"])
    for changed in [
        bad,
        rows[:-1],
        rows + [rows[0]],
        rows + [{**rows[0], "case_id": "foreign"}],
    ]:
        with pytest.raises(ValueError):
            runner().summarize_evaluation(cases, changed)


def test_foreign_model_records_cannot_hide_fabricated_references():
    cases = runner().validate_cases(fixture_document())
    count = runner().raw_reference_violations(
        {"references": [{"id": "anchor"}]},
        [
            {
                "candidate_id": "foreign",
                "direct_reference_id": "invented",
                "associations": [{"reference_id": "anchor"}],
            }
        ],
    )
    report = runner().summarize_evaluation(
        cases, observations(cases), raw_reference_violations=count
    )
    assert report["fabricated_reference_count"] == 1
    assert report["quality_gate_passed"] is False


def compact_call():
    payload = {
        "phase": "score",
        "pairs": [
            {"candidate_id": "C1", "soc_code": "15-1252.00"},
            {"candidate_id": "C2", "soc_code": "15-1252.00"},
        ],
        "candidates": [
            {"candidate_id": "C1", "display_name": "Write programs"},
            {"candidate_id": "C2", "display_name": "Review programs"},
        ],
        "references": [{"id": "R1", "soc_code": "15-1252.00", "label": "Programming"}],
        "passages": {"E1": {"candidate_ids": ["C1"]}, "E2": {"candidate_ids": ["C2"]}},
    }
    rows = [
        {
            "c": "C1",
            "b": "ai_estimate",
            "d": None,
            "v": 4,
            "a": [
                {
                    "r": "R1",
                    "k": "broader",
                    "why": "Programming anchors this capability.",
                }
            ],
            "e": ["E1"],
            "why": "The verified responsibility requires this capability.",
            "limits": [],
        },
        {
            "c": "C2",
            "b": "ai_estimate",
            "d": None,
            "v": 3,
            "a": [
                {
                    "r": "R1",
                    "k": "related",
                    "why": "Programming supports this capability.",
                }
            ],
            "e": ["E2"],
            "why": "The verified responsibility supports this capability.",
            "limits": [],
        },
    ]
    maps = (
        {"C1": "candidate-a", "C2": "candidate-b"},
        {"R1": "reference-a"},
        {"E1": "passage-a", "E2": "passage-b"},
    )
    return payload, rows, maps


def test_live_calibration_audit_expands_compact_ids_before_reference_checks():
    payload, rows, maps = compact_call()
    canonical_payload, canonical_rows = runner().canonical_score_call(
        payload, rows, maps
    )
    assert canonical_rows[0]["candidate_id"] == "candidate-a"
    assert canonical_rows[0]["associations"][0]["reference_id"] == "reference-a"
    assert canonical_rows[0]["supporting_evidence_ids"] == ["passage-a"]
    assert canonical_payload["references"][0]["id"] == "reference-a"
    assert canonical_payload["pairs"][1]["candidate_id"] == "candidate-b"
    assert runner().raw_reference_violations(canonical_payload, canonical_rows) == 0


@pytest.mark.parametrize(
    "damage",
    [
        "candidate",
        "canonical_fallback",
        "duplicate",
        "reference",
        "passage",
        "cross_candidate",
    ],
)
def test_live_calibration_audit_rejects_corrupted_aliases(damage):
    payload, rows, maps = compact_call()
    if damage == "candidate":
        rows[0]["c"] = "C999"
    elif damage == "canonical_fallback":
        rows[0]["c"] = "candidate-a"
    elif damage == "duplicate":
        rows[0]["c"] = "C2"
    elif damage == "reference":
        rows[0]["a"][0]["r"] = "R999"
    elif damage == "passage":
        rows[0]["e"] = ["E999"]
    else:
        rows[0]["e"] = ["E2"]
    with pytest.raises(ValueError):
        runner().canonical_score_call(payload, rows, maps)


@pytest.mark.parametrize("foreign_candidate", [False, True])
def test_live_audit_keeps_raw_violations_when_real_request_rejects(foreign_candidate):
    import asyncio
    import json
    from threading import BoundedSemaphore
    from time import monotonic
    from types import SimpleNamespace

    from pydantic import TypeAdapter

    from app.modules.marketdemandanalyst.priority_service import (
        SkillPriorityService,
        _expand_scoring_decisions,
        _ScoringDecision,
        _Unavailable,
    )

    payload, rows, aliases = compact_call()
    rows[0]["a"][0]["r"] = "R999"
    if foreign_candidate:
        rows[0]["c"] = "C999"
        rows[0]["official_value"] = (
            5  # Also force rejection at the actual transport adapter.
        )
    calls = []
    audit = runner()

    async def invoke(messages, *, config):
        audit.record_score_reply(calls, payload, rows, aliases)
        return SimpleNamespace(content=json.dumps({"results": rows}))

    service = SkillPriorityService(
        llm_factory=lambda **kwargs: SimpleNamespace(ainvoke=invoke)
    )
    with pytest.raises(_Unavailable):
        wire = asyncio.run(
            service._request(
                payload,
                "prompt",
                TypeAdapter(list[_ScoringDecision]),
                monotonic() + 1,
                BoundedSemaphore(2),
            )
        )
        _expand_scoring_decisions(wire, *aliases, "15-1252.00", payload)
    assert len(calls) == 1
    assert calls[0]["raw_reference_violations"] == 1
    assert calls[0]["alias_violations"] == 1
    cases = audit.validate_cases(fixture_document())
    report = audit.summarize_evaluation(
        cases,
        observations(cases),
        raw_reference_violations=calls[0]["raw_reference_violations"],
        raw_alias_violations=calls[0]["alias_violations"],
    )
    assert report["within_one_point_rate"] == 1
    assert report["abstention_rate"] == 1
    assert report["fabricated_reference_count"] == 1
    assert report["invalid_alias_count"] == 1
    assert report["quality_gate_passed"] is False
