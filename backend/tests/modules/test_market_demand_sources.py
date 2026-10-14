"""Selected-source boundary, deterministic merge, and concurrency behavior."""

from threading import Barrier, Lock

import pandas as pd
import pytest


def service(scrape=None, hh=None, configured=True):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService

    return JobSourceService(
        user_agent="test" if configured else None,
        access_token="synthetic-secret" if configured else None,
        jobspy_scraper=scrape,
        headhunter=hh,
    )


def country(raw="Uzbekistan"):
    from app.modules.marketdemandanalyst.countries import normalize_job_search_country

    return normalize_job_search_country(raw)


def test_uzbekistan_aliases_and_catalog_without_network():
    for raw in ["UZ", "Uzbekistan", "O‘zbekiston"]:
        assert country(raw).key == "Uzbekistan"
        assert country(raw).jobspy_country is None
    entries = {item.id: item for item in service(configured=False).catalog(country())}
    assert entries["indeed"].availability == "unsupported_country"
    assert entries["linkedin"].availability == "available"
    assert entries["headhunter"].availability == "not_configured"
    assert service().catalog(country())[2].availability == "available"


def test_uzbek_country_confirmation_keeps_the_configured_country_key():
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.tools import set_job_search_country

    state = {"run_id": "owned-run", "job_search_country": "Uzbekistan"}
    with bind_tool_store(state):
        set_job_search_country.invoke({"country": "Uzbekistan"})
    assert state["job_search_country"] == "Uzbekistan"
    assert state["job_search_country_confirmed"] is True


def test_normalize_sources_rejects_empty_unknown_and_deduplicates():
    from app.modules.marketdemandanalyst.job_sources import normalize_job_sources

    assert normalize_job_sources(None) == ("indeed", "linkedin", "headhunter")
    assert normalize_job_sources(["headhunter", "linkedin", "headhunter"]) == (
        "linkedin",
        "headhunter",
    )
    for values in [[], ["other"]]:
        with pytest.raises(ValueError):
            normalize_job_sources(values)


def test_catalog_requires_owned_teacher_course(client, teacher_auth_headers):
    response = client.post(
        "/courses", json={"title": "Source course"}, headers=teacher_auth_headers
    )
    course_id = response.json()["id"]
    response = client.get(
        f"/courses/{course_id}/market-demand/sources?country=Uzbekistan",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert [item["id"] for item in response.json()] == [
        "indeed",
        "linkedin",
        "headhunter",
    ]
    assert (
        client.get(
            f"/courses/{course_id + 1000}/market-demand/sources",
            headers=teacher_auth_headers,
        ).status_code
        == 404
    )
    assert "synthetic-secret" not in response.text


def test_only_selected_provider_no_fallback_and_uzbek_linkedin_arguments():
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "id": "a",
                    "title": "Developer",
                    "company": "Company",
                    "description": "Python " * 20,
                    "job_url": "https://www.linkedin.com/jobs/view/a",
                }
            ]
        )

    result = service(scrape=scrape).fetch(
        search_terms=["Python", " Python "], country=country(), sources=("linkedin",)
    )
    assert len(result.records) == 1
    assert set(result.outcomes) == {"linkedin"}
    assert calls[0]["site_name"] == ["linkedin"]
    assert calls[0]["location"] == "Uzbekistan"
    assert "country_indeed" not in calls[0]
    assert len(calls) == 1

    def failing(**kwargs):
        raise RuntimeError("synthetic-secret Authorization failure")

    result = service(scrape=failing).fetch(
        search_terms=["Python"], country=country(), sources=("linkedin",)
    )
    assert not result.records and result.outcomes["linkedin"].status == "error"
    assert "synthetic-secret" not in result.model_dump_json()


def test_same_title_company_different_ids_retained_and_short_payloads_not_filtered():
    rows = [
        {
            "id": str(i),
            "title": "Same",
            "company": "Same",
            "description": "x" if i == 1 else "Python " * 30,
            "job_url": f"https://www.linkedin.com/jobs/view/{i}",
        }
        for i in [1, 2]
    ]
    result = service(scrape=lambda **kwargs: pd.DataFrame(rows)).fetch(
        search_terms=["Python"], country=country(), sources=("linkedin",)
    )
    assert len(result.records) == 2
    assert result.outcomes["linkedin"].received_count == 2
    assert result.outcomes["linkedin"].usable_count == 1
    assert result.records[0].raw_payload["description"] == "x"


