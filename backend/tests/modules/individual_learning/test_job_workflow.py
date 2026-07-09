from __future__ import annotations

from contextlib import nullcontext

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import IndividualRunStatus
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.service import IndividualLearningService


def _create_individual(db_session) -> User:
    user = User(
        email="job-workflow@example.com",
        hashed_password="hashed",
        first_name="Indy",
        last_name="Learner",
        role=UserRole.INDIVIDUAL,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _seed_profile(db_session, *, user_id: int):
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=user_id,
        blob_path=f"users/{user_id}/cv/hash/cv.pdf",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="a" * 64,
        size_bytes=123,
    )
    extraction = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user_id,
        model_provider="test-provider",
        model_name="test-model",
        raw_text_hash="b" * 64,
    )
    repository.complete_cv_extraction(
        extraction,
        extracted_profile={
            "summary": "Backend engineer",
            "skills": [
                {
                    "name": "Python",
                    "category": "Programming",
                    "evidence": "Built APIs",
                    "confidence": 0.9,
                }
            ],
            "target_title_suggestions": ["Backend Engineer"],
            "confidence_summary": {"skills": 0.9},
        },
        target_title_suggestions=["Backend Engineer"],
        confidence_summary={"skills": 0.9},
    )
    repository.complete_cv_document(document)
    profile = repository.upsert_profile_status(
        user_id=user_id,
        onboarding_status="needs_profile_review",
    )
    profile.preferred_country = "USA"
    profile.preferred_location = "New York"
    db_session.commit()
    return document


class DummyDriver:
    def __init__(self) -> None:
        self.session_value = object()

    def session(self):
        return nullcontext(self.session_value)


def test_first_resume_runs_real_adapters_and_keeps_partial_job_results(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session)
    document = _seed_profile(db_session, user_id=user.id)
    search_calls: list[tuple[list[str], str, str]] = []
    skill_calls: list[str] = []
    projected: dict[str, object] = {}

    def fake_search(
        target_titles: list[str], country: str, location: str
    ) -> list[dict]:
        search_calls.append((target_titles, country, location))
        if target_titles == ["Platform Engineer"]:
            raise RuntimeError("provider unavailable")
        return [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "company": "Example",
                "description": "Python and Docker",
            },
            {
                "url": "https://jobs.example/api",
                "title": "API Engineer",
                "company": "Example",
                "description": "API ownership",
            },
        ]

    def fake_extract(jobs: list[dict]) -> dict[str, list[dict]]:
        url = jobs[0]["url"]
        skill_calls.append(url)
        if url.endswith("/api"):
            raise RuntimeError("skill provider unavailable")
        return {
            url: [
                {"name": "Python", "category": "Programming"},
                {"name": "Docker", "category": "DevOps"},
            ]
        }

    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 1,
    )

    def fake_project(session, *, jobs, skills_by_job_url):
        projected.update(
            {
                "session": session,
                "jobs": jobs,
                "skills_by_job_url": skills_by_job_url,
            }
        )
        return {"jobs": len(jobs), "market_skills": 2}

    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        fake_project,
    )
    driver = DummyDriver()
    service = IndividualLearningService(
        db_session,
        driver,
        graph_checkpointer=InMemorySaver(),
        job_searcher=fake_search,
        market_skill_extractor=fake_extract,
    )

    started = service.start_individual_graph(user.id, document.id)
    resumed = service.resume_individual_graph(
        user.id,
        started.thread_id,
        {
            "approved": True,
            "target_titles": ["Backend Engineer", "Platform Engineer"],
        },
    )

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    search_run = repository.get_latest_job_search_run(user.id)
    match_run = repository.get_latest_job_match_run(user.id)

    assert search_calls == [
        (["Backend Engineer"], "USA", "New York"),
        (["Platform Engineer"], "USA", "New York"),
    ]
    assert skill_calls == [
        "https://jobs.example/backend",
        "https://jobs.example/api",
    ]
    assert resumed.interrupt is not None
    assert resumed.interrupt["kind"] == "choose_jobs_and_skills"
    candidate_jobs = resumed.interrupt["candidate_jobs"]
    assert [job["url"] for job in candidate_jobs] == [
        "https://jobs.example/backend",
        "https://jobs.example/api",
    ]
    assert candidate_jobs[0]["match_score"] == 50.0
    assert candidate_jobs[0]["skills"] == [
        {
            "name": "Python",
            "category": "Programming",
            "description": "",
            "coverage": "covered",
        },
        {
            "name": "Docker",
            "category": "DevOps",
            "description": "",
            "coverage": "gap",
        },
    ]
    assert candidate_jobs[1]["match_score"] == 0.0
    assert candidate_jobs[1]["skills"] == []
    assert projected["session"] is driver.session_value
    assert projected["skills_by_job_url"] == {
        "https://jobs.example/backend": [
            {"name": "Python", "category": "Programming", "description": ""},
            {"name": "Docker", "category": "DevOps", "description": ""},
        ],
        "https://jobs.example/api": [],
    }
    assert profile is not None
    assert profile.onboarding_status == "needs_skill_selection"
    assert search_run is not None
    assert search_run.status == IndividualRunStatus.PARTIAL.value
    assert len(search_run.fetched_jobs_json) == 2
    assert "Platform Engineer: provider unavailable" in (search_run.error_message or "")
    assert "API Engineer: skill provider unavailable" in (
        search_run.error_message or ""
    )
    assert match_run is not None
    assert match_run.job_search_run_id == search_run.id
    assert match_run.status == IndividualRunStatus.PARTIAL.value
    assert match_run.scores_json[0] == {
        "job_url": "https://jobs.example/backend",
        "match_score": 50.0,
        "covered_skills": 1,
        "total_skills": 2,
    }
    assert any(
        gap["skill_name"] == "Docker" and gap["coverage"] == "gap"
        for gap in match_run.skill_gap_json
    )


