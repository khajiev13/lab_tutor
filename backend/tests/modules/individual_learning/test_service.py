from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langgraph.types import Command

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.job_matcher import score_market_skill_coverage
from app.modules.individual_learning.job_search import (
    extract_market_skills_for_jobs,
    search_jobs_for_titles,
)
from app.modules.individual_learning.models import IndividualRunStatus
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.service import IndividualLearningService


def _stub_learning_run_repository(service, monkeypatch, *, run_id: str) -> None:
    run = SimpleNamespace(run_id=run_id, status="running", error_message=None)
    monkeypatch.setattr(
        service._repo,
        "create_learning_run",
        lambda **_kwargs: run,
    )

    def complete_learning_run(_run, *, status, error_message):
        run.status = status
        run.error_message = error_message
        return run

    monkeypatch.setattr(
        service._repo,
        "complete_learning_run",
        complete_learning_run,
    )
    service._run_id_factory = lambda: run_id


def test_get_profile_returns_default_onboarding_state() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    profile = service.get_profile(user_id=42)

    assert profile.user_id == 42
    assert profile.onboarding_status == "needs_cv"
    assert profile.target_titles == []


def test_select_skills_requires_market_skills() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    with pytest.raises(
        ValueError, match="Select at least one market skill before building"
    ):
        service.validate_selected_skill_names([])


def test_select_skills_rejects_more_than_twenty_market_skills() -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    with pytest.raises(
        ValueError,
        match="Select no more than 20 market skills before building",
    ):
        service.validate_selected_skill_names([f"Skill {index}" for index in range(21)])


def test_select_skills_persists_unique_clean_market_skill_names(monkeypatch) -> None:
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

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: ["Python", "Docker"],
        raising=False,
    )

    def fake_select_market_skills(
        session,
        *,
        user_id: int,
        skill_names: list[str],
        source: str,
    ) -> int:
        captured["user_id"] = user_id
        captured["skill_names"] = skill_names
        captured["source"] = source
        return len(skill_names)

    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        fake_select_market_skills,
    )

    count = service.select_skills(
        user_id=7,
        skill_names=[" Python ", "Docker", "Python", ""],
        source="manual-selection",
    )

    assert count == 2
    assert captured == {
        "user_id": 7,
        "skill_names": ["Python", "Docker"],
        "source": "manual-selection",
    }


def test_select_skills_enforces_cap_against_persisted_plus_valid_market_skills(
    monkeypatch,
) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    select_market_skills = []

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [f"Persisted {index}" for index in range(19)],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: ["GraphQL", "Docker"],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda *_args, **_kwargs: select_market_skills.append("called"),
    )

    with pytest.raises(
        ValueError,
        match="Select no more than 20 market skills before building",
    ):
        service.select_skills(
            user_id=7,
            skill_names=["GraphQL", "Docker"],
        )

    assert select_market_skills == []


def test_select_skills_rejects_market_skill_not_sourced_from_user_interest(
    monkeypatch,
) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    writes: list[str] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: ["Docker"],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda *_args, **_kwargs: writes.append("selected"),
    )

    with pytest.raises(
        ValueError,
        match="Select only market skills sourced from your interested jobs",
    ):
        service.select_skills(user_id=7, skill_names=["Docker", "CV-only"])

    assert writes == []


