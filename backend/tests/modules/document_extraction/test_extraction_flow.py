from __future__ import annotations

from concurrent.futures import Future
from datetime import UTC, datetime
from typing import Any

from app.modules.courses.models import FileProcessingStatus
from app.modules.courses.repository import CourseRepository
from app.modules.document_extraction.schemas import (
    CanonicalExtractionResult,
    CompleteExtractionResult,
    ExtractionMetadata,
)
from app.modules.document_extraction.service import (
    DocumentExtractionService,
    run_course_extraction_background,
)


def _ok_result(*, filename: str) -> CompleteExtractionResult:
    return CompleteExtractionResult(
        extraction=CanonicalExtractionResult(
            topic=f"Topic for {filename}",
            summary="A short summary.",
            keywords=["k1", "k2", "k3", "k4", "k5"],
            concepts=[],
        ),
        metadata=ExtractionMetadata(
            source_filename=filename,
            original_text_length=200,
            processed_text_length=200,
            model_used="test",
        ),
        success=True,
        error_message=None,
    )


def _fail_result(*, filename: str, msg: str) -> CompleteExtractionResult:
    return CompleteExtractionResult(
        extraction=CanonicalExtractionResult(
            topic="Extraction Failed",
            summary="Extraction failed due to an error.",
            keywords=["extraction", "failed", "error", "processing", "system"],
            concepts=[],
        ),
        metadata=ExtractionMetadata(
            source_filename=filename,
            original_text_length=200,
            processed_text_length=200,
            model_used="test",
        ),
        success=False,
        error_message=msg,
    )


