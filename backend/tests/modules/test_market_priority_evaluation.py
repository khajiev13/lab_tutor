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
