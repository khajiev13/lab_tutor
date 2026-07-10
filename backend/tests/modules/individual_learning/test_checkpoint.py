from __future__ import annotations

import importlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from sqlalchemy.orm import Session

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


def test_profile_recovery_does_not_pair_new_document_with_old_extraction(
    db_session,
) -> None:
    user, old_document_id = _seed_completed_cv(db_session)
    repository = IndividualLearningRepository(db_session)
    new_document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/new-opaque-id",
        original_filename="new.pdf",
        content_type="application/pdf",
        content_hash="c" * 64,
        size_bytes=456,
    )
    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="extracting",
    )
    assert new_document.id != old_document_id

    profile = IndividualLearningService(
        db_session,
        None,
        graph_checkpointer=InMemorySaver(),
    ).get_profile(user.id)

    assert profile.cv_document_id == new_document.id
    assert profile.extraction_run_id is None
    assert profile.active_thread_id is None
    assert profile.extracted_profile is None
    assert profile.pending_interrupt is None
    # A processing document without a live lease represents an interrupted
    # worker and must recover instead of leaving the UI waiting forever.
    assert profile.next_step == "retry_cv"


def test_same_hash_reupload_refreshes_recency_and_uses_new_extraction_thread(
    db_session,
) -> None:
    user, first_document_id = _seed_completed_cv(db_session)
    repository = IndividualLearningRepository(db_session)
    first_document = repository.get_owned_cv_document(
        user_id=user.id,
        cv_document_id=first_document_id,
    )
    first_extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=first_document_id,
    )
    assert first_document is not None
    assert first_extraction is not None
    checkpointer = InMemorySaver()
    service = IndividualLearningService(
        db_session,
        None,
        graph_checkpointer=checkpointer,
    )
    first_started = service.start_individual_graph(user.id, first_document.id)

    second_document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/second-opaque-id",
        original_filename="second.pdf",
        content_type="application/pdf",
        content_hash="d" * 64,
        size_bytes=456,
    )
    second_extraction = repository.create_cv_extraction_run(
        cv_document_id=second_document.id,
        user_id=user.id,
        model_provider="test",
        model_name="test",
        raw_text_hash="e" * 64,
    )
    repository.complete_cv_extraction(
        second_extraction,
        extracted_profile={"summary": "Profile B", "skills": []},
        target_title_suggestions=["Role B"],
        confidence_summary={},
    )
    repository.complete_cv_document(second_document)
    first_document.uploaded_at = datetime.now(UTC) - timedelta(days=2)
    second_document.uploaded_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()

    reuploaded_first = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/reuploaded-opaque-id",
        original_filename="renamed-first.pdf",
        content_type="application/pdf",
        content_hash="a" * 64,
        size_bytes=789,
    )
    latest_first_extraction = repository.create_cv_extraction_run(
        cv_document_id=reuploaded_first.id,
        user_id=user.id,
        model_provider="test",
        model_name="test",
        raw_text_hash="f" * 64,
    )
    repository.complete_cv_extraction(
        latest_first_extraction,
        extracted_profile={"summary": "Profile A refreshed", "skills": []},
        target_title_suggestions=["Role A2"],
        confidence_summary={},
    )
    repository.complete_cv_document(reuploaded_first)
    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="needs_profile_review",
    )
    second_started = service.start_individual_graph(user.id, reuploaded_first.id)
    recovered = service.get_profile(user.id)

    assert reuploaded_first.id == first_document.id
    assert reuploaded_first.uploaded_at > second_document.uploaded_at
    assert second_started.thread_id == (
        f"individual-{user.id}-cv-{first_document.id}"
        f"-extraction-{latest_first_extraction.id}"
    )
    assert second_started.thread_id != first_started.thread_id
    assert recovered.cv_document_id == first_document.id
    assert recovered.extraction_run_id == latest_first_extraction.id
    assert recovered.active_thread_id == second_started.thread_id
    assert recovered.extracted_profile is not None
    assert recovered.extracted_profile["summary"] == "Profile A refreshed"


def test_resume_rejects_old_cv_thread_after_newer_cv_completed(db_session) -> None:
    user, first_document_id = _seed_completed_cv(db_session)
    repository = IndividualLearningRepository(db_session)
    checkpointer = InMemorySaver()
    service = IndividualLearningService(
        db_session,
        None,
        graph_checkpointer=checkpointer,
    )
    first_started = service.start_individual_graph(user.id, first_document_id)

    second_document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/newer-opaque-id",
        original_filename="newer.pdf",
        content_type="application/pdf",
        content_hash="c" * 64,
        size_bytes=456,
    )
    second_extraction = repository.create_cv_extraction_run(
        cv_document_id=second_document.id,
        user_id=user.id,
        model_provider="test",
        model_name="test",
        raw_text_hash="d" * 64,
    )
    repository.complete_cv_extraction(
        second_extraction,
        extracted_profile={"summary": "Current profile", "skills": []},
        target_title_suggestions=["Current role"],
        confidence_summary={},
    )
    repository.complete_cv_document(second_document)
    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="needs_profile_review",
    )

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            first_started.thread_id,
            {"approved": True, "target_titles": ["Stale role"]},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Workflow attempt is stale; reload the current profile"
    )
    current_profile = repository.get_profile(user.id)
    assert current_profile is not None
    assert current_profile.onboarding_status == "needs_profile_review"
    assert current_profile.target_titles_json == []


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


