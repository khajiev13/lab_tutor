"""AI role decisions retain every posting without title-pattern fallback merges."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.marketdemandanalyst import job_groups


def model_response(monkeypatch, groups=None, *, error=None):
    class Model:
        def invoke(self, messages, **kwargs):
            if error:
                raise error
            return SimpleNamespace(content=json.dumps(groups))

    monkeypatch.setattr(
        job_groups, "_get_extraction_llm", lambda **kwargs: Model(), raising=False
    )


def test_ai_groups_equivalent_roles_and_preserves_all_original_postings(monkeypatch):
    jobs = [
        {"title": "Data Engineer", "description": "Develop data pipelines"},
        {"title": "Middle Data Engineer", "description": "Build ETL pipelines"},
        {"title": "Разработчик платформы данных", "description": "Разработка ETL"},
        {"title": "Fraud Analyst", "description": "Investigate payment fraud"},
    ]
    for index, job in enumerate(jobs):
        job["url"] = f"https://hh.uz/vacancy/{index}"
    original = deepcopy(jobs)
    model_response(
        monkeypatch,
        [
            {"name": "Data Engineer", "job_ids": ["j0", "j1", "j2"]},
            {"name": "Fraud Analyst", "job_ids": ["j3"]},
        ],
    )
    assert job_groups.group_jobs_by_title(jobs) == {
        "Data Engineer": [0, 1, 2],
        "Fraud Analyst": [3],
    }
    assert jobs == original


@pytest.mark.parametrize("preamble", ["", "Company background. " * 100])
def test_description_context_allows_ai_to_separate_identical_titles(
    monkeypatch, preamble
):
    jobs = [
        {"title": "Analyst", "description": "Design data pipelines and warehouses"},
        {"title": "Analyst", "description": "Investigate suspicious card payments"},
    ]
    for job in jobs:
        job["description"] = preamble + job["description"]

    class Model:
        def invoke(self, messages, **kwargs):
            payload = json.loads(messages[1][1])
            assert payload["jobs"] == [
                {"job_id": "j0", **jobs[0]},
                {"job_id": "j1", **jobs[1]},
            ]
            return SimpleNamespace(
                content=json.dumps(
                    [
                        {"name": "Data Engineer", "job_ids": ["j0"]},
                        {"name": "Fraud Analyst", "job_ids": ["j1"]},
                    ]
                )
            )

    monkeypatch.setattr(
        job_groups, "_get_extraction_llm", lambda **kwargs: Model(), raising=False
    )
    assert job_groups.group_jobs_by_title(jobs) == {
        "Data Engineer": [0],
        "Fraud Analyst": [1],
    }


@pytest.mark.parametrize(
    "response",
    [
        [{"name": "Data Engineer", "job_ids": ["j0"]}],
        [{"name": "Data Engineer", "job_ids": ["j0", "j0", "j1"]}],
        [{"name": "Data Engineer", "job_ids": ["j0", "j1", "j99"]}],
        [
            {"name": "Data Engineer", "job_ids": ["j0"]},
            {"name": "Data Engineer", "job_ids": ["j1"]},
        ],
        [{"name": "", "job_ids": ["j0", "j1"]}],
        [{"name": "Data Engineer", "job_ids": [0, 1]}],
        {"Data Engineer": ["j0", "j1"]},
    ],
)
def test_invalid_ai_partition_keeps_every_original_posting_separate(
    monkeypatch, response
):
    jobs = [{"title": "Data Engineer"}, {"title": "Middle Data Engineer"}]
    model_response(monkeypatch, response)
    assert job_groups.group_jobs_by_title(jobs) == {
        "Data Engineer [posting 1]": [0],
        "Middle Data Engineer [posting 2]": [1],
    }


def test_model_failure_never_reverts_to_title_rules(monkeypatch):
    jobs = [{"title": "Data Engineer"}, {"title": "Middle Data Engineer"}]
    model_response(monkeypatch, error=TimeoutError("model unavailable"))
    assert job_groups.group_jobs_by_title(jobs) == {
        "Data Engineer [posting 1]": [0],
        "Middle Data Engineer [posting 2]": [1],
    }


def test_empty_and_single_posting_need_no_semantic_decision(monkeypatch):
    model_response(monkeypatch, error=AssertionError("No grouping needed"))
    assert job_groups.group_jobs_by_title([]) == {}
    assert job_groups.group_jobs_by_title([{"title": "Middle Data Engineer"}]) == {
        "Middle Data Engineer": [0]
    }


def test_busy_model_pool_keeps_postings_without_an_unbounded_wait(monkeypatch):
    class BusyPool:
        def acquire(self, *, timeout):
            assert 0 < timeout <= 5
            return False

        def __enter__(self):
            pytest.fail("Grouping must bound its wait for a model slot")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(job_groups, "_EXTRACTION_SLOTS", BusyPool())
    model_response(monkeypatch, error=AssertionError("Busy pool must not call model"))
    assert job_groups.group_jobs_by_title(
        [{"title": "Data Engineer"}, {"title": "Middle Data Engineer"}]
    ) == {
        "Data Engineer [posting 1]": [0],
        "Middle Data Engineer [posting 2]": [1],
    }


def test_collected_source_jobs_use_ai_groups(monkeypatch):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    class Sources:
        def load_config(self, state):
            return {"country": "Uzbekistan", "evidence_sources": ["jobs"]}

        def collect_sources(self, *args, **kwargs):
            return {
                "jobs": [
                    {"title": "Data Engineer"},
                    {"title": "Разработчик платформы данных"},
                ],
                "source_outcomes": {},
                "candidate_revision": 1,
                "onet_evidence": [],
                "candidates": [],
            }

    monkeypatch.setattr(tools, "get_market_source_service", Sources)
    model_response(monkeypatch, [{"name": "Data Engineer", "job_ids": ["j0", "j1"]}])
    with bind_tool_store({"run_id": "run"}):
        tools.fetch_jobs.invoke(
            {"search_terms": "Data Engineer", "country": "Uzbekistan"}
        )
        assert tools.tool_store["job_groups"] == {"Data Engineer": [0, 1]}