def test_build_learning_path_runs_sync_resource_pipeline(monkeypatch) -> None:
    selection_calls: list[dict[str, object]] = []
    reading_writes: list[tuple[str, str, list[object], str, str]] = []
    question_writes: list[tuple[str, list[object]]] = []
    captured_profiles: list[object] = []

    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    _stub_learning_run_repository(service, monkeypatch, run_id="test-run-1")

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: ["GraphQL"],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_market_skill_profiles",
        lambda _session, *, skill_names: [
            {
                "name": "GraphQL",
                "description": "Build production GraphQL APIs",
                "category": "Backend",
                "concepts": [{"name": "Resolvers", "definition": "Field handlers"}],
                "job_evidence": ["Need GraphQL API ownership"],
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_profiles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("build should not load all persisted selected skills")
        ),
    )

    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda _session, *, user_id, skill_names, source: (
            selection_calls.append(
                {
                    "user_id": user_id,
                    "skill_names": skill_names,
                    "source": source,
                }
            )
            or len(skill_names)
        ),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.fetch_readings_for_skill",
        lambda skill_profile: (
            captured_profiles.append(skill_profile) or ["reading-resource"]
        ),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.fetch_videos_for_skill",
        lambda skill_profile: ["video-resource"],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.generate_questions_for_skill",
        lambda *_args: [
            SimpleNamespace(text="Q1", difficulty="easy", options=["A", "B", "C", "D"]),
            SimpleNamespace(
                text="Q2", difficulty="medium", options=["A", "B", "C", "D"]
            ),
            SimpleNamespace(text="Q3", difficulty="hard", options=["A", "B", "C", "D"]),
        ],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.write_resources",
        lambda _session,
        skill_name,
        skill_type,
        resources,
        resource_label,
        relationship: (
            reading_writes.append(
                (skill_name, skill_type, resources, resource_label, relationship)
            )
            or len(resources)
        ),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.write_market_skill_questions",
        lambda _session, skill_name, questions: (
            question_writes.append((skill_name, questions)) or len(questions)
        ),
        raising=False,
    )

    result = service.build_learning_path(user_id=7, selected_skill_names=["GraphQL"])

    assert result == {"status": "completed", "run_id": "test-run-1"}
    assert selection_calls == [
        {
            "user_id": 7,
            "skill_names": ["GraphQL"],
            "source": "individual_market_skill",
        }
    ]
    assert captured_profiles
    skill_profile = captured_profiles[0]
    assert skill_profile.name == "GraphQL"
    assert skill_profile.skill_type == "market"
    assert skill_profile.category == "Backend"
    assert reading_writes == [
        ("GraphQL", "market", ["reading-resource"], "READING_RESOURCE", "HAS_READING"),
        ("GraphQL", "market", ["video-resource"], "VIDEO_RESOURCE", "HAS_VIDEO"),
    ]
    assert len(question_writes) == 1
    assert question_writes[0][0] == "GraphQL"
    assert len(question_writes[0][1]) == 3


def test_build_learning_path_requires_valid_persisted_market_skills(
    monkeypatch,
) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_profiles",
        lambda _session, *, user_id: [],
    )

    with pytest.raises(
        ValueError, match="Select at least one market skill before building"
    ):
        service.build_learning_path(user_id=7, selected_skill_names=[])


def test_build_learning_path_rejects_non_market_request_even_with_existing_selection(
    monkeypatch,
) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    select_market_skills = []
    fetch_calls = []

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: ["Persisted GraphQL"],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: [],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda *_args, **_kwargs: select_market_skills.append("called"),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.fetch_readings_for_skill",
        lambda *_args, **_kwargs: fetch_calls.append("called"),
    )

    with pytest.raises(
        ValueError,
        match="Select only valid market skills before building",
    ):
        service.build_learning_path(user_id=7, selected_skill_names=["CV-only"])

    assert select_market_skills == []
    assert fetch_calls == []


def test_build_learning_path_empty_request_builds_existing_selected_market_skills(
    monkeypatch,
) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    _stub_learning_run_repository(service, monkeypatch, run_id="test-run-2")
    selection_calls = []
    fetched_skill_names = []

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: ["GraphQL"],
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda *_args, **_kwargs: selection_calls.append("called"),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_profiles",
        lambda _session, *, user_id: [
            {
                "name": "GraphQL",
                "description": "Build production GraphQL APIs",
                "category": "Backend",
                "concepts": [{"name": "Resolvers", "definition": "Field handlers"}],
                "job_evidence": ["Need GraphQL API ownership"],
            }
        ],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_market_skill_profiles",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("empty build should use persisted selected skills")
        ),
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.fetch_readings_for_skill",
        lambda skill_profile: (fetched_skill_names.append(skill_profile.name) or []),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.fetch_videos_for_skill",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.generate_questions_for_skill",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.write_market_skill_questions",
        lambda *_args, **_kwargs: 0,
        raising=False,
    )

    result = service.build_learning_path(user_id=7, selected_skill_names=[])

    assert result == {"status": "completed", "run_id": "test-run-2"}
    assert selection_calls == []
    assert fetched_skill_names == ["GraphQL"]


