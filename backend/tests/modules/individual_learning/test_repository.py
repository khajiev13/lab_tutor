from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import (
    CVDocument,
    CVDocumentStatus,
    IndividualRunStatus,
)
from app.modules.individual_learning.repository import IndividualLearningRepository


def _create_individual(db_session, *, email: str = "individual@example.com") -> User:
    user = User(
        email=email,
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


def test_repository_persists_cv_extraction_lifecycle_and_recovery(db_session) -> None:
    user = _create_individual(db_session)
    repository = IndividualLearningRepository(db_session)

    profile = repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="extracting",
    )
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/hash/cv.pdf",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="a" * 64,
        size_bytes=123,
    )
    extraction = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user.id,
        model_provider="openai-compatible",
        model_name="fake-model",
        raw_text_hash="b" * 64,
    )

    repository.complete_cv_extraction(
        extraction,
        extracted_profile={
            "summary": "Backend engineer",
            "skills": [{"name": "Python", "confidence": 0.9}],
        },
        target_title_suggestions=["Backend Engineer"],
        confidence_summary={"skills": 0.9},
    )
    repository.complete_cv_document(document)
    repository.upsert_profile_status(
        user_id=user.id,
        onboarding_status="needs_profile_review",
    )

    recovered_profile = repository.get_profile(user.id)
    recovered_document = repository.get_latest_cv_document(user.id)
    recovered_extraction = repository.get_latest_cv_extraction(user.id)

    assert profile.user_id == user.id
    assert recovered_profile is not None
    assert recovered_profile.onboarding_status == "needs_profile_review"
    assert recovered_document is not None
    assert recovered_document.status == CVDocumentStatus.COMPLETED.value
    assert recovered_document.processed_at is not None
    assert recovered_extraction is not None
    assert recovered_extraction.status == IndividualRunStatus.COMPLETED.value
    assert recovered_extraction.extracted_profile_json["skills"][0]["name"] == "Python"
    assert recovered_extraction.target_title_suggestions_json == ["Backend Engineer"]
    assert recovered_extraction.completed_at is not None


def test_repository_marks_cv_extraction_failure_without_losing_uploaded_document(
    db_session,
) -> None:
    user = _create_individual(db_session)
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/hash/cv.docx",
        original_filename="cv.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        content_hash="c" * 64,
        size_bytes=456,
    )
    extraction = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user.id,
        model_provider="openai-compatible",
        model_name="fake-model",
        raw_text_hash="d" * 64,
    )

    repository.fail_cv_extraction(
        extraction,
        document=document,
        error_message="structured extraction failed",
    )
    repository.upsert_profile_status(user_id=user.id, onboarding_status="error")

    recovered_document = repository.get_owned_cv_document(
        user_id=user.id,
        cv_document_id=document.id,
    )
    recovered_extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=document.id,
    )

    assert recovered_document is not None
    assert recovered_document.blob_path.endswith("/cv.docx")
    assert recovered_document.status == CVDocumentStatus.FAILED.value
    assert recovered_document.error_message == "structured extraction failed"
    assert recovered_extraction is not None
    assert recovered_extraction.status == IndividualRunStatus.FAILED.value
    assert recovered_extraction.error_message == "structured extraction failed"
    assert recovered_extraction.completed_at is not None


def test_repository_finalizes_cv_document_extraction_and_profile_atomically(
    db_session,
) -> None:
    user = _create_individual(db_session, email="atomic-cv-success@example.com")
    repository = IndividualLearningRepository(db_session)
    repository.upsert_profile_status(user_id=user.id, onboarding_status="extracting")
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/atomic/document",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="1" * 64,
        size_bytes=123,
    )
    extraction = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user.id,
        model_provider="test-provider",
        model_name="test-model",
        raw_text_hash="2" * 64,
    )

    repository.complete_cv_lifecycle(
        document=document,
        extraction=extraction,
        user_id=user.id,
        extracted_profile={"summary": "Backend engineer", "skills": []},
        target_title_suggestions=["Backend Engineer"],
        confidence_summary={},
    )

    profile = repository.get_profile(user.id)
    assert profile is not None
    assert profile.onboarding_status == "needs_profile_review"
    assert document.status == CVDocumentStatus.COMPLETED.value
    assert extraction.status == IndividualRunStatus.COMPLETED.value