def test_job_search_with_no_usable_candidates_stays_recoverable(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session)
    document = _seed_profile(db_session, user_id=user.id)
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 1,
    )
    project_calls: list[object] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: project_calls.append("projected"),
    )
    search_calls = 0

    def search_with_recovery(*_args):
        nonlocal search_calls
        search_calls += 1
        if search_calls == 1:
            return []
        return [
            {
                "url": "https://jobs.example/recovered",
                "title": "Backend Engineer",
            }
        ]

    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
        job_searcher=search_with_recovery,
        market_skill_extractor=lambda _jobs: {},
    )
    started = service.start_individual_graph(user.id, document.id)

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            started.thread_id,
            {"approved": True, "target_titles": ["Backend Engineer"]},
        )

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    search_run = repository.get_latest_job_search_run(user.id)

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "No usable job postings were found"
    assert profile is not None
    assert profile.onboarding_status == "needs_jobs"
    assert search_run is not None
    assert search_run.status == IndividualRunStatus.FAILED.value
    assert search_run.error_message == "No usable job postings were found"
    assert project_calls == []

    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="needs_skill_selection",
    )
    recovery = service.get_profile(user.id)
    assert recovery.active_thread_id == started.thread_id
    assert recovery.next_step == "search_jobs"
    assert recovery.pending_interrupt is None
    assert recovery.target_titles == ["Backend Engineer"]

    recovered = service.resume_individual_graph(
        user.id,
        recovery.active_thread_id,
        {"approved": True, "target_titles": recovery.target_titles},
    )
    recovered_profile = repository.get_profile(user.id)
    recovered_run = repository.get_latest_job_search_run(user.id)

    assert recovered.interrupt is not None
    assert recovered.interrupt["kind"] == "choose_jobs_and_skills"
    assert recovered.interrupt["candidate_jobs"][0]["url"] == (
        "https://jobs.example/recovered"
    )
    assert recovered_profile is not None
    assert recovered_profile.onboarding_status == "needs_skill_selection"
    assert recovered_run is not None
    assert recovered_run.id == search_run.id
    assert recovered_run.status == IndividualRunStatus.COMPLETED.value
    assert project_calls == ["projected"]


def _build_selection_service(db_session, monkeypatch):
    user = _create_individual(db_session)
    document = _seed_profile(db_session, user_id=user.id)
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: {"jobs": 1, "market_skills": 1},
    )
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
        job_searcher=lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "company": "Example",
                "description": "Docker deployment",
            }
        ],
        market_skill_extractor=lambda jobs: {
            jobs[0]["url"]: [
                {"name": "Docker", "category": "DevOps"},
            ]
        },
    )
    started = service.start_individual_graph(user.id, document.id)
    review = service.resume_individual_graph(
        user.id,
        started.thread_id,
        {"approved": True, "target_titles": ["Backend Engineer"]},
    )
    assert review.interrupt is not None
    assert review.interrupt["kind"] == "choose_jobs_and_skills"
    return service, user, started.thread_id


def test_lost_first_resume_response_returns_recovery_conflict_without_consuming_selection(
    db_session,
    monkeypatch,
) -> None:
    service, user, thread_id = _build_selection_service(db_session, monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            thread_id,
            {"approved": True, "target_titles": ["Backend Engineer"]},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Workflow state changed; reload the current profile"
    )
    recovery = service.get_profile(user.id)
    assert recovery.next_step == "select_jobs_and_skills"
    assert recovery.pending_interrupt is not None
    assert recovery.pending_interrupt["kind"] == "choose_jobs_and_skills"

    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_candidate_market_skills",
        lambda *_args, **_kwargs: 1,
    )
    completed = service.resume_individual_graph(
        user.id,
        thread_id,
        {
            "selected_posting_urls": ["https://jobs.example/backend"],
            "selected_skill_names": ["Docker"],
        },
    )
    assert completed.status == "completed"