def test_build_learning_path_records_partial_run_and_preserves_successful_resources(
    db_session,
    monkeypatch,
) -> None:
    user = User(
        email="partial-learning@example.com",
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

    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: list(skill_names),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda _session, **kwargs: len(kwargs["skill_names"]),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_market_skill_profiles",
        lambda _session, *, skill_names: [
            {
                "name": name,
                "description": f"Learn {name}",
                "category": "Backend",
                "concepts": [],
                "job_evidence": [],
            }
            for name in skill_names
        ],
    )
    resource_writes: list[tuple[str, str]] = []

    def fetch_videos(skill_profile):
        if skill_profile.name == "Docker":
            raise RuntimeError("video provider unavailable")
        return []

    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        reading_fetcher=lambda skill_profile: [f"reading:{skill_profile.name}"],
        video_fetcher=fetch_videos,
        question_generator=lambda *_args: [],
        resource_writer=lambda _session,
        skill_name,
        _skill_type,
        resources,
        label,
        _rel: (resource_writes.append((skill_name, label)) or len(resources)),
        question_writer=lambda *_args, **_kwargs: 0,
        run_id_factory=lambda: "learning-run-1",
    )

    response = service.build_learning_path(
        user_id=user.id,
        selected_skill_names=["GraphQL", "Docker"],
    )

    run = IndividualLearningRepository(db_session).get_latest_learning_run(user.id)

    assert response == {"status": "partial", "run_id": "learning-run-1"}
    assert resource_writes == [
        ("GraphQL", "READING_RESOURCE"),
        ("Docker", "READING_RESOURCE"),
    ]
    assert run is not None
    assert run.selected_skill_names_json == ["GraphQL", "Docker"]
    assert run.status == IndividualRunStatus.PARTIAL.value
    assert "Docker videos: video provider unavailable" in (run.error_message or "")
    assert run.completed_at is not None


def test_build_learning_path_records_failed_and_completed_runs(
    db_session,
    monkeypatch,
) -> None:
    user = User(
        email="learning-statuses@example.com",
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

    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_selected_market_skill_names",
        lambda _session, *, user_id: [],
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.resolve_interested_market_skill_names",
        lambda _session, *, user_id, skill_names: list(skill_names),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_market_skills",
        lambda _session, **kwargs: len(kwargs["skill_names"]),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_market_skill_profiles",
        lambda _session, *, skill_names: [
            {
                "name": name,
                "description": f"Learn {name}",
                "category": "Backend",
                "concepts": [],
                "job_evidence": [],
            }
            for name in skill_names
        ],
    )

    def fail_provider(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    failed_service = IndividualLearningService(
        db_session,
        DummyDriver(),
        reading_fetcher=fail_provider,
        video_fetcher=fail_provider,
        question_generator=fail_provider,
        resource_writer=lambda *_args, **_kwargs: 0,
        question_writer=lambda *_args, **_kwargs: 0,
        run_id_factory=lambda: "learning-run-failed",
    )
    failed_response = failed_service.build_learning_path(
        user_id=user.id,
        selected_skill_names=["GraphQL"],
    )
    failed_run = IndividualLearningRepository(db_session).get_latest_learning_run(
        user.id
    )

    completed_service = IndividualLearningService(
        db_session,
        DummyDriver(),
        reading_fetcher=lambda _profile: [],
        video_fetcher=lambda _profile: [],
        question_generator=lambda *_args: [],
        resource_writer=lambda *_args, **_kwargs: 0,
        question_writer=lambda *_args, **_kwargs: 0,
        run_id_factory=lambda: "learning-run-completed",
    )
    completed_response = completed_service.build_learning_path(
        user_id=user.id,
        selected_skill_names=["GraphQL"],
    )
    completed_run = IndividualLearningRepository(db_session).get_latest_learning_run(
        user.id
    )

    assert failed_response == {
        "status": "failed",
        "run_id": "learning-run-failed",
    }
    assert failed_run is not None
    assert failed_run.status == IndividualRunStatus.FAILED.value
    assert failed_run.error_message is not None
    assert completed_response == {
        "status": "completed",
        "run_id": "learning-run-completed",
    }
    assert completed_run is not None
    assert completed_run.status == IndividualRunStatus.COMPLETED.value
    assert completed_run.error_message is None


def test_get_learning_path_reads_selected_market_skill_projection(monkeypatch) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())

    monkeypatch.setattr(
        "app.modules.individual_learning.service.get_individual_learning_path",
        lambda _session, *, user_id: {
            "user_id": user_id,
            "selected_skills": [
                {
                    "name": "GraphQL",
                    "description": "Build production GraphQL APIs",
                    "source": "individual_market_skill",
                    "readings": [
                        {
                            "id": "reading-1",
                            "title": "Guide",
                            "url": "https://example.com",
                        }
                    ],
                    "videos": [],
                    "questions": [],
                }
            ],
            "total_selected_skills": 1,
            "skills_with_resources": 1,
        },
    )

    response = service.get_learning_path(user_id=7)

    assert response["user_id"] == 7
    assert response["total_selected_skills"] == 1
    assert response["skills_with_resources"] == 1
    assert response["selected_skills"][0]["name"] == "GraphQL"