def test_selected_sources_overlap_and_headhunter_concurrency_is_bounded():
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy
    from app.providers.headhunter import HeadHunterSearchResult

    overlap = Barrier(2, timeout=5)
    two_hh = Barrier(2, timeout=5)
    lock = Lock()
    active = maximum = 0
    calls = []

    class HH:
        def search_jobs(self, term, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
                calls.append(term)
            if term == "first":
                overlap.wait()
            if term in ["first", "second"]:
                two_hh.wait()
            with lock:
                active -= 1
            return HeadHunterSearchResult(
                jobs=[
                    ProviderVacancy(
                        provider="headhunter",
                        native_id=term,
                        title=term,
                        original_url=f"https://hh.uz/vacancy/{term}",
                        original_description="Python " * 20,
                        description_text="Python " * 20,
                        raw_payload={"id": term},
                    )
                ]
            )

    def scrape(**kwargs):
        if kwargs["search_term"] == "first":
            overlap.wait()
        return pd.DataFrame()

    result = service(scrape=scrape, hh=HH()).fetch(
        search_terms=["first", "second", "third", "fourth"],
        country=country(),
        sources=("linkedin", "headhunter"),
    )
    assert maximum == 2
    assert calls and len(result.records) == 4
    assert result.outcomes["headhunter"].status == "success"
    assert result.outcomes["linkedin"].status == "empty"


def test_onet_only_skips_unavailable_provider_validation_and_fetch():
    svc = service(
        scrape=lambda **kwargs: pytest.fail("O*NET-only fetch"), configured=False
    )
    svc.validate_compatibility(
        country(), ("indeed", "headhunter"), evidence_sources=("onet",)
    )
    result = svc.fetch(
        search_terms=["Python"],
        country=country(),
        sources=("indeed", "headhunter"),
        evidence_sources=("onet",),
    )
    assert not result.records and not result.outcomes


def test_automatic_sources_keep_uzbek_jobs_when_other_providers_unavailable():
    def scrape(**kwargs):
        assert kwargs["site_name"] == ["linkedin"]
        assert kwargs["location"] == "Uzbekistan"
        assert "country_indeed" not in kwargs
        return pd.DataFrame(
            [
                {
                    "id": "uz1",
                    "title": "Engineer",
                    "company": "Local",
                    "description": "SQL Python " * 10,
                    "job_url": "https://www.linkedin.com/jobs/view/uz1",
                }
            ]
        )

    result = service(scrape=scrape, configured=False).fetch(
        search_terms=["Engineer"],
        country=country(),
        sources=("indeed", "linkedin", "headhunter"),
    )
    assert len(result.jobs) == 1
    assert result.outcomes["linkedin"].status == "success"
    assert result.outcomes["indeed"].status == "error"
    assert "country" in " ".join(result.outcomes["indeed"].warnings)
    assert result.outcomes["headhunter"].status == "error"
    assert "configured" in " ".join(result.outcomes["headhunter"].warnings)


def test_all_unavailable_providers_fail_before_network_work():
    svc = service(
        scrape=lambda **kwargs: pytest.fail("unavailable provider request"),
        configured=False,
    )
    with pytest.raises(ValueError, match="No available job provider"):
        svc.fetch(
            search_terms=["Engineer"],
            country=country(),
            sources=("indeed", "headhunter"),
        )


def test_partial_failure_preserves_other_query_results_with_safe_outcomes():
    def scrape(**kwargs):
        if kwargs["search_term"] == "failing":
            raise RuntimeError("synthetic-secret")
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Python",
                    "description": "Python " * 30,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                }
            ]
        )

    result = service(scrape=scrape).fetch(
        search_terms=["ok", "failing"], country=country(), sources=("linkedin",)
    )
    assert len(result.records) == 1
    assert result.outcomes["linkedin"].status == "partial"
    assert result.outcomes["linkedin"].received_count == 1
    assert "synthetic-secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "terms,cap", [([], 15), ([" "], 15), (["ok"], 0), (["ok"], 101)]
)
def test_invalid_fetch_never_starts_source_tasks(terms, cap):
    with pytest.raises(ValueError):
        service(scrape=lambda **kwargs: pytest.fail("invalid dispatch")).fetch(
            search_terms=terms,
            country=country(),
            sources=("linkedin",),
            results_per_source=cap,
        )


