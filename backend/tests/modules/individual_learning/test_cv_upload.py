from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import threading

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.modules.auth.models import User, UserRole
from app.modules.individual_learning.models import IndividualRunStatus
from app.modules.individual_learning.repository import IndividualLearningRepository
from app.modules.individual_learning.schemas import CVProfileExtraction
from app.modules.individual_learning.service import (
    CV_UPLOAD_CHUNK_BYTES,
    MAX_CV_UPLOAD_BYTES,
    IndividualLearningService,
)
from app.providers.storage import BlobService


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
        self.blobs: dict[str, bytes] = {}

    async def upload_bytes(self, data: bytes, blob_path: str) -> str:
        self.uploads.append((data, blob_path))
        self.blobs[blob_path] = data
        return f"https://storage.example/{blob_path}"

    def download_bytes(self, blob_path: str, *, max_bytes: int) -> bytes:
        data = self.blobs[blob_path]
        if len(data) > max_bytes:
            raise ValueError("Blob exceeds the download limit")
        return data

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
    assert len(storage.uploads) == 1
    uploaded_bytes, uploaded_path = storage.uploads[0]
    assert uploaded_bytes == b"document-bytes"
    assert uploaded_path == f"users/{user.id}/cv/{expected_content_hash}/document"
    assert filename not in uploaded_path
    assert profile_extractor.inputs == [extracted_text]
    assert parser_thread_ids and parser_thread_ids[0] != caller_thread_id
    assert (
        profile_extractor.thread_ids
        and profile_extractor.thread_ids[0] != caller_thread_id
    )
    assert profile is not None
    assert profile.onboarding_status == "needs_profile_review"
    assert document is not None
    assert document.content_hash == expected_content_hash
    assert document.original_filename == filename
    assert document.blob_path == uploaded_path
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


def test_upload_cv_streams_with_bounded_reads_before_processing(db_session) -> None:
    user = _create_individual(db_session, email="bounded-upload@example.com")
    storage = FakeStorage()

    class GuardedFile(io.BytesIO):
        def __init__(self, value: bytes) -> None:
            super().__init__(value)
            self.read_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            assert 0 < size <= CV_UPLOAD_CHUNK_BYTES
            self.read_sizes.append(size)
            return super().read(size)

    guarded_file = GuardedFile(b"document-bytes")
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: (
            "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript data "
            "analysis machine learning dashboards APIs cloud deployment testing "
            "architecture collaboration documentation monitoring orchestration"
        ),
        cv_profile_extractor=FakeProfileExtractor(),
    )
    upload = UploadFile(
        filename="cv.pdf",
        file=guarded_file,
        headers=Headers({"content-type": "application/pdf"}),
    )

    response = asyncio.run(service.upload_cv(user.id, upload))

    assert response.status == "completed"
    assert len(guarded_file.read_sizes) >= 2
    assert all(size == CV_UPLOAD_CHUNK_BYTES for size in guarded_file.read_sizes)


def test_upload_cv_rejects_oversized_stream_before_storage_or_database(
    db_session,
) -> None:
    user = _create_individual(db_session, email="oversized-upload@example.com")
    storage = FakeStorage()
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: "unused",
        cv_profile_extractor=FakeProfileExtractor(),
    )
    upload = UploadFile(
        filename="cv.pdf",
        file=io.BytesIO(b"x" * (MAX_CV_UPLOAD_BYTES + 1)),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.upload_cv(user.id, upload))

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "CV file exceeds the upload size limit"
    assert storage.uploads == []
    assert (
        IndividualLearningRepository(db_session).get_latest_cv_document(user.id) is None
    )


def test_upload_cv_reader_accepts_stream_at_exact_size_limit() -> None:
    service = IndividualLearningService(None, None, storage=FakeStorage())
    upload = UploadFile(
        filename="cv.pdf",
        file=io.BytesIO(b"x" * MAX_CV_UPLOAD_BYTES),
        headers=Headers({"content-type": "application/pdf"}),
    )

    content = asyncio.run(service._read_cv_upload(upload))

    assert len(content) == MAX_CV_UPLOAD_BYTES


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
    assert document.error_message == "Structured CV extraction failed"
    assert document.blob_path.startswith(f"users/{user.id}/cv/")
    assert extraction is not None
    assert extraction.status == "failed"
    assert extraction.error_message == "Structured CV extraction failed"
    assert raw_cv not in caplog.text


