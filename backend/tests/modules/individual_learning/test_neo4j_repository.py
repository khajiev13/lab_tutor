from __future__ import annotations

from app.modules.individual_learning import neo4j_repository
from app.modules.individual_learning.schemas import CVSkillExtraction


class FakeResult:
    def __init__(
        self, single_record: dict | None = None, rows: list[dict] | None = None
    ) -> None:
        self._single_record = single_record
        self._rows = rows or []

    def single(self):
        return self._single_record

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._results = list(results or [FakeResult({"written": 1})])

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if self._results:
            return self._results.pop(0)
        return FakeResult({"written": 1})


def test_upsert_cv_skills_uses_cv_skill_label_and_has_skill() -> None:
    session = FakeSession()

    count = neo4j_repository.upsert_cv_skills(
        session,
        user_id=7,
        skills=[
            CVSkillExtraction(name="Python", evidence="Built APIs", confidence=0.9)
        ],
        cv_document_id=3,
        extraction_run_id=5,
    )

    query, params = session.calls[0]

    assert count == 1
    assert "MATCH (u:USER:INDIVIDUAL {id: $user_id})" in query
    assert "MERGE (sk:SKILL:CV_SKILL" in query
    assert "MERGE (u)-[r:HAS_SKILL]->(sk)" in query
    assert params["user_id"] == 7
    assert params["cv_document_id"] == 3
    assert params["extraction_run_id"] == 5


def test_upsert_job_postings_and_market_skills_uses_market_skill_and_sourced_from() -> (
    None
):
    session = FakeSession(
        [
            FakeResult({"written": 1}),
            FakeResult({"written": 2}),
        ]
    )

    counts = neo4j_repository.upsert_job_postings_and_market_skills(
        session,
        jobs=[
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "company": "Example",
            }
        ],
        skills_by_job_url={
            "https://jobs.example/backend": [
                {
                    "name": "Python",
                    "category": "Programming",
                    "description": "Backend work",
                },
                {"name": "SQL"},
            ]
        },
    )

    jobs_query = session.calls[0][0]
    skills_query, params = session.calls[1]

    assert counts == {"jobs": 1, "market_skills": 2}
    assert "MERGE (jp:JOB_POSTING {url: job.url})" in jobs_query
    assert "MERGE (sk:SKILL:MARKET_SKILL {name: pair.name})" in skills_query
    assert "MERGE (sk)-[:SOURCED_FROM]->(jp)" in skills_query
    assert "CV_SKILL" not in skills_query
    assert params["pairs"] == [
        {
            "url": "https://jobs.example/backend",
            "name": "Python",
            "category": "Programming",
            "description": "Backend work",
        },
        {"url": "https://jobs.example/backend", "name": "SQL"},
    ]


def test_select_job_postings_links_individual_directly_to_job_postings() -> None:
    session = FakeSession([FakeResult({"written": 1})])

    count = neo4j_repository.select_job_postings(
        session,
        user_id=7,
        posting_urls=["https://jobs.example/backend"],
        run_id="run-123",
    )

    query, params = session.calls[0]

    assert count == 1
    assert "MATCH (u:USER:INDIVIDUAL {id: $user_id})" in query
    assert "MATCH (jp:JOB_POSTING {url: url})" in query
    assert "MERGE (u)-[r:INTERESTED_IN]->(jp)" in query
    assert "INTERESTED_POSITION" not in query
    assert params["run_id"] == "run-123"


def test_select_market_skills_rejects_cv_skill_label() -> None:
    session = FakeSession()

    count = neo4j_repository.select_market_skills(
        session, user_id=7, skill_names=["Python"]
    )
    query, params = session.calls[0]

    assert count == 1
    assert "MATCH (sk:SKILL:MARKET_SKILL" in query
    assert "CV_SKILL" not in query
    assert "MERGE (u)-[r:SELECTED_SKILL]->(sk)" in query
    assert params["source"] == "individual_market_skill"


def test_select_candidate_market_skills_is_scoped_to_selected_candidate_jobs() -> None:
    session = FakeSession([FakeResult({"written": 1})])

    count = neo4j_repository.select_candidate_market_skills(
        session,
        user_id=7,
        skill_names=["Docker"],
        posting_urls=["https://jobs.example/backend"],
        job_search_run_id="12",
        match_run_id="13",
    )

    query, params = session.calls[0]

    assert count == 1
    assert "MATCH (jp:JOB_POSTING)<-[:SOURCED_FROM]-(sk:SKILL:MARKET_SKILL" in query
    assert "WHERE jp.url IN $posting_urls" in query
    assert "MERGE (u)-[r:SELECTED_SKILL]->(sk)" in query
    assert "CV_SKILL" not in query
    assert params["posting_urls"] == ["https://jobs.example/backend"]
    assert params["job_search_run_id"] == "12"
    assert params["match_run_id"] == "13"


def test_resolve_interested_market_skills_requires_user_job_interest() -> None:
    session = FakeSession([FakeResult(rows=[{"name": "Docker"}])])

    names = neo4j_repository.resolve_interested_market_skill_names(
        session,
        user_id=7,
        skill_names=["Docker", "CV-only"],
    )

    query, params = session.calls[0]

    assert names == ["Docker"]
    assert "(u)-[:INTERESTED_IN]->(jp:JOB_POSTING)" in query
    assert "(sk:SKILL:MARKET_SKILL)-[:SOURCED_FROM]->(jp)" in query
    assert "CV_SKILL" not in query
    assert params == {"user_id": 7, "skill_names": ["Docker", "CV-only"]}


def test_get_individual_skill_bank_reads_only_market_skills_from_interested_jobs() -> (
    None
):
    session = FakeSession(
        [
            FakeResult(rows=[{"url": "https://jobs.example/backend"}]),
            FakeResult(rows=[{"name": "Python"}]),
            FakeResult(
                rows=[
                    {
                        "posting": {
                            "url": "https://jobs.example/backend",
                            "title": "Backend Engineer",
                            "company": "Example",
                            "skills": [{"name": "Python", "category": "Programming"}],
                        }
                    }
                ]
            ),
        ]
    )

    result = neo4j_repository.get_individual_skill_bank(session, user_id=7)
    interested_query, interested_params = session.calls[0]
    selected_query, selected_params = session.calls[1]
    bank_query, bank_params = session.calls[2]

    assert result == {
        "postings": [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "company": "Example",
                "skills": [{"name": "Python", "category": "Programming"}],
            }
        ],
        "selected_skill_names": ["Python"],
        "interested_posting_urls": ["https://jobs.example/backend"],
    }
    assert (
        "MATCH (u:USER:INDIVIDUAL {id: $user_id})-[r:INTERESTED_IN]->(jp:JOB_POSTING)"
        in interested_query
    )
    assert (
        "MATCH (:USER:INDIVIDUAL {id: $user_id})-[:SELECTED_SKILL]->(sk:MARKET_SKILL)"
        in selected_query
    )
    assert "MATCH (jp:JOB_POSTING)<-[:SOURCED_FROM]-(ms:MARKET_SKILL)" in bank_query
    assert "CV_SKILL" not in bank_query
    assert interested_params["user_id"] == 7
    assert selected_params["user_id"] == 7
    assert bank_params["interested_urls"] == ["https://jobs.example/backend"]