def test_direct_posting_link_survives_normalization_and_repeated_query_union():
    def scrape(**kwargs):
        return pd.DataFrame(
            [
                {
                    "id": "10",
                    "title": "Python",
                    "description": "Python " * 1000,
                    "job_url": "https://www.linkedin.com/jobs/view/10",
                    "job_url_direct": "https://company.example/careers/10",
                }
            ]
        )

    result = service(scrape=scrape).fetch(
        search_terms=["Python", "Data"], country=country(), sources=("linkedin",)
    )
    assert len(result.records) == 1
    assert result.records[0].source_urls == [
        "https://www.linkedin.com/jobs/view/10",
        "https://company.example/careers/10",
    ]
    assert result.records[0].query_membership == ["Python", "Data"]
    assert len(result.jobs[0]["description"]) == 7000
    assert result.jobs[0]["source_urls"] == [
        "https://www.linkedin.com/jobs/view/10",
        "https://company.example/careers/10",
    ]


@pytest.mark.parametrize(
    "url,identity",
    [
        (
            "HTTPS://HH.UZ:443/Vacancy/10?b=2&a=1#A",
            "url:https://hh.uz/Vacancy/10?b=2&a=1#A",
        ),
        ("http://HH.UZ:80/vacancy/10", "url:http://hh.uz/vacancy/10"),
        (
            "https://HH.UZ:8443/vacancy/10?ref=Original#different-vacancy",
            "url:https://hh.uz:8443/vacancy/10?ref=Original#different-vacancy",
        ),
    ],
)
def test_url_only_identity_normalizes_safe_parts_and_keeps_original(url, identity):
    from app.modules.marketdemandanalyst.job_sources import vacancy_identity
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy

    record = ProviderVacancy(provider="headhunter", title="Python", original_url=url)
    assert vacancy_identity(record) == identity
    assert record.original_url == url


def test_url_identity_preserves_path_case_query_order_and_fragments():
    from app.modules.marketdemandanalyst.job_sources import vacancy_identity
    from app.modules.marketdemandanalyst.schemas import ProviderVacancy

    urls = [
        "https://hh.uz/Vacancy/10?a=1&b=2#one",
        "https://hh.uz/vacancy/10?a=1&b=2#one",
        "https://hh.uz/Vacancy/10?b=2&a=1#one",
        "https://hh.uz/Vacancy/10?a=1&b=2#two",
    ]
    identities = [
        vacancy_identity(
            ProviderVacancy(provider="headhunter", title="Python", original_url=url)
        )
        for url in urls
    ]
    assert len(set(identities)) == 4


def test_eight_queries_start_both_selected_providers_before_any_release():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from app.modules.marketdemandanalyst.schemas import ProviderVacancy
    from app.providers.headhunter import HeadHunterSearchResult

    release = Event()
    linkedin_started = Event()
    linkedin_completed = Event()
    hh_started = Event()
    two_hh_started = Event()
    active_lock = Lock()
    active = maximum = 0

    def scrape(**kwargs):
        linkedin_started.set()
        if not release.wait(10):
            raise TimeoutError("LinkedIn test provider was not released")
        linkedin_completed.set()
        term = kwargs["search_term"]
        return pd.DataFrame(
            [
                {
                    "id": term,
                    "title": term,
                    "description": "Python " * 20,
                    "job_url": f"https://www.linkedin.com/jobs/view/{term}",
                }
            ]
        )

    class HH:
        def search_jobs(self, term, **kwargs):
            nonlocal active, maximum
            with active_lock:
                active += 1
                maximum = max(maximum, active)
                if active == 2:
                    two_hh_started.set()
            hh_started.set()
            try:
                if not release.wait(10):
                    raise TimeoutError("HeadHunter test provider was not released")
                return HeadHunterSearchResult(
                    jobs=[
                        ProviderVacancy(
                            provider="headhunter",
                            native_id=term,
                            title=term,
                            original_url=f"https://hh.uz/vacancy/{term}",
                            original_description="Python " * 20,
                            description_text="Python " * 20,
                            raw_payload={"id": term},
                            query_membership=[term],
                        )
                    ]
                )
            finally:
                with active_lock:
                    active -= 1

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            service(scrape=scrape, hh=HH()).fetch,
            search_terms=[f"q{i}" for i in range(8)],
            country=country(),
            sources=("linkedin", "headhunter"),
        )
        try:
            assert linkedin_started.wait(5), "First selected provider never started"
            assert hh_started.wait(5), (
                "Second selected provider was starved by the initial eight tasks"
            )
            assert two_hh_started.wait(5), (
                "Two HeadHunter slots were never used concurrently"
            )
            assert not linkedin_completed.is_set(), (
                "First provider completed before second provider started"
            )
        finally:
            release.set()
        result = future.result(timeout=12)
    assert maximum == 2
    assert len(result.records) == 16
    assert [record.provider for record in result.records] == ["linkedin"] * 8 + [
        "headhunter"
    ] * 8
    assert [
        record.native_id for record in result.records if record.provider == "headhunter"
    ] == [f"q{i}" for i in range(8)]