def test_second_resume_persists_only_checkpointed_jobs_and_market_skills(
    db_session,
    monkeypatch,
) -> None:
    service, user, thread_id = _build_selection_service(db_session, monkeypatch)
    writes: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        lambda _session, **kwargs: (writes.append(("jobs", kwargs)) or 1),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_candidate_market_skills",
        lambda _session, **kwargs: (writes.append(("skills", kwargs)) or 1),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("second resume must use candidate-scoped selection")
        ),
    )

    response = service.resume_individual_graph(
        user.id,
        thread_id,
        {
            "selected_posting_urls": ["https://jobs.example/backend"],
            "selected_skill_names": ["Docker"],
        },
    )

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    search_run = repository.get_latest_job_search_run(user.id)
    match_run = repository.get_latest_job_match_run(user.id)

    assert response.status == "completed"
    assert response.selected_posting_urls == ["https://jobs.example/backend"]
    assert response.selected_skill_names == ["Docker"]
    assert profile is not None
    assert profile.onboarding_status == "ready"
    assert search_run is not None
    assert search_run.selected_posting_urls_json == ["https://jobs.example/backend"]
    assert match_run is not None
    assert writes == [
        (
            "jobs",
            {
                "user_id": user.id,
                "posting_urls": ["https://jobs.example/backend"],
                "run_id": str(search_run.id),
            },
        ),
        (
            "skills",
            {
                "user_id": user.id,
                "skill_names": ["Docker"],
                "posting_urls": ["https://jobs.example/backend"],
                "job_search_run_id": str(search_run.id),
                "match_run_id": str(match_run.id),
            },
        ),
    ]

    with pytest.raises(HTTPException) as lost_response_retry:
        service.resume_individual_graph(
            user.id,
            thread_id,
            {
                "selected_posting_urls": ["https://jobs.example/backend"],
                "selected_skill_names": ["Docker"],
            },
        )

    assert lost_response_retry.value.status_code == 409
    assert lost_response_retry.value.detail == (
        "Workflow state changed; reload the current profile"
    )
    assert len(writes) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {
            "selected_posting_urls": ["https://jobs.example/injected"],
            "selected_skill_names": ["Docker"],
        },
        {
            "selected_posting_urls": ["https://jobs.example/backend"],
            "selected_skill_names": ["CV-only"],
        },
    ],
)
def test_second_resume_rejects_non_checkpointed_job_or_skill(
    db_session,
    monkeypatch,
    payload,
) -> None:
    service, user, thread_id = _build_selection_service(db_session, monkeypatch)
    writes: list[str] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        lambda *_args, **_kwargs: (writes.append("jobs") or 1),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_candidate_market_skills",
        lambda *_args, **_kwargs: (writes.append("skills") or 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(user.id, thread_id, payload)

    profile = IndividualLearningRepository(db_session).get_profile(user.id)
    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail == "Selections must come from the checkpointed candidates"
    )
    assert profile is not None
    assert profile.onboarding_status == "needs_skill_selection"
    assert writes == []

    retried = service.resume_individual_graph(
        user.id,
        thread_id,
        {
            "selected_posting_urls": ["https://jobs.example/backend"],
            "selected_skill_names": ["Docker"],
        },
    )
    assert retried.status == "completed"
    assert writes == ["jobs", "skills"]


def test_second_resume_rejects_skill_sourced_only_from_unselected_candidate(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session)
    document = _seed_profile(db_session, user_id=user.id)
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: {"jobs": 2, "market_skills": 2},
    )
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
        job_searcher=lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
            },
            {
                "url": "https://jobs.example/platform",
                "title": "Platform Engineer",
            },
        ],
        market_skill_extractor=lambda jobs: {
            jobs[0]["url"]: [
                {
                    "name": (
                        "Docker"
                        if jobs[0]["url"].endswith("/backend")
                        else "Kubernetes"
                    )
                }
            ]
        },
    )
    started = service.start_individual_graph(user.id, document.id)
    service.resume_individual_graph(
        user.id,
        started.thread_id,
        {"approved": True, "target_titles": ["Backend Engineer"]},
    )
    writes: list[str] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        lambda *_args, **_kwargs: (writes.append("jobs") or 1),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            started.thread_id,
            {
                "selected_posting_urls": ["https://jobs.example/backend"],
                "selected_skill_names": ["Kubernetes"],
            },
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail == "Selections must come from the checkpointed candidates"
    )
    assert writes == []