def test_partial_failure_marks_course_failed_and_keeps_file_statuses(
    client, db_session, teacher_auth_headers, mock_blob_service, monkeypatch
):
    create_res = client.post(
        "/courses",
        json={"title": "Extraction Course 1", "description": "desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Upload two text files (both start as pending).
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("ok.txt", b"a" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("bad.txt", b"b" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )

    # Ensure extraction uses mocked blob service too.
    monkeypatch.setattr(
        "app.modules.document_extraction.service.blob_service", mock_blob_service
    )
    mock_blob_service.download_file.return_value = b"x" * 200

    outcomes: dict[str, bool] = {"ok.txt": True, "bad.txt": False}

    class DummyExtractor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def extract(self, *, text: str, source_filename: str | None = None):
            assert source_filename is not None
            if outcomes.get(source_filename, False):
                return _ok_result(filename=source_filename)
            return _fail_result(filename=source_filename, msg="boom")

    monkeypatch.setattr(
        "app.modules.document_extraction.service.DocumentLLMExtractor", DummyExtractor
    )

    DocumentExtractionService(db=db_session, neo4j_session=None).run_course_extraction(
        course_id=course_id, teacher_id=1
    )

    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "failed"

    statuses = client.get(
        f"/courses/{course_id}/presentations/status", headers=teacher_auth_headers
    ).json()
    by_name = {f["filename"]: f for f in statuses}
    assert by_name["ok.txt"]["status"] == FileProcessingStatus.PROCESSED.value
    assert by_name["bad.txt"]["status"] == FileProcessingStatus.FAILED.value


def test_retry_reprocesses_only_failed_or_pending(
    client, db_session, teacher_auth_headers, mock_blob_service, monkeypatch
):
    create_res = client.post(
        "/courses",
        json={"title": "Extraction Course 2", "description": "desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("ok.txt", b"a" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("bad.txt", b"b" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )

    monkeypatch.setattr(
        "app.modules.document_extraction.service.blob_service", mock_blob_service
    )
    mock_blob_service.download_file.return_value = b"x" * 200

    outcomes: dict[str, bool] = {"ok.txt": True, "bad.txt": False}
    called: list[str] = []

    class DummyExtractor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def extract(self, *, text: str, source_filename: str | None = None):
            assert source_filename is not None
            called.append(source_filename)
            if outcomes.get(source_filename, False):
                return _ok_result(filename=source_filename)
            return _fail_result(filename=source_filename, msg="boom")

    monkeypatch.setattr(
        "app.modules.document_extraction.service.DocumentLLMExtractor", DummyExtractor
    )

    DocumentExtractionService(db=db_session, neo4j_session=None).run_course_extraction(
        course_id=course_id, teacher_id=1
    )
    assert set(called) == {"ok.txt", "bad.txt"}

    # Flip the failed file to success and retry; only bad.txt should be processed.
    outcomes["bad.txt"] = True
    called.clear()
    DocumentExtractionService(db=db_session, neo4j_session=None).run_course_extraction(
        course_id=course_id, teacher_id=1
    )
    assert called == ["bad.txt"]

    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "finished"

    statuses = client.get(
        f"/courses/{course_id}/presentations/status", headers=teacher_auth_headers
    ).json()
    by_name = {f["filename"]: f for f in statuses}
    assert by_name["ok.txt"]["status"] == FileProcessingStatus.PROCESSED.value
    assert by_name["bad.txt"]["status"] == FileProcessingStatus.PROCESSED.value


def test_upload_after_finished_flips_course_back_to_failed(
    client, db_session, teacher_auth_headers, mock_blob_service, monkeypatch
):
    create_res = client.post(
        "/courses",
        json={"title": "Extraction Course 3", "description": "desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("one.txt", b"a" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )

    monkeypatch.setattr(
        "app.modules.document_extraction.service.blob_service", mock_blob_service
    )
    mock_blob_service.download_file.return_value = b"x" * 200

    class DummyExtractor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def extract(self, *, text: str, source_filename: str | None = None):
            assert source_filename is not None
            return _ok_result(filename=source_filename)

    monkeypatch.setattr(
        "app.modules.document_extraction.service.DocumentLLMExtractor", DummyExtractor
    )

    DocumentExtractionService(db=db_session, neo4j_session=None).run_course_extraction(
        course_id=course_id, teacher_id=1
    )
    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "finished"

    # Uploading a new pending file should flip the course back to failed.
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("two.txt", b"b" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )
    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "failed"


def test_start_extraction_is_idempotent_when_all_files_processed(
    client, db_session, teacher_auth_headers, mock_blob_service, monkeypatch
):
    create_res = client.post(
        "/courses",
        json={"title": "Extraction Course 4", "description": "desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("one.txt", b"a" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )

    monkeypatch.setattr(
        "app.modules.document_extraction.service.blob_service", mock_blob_service
    )
    mock_blob_service.download_file.return_value = b"x" * 200

    class DummyExtractor:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def extract(self, *, text: str, source_filename: str | None = None):
            assert source_filename is not None
            return _ok_result(filename=source_filename)

    monkeypatch.setattr(
        "app.modules.document_extraction.service.DocumentLLMExtractor", DummyExtractor
    )

    # First run processes the file and marks the course finished.
    DocumentExtractionService(db=db_session, neo4j_session=None).run_course_extraction(
        course_id=course_id, teacher_id=1
    )
    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "finished"

    # Starting extraction again should be a no-op and immediately return finished.
    res = client.post(f"/courses/{course_id}/extract", headers=teacher_auth_headers)
    assert res.status_code == 202
    assert res.json()["status"] == "finished"


def test_background_extraction_dispatches_pending_files_with_bounded_concurrency(
    client, db_session, teacher_auth_headers, mock_blob_service, monkeypatch
):
    # Create course
    create_res = client.post(
        "/courses",
        json={"title": "Background Concurrent", "description": "desc"},
        headers=teacher_auth_headers,
    )
    course_id = create_res.json()["id"]

    # Upload two pending text files.
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("one.txt", b"a" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )
    client.post(
        f"/courses/{course_id}/presentations",
        files={"files": ("two.txt", b"b" * 200, "text/plain")},
        headers=teacher_auth_headers,
    )

    # Ensure the background path uses the mocked blob service too.
    monkeypatch.setattr(
        "app.modules.document_extraction.service.blob_service", mock_blob_service
    )
    # Ensure Neo4j is disabled for this unit test.
    monkeypatch.setattr(
        "app.modules.document_extraction.service.create_neo4j_driver", lambda: None
    )

    # Make SessionLocal in the module use the same engine as the test DB.
    # We keep it as a sessionmaker so each call returns a fresh session.
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    monkeypatch.setattr(
        "app.modules.document_extraction.service.SessionLocal", TestingSessionLocal
    )

    # Capture that we bound concurrency to 4 and that we dispatch both files.
    observed_max_workers: list[int] = []
    dispatched_file_ids: list[int] = []

    def dummy_process_file(
        *,
        course_id: int,
        teacher_id: int,
        course_file_id: int,
        filename: str,
        blob_path: str,
        neo4j_driver,
    ) -> None:
        _ = (course_id, teacher_id, filename, blob_path, neo4j_driver)
        dispatched_file_ids.append(course_file_id)
        with TestingSessionLocal() as db:
            CourseRepository(db).update_course_file_status(
                course_file_id,
                FileProcessingStatus.PROCESSED,
                processed_at=datetime.now(UTC),
                last_error=None,
            )

    class DummyExecutor:
        def __init__(self, *, max_workers: int):
            observed_max_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, /, **kwargs):
            fut: Future[None] = Future()
            try:
                fn(**kwargs)
                fut.set_result(None)
            except Exception as e:
                fut.set_exception(e)
            return fut

    monkeypatch.setattr(
        "app.modules.document_extraction.service._process_course_file_background",
        dummy_process_file,
    )
    monkeypatch.setattr(
        "app.modules.document_extraction.service.ThreadPoolExecutor", DummyExecutor
    )

    # Run the actual background entrypoint (synchronously in the test).
    run_course_extraction_background(course_id=course_id, teacher_id=1)

    # Assert we bounded concurrency to 4.
    assert observed_max_workers == [4]

    # Assert both pending files were dispatched.
    statuses = client.get(
        f"/courses/{course_id}/presentations/status", headers=teacher_auth_headers
    ).json()
    assert len(statuses) == 2
    assert set(dispatched_file_ids) == {f["id"] for f in statuses}

    by_name = {f["filename"]: f for f in statuses}
    assert by_name["one.txt"]["status"] == FileProcessingStatus.PROCESSED.value
    assert by_name["two.txt"]["status"] == FileProcessingStatus.PROCESSED.value

    course = client.get(f"/courses/{course_id}", headers=teacher_auth_headers).json()
    assert course["extraction_status"] == "finished"
