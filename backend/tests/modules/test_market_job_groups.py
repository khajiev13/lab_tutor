"""Role groups combine seniority/translation variants without losing postings."""

from copy import deepcopy


def test_seniority_and_bilingual_variants_keep_all_original_postings():
    from app.modules.marketdemandanalyst.job_groups import group_jobs_by_title

    titles = [
        "Data Engineer",
        "Middle Data Engineer",
        "Senior Data Engineer",
        "Data Engineer (Middle+)",
        "Data Engineer/Младший Инженер Данных",
        "Младший инженер данных",
        "Data Analyst / Младший Аналитик Данных",
        "Младший Аналитик Данных (Junior Data Analyst)",
        "Data Systems Engineer",
        "Data Scientist / ML Engineer (Middle+)",
        "Fraud Analyst",
    ]
    jobs = [
        {"title": title, "url": f"https://hh.uz/vacancy/{i}"}
        for i, title in enumerate(titles)
    ]
    original = deepcopy(jobs)
    groups = group_jobs_by_title(jobs)
    assert groups["Data Engineer"] == list(range(6))
    assert groups["Data Analyst"] == [6, 7]
    assert groups["Data Systems Engineer"] == [8]
    assert groups["Data Scientist / Ml Engineer"] == [9]
    assert groups["Fraud Analyst"] == [10]
    assert sorted(i for indices in groups.values() for i in indices) == list(range(11))
    assert jobs == original
    assert list(groups)[:2] == ["Data Engineer", "Data Analyst"]


def test_distinct_specializations_and_mixed_roles_are_not_fuzzy_merged():
    from app.modules.marketdemandanalyst.job_groups import group_jobs_by_title

    titles = [
        "Data Engineer",
        "Data Engineer / Data Analyst",
        "Data Platform Engineer",
        "Data Quality Engineer",
        "Database Engineer",
        "Data Analyst",
        "Business Analyst",
        "Java Developer",
        "C++/Java Software Engineer",
    ]
    groups = group_jobs_by_title([{"title": title} for title in titles])
    assert len(groups) == len(titles)


def test_collected_source_jobs_use_the_shared_role_groups(monkeypatch):
    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    class Sources:
        def load_config(self, state):
            return {"country": "Uzbekistan", "evidence_sources": ["jobs"]}

        def collect_sources(self, *args, **kwargs):
            return {
                "jobs": [{"title": "Data Engineer"}, {"title": "Middle Data Engineer"}],
                "source_outcomes": {},
                "candidate_revision": 1,
                "onet_evidence": [],
                "candidates": [],
            }

    monkeypatch.setattr(tools, "get_market_source_service", Sources)
    with bind_tool_store({"run_id": "run"}):
        tools.fetch_jobs.invoke(
            {"search_terms": "Data Engineer", "country": "Uzbekistan"}
        )
        assert tools.tool_store["job_groups"] == {"Data Engineer": [0, 1]}
