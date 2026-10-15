import asyncio
from datetime import UTC, datetime
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.courses.materials_readiness_service import MaterialsReadinessService
from app.modules.courses.models import (
    Course,
    CourseFile,
    ExtractionStatus,
    FileProcessingStatus,
)
from app.modules.courses.repository import CourseRepository
from app.modules.courses.service import CourseService


@pytest.fixture
def ready_uploaded_course(client, db_session, teacher_auth_headers, mock_blob_service):
    created = client.post(
        "/courses",
        headers=teacher_auth_headers,
        json={"title": "Upload readiness"},
    )
    assert created.status_code == 201
    course_id = created.json()["id"]
    uploaded = client.post(
        f"/courses/{course_id}/presentations",
        headers=teacher_auth_headers,
        files={"files": ("lecture.txt", b"original material", "text/plain")},
    )
    assert uploaded.status_code == 201
    course = db_session.get(Course, course_id)
    file = db_session.scalar(
        select(CourseFile).where(CourseFile.course_id == course_id)
    )
    course.extraction_status = ExtractionStatus.FINISHED
    file.status = FileProcessingStatus.PROCESSED
    file.processed_at = datetime.now(UTC)
    db_session.commit()
    return course, file


@pytest.mark.parametrize("filename", ["another-lecture.txt", "lecture.txt"])
def test_upload_blocks_agents_before_blob_write_and_queues_new_content(
    client,
    db_session,
    teacher_auth_headers,
    mock_blob_service,
    ready_uploaded_course,
    filename,
):
    course, original = ready_uploaded_course
    course_id, teacher_id = course.id, course.teacher_id
    during_upload = []

    async def delayed_upload(content, destination_path):
        # A separate SQL session observes the boundary during the external write.
        with SessionLocal() as db:
            repository = CourseRepository(db)
            readiness = MaterialsReadinessService(repository).get_readiness(
                course_id, teacher_id
            )
            stored_file = repository.get_course_file_by_blob_path(
                course_id, destination_path
            )
            during_upload.append(
                (readiness, stored_file.status if stored_file is not None else None)
            )
        return "http://mock-url/updated.txt"

    mock_blob_service.upload_bytes.side_effect = delayed_upload
    response = client.post(
        f"/courses/{course_id}/presentations",
        headers=teacher_auth_headers,
        files={"files": (filename, b"new material", "text/plain")},
    )

    assert response.status_code == 201
    readiness, file_status = during_upload[0]
    assert readiness.ready is False
    assert readiness.status == "processing"
    assert file_status == FileProcessingStatus.PROCESSING
    db_session.expire_all()
    uploaded_file = db_session.scalar(
        select(CourseFile).where(
            CourseFile.course_id == course_id, CourseFile.filename == filename
        )
    )
    assert uploaded_file.status == FileProcessingStatus.PENDING
    assert uploaded_file.processed_at is None
    after = client.get(
        f"/courses/{course_id}/materials-readiness", headers=teacher_auth_headers
    )
    assert after.json()["ready"] is False
    assert after.json()["status"] == "processing"


def test_failed_new_upload_is_visible_and_can_be_retried(
    client,
    db_session,
    teacher_auth_headers,
    mock_blob_service,
    ready_uploaded_course,
):
    course, _ = ready_uploaded_course
    mock_blob_service.upload_bytes.side_effect = RuntimeError("Blob unavailable")
    url = f"/courses/{course.id}/presentations"
    files = {"files": ("retry.txt", b"new material", "text/plain")}

    failed = client.post(url, headers=teacher_auth_headers, files=files)

    assert failed.status_code == 500
    db_session.expire_all()
    failed_file = db_session.scalar(
        select(CourseFile).where(
            CourseFile.course_id == course.id, CourseFile.filename == "retry.txt"
        )
    )
    assert failed_file is not None
    assert failed_file.status == FileProcessingStatus.FAILED
    assert failed_file.content_hash is None
    assert "Blob unavailable" in failed_file.last_error

    mock_blob_service.upload_bytes.side_effect = None
    retried = client.post(url, headers=teacher_auth_headers, files=files)

    assert retried.status_code == 201
    db_session.expire_all()
    assert failed_file.status == FileProcessingStatus.PENDING
    assert failed_file.last_error is None


def test_failed_replacement_keeps_original_processed_material(
    client,
    db_session,
    teacher_auth_headers,
    mock_blob_service,
    ready_uploaded_course,
):
    course, original = ready_uploaded_course
    course_id, teacher_id = course.id, course.teacher_id
    old_hash, old_processed_at = original.content_hash, original.processed_at
    during_upload = []

    async def failed_upload(content, destination_path):
        with SessionLocal() as db:
            during_upload.append(
                MaterialsReadinessService(CourseRepository(db)).get_readiness(
                    course_id, teacher_id
                )
            )
        raise RuntimeError("Replacement upload failed")

    mock_blob_service.upload_bytes.side_effect = failed_upload
    response = client.post(
        f"/courses/{course_id}/presentations",
        headers=teacher_auth_headers,
        files={"files": ("lecture.txt", b"new material", "text/plain")},
    )

    assert response.status_code == 500
    assert during_upload[0].ready is False
    db_session.expire_all()
    assert original.content_hash == old_hash
    assert original.status == FileProcessingStatus.PROCESSED
    assert original.processed_at == old_processed_at
    assert course.extraction_status == ExtractionStatus.FINISHED
    assert (
        client.get(
            f"/courses/{course_id}/materials-readiness", headers=teacher_auth_headers
        ).json()["ready"]
        is True
    )


@pytest.mark.anyio
@pytest.mark.parametrize("filename", ["cancelled.txt", "lecture.txt"])
async def test_cancelled_upload_does_not_leave_processing_materials(
    db_session, mock_blob_service, ready_uploaded_course, filename
):
    course, original = ready_uploaded_course
    previous_hash = original.content_hash
    mock_blob_service.upload_bytes.side_effect = asyncio.CancelledError()
    service = CourseService(CourseRepository(db_session), None, None)
    teacher = db_session.get(User, course.teacher_id)

    with pytest.raises(asyncio.CancelledError):
        await service.upload_presentations(
            course.id,
            [UploadFile(file=BytesIO(b"new material"), filename=filename)],
            teacher,
        )

    db_session.expire_all()
    file = db_session.scalar(
        select(CourseFile).where(
            CourseFile.course_id == course.id, CourseFile.filename == filename
        )
    )
    if filename == "lecture.txt":
        assert file.status == FileProcessingStatus.PROCESSED
        assert file.content_hash == previous_hash
    else:
        assert file.status == FileProcessingStatus.FAILED
        assert file.content_hash is None