def test_duplicate_start_returns_the_advanced_checkpoint_without_resetting_it(
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
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=checkpointer,
        job_searcher=lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
            }
        ],
        market_skill_extractor=lambda jobs: {jobs[0]["url"]: [{"name": "Docker"}]},
    )
    started = service.start_individual_graph(user.id, cv_document_id)
    advanced = service.resume_individual_graph(
        user.id,
        started.thread_id,
        {"approved": True, "target_titles": ["Backend Engineer"]},
    )

    duplicate = service.start_individual_graph(user.id, cv_document_id)

    assert advanced.interrupt is not None
    assert advanced.interrupt["kind"] == "choose_jobs_and_skills"
    assert duplicate.interrupt == advanced.interrupt
    assert duplicate.target_titles == ["Backend Engineer"]


def test_workflow_lease_heartbeat_prevents_theft_past_the_expiry_boundary(
    db_session,
    monkeypatch,
) -> None:
    user, cv_document_id = _seed_completed_cv(db_session)
    repository = IndividualLearningRepository(db_session)
    extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=cv_document_id,
    )
    assert extraction is not None
    user_id = user.id
    extraction_run_id = extraction.id
    bind = db_session.get_bind()
    entered_graph = Event()
    release_graph = Event()

    class BlockingGraph:
        @staticmethod
        def get_state(_config):
            return SimpleNamespace(values={}, next=(), tasks=())

        @staticmethod
        def invoke(_payload, _config):
            entered_graph.set()
            assert release_graph.wait(timeout=5)
            return {
                "target_titles": [],
                "selected_posting_urls": [],
                "selected_skill_names": [],
            }

    monkeypatch.setattr(
        "app.modules.individual_learning.service.WORKFLOW_OPERATION_STALE_AFTER",
        timedelta(milliseconds=80),
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.WORKFLOW_LEASE_HEARTBEAT_SECONDS",
        0.01,
        raising=False,
    )
    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        lambda _self: BlockingGraph(),
    )

    def run_start():
        with Session(bind=bind) as worker_session:
            return IndividualLearningService(
                worker_session,
                None,
            ).start_individual_graph(user_id, cv_document_id)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_start)
        assert entered_graph.wait(timeout=5)
        time.sleep(0.2)
        now = datetime.now(UTC)
        try:
            with Session(bind=bind) as competing_session:
                stolen = IndividualLearningRepository(
                    competing_session
                ).claim_workflow_operation(
                    extraction_run_id=extraction_run_id,
                    user_id=user_id,
                    operation_token="competing-operation",
                    now=now,
                    stale_before=now - timedelta(milliseconds=80),
                )
            assert stolen is False
        finally:
            release_graph.set()
        assert future.result(timeout=5).status == "completed"


def test_workflow_lease_is_released_when_graph_invoke_raises(
    db_session,
    monkeypatch,
) -> None:
    user, cv_document_id = _seed_completed_cv(db_session)
    repository = IndividualLearningRepository(db_session)
    extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=cv_document_id,
    )
    assert extraction is not None

    class FailingGraph:
        @staticmethod
        def get_state(_config):
            return SimpleNamespace(values={}, next=(), tasks=())

        @staticmethod
        def invoke(_payload, _config):
            raise RuntimeError("injected graph failure")

    monkeypatch.setattr(
        IndividualLearningService,
        "_get_graph",
        lambda _self: FailingGraph(),
    )
    service = IndividualLearningService(db_session, None)

    with pytest.raises(RuntimeError, match="injected graph failure"):
        service.start_individual_graph(user.id, cv_document_id)

    db_session.expire_all()
    recovered = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=cv_document_id,
    )
    assert recovered is not None
    assert recovered.workflow_lease_token is None
    assert recovered.workflow_lease_started_at is None
    now = datetime.now(UTC)
    assert repository.claim_workflow_operation(
        extraction_run_id=extraction.id,
        user_id=user.id,
        operation_token="operation-after-failure",
        now=now,
        stale_before=now - timedelta(hours=1),
    )
    repository.release_workflow_operation(
        extraction_run_id=extraction.id,
        user_id=user.id,
        operation_token="operation-after-failure",
    )
