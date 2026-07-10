from __future__ import annotations

from contextlib import nullcontext

import pytest
from fastapi import HTTPException
from langgraph.checkpoint.memory import InMemorySaver

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import (
    CVDocumentStatus,
    IndividualRunStatus,
)
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.service import IndividualLearningService


def _create_individual(db_session, *, email: str) -> User:
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


def _seed_completed_extraction(db_session, *, user_id: int):
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=user_id,
        blob_path=f"users/{user_id}/cv/hash/cv.pdf",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash=str(user_id).zfill(64),
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
    repository.upsert_profile_status(
        user_id=user_id,
        onboarding_status="needs_profile_review",
    )
    return document, extraction


class DummyDriver:
    def __init__(self) -> None:
        self.session_value = object()

    def session(self):
        return nullcontext(self.session_value)


def test_first_resume_durably_approves_stored_profile_titles_and_cv_skills(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session, email="owner@example.com")
    document, extraction = _seed_completed_extraction(db_session, user_id=user.id)
    driver = DummyDriver()
    checkpointer = InMemorySaver()
    captured: dict[str, object] = {}

    def fake_upsert_cv_skills(
        session,
        *,
        user_id,
        skills,
        cv_document_id,
        extraction_run_id,
    ) -> int:
        captured.update(
            {
                "session": session,
                "user_id": user_id,
                "skills": skills,
                "cv_document_id": cv_document_id,
                "extraction_run_id": extraction_run_id,
            }
        )
        return len(skills)

    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        fake_upsert_cv_skills,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: {"jobs": 0, "market_skills": 0},
    )
    service = IndividualLearningService(
        db_session,
        driver,
        graph_checkpointer=checkpointer,
        job_searcher=lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
            }
        ],
        market_skill_extractor=lambda jobs: {jobs[0]["url"]: [{"name": "Docker"}]},
    )

    started = service.start_individual_graph(user.id, document.id)
    resumed = service.resume_individual_graph(
        user.id,
        started.thread_id,
        {
            "approved": True,
            "target_titles": [" Backend Engineer ", "Platform Engineer"],
        },
    )

    profile = IndividualLearningRepository(db_session).get_profile(user.id)

    assert started.interrupt is not None
    assert started.interrupt["kind"] == "review_profile_and_roles"
    assert resumed.interrupt is not None
    assert resumed.interrupt["kind"] == "choose_jobs_and_skills"
    assert profile is not None
    assert profile.target_titles_json == ["Backend Engineer", "Platform Engineer"]
    assert profile.reviewed_at is not None
    assert profile.onboarding_status == "needs_skill_selection"
    assert captured["session"] is driver.session_value
    assert captured["user_id"] == user.id
    assert captured["cv_document_id"] == document.id
    assert captured["extraction_run_id"] == extraction.id
    skills = captured["skills"]
    assert len(skills) == 1
    assert skills[0].name == "Python"
    assert skills[0].evidence == "Built APIs"


def test_profile_review_requires_all_normalized_cv_skills_to_be_projected(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session, email="projection-count@example.com")
    document, _ = _seed_completed_extraction(db_session, user_id=user.id)
    search_calls: list[str] = []
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        lambda *_args, **_kwargs: 0,
    )
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
        job_searcher=lambda *_args: search_calls.append("searched") or [],
    )
    started = service.start_individual_graph(user.id, document.id)

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            started.thread_id,
            {"approved": True, "target_titles": ["Backend Engineer"]},
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "CV skill projection is incomplete; retry approval"
    assert search_calls == []
    recovery = service.get_profile(user.id)
    assert recovery.next_step == "review_profile"
    assert recovery.pending_interrupt is not None
    assert recovery.pending_interrupt["kind"] == "review_profile_and_roles"


def test_profile_review_normalizes_distinct_skills_and_omits_removed_skill(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session, email="changed-profile@example.com")
    document, extraction = _seed_completed_extraction(db_session, user_id=user.id)
    extraction.extracted_profile_json = {
        **extraction.extracted_profile_json,
        "skills": [
            *extraction.extracted_profile_json["skills"],
            {"name": "Legacy Skill", "confidence": 0.7},
        ],
    }
    db_session.commit()
    captured_skills: list[object] = []

    def capture_projection(_session, *, skills, **_kwargs) -> int:
        captured_skills.extend(skills)
        return len(skills)

    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_cv_skills",
        capture_projection,
    )
    monkeypatch.setattr(
        "app.modules.individual_learning.service.upsert_job_postings_and_market_skills",
        lambda *_args, **_kwargs: {"jobs": 1, "market_skills": 0},
    )
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
        job_searcher=lambda *_args: [
            {
                "url": "https://jobs.example/backend",
                "title": "Backend Engineer",
            }
        ],
        market_skill_extractor=lambda jobs: {
            jobs[0]["url"]: [{"name": "Docker", "category": "DevOps"}]
        },
    )
    started = service.start_individual_graph(user.id, document.id)

    service.resume_individual_graph(
        user.id,
        started.thread_id,
        {
            "approved": True,
            "target_titles": ["Backend Engineer"],
            "profile": {
                "summary": "Edited profile",
                "skills": [
                    {"name": " Python ", "confidence": 0.9},
                    {"name": "python", "confidence": 0.8},
                    {"name": "Docker", "confidence": 0.7},
                ],
                "target_title_suggestions": ["Backend Engineer"],
            },
        },
    )

    persisted = IndividualLearningRepository(db_session).get_latest_cv_extraction(
        user.id,
        cv_document_id=document.id,
    )
    assert persisted is not None
    assert [skill.name for skill in captured_skills] == ["Python", "Docker"]
    assert [skill["name"] for skill in persisted.extracted_profile_json["skills"]] == [
        "Python",
        "Docker",
    ]