def test_repository_rolls_back_all_cv_finalization_state_on_commit_fault(
    db_session,
) -> None:
    user = _create_individual(db_session, email="atomic-cv-fault@example.com")
    repository = IndividualLearningRepository(db_session)
    repository.upsert_profile_status(user_id=user.id, onboarding_status="extracting")
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/fault/document",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="3" * 64,
        size_bytes=456,
    )
    extraction = repository.create_cv_extraction_run(
        cv_document_id=document.id,
        user_id=user.id,
        model_provider="test-provider",
        model_name="test-model",
        raw_text_hash="4" * 64,
    )
    injected = False

    def fail_completed_commit(session) -> None:
        nonlocal injected
        if not injected and extraction.status == IndividualRunStatus.COMPLETED.value:
            injected = True
            raise RuntimeError("injected finalization fault")

    event.listen(db_session, "before_commit", fail_completed_commit)
    try:
        with pytest.raises(RuntimeError, match="injected finalization fault"):
            repository.complete_cv_lifecycle(
                document=document,
                extraction=extraction,
                user_id=user.id,
                extracted_profile={"summary": "Backend engineer", "skills": []},
                target_title_suggestions=["Backend Engineer"],
                confidence_summary={},
            )
    finally:
        event.remove(db_session, "before_commit", fail_completed_commit)

    db_session.expire_all()
    profile = repository.get_profile(user.id)
    recovered_document = repository.get_owned_cv_document(
        user_id=user.id,
        cv_document_id=document.id,
    )
    recovered_extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=document.id,
    )
    assert injected is True
    assert profile is not None
    assert profile.onboarding_status == "extracting"
    assert recovered_document is not None
    assert recovered_document.status == CVDocumentStatus.PROCESSING.value
    assert recovered_extraction is not None
    assert recovered_extraction.status == IndividualRunStatus.RUNNING.value


def test_repository_concurrent_document_and_profile_upserts_are_idempotent(
    db_session,
) -> None:
    user = _create_individual(db_session, email="concurrent-cv-upsert@example.com")
    user_id = user.id
    bind = db_session.get_bind()
    document_barrier = Barrier(2)

    def upsert_document(index: int) -> int:
        with Session(bind=bind) as session:
            document_barrier.wait(timeout=10)
            document = IndividualLearningRepository(session).upsert_cv_document(
                user_id=user_id,
                blob_path=f"users/{user_id}/cv/shared/document",
                original_filename=f"cv-{index}.pdf",
                content_type="application/pdf",
                content_hash="5" * 64,
                size_bytes=100 + index,
            )
            return document.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        document_ids = list(executor.map(upsert_document, range(2)))

    profile_barrier = Barrier(2)

    def upsert_profile(index: int) -> int:
        with Session(bind=bind) as session:
            profile_barrier.wait(timeout=10)
            profile = IndividualLearningRepository(session).upsert_profile_status(
                user_id=user_id,
                onboarding_status=("extracting" if index == 0 else "error"),
            )
            return profile.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        profile_ids = list(executor.map(upsert_profile, range(2)))

    db_session.expire_all()
    assert len(set(document_ids)) == 1
    assert len(set(profile_ids)) == 1
    assert (
        db_session.scalar(
            select(func.count(CVDocument.id)).where(
                CVDocument.user_id == user_id,
                CVDocument.content_hash == "5" * 64,
            )
        )
        == 1
    )


def test_repository_serializes_per_user_cv_attempts_across_sessions(db_session) -> None:
    user = _create_individual(db_session, email="concurrent-cv-lock@example.com")
    repository = IndividualLearningRepository(db_session)
    first_lock = repository.acquire_user_cv_lock(user.id)
    second_acquired = Event()

    def acquire_second_lock() -> None:
        second_repository = IndividualLearningRepository(
            Session(bind=db_session.get_bind())
        )
        lock = second_repository.acquire_user_cv_lock(user.id)
        second_acquired.set()
        second_repository.release_user_cv_lock(lock, user.id)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(acquire_second_lock)
            assert second_acquired.wait(timeout=0.2) is False
            repository.release_user_cv_lock(first_lock, user.id)
            future.result(timeout=10)
    finally:
        if not second_acquired.is_set():
            repository.release_user_cv_lock(first_lock, user.id)

    assert second_acquired.is_set()


