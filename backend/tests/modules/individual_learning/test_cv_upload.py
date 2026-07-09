from __future__ import annotations

import asyncio
import hashlib
import io
import threading

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import IndividualRunStatus
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.schemas import CVProfileExtraction
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


class FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []

    async def upload_bytes(self, data: bytes, blob_path: str) -> str:
        self.uploads.append((data, blob_path))
        return f"https://storage.example/{blob_path}"

    @staticmethod
    def sha256_hex(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()


class FakeProfileExtractor:
    model_provider = "test-provider"
    model_name = "test-model"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.inputs: list[str] = []
        self.thread_ids: list[int] = []

    def extract(self, text: str) -> CVProfileExtraction:
        self.inputs.append(text)
        self.thread_ids.append(threading.get_ident())
        if self.error is not None:
            raise self.error
        return CVProfileExtraction(
            summary="Backend engineer",
            skills=[
                {
                    "name": "Python",
                    "category": "Programming",
                    "evidence": "Built APIs",
                    "confidence": 0.9,
                }
            ],
            target_title_suggestions=["Backend Engineer"],
            confidence_summary={"skills": 0.9},
        )


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("cv.pdf", "application/pdf"),
        (
            "cv.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
def test_upload_cv_runs_scoped_storage_and_structured_extraction_pipeline(
    db_session,
    filename: str,
    content_type: str,
) -> None:
    user = _create_individual(db_session, email=f"{filename}@example.com")
    storage = FakeStorage()
    profile_extractor = FakeProfileExtractor()
    parser_calls: list[dict[str, object]] = []
    parser_thread_ids: list[int] = []
    caller_thread_id = threading.get_ident()
    extracted_text = (
        "Private CV body with enough parsed details for structured extraction"
    )

    def parse_cv(**kwargs) -> str:
        parser_calls.append(kwargs)
        parser_thread_ids.append(threading.get_ident())
        return extracted_text

    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=parse_cv,
        cv_profile_extractor=profile_extractor,
    )
    upload = UploadFile(
        filename=filename,
        file=io.BytesIO(b"document-bytes"),
        headers=Headers({"content-type": content_type}),
    )

    response = asyncio.run(service.upload_cv(user.id, upload))

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    extraction = repository.get_latest_cv_extraction(user.id)
    document = repository.get_owned_cv_document(
        user_id=user.id,
        cv_document_id=response.id,
    )
    expected_content_hash = hashlib.sha256(b"document-bytes").hexdigest()

    assert response.status == "completed"
    assert parser_calls == [
        {
            "filename": filename,
            "content_type": content_type,
            "data": b"document-bytes",
        }
    ]
    assert storage.uploads == [
        (
            b"document-bytes",
            f"users/{user.id}/cv/{expected_content_hash}/{filename}",
        )
    ]
    assert profile_extractor.inputs == [extracted_text]
    assert parser_thread_ids and parser_thread_ids[0] != caller_thread_id
    assert (
        profile_extractor.thread_ids
        and profile_extractor.thread_ids[0] != caller_thread_id
    )
    assert profile is not None
    assert profile.onboarding_status == "needs_profile_review"
    assert document is not None
    assert document.status == "completed"
    assert extraction is not None
    assert extraction.model_provider == "test-provider"
    assert extraction.model_name == "test-model"
    assert (
        extraction.raw_text_hash == hashlib.sha256(extracted_text.encode()).hexdigest()
    )
    assert extraction.status == IndividualRunStatus.COMPLETED.value
    assert extraction.extracted_profile_json["summary"] == "Backend engineer"
    assert extraction.target_title_suggestions_json == ["Backend Engineer"]
    assert extraction.confidence_summary_json == {"skills": 0.9}


def test_upload_cv_records_structured_extraction_failure_without_logging_raw_cv(
    db_session,
    caplog,
) -> None:
    user = _create_individual(db_session, email="failed-cv@example.com")
    storage = FakeStorage()
    raw_cv = "PRIVATE-CV-SECRET-4711"
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: raw_cv,
        cv_profile_extractor=FakeProfileExtractor(
            error=RuntimeError("structured provider unavailable")
        ),
    )
    upload = UploadFile(
        filename="cv.pdf",
        file=io.BytesIO(b"document-bytes"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.upload_cv(user.id, upload))

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    document = repository.get_latest_cv_document(user.id)
    extraction = repository.get_latest_cv_extraction(user.id)

    assert exc_info.value.status_code == 502
    assert profile is not None
    assert profile.onboarding_status == "error"
    assert document is not None
    assert document.status == "failed"
    assert document.blob_path.startswith(f"users/{user.id}/cv/")
    assert extraction is not None
    assert extraction.status == "failed"
    assert extraction.error_message == "structured provider unavailable"
    assert raw_cv not in caplog.text


@pytest.mark.parametrize(
    ("parse_error", "expected_status", "expected_detail"),
    [
        (ValueError("Invalid PDF CV file"), 400, "Invalid PDF CV file"),
        (RuntimeError("parser crashed"), 500, "Failed to parse CV file"),
    ],
)
def test_supported_cv_parse_failure_preserves_scoped_blob_and_durable_error(
    db_session,
    caplog,
    parse_error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    user = _create_individual(
        db_session,
        email=f"corrupt-cv-{expected_status}@example.com",
    )
    storage = FakeStorage()
    raw_marker = "CORRUPT-PRIVATE-CV-9911"

    def fail_parse(**_kwargs):
        raise parse_error

    profile_extractor = FakeProfileExtractor()
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=fail_parse,
        cv_profile_extractor=profile_extractor,
    )
    upload = UploadFile(
        filename="corrupt.pdf",
        file=io.BytesIO(raw_marker.encode()),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.upload_cv(user.id, upload))

    repository = IndividualLearningRepository(db_session)
    profile = repository.get_profile(user.id)
    document = repository.get_latest_cv_document(user.id)
    extraction = repository.get_latest_cv_extraction(user.id)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_detail
    assert storage.uploads
    assert storage.uploads[0][1].startswith(f"users/{user.id}/cv/")
    assert document is not None
    assert document.status == "failed"
    assert document.error_message == str(parse_error)
    assert extraction is not None
    assert extraction.status == "failed"
    assert extraction.error_message == str(parse_error)
    assert profile is not None
    assert profile.onboarding_status == "error"
    assert profile_extractor.inputs == []
    assert raw_marker not in caplog.text
