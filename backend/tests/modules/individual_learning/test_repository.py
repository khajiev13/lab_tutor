from __future__ import annotations

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import (
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
    )
    second_match = repository.get_or_create_job_match_run(
        user_id=user.id,
        job_search_run_id=first_search.id,
    )

    assert first_search.id == second_search.id
    assert first_match.id == second_match.id


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
