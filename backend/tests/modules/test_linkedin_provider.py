"""Exercise JobSpy's real card/detail parser at the HTTP boundary."""

from types import SimpleNamespace

import pytest


@pytest.mark.parametrize(
    "location",
    ["Tashkent, Tashkent, Uzbekistan", "Almaty, Almaty, Kazakhstan", "Uzbekistan"],
)
def test_unlisted_location_country_does_not_discard_linkedin_jobs(
    monkeypatch, location
):
    from app.modules.marketdemandanalyst.countries import normalize_job_search_country
    from app.modules.marketdemandanalyst.job_sources import JobSourceService

    requests = []

    class Session:
        headers = {}

        def get(self, url, **kwargs):
            requests.append((url, kwargs))
            if "seeMoreJobPostings" in url:
                html = f"""<div class="base-search-card">
                  <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/data-engineer-123?tracking=x">
                    <span class="sr-only">Middle Data Engineer</span></a>
                  <h4 class="base-search-card__subtitle"><a href="https://www.linkedin.com/company/example">Example</a></h4>
                  <div class="base-search-card__metadata">
                    <span class="job-search-card__location">{location}</span>
                    <time class="job-search-card__listdate" datetime="2026-10-15"></time>
                  </div></div>"""
            else:
                assert url == "https://www.linkedin.com/jobs/view/123"
                html = '<div class="show-more-less-html__markup">Build data pipelines with Python and SQL. Maintain reliable data warehouses and ETL processes.</div>'
            return SimpleNamespace(
                status_code=200, text=html, url=url, raise_for_status=lambda: None
            )

    monkeypatch.setattr("jobspy.linkedin.create_session", lambda **kwargs: Session())
    result = JobSourceService().fetch(
        search_terms=["Data Engineer"],
        country=normalize_job_search_country("Uzbekistan"),
        sources=("linkedin",),
        results_per_source=1,
    )
    assert result.outcomes["linkedin"].status == "success"
    assert len(result.jobs) == 1
    record = result.records[0]
    assert record.native_id == "li-123"
    assert record.title == "Middle Data Engineer"
    assert record.original_url == "https://www.linkedin.com/jobs/view/123"
    assert record.location == location
    assert "ETL processes" in record.description_text
    assert (
        record.raw_payload["company_url"] == "https://www.linkedin.com/company/example"
    )
    assert requests[0][1]["params"]["location"] == "Uzbekistan"
    assert len(requests) == 2
