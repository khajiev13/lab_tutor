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
    session = FakeSession([FakeResult({"written": 1})])

    count = neo4j_repository.upsert_cv_skills(
        session,
        user_id=7,
        skills=[
            CVSkillExtraction(name="Python", evidence="Built APIs", confidence=0.9)
        ],
        cv_document_id=3,
        extraction_run_id=5,
    )

    assert len(session.calls) == 1
    query, params = session.calls[0]

    assert count == 1
    assert "MERGE (u:USER {id: $user_id})" in query
    assert "SET u:INDIVIDUAL" in query
    assert "OPTIONAL MATCH (u)-[stale:HAS_SKILL]->(existing:SKILL:CV_SKILL)" in query
    assert "collect({relationship: stale, name: existing.name})" in query
    assert "NOT item.name IN $skill_names" in query
    assert "DELETE item.relationship" in query
    assert "FOREACH (skill IN $skills" in query
    assert "MERGE (sk:SKILL:CV_SKILL" in query
    assert "MERGE (u)-[r:HAS_SKILL]->(sk)" in query
    assert params["user_id"] == 7
    assert params["skill_names"] == ["Python"]
    assert params["cv_document_id"] == 3
    assert params["extraction_run_id"] == 5


def test_upsert_cv_skills_self_heals_missing_individual_and_counts_distinct_skills() -> (
    None
):
    session = FakeSession([FakeResult({"written": 2})])

    count = neo4j_repository.upsert_cv_skills(
        session,
        user_id=404,
        skills=[
            CVSkillExtraction(name=" Python "),
            CVSkillExtraction(name="python"),
            CVSkillExtraction(name="Docker"),
        ],
        cv_document_id=3,
        extraction_run_id=5,
    )

    query, params = session.calls[0]
    assert count == 2
    assert len(session.calls) == 1
    assert "MERGE (u:USER {id: $user_id})" in query
    assert "SET u:INDIVIDUAL" in query
    assert params["skill_names"] == ["Python", "Docker"]
    assert [skill["name"] for skill in params["skills"]] == ["Python", "Docker"]


def test_second_cv_projection_replaces_skills_removed_from_first_cv() -> None:
    session = FakeSession([FakeResult({"written": 2}), FakeResult({"written": 1})])

    neo4j_repository.upsert_cv_skills(
        session,
        user_id=7,
        skills=[CVSkillExtraction(name="Python"), CVSkillExtraction(name="Legacy")],
        cv_document_id=3,
        extraction_run_id=5,
    )
    count = neo4j_repository.upsert_cv_skills(
        session,
        user_id=7,
        skills=[CVSkillExtraction(name="Docker")],
        cv_document_id=4,
        extraction_run_id=6,
    )

    second_query, second_params = session.calls[1]
    assert count == 1
    assert "NOT item.name IN $skill_names" in second_query
    assert "DELETE item.relationship" in second_query
    assert second_params["skill_names"] == ["Docker"]
    assert second_params["cv_document_id"] == 4
    assert second_params["extraction_run_id"] == 6


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
    assert "jp.skill_extraction_status" in jobs_query
    assert "jp.skill_extraction_error" in jobs_query
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
    assert "OPTIONAL MATCH (u)-[stale:INTERESTED_IN]->(:JOB_POSTING)" in query
    assert "DELETE relationship" in query
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
    assert "OPTIONAL MATCH (u)-[stale:SELECTED_SKILL]->(:SKILL:MARKET_SKILL)" in query
    assert "DELETE relationship" in query
    assert "MERGE (u)-[r:SELECTED_SKILL]->(sk)" in query
    assert "CV_SKILL" not in query
    assert params["posting_urls"] == ["https://jobs.example/backend"]
    assert params["job_search_run_id"] == "12"
    assert params["match_run_id"] == "13"


def test_second_checkpoint_selection_replaces_first_attempt_relationships() -> None:
    session = FakeSession(
        [
            FakeResult({"written": 1}),
            FakeResult({"written": 1}),
            FakeResult({"written": 1}),
            FakeResult({"written": 1}),
        ]
    )

    neo4j_repository.select_job_postings(
        session,
        user_id=7,
        posting_urls=["https://jobs.example/a"],
        run_id="run-a",
    )
    neo4j_repository.select_candidate_market_skills(
        session,
        user_id=7,
        skill_names=["Skill A"],
        posting_urls=["https://jobs.example/a"],
        job_search_run_id="run-a",
        match_run_id="match-a",
    )
    neo4j_repository.select_job_postings(
        session,
        user_id=7,
        posting_urls=["https://jobs.example/b"],
        run_id="run-b",
    )
    neo4j_repository.select_candidate_market_skills(
        session,
        user_id=7,
        skill_names=["Skill B"],
        posting_urls=["https://jobs.example/b"],
        job_search_run_id="run-b",
        match_run_id="match-b",
    )

    second_job_query, second_job_params = session.calls[2]
    second_skill_query, second_skill_params = session.calls[3]
    assert "DELETE relationship" in second_job_query
    assert "DELETE relationship" in second_skill_query
    assert second_job_params["posting_urls"] == ["https://jobs.example/b"]
    assert second_skill_params["skill_names"] == ["Skill B"]


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
                            "skill_extraction_status": "failed",
                            "skill_extraction_error": (
                                "Skill extraction is temporarily unavailable"
                            ),
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
                "skill_extraction_status": "failed",
                "skill_extraction_error": (
                    "Skill extraction is temporarily unavailable"
                ),
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
    assert "MATCH (jp:JOB_POSTING {url: url})" in bank_query
    assert "OPTIONAL MATCH (jp)<-[:SOURCED_FROM]-(ms:MARKET_SKILL)" in bank_query
    assert "WHERE skill.name IS NOT NULL" in bank_query
    assert ".skill_extraction_status" in bank_query
    assert ".skill_extraction_error" in bank_query
    assert "CV_SKILL" not in bank_query
    assert interested_params["user_id"] == 7
    assert selected_params["user_id"] == 7
    assert bank_params["interested_urls"] == ["https://jobs.example/backend"]
