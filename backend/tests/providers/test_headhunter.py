"""Synthetic HTTP boundary tests; no live credentials or provider calls."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest


def detail(native_id="10", **overrides):
    return {
        "id": native_id,
        "name": "Разработчик",
        "employer": None,
        "area": {"id": "97", "name": "Toshkent"},
        "description": "<p>Python — ma’lumotlar</p><ul><li>Русский</li><li>中文</li></ul>"
        + "x" * 6000,
        "alternate_url": f"https://hh.uz/vacancy/{native_id}",
        "key_skills": [{"name": "Python"}, {"name": ""}],
        "published_at": "2026-10-08T10:00:00+0500",
        "archived": False,
        "salary_range": {"from": 1000, "currency": "UZS"},
        "unfamiliar": {"nested": ["keep", "everything"]},
        **overrides,
    }


def provider(handler):
    from app.providers.headhunter import HeadHunterService

    return HeadHunterService(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="LabTutor test@example.invalid",
        access_token="synthetic-secret",
    )


def test_search_fetches_full_details_with_correct_headers_and_market():
    calls = []
    payload = detail()

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-secret"
        assert request.headers["HH-User-Agent"] == "LabTutor test@example.invalid"
        assert request.url.host == "api.hh.ru"
        assert request.url.params["host"] == "hh.uz"
        assert request.extensions["timeout"]["read"] == 15
        assert request.extensions["timeout"]["connect"] == 5
        if request.url.path == "/vacancies":
            assert request.url.params["area"] == "97"
            assert request.url.params["page"] == "0"
            assert request.url.params["per_page"] == "15"
            assert "period" not in request.url.params
            since = datetime.fromisoformat(request.url.params["date_from"])
            assert (
                abs((datetime.now(UTC) - timedelta(hours=72) - since).total_seconds())
                < 3
            )
            return httpx.Response(
                200,
                json={
                    "items": [{"id": "10", "employer": {"name": "Search employer"}}],
                    "pages": 1,
                },
            )
        return httpx.Response(200, json=payload)

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=15)
    assert len(calls) == 2
    job = result.jobs[0]
    assert job.raw_payload == payload
    assert job.original_description == payload["description"]
    assert len(job.description_text) > 6000
    assert job.company == "Search employer"
    assert job.skill_tags == ["Python"]
    assert job.original_url == "https://hh.uz/vacancy/10"
    assert "synthetic-secret" not in result.model_dump_json()


def test_multilingual_html_normalization():
    from app.providers.headhunter import html_to_text

    assert (
        html_to_text(
            "<p>O‘zbekiston &amp; 中文</p><script>secret()</script><style>x</style><ul><li>Русский</li><li>Python</li></ul>"
        )
        == "O‘zbekiston & 中文\nРусский\nPython"
    )


def test_missing_employer_and_repeated_ids_fetch_once():
    details = []

    def handler(request):
        if request.url.path == "/vacancies":
            return httpx.Response(
                200,
                json={"items": [{"id": "10"}, {"id": "10"}, {"id": "11"}], "pages": 1},
            )
        details.append(request.url.path)
        return httpx.Response(200, json=detail(request.url.path.rsplit("/", 1)[1]))

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=15)
    assert len(result.jobs) == 2
    assert len(details) == 2
    assert result.jobs[0].company == ""


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>CAPTCHA</html>"),
        httpx.Response(200, json={"items": "bad"}),
        httpx.Response(200, json={"items": [], "pages": "bad"}),
    ],
)
def test_malformed_search_stops_with_safe_error(response):
    result = provider(lambda request: response).search_jobs(
        "Python", area_id="97", results_wanted=15
    )
    assert result.error
    assert "CAPTCHA" not in result.model_dump_json()
    assert not result.jobs


def test_detail_404_is_partial_and_forbidden_stops_details():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/vacancies":
            return httpx.Response(
                200, json={"items": [{"id": str(i)} for i in range(4)], "pages": 1}
            )
        native_id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(
            {"0": 404, "1": 200, "2": 403}[native_id], json=detail(native_id)
        )

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=15)
    assert [job.native_id for job in result.jobs] == ["1"]
    assert result.warnings and result.error
    assert "/vacancies/3" not in calls


@pytest.mark.parametrize("status", [401, 403, 400])
def test_terminal_auth_errors_are_not_retried(status):
    calls = []
    result = provider(
        lambda request: (
            calls.append(request),
            httpx.Response(status, json={"errors": [{"value": "synthetic-secret"}]}),
        )[1]
    ).search_jobs("Python", area_id="97", results_wanted=15)
    assert len(calls) == 1
    assert result.error
    assert "synthetic-secret" not in result.model_dump_json()


def test_retry_budget_and_large_retry_after(monkeypatch):
    from app.providers import headhunter

    delays = []
    monkeypatch.setattr(headhunter.time, "sleep", delays.append)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "100"})

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=15)
    assert result.error and len(calls) == 1 and not delays
    calls.clear()
    result = provider(
        lambda request: (calls.append(request), httpx.Response(503))[1]
    ).search_jobs("Python", area_id="97", results_wanted=15)
    assert result.error and len(calls) == 3 and sum(delays) <= 5


@pytest.mark.parametrize("term,cap", [("", 15), ("Python", 0), ("Python", 101)])
def test_invalid_queries_do_not_contact_provider(term, cap):
    with pytest.raises(ValueError):
        provider(
            lambda request: pytest.fail("invalid query made HTTP request")
        ).search_jobs(term, area_id="97", results_wanted=cap)


def test_pagination_fetches_details_until_result_cap_and_keeps_partial_on_bad_detail():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/vacancies":
            page = int(request.url.params["page"])
            return httpx.Response(
                200, json={"items": [{"id": str(page + 1)}], "pages": 3}
            )
        if request.url.path.endswith("/2"):
            return httpx.Response(200, json={"id": "2", "description": ["malformed"]})
        return httpx.Response(200, json=detail("1"))

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=2)
    assert [job.native_id for job in result.jobs] == ["1"]
    assert result.error and len(calls) == 4


def test_echoed_credentials_never_escape_records_or_descriptions():
    def handler(request):
        if request.url.path == "/vacancies":
            return httpx.Response(200, json={"items": [{"id": "10"}], "pages": 1})
        return httpx.Response(
            200,
            json=detail(
                description="<p>synthetic-secret</p>",
                unexpected={
                    "Authorization": "Bearer synthetic-secret",
                    "note": "synthetic-secret",
                },
            ),
        )

    result = provider(handler).search_jobs("Python", area_id="97", results_wanted=15)
    assert result.jobs and "synthetic-secret" not in result.model_dump_json()
