from __future__ import annotations

import importlib
import sys
from contextlib import nullcontext
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.graph import build_individual_learning_graph
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.service import IndividualLearningService


def test_checkpoint_module_does_not_connect_during_import(monkeypatch) -> None:
    from psycopg_pool import ConnectionPool as RealConnectionPool

    pool_factory = MagicMock()
    monkeypatch.setattr("psycopg_pool.ConnectionPool", pool_factory)
    sys.modules.pop("app.modules.individual_learning.checkpoint", None)

    checkpoint = importlib.import_module("app.modules.individual_learning.checkpoint")

    pool_factory.assert_not_called()
    checkpoint.ConnectionPool = RealConnectionPool


def test_production_checkpointer_is_lazy_shared_and_closes_owned_pool(
    monkeypatch,
) -> None:
    checkpoint = importlib.import_module("app.modules.individual_learning.checkpoint")
    checkpoint.close_individual_learning_checkpointer()
    pools: list[object] = []
    savers: list[object] = []

    class FakePool:
        check_connection = object()

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.open_calls: list[bool] = []
            self.close_calls = 0
            pools.append(self)

        def open(self, *, wait: bool) -> None:
            self.open_calls.append(wait)

        def close(self) -> None:
            self.close_calls += 1

    class FakeSaver:
        def __init__(self, *, conn) -> None:
            self.conn = conn
            self.setup_calls = 0
            savers.append(self)

        def setup(self) -> None:
            self.setup_calls += 1

    monkeypatch.setattr(checkpoint, "ConnectionPool", FakePool)
    monkeypatch.setattr(checkpoint, "PostgresSaver", FakeSaver)
    monkeypatch.setattr(
        checkpoint,
        "_get_checkpoint_db_url",
        lambda: "postgresql://user:pass@db:5432/lab_tutor",
    )

    first = checkpoint.get_individual_learning_checkpointer()
    second = checkpoint.get_individual_learning_checkpointer()

    assert first is second
    assert len(pools) == 1
    assert len(savers) == 1
    assert pools[0].open_calls == [True]
    assert pools[0].kwargs["open"] is False
    assert pools[0].kwargs["min_size"] == 1
    assert savers[0].conn is pools[0]
    assert savers[0].setup_calls == 1

    checkpoint.close_individual_learning_checkpointer()

    assert pools[0].close_calls == 1


def test_production_checkpointer_closes_pool_when_setup_fails(monkeypatch) -> None:
    checkpoint = importlib.import_module("app.modules.individual_learning.checkpoint")
    checkpoint.close_individual_learning_checkpointer()
    pools: list[object] = []

    class FakePool:
        check_connection = object()

        def __init__(self, **_kwargs) -> None:
            self.close_calls = 0
            pools.append(self)

        def open(self, *, wait: bool) -> None:
            assert wait is True

        def close(self) -> None:
            self.close_calls += 1

    class FailingSaver:
        def __init__(self, *, conn) -> None:
            assert conn is pools[0]

        def setup(self) -> None:
            raise RuntimeError("checkpoint DDL failed")

    monkeypatch.setattr(checkpoint, "ConnectionPool", FakePool)
    monkeypatch.setattr(checkpoint, "PostgresSaver", FailingSaver)

    with pytest.raises(RuntimeError, match="checkpoint DDL failed"):
        checkpoint.get_individual_learning_checkpointer()

    assert pools[0].close_calls == 1