def test_resume_individual_graph_rejects_malformed_thread_id(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(
            lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))
        ),
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
        staticmethod(
            lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))
        ),
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


def test_resume_individual_graph_rejects_missing_cv_for_owned_thread(
    monkeypatch,
) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    def fake_load_profile_payload(
        user_id: int, cv_document_id: int
    ) -> dict[str, object]:
        assert user_id == 7
        assert cv_document_id == 3
        raise HTTPException(status_code=404, detail="CV document not found")

    monkeypatch.setattr(service, "_load_profile_payload", fake_load_profile_payload)
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(
            lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))
        ),
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
        raise AssertionError(
            "Expected HTTPException when CV ownership cannot be proven"
        )


def test_resume_individual_graph_rejects_owned_thread_when_db_is_unavailable(
    monkeypatch,
) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(
            lambda: (_ for _ in ()).throw(AssertionError("graph should not be built"))
        ),
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
        raise AssertionError(
            "Expected HTTPException when DB ownership proof is unavailable"
        )


def test_resume_individual_graph_rejects_missing_checkpoint_without_invoking_graph(
    monkeypatch,
) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)
    captured: dict[str, object] = {}

    class DummyGraph:
        def get_state(self, config: dict[str, object]):
            captured["state_config"] = config
            return SimpleNamespace(next=(), values={})

        def invoke(
            self, command: Command, config: dict[str, object]
        ) -> dict[str, object]:
            raise AssertionError("graph must not be invoked without a pending state")

    monkeypatch.setattr(
        service, "_validate_resume_thread", lambda user_id, thread_id: (3, 4)
    )
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: DummyGraph()),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3-extraction-4",
            payload={"approved": True},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Workflow state changed; reload the current profile"
    )
    assert captured["state_config"] == {
        "configurable": {"thread_id": "individual-7-cv-3-extraction-4"}
    }


def test_resume_individual_graph_rejects_unexpected_pending_state(monkeypatch) -> None:
    service = IndividualLearningService(db=None, neo4j_driver=None)

    class DummyGraph:
        def get_state(self, _config: dict[str, object]):
            return SimpleNamespace(next=("unexpected_node",), values={})

        def invoke(self, _command: Command, _config: dict[str, object]):
            raise AssertionError("unexpected graph state must not be invoked")

    monkeypatch.setattr(
        service,
        "_validate_resume_thread",
        lambda user_id, thread_id: (3, 4),
    )
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        staticmethod(lambda: DummyGraph()),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user_id=7,
            thread_id="individual-7-cv-3-extraction-4",
            payload={"approved": True},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Workflow state changed; reload the current profile"
    )


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
    monkeypatch.setattr(
        service, "_list_cv_skill_names", lambda user_id: ["Query PostgreSQL databases"]
    )

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
    search_run = SimpleNamespace(
        id=12,
        fetched_jobs_json=[
            {"url": "https://jobs.example/backend"},
            {"url": "https://jobs.example/platform"},
        ],
    )
    monkeypatch.setattr(
        service._repo,
        "get_latest_job_search_run",
        lambda user_id: search_run,
    )
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        service._repo,
        "record_job_selections",
        lambda **kwargs: (recorded.append(kwargs) or True),
    )

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
    assert captured["run_id"] == "12"
    assert recorded == [
        {
            "user_id": 7,
            "job_search_run_id": 12,
            "posting_urls": [
                "https://jobs.example/backend",
                "https://jobs.example/platform",
            ],
        }
    ]


