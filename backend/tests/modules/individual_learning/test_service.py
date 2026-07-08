from __future__ import annotations

from fastapi import HTTPException
from langgraph.types import Command

from app.modules.individual_learning.job_matcher import score_market_skill_coverage
from app.modules.individual_learning.service import IndividualLearningService


def test_get_profile_returns_default_onboarding_state() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    profile = service.get_profile(user_id=42)

    assert profile.user_id == 42
    assert profile.onboarding_status == "needs_cv"
    assert profile.target_titles == []


def test_resume_individual_graph_rejects_malformed_thread_id(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3-extra",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException for malformed thread_id")


def test_resume_individual_graph_rejects_foreign_thread_id(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-999-cv-12",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException for foreign thread_id")


def test_resume_individual_graph_rejects_missing_cv_for_owned_thread(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    def fake_load_profile_payload(user_id: int, cv_document_id: int) -> dict[str, object]:
        assert user_id == 7
        assert cv_document_id == 3
        raise HTTPException(status_code=404, detail="CV document not found")

    monkeypatch.setattr(service, "_load_profile_payload", fake_load_profile_payload)
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException when CV ownership cannot be proven")


def test_resume_individual_graph_rejects_owned_thread_when_db_is_unavailable(
    monkeypatch,
) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))),
    )

    try:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3",
            payload={},
        )
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail == "Thread does not belong to the current user"
    else:
        raise AssertionError("Expected HTTPException when DB ownership proof is unavailable")


def test_resume_individual_graph_allows_owned_thread_and_invokes_graph(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    resume_payload = {"approved": True}
    captured: dict[str, object] = {}

    class DummyGraph:
        def invoke(self, command: Command, config: dict[str, object]) -> dict[str, object]:
            captured["command"] = command
            captured["config"] = config
            return {
                "target_titles": ["Data Analyst"],
                "selected_posting_urls": [],
                "selected_skill_names": [],
            }

    monkeypatch.setattr(service, "_validate_resume_thread", lambda user_id, thread_id: 3)
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: DummyGraph()),
    )

    response = service.resume_individual_graph(
        user_id=7,
        thread_id="individual-7-cv-3",
        payload=resume_payload,
    )

    assert captured["config"] == {"configurable": {"thread_id": "individual-7-cv-3"}}
    assert isinstance(captured["command"], Command)
    assert captured["command"].resume == resume_payload
    assert response.status == "completed"


def test_score_market_skill_coverage_marks_existing_and_gap_skills() -> None:
    scores = score_market_skill_coverage(
        cv_skill_names=["Build APIs with FastAPI", "Query PostgreSQL databases"],
        market_skill_names=[
            "Query PostgreSQL databases",
            "Deploy services with Docker",
        ],
    )

    by_name = {score.skill_name: score for score in scores}
    assert by_name["Query PostgreSQL databases"].coverage == "covered"
    assert by_name["Deploy services with Docker"].coverage == "gap"


def test_get_skill_banks_overlays_selected_and_coverage(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_individual_skill_bank",
        lambda session, user_id: {
            "postings": [
                {
                    "url": "https://jobs.example/backend",
                    "title": "Backend Engineer",
                    "company": "Example",
                    "site": "indeed",
                    "search_term": "Backend Engineer",
                    "skills": [
                        {
                            "name": "Query PostgreSQL databases",
                            "description": "SQL work",
                            "category": "Database",
                        },
                        {
                            "name": "Deploy services with Docker",
                            "description": "Operations",
                            "category": "DevOps",
                        },
                    ],
                }
            ],
            "selected_skill_names": ["Deploy services with Docker"],
            "interested_posting_urls": ["https://jobs.example/backend"],
        },
    )

    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    monkeypatch.setattr(service, "_list_cv_skill_names", lambda user_id: ["Query PostgreSQL databases"])

    response = service.get_skill_banks(user_id=7)

    assert response.selected_skill_names == ["Deploy services with Docker"]
    assert response.interested_posting_urls == ["https://jobs.example/backend"]
    posting = response.market_skill_bank[0]
    assert posting.is_interested is True
    skills_by_name = {skill.name: skill for skill in posting.skills}
    assert skills_by_name["Query PostgreSQL databases"].coverage == "covered"
    assert skills_by_name["Query PostgreSQL databases"].is_selected is False
    assert skills_by_name["Deploy services with Docker"].coverage == "gap"
    assert skills_by_name["Deploy services with Docker"].is_selected is True


def test_select_interested_jobs_uses_direct_individual_to_job_link(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())

    def fake_select_job_postings(
        session,
        *,
        user_id: int,
        posting_urls: list[str],
        run_id: str,
    ) -> int:
        captured["user_id"] = user_id
        captured["posting_urls"] = posting_urls
        captured["run_id"] = run_id
        return 2

    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        fake_select_job_postings,
    )

    count = service.select_interested_jobs(
        user_id=7,
        posting_urls=[
            "https://jobs.example/backend",
            "https://jobs.example/platform",
        ],
    )

    assert count == 2
    assert captured["user_id"] == 7
    assert captured["posting_urls"] == [
        "https://jobs.example/backend",
        "https://jobs.example/platform",
    ]
    assert captured["run_id"] == "manual-selection"