def test_postgres_checkpointer_resumes_after_owned_pool_restart(db_session) -> None:
    checkpoint = importlib.import_module("app.modules.individual_learning.checkpoint")
    checkpoint.close_individual_learning_checkpointer()
    thread_id = f"checkpoint-restart-{uuid4()}"
    config = {"configurable": {"thread_id": thread_id}}

    first_checkpointer = checkpoint.get_individual_learning_checkpointer()
    assert isinstance(first_checkpointer, PostgresSaver)
    first_graph = build_individual_learning_graph(first_checkpointer)
    first_graph.invoke(
        {
            "thread_id": thread_id,
            "user_id": 7,
            "cv_document_id": 3,
            "profile": {"skills": [], "target_title_suggestions": ["Data Analyst"]},
            "target_titles": [],
            "candidate_jobs": [
                {
                    "url": "https://jobs.example/data",
                    "title": "Data Analyst",
                    "skills": [{"name": "SQL"}],
                }
            ],
            "skill_bank": [{"name": "SQL"}],
            "selected_posting_urls": [],
            "selected_skill_names": [],
        },
        config,
    )
    checkpoint.close_individual_learning_checkpointer()

    second_checkpointer = checkpoint.get_individual_learning_checkpointer()
    try:
        second_graph = build_individual_learning_graph(second_checkpointer)
        resumed = second_graph.invoke(
            Command(resume={"approved": True, "target_titles": ["Data Analyst"]}),
            config,
        )
        assert resumed["__interrupt__"][0].value["kind"] == "choose_jobs_and_skills"
    finally:
        second_checkpointer.delete_thread(thread_id)
        checkpoint.close_individual_learning_checkpointer()


def _seed_completed_cv(db_session) -> tuple[User, int]:
    user = User(
        email="checkpoint-owner@example.com",
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
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/hash/cv.pdf",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="a" * 64,
        size_bytes=123,
    )
    run = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user.id,
        model_provider="test",
        model_name="test",
        raw_text_hash="b" * 64,
    )
    repository.complete_cv_extraction(
        run,
        extracted_profile={
            "skills": [{"name": "Python", "confidence": 0.9}],
            "target_title_suggestions": ["Backend Engineer"],
        },
        target_title_suggestions=["Backend Engineer"],
        confidence_summary={"skills": 0.9},
    )
    repository.complete_cv_document(document)
    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="needs_profile_review",
    )
    return user, document.id


def test_graph_reconstructs_across_service_instances_with_shared_checkpointer(
    db_session,
    monkeypatch,
) -> None:
    user, cv_document_id = _seed_completed_cv(db_session)
    checkpointer = InMemorySaver()

    class DummyDriver:
        def session(self):
            return nullcontext(object())

    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: {"jobs": 1, "market_skills": 1},
    )
    dependencies = {
        "graph_checkpointer": checkpointer,
        "job_searcher": lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
            }
        ],
        "market_skill_extractor": lambda jobs: {jobs[0]["url"]: [{"name": "Docker"}]},
    }
    first_service = IndividualLearningService(
        db_session,
        DummyDriver(),
        **dependencies,
    )
    started = first_service.start_individual_graph(user.id, cv_document_id)

    second_service = IndividualLearningService(
        db_session,
        DummyDriver(),
        **dependencies,
    )
    recovered_review = second_service.get_profile(user.id)
    assert recovered_review.active_thread_id == started.thread_id
    assert recovered_review.cv_document_id == cv_document_id
    assert recovered_review.extraction_run_id is not None
    assert recovered_review.next_step == "review_profile"
    assert recovered_review.extracted_profile is not None
    assert recovered_review.extracted_profile["skills"][0]["name"] == "Python"
    assert recovered_review.pending_interrupt is not None
    assert recovered_review.pending_interrupt["kind"] == "review_profile_and_roles"

    resumed = second_service.resume_individual_graph(
        user.id,
        started.thread_id,
        {"approved": True, "target_titles": ["Backend Engineer"]},
    )

    assert resumed.interrupt is not None
    assert resumed.interrupt["kind"] == "choose_jobs_and_skills"
    assert resumed.interrupt["candidate_jobs"][0]["url"] == (
        "https://jobs.example/backend"
    )
    recovered_jobs = first_service.get_profile(user.id)
    assert recovered_jobs.onboarding_status == "needs_skill_selection"
    assert recovered_jobs.next_step == "select_jobs_and_skills"
    assert recovered_jobs.pending_interrupt is not None
    assert recovered_jobs.pending_interrupt["kind"] == "choose_jobs_and_skills"