def test_graph_start_rejects_cv_owned_by_another_individual(db_session) -> None:
    owner = _create_individual(db_session, email="cv-owner@example.com")
    attacker = _create_individual(db_session, email="other@example.com")
    document, _ = _seed_completed_extraction(db_session, user_id=owner.id)
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.start_individual_graph(attacker.id, document.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "CV document not found"


def test_graph_start_rejects_owned_but_stale_cv_lifecycle(db_session) -> None:
    user = _create_individual(db_session, email="stale-start@example.com")
    stale_document, _ = _seed_completed_extraction(db_session, user_id=user.id)
    repository = IndividualLearningRepository(db_session)
    current_document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/current/document",
        original_filename="current.pdf",
        content_type="application/pdf",
        content_hash="f" * 64,
        size_bytes=456,
    )
    current_extraction = repository.create_cv_extraction_run(
        cv_document_id=current_document.id,
        user_id=user.id,
        model_provider="test-provider",
        model_name="test-model",
        raw_text_hash="e" * 64,
    )
    repository.complete_cv_extraction(
        current_extraction,
        extracted_profile={"summary": "Current", "skills": []},
        target_title_suggestions=["Platform Engineer"],
        confidence_summary={},
    )
    repository.complete_cv_document(current_document)
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
    )

    with pytest.raises(HTTPException) as exc_info:
        service.start_individual_graph(user.id, stale_document.id)

    assert current_document.id != stale_document.id
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "Workflow attempt is stale; reload the current profile"
    )


@pytest.mark.parametrize(
    ("document_status", "extraction_status"),
    [
        (CVDocumentStatus.PROCESSING.value, IndividualRunStatus.COMPLETED.value),
        (CVDocumentStatus.FAILED.value, IndividualRunStatus.COMPLETED.value),
        (CVDocumentStatus.COMPLETED.value, None),
        (CVDocumentStatus.COMPLETED.value, IndividualRunStatus.RUNNING.value),
        (CVDocumentStatus.COMPLETED.value, IndividualRunStatus.FAILED.value),
    ],
)
def test_graph_start_requires_completed_document_and_latest_extraction_without_checkpoint(
    db_session,
    document_status: str,
    extraction_status: str | None,
) -> None:
    user = _create_individual(
        db_session,
        email=f"start-gate-{document_status}-{extraction_status}@example.com",
    )
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=user.id,
        blob_path=f"users/{user.id}/cv/opaque",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash=f"{user.id:064x}",
        size_bytes=123,
    )
    if extraction_status is not None:
        extraction = repository.create_cv_extraction_run(
            cv_document_id=document.id,
            user_id=user.id,
            model_provider="test-provider",
            model_name="test-model",
            raw_text_hash="b" * 64,
        )
        extraction.status = extraction_status
        if extraction_status == IndividualRunStatus.COMPLETED.value:
            extraction.extracted_profile_json = {
                "summary": "Backend engineer",
                "skills": [],
            }
        db_session.commit()
    document.status = document_status
    db_session.commit()

    checkpointer = InMemorySaver()
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=checkpointer,
    )
    with pytest.raises(HTTPException) as exc_info:
        service.start_individual_graph(user.id, document.id)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        "CV processing is incomplete; retry extraction or upload the CV again"
    )
    assert list(checkpointer.list(None)) == []


@pytest.mark.parametrize(
    ("payload", "expected_detail"),
    [
        (
            {"approved": False, "target_titles": ["Backend Engineer"]},
            "Profile approval is required before job search",
        ),
        (
            {"approved": True, "target_titles": ["Backend Engineer", 7]},
            "Target titles must be a list of text values",
        ),
        (
            {
                "approved": True,
                "target_titles": [
                    "Role 1",
                    "Role 2",
                    "Role 3",
                    "Role 4",
                    "Role 5",
                    "Role 6",
                    "Role 7",
                    "Role 8",
                    "Role 9",
                    "Role 10",
                    "Role 11",
                ],
            },
            "Select no more than 10 target titles",
        ),
        (
            {
                "approved": True,
                "target_titles": ["Backend Engineer"],
                "profile": {
                    "skills": [{"name": {"unexpected": "object"}}],
                },
            },
            "Reviewed profile is invalid",
        ),
    ],
)
def test_first_resume_rejects_unapproved_or_malformed_profile_review(
    db_session,
    payload,
    expected_detail: str,
) -> None:
    user = _create_individual(
        db_session,
        email=f"invalid-{expected_detail[:8]}-{len(payload['target_titles'])}@example.com",
    )
    document, _ = _seed_completed_extraction(db_session, user_id=user.id)
    service = IndividualLearningService(
        db_session,
        DummyDriver(),
        graph_checkpointer=InMemorySaver(),
    )
    started = service.start_individual_graph(user.id, document.id)

    with pytest.raises(HTTPException) as exc_info:
        service.resume_individual_graph(
            user.id,
            started.thread_id,
            payload,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == expected_detail
