"""Grounded extraction and bounded recovery at the external model boundary."""

import json
from types import SimpleNamespace

from app.modules.marketdemandanalyst import extractor


def job(description="Build Python pipelines.\nExplain results to colleagues."):
    return {
        "snapshot_id": "posting-1",
        "demand_identity": "provider:1",
        "description": description,
        "title": "Data engineer",
        "skill_tags": ["Python"],
        "site": "linkedin",
        "url": "https://example.test/job/1",
        "status": "active",
    }


def completion(rows, **metadata):
    return SimpleNamespace(
        content=json.dumps({"skills": rows}), response_metadata=metadata
    )


def row(name="Build data pipelines", **changes):
    return {
        "name": name,
        "category": "data_processing",
        "evidence_ids": ["P0"],
        **changes,
    }


def install(monkeypatch, responses):
    calls = []

    class LLM:
        def invoke(self, prompt, **kwargs):
            calls.append((prompt, kwargs))
            value = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(value, Exception):
                raise value
            return value

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kw: LLM())
    return calls


def test_source_ids_preserve_exact_unicode_evidence_without_model_quotations(
    monkeypatch,
):
    source = "  Разрабатывать ETL — процессы.\nОбъяснять результаты."
    calls = install(monkeypatch, [completion([row()])])

    result = extractor._extract_evidenced_job(job(source))

    assert result["assessments"][0]["status"] == "full"
    ref = result["skills"][0]["evidence_references"][0]
    assert ref["excerpt"] == "Разрабатывать ETL — процессы."
    assert source[ref["excerpt_start"] : ref["excerpt_end"]] == ref["excerpt"]
    assert ref["original_phrase"] == ref["excerpt"]
    payload = json.loads(calls[0][0].split("Source data:\n", 1)[1])
    assert payload["passages"][0] == {"id": "P0", "text": ref["excerpt"]}
    assert calls[0][1]["response_format"] == {"type": "json_object"}
    assert calls[0][1]["config"]["tags"] == ["nostream"]


def test_malformed_json_is_retried_once_and_successful_recovery_is_full(monkeypatch):
    calls = install(
        monkeypatch,
        [
            SimpleNamespace(content='{"skills":[', response_metadata={}),
            completion([row()]),
        ],
    )

    result = extractor._extract_evidenced_job(job())

    assert len(calls) == 2
    assert result["assessments"][0]["status"] == "full"
    assert result["assessments"][0]["warnings"] == []
    assert len(result["skills"]) == 1


def test_transient_timeout_recovers_without_discarding_prior_success(monkeypatch):
    calls = install(
        monkeypatch, [TimeoutError("secret transport detail"), completion([row()])]
    )
    result = extractor._extract_evidenced_job(job())
    assert len(calls) == 2
    assert result["assessments"][0]["status"] == "full"
    assert "secret" not in str(result)


def test_unknown_source_ids_remain_partial_and_good_evidence_survives(monkeypatch):
    calls = install(
        monkeypatch, [completion([row(), row("Invented task", evidence_ids=["P999"])])]
    )
    result = extractor._extract_evidenced_job(job())
    assert len(calls) == 2
    assert [s["name"] for s in result["skills"]] == ["Build data pipelines"]
    assert result["assessments"][0]["status"] == "partial"
    assert result["assessments"][0]["assessed_chunks"] == 1
    assert "1 unsupported extraction rows" in str(result["assessments"])


def test_invalid_row_does_not_discard_valid_rows(monkeypatch):
    calls = install(monkeypatch, [completion([row(), 17])])
    result = extractor._extract_evidenced_job(job())
    assert len(calls) == 2
    assert len(result["skills"]) == 1
    assert result["assessments"][0]["status"] == "partial"


def test_exhausted_recovery_reports_safe_reason_without_claiming_completion(
    monkeypatch,
):
    calls = install(monkeypatch, [TimeoutError("private key or provider response")])
    result = extractor._extract_evidenced_job(job())
    assert len(calls) == 2
    assessment = result["assessments"][0]
    assert assessment["status"] == "failed"
    assert assessment["assessed_chunks"] == 0
    assert "TimeoutError" in str(assessment["warnings"])
    assert "private" not in str(result)


def test_truncated_output_is_retried_even_when_returned_prefix_is_valid_json(
    monkeypatch,
):
    calls = install(
        monkeypatch, [completion([row()], finish_reason="length"), completion([row()])]
    )
    result = extractor._extract_evidenced_job(job())
    assert len(calls) == 2
    assert result["assessments"][0]["status"] == "full"
    assert len(result["skills"]) == 1


def test_source_offsets_remain_global_in_later_chunks(monkeypatch):
    source = "x" * 4300 + "\nExplain results to colleagues."
    calls = []

    class LLM:
        def invoke(self, prompt, **kwargs):
            calls.append(prompt)
            payload = json.loads(prompt.split("Source data:\n", 1)[1])
            matches = [
                p["id"]
                for p in payload["passages"]
                if p["text"] == "Explain results to colleagues."
            ]
            return completion(
                [row("Explain results", evidence_ids=matches)] if matches else []
            )

    monkeypatch.setattr(extractor, "_get_extraction_llm", lambda **kw: LLM())
    result = extractor._extract_evidenced_job(job(source))
    assert len(calls) == 2
    assert result["assessments"][0]["status"] == "full"
    assert result["assessments"][0]["assessed_chunks"] == 2
    ref = result["skills"][0]["evidence_references"][0]
    assert ref["excerpt_start"] == 4301
    assert (
        source[ref["excerpt_start"] : ref["excerpt_end"]]
        == "Explain results to colleagues."
    )


def test_provider_tag_ids_resolve_only_to_supplied_tags(monkeypatch):
    install(monkeypatch, [completion([row("Use Python", evidence_ids=["T0"])])])
    result = extractor._extract_evidenced_job(job())
    ref = result["skills"][0]["evidence_references"][0]
    assert ref["evidence_kind"] == "provider_tag"
    assert ref["original_phrase"] == "Python"
    assert ref["excerpt"] is None