def test_upload_cv_sanitizes_unrecognized_parser_value_error(
    db_session,
    caplog,
) -> None:
    user = _create_individual(db_session, email="unsafe-parser-error@example.com")
    storage = FakeStorage()
    private_marker = "PRIVATE-PARSER-DETAIL-8821"

    def fail_parse(**_kwargs):
        raise ValueError(private_marker)

    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=fail_parse,
        cv_profile_extractor=FakeProfileExtractor(),
    )
    upload = UploadFile(
        filename="cv.pdf",
        file=io.BytesIO(b"private-document-bytes"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.upload_cv(user.id, upload))

    repository = IndividualLearningRepository(db_session)
    document = repository.get_latest_cv_document(user.id)
    extraction = repository.get_latest_cv_extraction(user.id)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "CV file could not be parsed safely"
    assert document is not None
    assert document.error_message == "CV file could not be parsed safely"
    assert extraction is not None
    assert extraction.error_message == "CV file could not be parsed safely"
    assert private_marker not in caplog.text
    assert private_marker not in str(exc_info.value.detail)


@pytest.mark.parametrize(
    (
        "parse_error",
        "expected_status",
        "expected_detail",
        "expected_durable_error",
    ),
    [
        (
            ValueError("Invalid PDF CV file"),
            400,
            "Invalid PDF CV file",
            "Invalid PDF CV file",
        ),
        (
            RuntimeError("parser crashed"),
            500,
            "Failed to parse CV file",
            "CV parser failed",
        ),
    ],
)
def test_supported_cv_parse_failure_preserves_scoped_blob_and_durable_error(
    db_session,
    caplog,
    parse_error: Exception,
    expected_status: int,
    expected_detail: str,
    expected_durable_error: str,
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
    assert document.error_message == expected_durable_error
    assert extraction is not None
    assert extraction.status == "failed"
    assert extraction.error_message == expected_durable_error
    assert profile is not None
    assert profile.onboarding_status == "error"
    assert profile_extractor.inputs == []
    assert raw_marker not in caplog.text


def test_failed_cv_document_can_retry_from_preserved_blob_without_reupload(
    db_session,
) -> None:
    user = _create_individual(db_session, email="retry-preserved-cv@example.com")
    storage = FakeStorage()
    extracted_text = (
        "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript data analysis "
        "machine learning dashboards APIs cloud deployment testing architecture "
        "collaboration documentation monitoring orchestration pipelines"
    )
    failing_service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: extracted_text,
        cv_profile_extractor=FakeProfileExtractor(
            error=RuntimeError("structured provider unavailable")
        ),
    )
    upload = UploadFile(
        filename="cv.pdf",
        file=io.BytesIO(b"retryable-document-bytes"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(HTTPException):
        asyncio.run(failing_service.upload_cv(user.id, upload))
    repository = IndividualLearningRepository(db_session)
    failed_document = repository.get_latest_cv_document(user.id)
    assert failed_document is not None
    assert failed_document.status == "failed"

    retry_service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: extracted_text,
        cv_profile_extractor=FakeProfileExtractor(),
    )
    response = asyncio.run(retry_service.retry_cv_document(user.id, failed_document.id))

    latest_extraction = repository.get_latest_cv_extraction(
        user.id,
        cv_document_id=failed_document.id,
    )
    profile = repository.get_profile(user.id)
    assert response.id == failed_document.id
    assert response.status == "completed"
    assert len(storage.uploads) == 1
    assert latest_extraction is not None
    assert latest_extraction.status == "completed"
    assert profile is not None
    assert profile.onboarding_status == "needs_profile_review"


def test_retry_cv_document_enforces_ownership_and_failed_status(db_session) -> None:
    owner = _create_individual(db_session, email="retry-owner@example.com")
    other = _create_individual(db_session, email="retry-other@example.com")
    repository = IndividualLearningRepository(db_session)
    document = repository.upsert_cv_document(
        user_id=owner.id,
        blob_path=f"users/{owner.id}/cv/hash/document",
        original_filename="cv.pdf",
        content_type="application/pdf",
        content_hash="9" * 64,
        size_bytes=123,
    )
    document.status = "failed"
    db_session.commit()
    service = IndividualLearningService(db_session, None, storage=FakeStorage())

    with pytest.raises(HTTPException) as not_owned:
        asyncio.run(service.retry_cv_document(other.id, document.id))

    assert not_owned.value.status_code == 404
    assert not_owned.value.detail == "CV document not found"

    document.status = "completed"
    db_session.commit()
    with pytest.raises(HTTPException) as not_failed:
        asyncio.run(service.retry_cv_document(owner.id, document.id))

    assert not_failed.value.status_code == 409
    assert not_failed.value.detail == "Only a failed CV document can be retried"


def test_upload_cv_finalization_fault_rolls_back_then_marks_retryable_failure(
    db_session,
    monkeypatch,
) -> None:
    user = _create_individual(db_session, email="finalization-fault@example.com")
    storage = FakeStorage()
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: (
            "Python SQL Azure FastAPI PostgreSQL Docker React TypeScript data "
            "analysis machine learning dashboards APIs cloud deployment testing "
            "architecture collaboration documentation monitoring orchestration"
        ),
        cv_profile_extractor=FakeProfileExtractor(),
    )
    real_complete = service._repo.complete_cv_lifecycle
    injected = False

    def fail_once(**kwargs) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise RuntimeError("injected finalization fault")
        real_complete(**kwargs)

    monkeypatch.setattr(service._repo, "complete_cv_lifecycle", fail_once)
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
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to finalize CV processing"
    assert injected is True
    assert profile is not None
    assert profile.onboarding_status == "error"
    assert document is not None
    assert document.status == "failed"
    assert extraction is not None
    assert extraction.status == "failed"


def test_upload_cv_hides_filename_and_provider_error_on_storage_failure(
    db_session,
    caplog,
) -> None:
    filename_marker = "private-candidate-name.pdf"
    secret_marker = "AZURE-CREDENTIAL-SECRET-8842"
    user = _create_individual(db_session, email="storage-failure@example.com")

    class FailingStorage(FakeStorage):
        async def upload_bytes(self, data: bytes, blob_path: str) -> str:
            self.uploads.append((data, blob_path))
            raise RuntimeError(f"{secret_marker} while uploading {filename_marker}")

    storage = FailingStorage()
    service = IndividualLearningService(
        db_session,
        None,
        storage=storage,
        cv_text_extractor=lambda **_kwargs: "unused",
        cv_profile_extractor=FakeProfileExtractor(),
    )
    upload = UploadFile(
        filename=filename_marker,
        file=io.BytesIO(b"private-document-bytes"),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.upload_cv(user.id, upload))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "CV storage is temporarily unavailable; retry"
    response_text = str(exc_info.value.detail)
    assert filename_marker not in response_text
    assert secret_marker not in response_text
    assert filename_marker not in caplog.text
    assert secret_marker not in caplog.text
    assert storage.uploads
    assert filename_marker not in storage.uploads[0][1]


def test_blob_upload_logging_omits_destination_and_raw_provider_exception(
    caplog,
) -> None:
    destination_marker = "users/77/cv/PRIVATE-DESTINATION-9921"
    secret_marker = "PROVIDER-SECRET-TOKEN-1138"

    class FailingBlobClient:
        url = "https://storage.invalid/blob"

        def upload_blob(self, _content: bytes, *, overwrite: bool) -> None:
            assert overwrite is True
            raise RuntimeError(secret_marker)

    class FakeContainerClient:
        def get_blob_client(self, destination_path: str):
            assert destination_path == destination_marker
            return FailingBlobClient()

    storage = BlobService.__new__(BlobService)
    storage.container_client = FakeContainerClient()

    with (
        caplog.at_level(logging.ERROR, logger="app.providers.storage"),
        pytest.raises(RuntimeError, match=secret_marker),
    ):
        asyncio.run(storage.upload_bytes(b"private", destination_marker))

    assert destination_marker not in caplog.text
    assert secret_marker not in caplog.text
    assert "RuntimeError" in caplog.text


def test_blob_download_bytes_stops_when_stream_exceeds_limit() -> None:
    downloaded_chunks: list[bytes] = []

    class FakeDownloader:
        def chunks(self):
            for chunk in (b"abc", b"def", b"unreachable"):
                downloaded_chunks.append(chunk)
                yield chunk

    class FakeBlobClient:
        def download_blob(self, *, max_concurrency: int):
            assert max_concurrency == 8
            return FakeDownloader()

    class FakeContainerClient:
        def get_blob_client(self, blob_path: str):
            assert blob_path == "users/7/cv/hash/document"
            return FakeBlobClient()

    storage = BlobService.__new__(BlobService)
    storage.container_client = FakeContainerClient()

    with pytest.raises(ValueError, match="Blob exceeds the download limit"):
        storage.download_bytes(
            "users/7/cv/hash/document",
            max_bytes=5,
        )

    assert downloaded_chunks == [b"abc", b"def"]


def test_blob_download_bytes_accepts_stream_at_exact_limit() -> None:
    class FakeDownloader:
        @staticmethod
        def chunks():
            return iter((b"abc", b"de"))

    class FakeBlobClient:
        @staticmethod
        def download_blob(*, max_concurrency: int):
            assert max_concurrency == 8
            return FakeDownloader()

    class FakeContainerClient:
        @staticmethod
        def get_blob_client(_blob_path: str):
            return FakeBlobClient()

    storage = BlobService.__new__(BlobService)
    storage.container_client = FakeContainerClient()

    content = storage.download_bytes("users/7/cv/hash/document", max_bytes=5)

    assert content == b"abcde"