def test_repository_persists_partial_job_search_and_match_runs(db_session) -> None:
    user = _create_individual(db_session, email="job-runs@example.com")
    repository = IndividualLearningRepository(db_session)

    search_run = repository.create_job_search_run(
        user_id=user.id,
        target_titles=["Backend Engineer", "Platform Engineer"],
        country="USA",
        location="New York",
    )
    repository.complete_job_search_run(
        search_run,
        jobs=[
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
                "match_score": 50.0,
            }
        ],
        status=IndividualRunStatus.PARTIAL.value,
        error_message="Platform Engineer: provider unavailable",
    )
    match_run = repository.create_job_match_run(
        user_id=user.id,
        job_search_run_id=search_run.id,
    )
    repository.complete_job_match_run(
        match_run,
        scores=[
            {
                "job_url": "https://jobs.example/backend",
                "match_score": 50.0,
            }
        ],
        skill_gaps=[
            {
                "job_url": "https://jobs.example/backend",
                "skill_name": "Docker",
                "coverage": "gap",
            }
        ],
        status=IndividualRunStatus.PARTIAL.value,
    )

    recovered_search = repository.get_latest_job_search_run(user.id)
    recovered_match = repository.get_latest_job_match_run(user.id)

    assert recovered_search is not None
    assert recovered_search.status == IndividualRunStatus.PARTIAL.value
    assert (
        recovered_search.fetched_jobs_json[0]["url"] == "https://jobs.example/backend"
    )
    assert recovered_search.error_message == "Platform Engineer: provider unavailable"
    assert recovered_search.completed_at is not None
    assert recovered_match is not None
    assert recovered_match.job_search_run_id == recovered_search.id
    assert recovered_match.status == IndividualRunStatus.PARTIAL.value
    assert recovered_match.scores_json[0]["match_score"] == 50.0
    assert recovered_match.skill_gap_json[0]["skill_name"] == "Docker"
    assert recovered_match.completed_at is not None


def test_repository_reuses_job_audit_runs_for_the_same_workflow_thread(
    db_session,
) -> None:
    user = _create_individual(db_session, email="idempotent-job-runs@example.com")
    repository = IndividualLearningRepository(db_session)

    first_search = repository.get_or_create_job_search_run(
        user_id=user.id,
        workflow_thread_id=f"individual-{user.id}-cv-9",
        target_titles=["Backend Engineer"],
        country="USA",
        location="New York",
    )
    second_search = repository.get_or_create_job_search_run(
        user_id=user.id,
        workflow_thread_id=f"individual-{user.id}-cv-9",
        target_titles=["Backend Engineer"],
        country="USA",
        location="New York",
    )
    first_match = repository.get_or_create_job_match_run(
        user_id=user.id,
        job_search_run_id=first_search.id,
        workflow_thread_id=f"individual-{user.id}-cv-9-extraction-10",
    )
    second_match = repository.get_or_create_job_match_run(
        user_id=user.id,
        job_search_run_id=first_search.id,
        workflow_thread_id=f"individual-{user.id}-cv-9-extraction-10",
    )

    assert first_search.id == second_search.id
    assert first_match.id == second_match.id


def test_repository_atomically_reuses_search_and_match_runs_across_sessions(
    db_session,
) -> None:
    user = _create_individual(db_session, email="concurrent-job-runs@example.com")
    bind = db_session.get_bind()
    search_thread_id = f"individual-{user.id}-cv-17-extraction-21"
    search_barrier = Barrier(2)

    def get_search_run_id() -> int:
        with Session(bind=bind) as session:
            search_barrier.wait()
            run = IndividualLearningRepository(session).get_or_create_job_search_run(
                user_id=user.id,
                workflow_thread_id=search_thread_id,
                target_titles=["Backend Engineer"],
                country="USA",
                location="New York",
            )
            return run.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        search_ids = list(executor.map(lambda _index: get_search_run_id(), range(2)))

    assert len(set(search_ids)) == 1
    match_barrier = Barrier(2)
    match_thread_id = f"{search_thread_id}-match"

    def get_match_run_id() -> int:
        with Session(bind=bind) as session:
            match_barrier.wait()
            run = IndividualLearningRepository(session).get_or_create_job_match_run(
                user_id=user.id,
                job_search_run_id=search_ids[0],
                workflow_thread_id=match_thread_id,
            )
            return run.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        match_ids = list(executor.map(lambda _index: get_match_run_id(), range(2)))

    assert len(set(match_ids)) == 1


def test_repository_records_job_selection_only_on_owned_search_run(db_session) -> None:
    owner = _create_individual(db_session, email="selection-owner@example.com")
    other = _create_individual(db_session, email="selection-other@example.com")
    repository = IndividualLearningRepository(db_session)
    search_run = repository.create_job_search_run(
        user_id=owner.id,
        target_titles=["Backend Engineer"],
        country="USA",
        location="New York",
    )

    assert (
        repository.record_job_selections(
            user_id=other.id,
            job_search_run_id=search_run.id,
            posting_urls=["https://jobs.example/backend"],
        )
        is False
    )
    assert repository.record_job_selections(
        user_id=owner.id,
        job_search_run_id=search_run.id,
        posting_urls=["https://jobs.example/backend"],
    )
    assert search_run.selected_posting_urls_json == ["https://jobs.example/backend"]