def test_select_interested_jobs_rejects_non_candidate_url(monkeypatch) -> None:
    class DummySessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class DummyDriver:
        def session(self):
            return DummySessionContext()

    service = IndividualLearningService(db=None, neo4j_driver=DummyDriver())
    monkeypatch.setattr(
        service._repo,
        "get_latest_job_search_run",
        lambda user_id: SimpleNamespace(
            id=12,
            fetched_jobs_json=[{"url": "https://jobs.example/backend"}],
        ),
    )
    writes: list[str] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.select_job_postings",
        lambda *_args, **_kwargs: writes.append("selected"),
    )

    with pytest.raises(
        ValueError,
        match="Select only jobs from your latest candidate search",
    ):
        service.select_interested_jobs(
            user_id=7,
            posting_urls=["https://jobs.example/injected"],
        )

    assert writes == []


def test_search_jobs_for_titles_defaults_country_for_location_only_calls(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeFrame:
        def iterrows(self):
            yield (
                0,
                {
                    "job_url": "https://jobs.example/backend",
                    "title": "Backend Engineer",
                    "company_name": "Example",
                    "site": "indeed",
                    "location": "New York, NY",
                    "description": "Build APIs with FastAPI and Docker",
                    "skills": None,
                },
            )

    class FakeJobSpyModule:
        @staticmethod
        def scrape_jobs(**kwargs):
            captured.update(kwargs)
            return FakeFrame()

    monkeypatch.setitem(sys.modules, "jobspy", FakeJobSpyModule)

    jobs = search_jobs_for_titles(
        target_titles=["Backend Engineer"],
        country="",
        location="New York",
    )

    assert captured["country_indeed"] == "USA"
    assert captured["location"] == "New York"
    assert jobs == [
        {
            "url": "https://jobs.example/backend",
            "title": "Backend Engineer",
            "company": "Example",
            "site": "indeed",
            "search_term": "Backend Engineer",
            "country": "USA",
            "location": "New York, NY",
            "description": "Build APIs with FastAPI and Docker",
            "skills": None,
        }
    ]


def test_search_jobs_for_titles_surfaces_provider_failure_for_partial_run_tracking(
    monkeypatch,
) -> None:
    class FakeJobSpyModule:
        @staticmethod
        def scrape_jobs(**_kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setitem(sys.modules, "jobspy", FakeJobSpyModule)

    with pytest.raises(RuntimeError, match="Backend Engineer: provider unavailable"):
        search_jobs_for_titles(
            target_titles=["Backend Engineer"],
            country="USA",
            location="New York",
        )


def test_extract_market_skills_for_jobs_prefers_explicit_skills_then_description_fallback() -> (
    None
):
    result = extract_market_skills_for_jobs(
        [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "skills": ["Python, SQL", {"name": "Docker"}, "Python"],
                "description": "FastAPI and Docker appear here too",
            },
            {
                "url": "https://jobs.example/platform",
                "title": "Platform Engineer",
                "skills": None,
                "description": "Need Kubernetes, AWS, and PostgreSQL experience",
            },
        ]
    )

    assert result["https://jobs.example/backend"] == [
        {"name": "Python", "category": "Market Skill"},
        {"name": "SQL", "category": "Market Skill"},
        {"name": "Docker", "category": "Market Skill"},
    ]
    assert result["https://jobs.example/platform"] == [
        {
            "name": "Kubernetes",
            "category": "Market Skill",
            "description": "Inferred from job description for Platform Engineer",
        },
        {
            "name": "PostgreSQL",
            "category": "Market Skill",
            "description": "Inferred from job description for Platform Engineer",
        },
        {
            "name": "AWS",
            "category": "Market Skill",
            "description": "Inferred from job description for Platform Engineer",
        },
    ]
