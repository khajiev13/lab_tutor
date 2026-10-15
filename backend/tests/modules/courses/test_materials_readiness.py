from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.courses.models import (
    Course,
    CourseFile,
    ExtractionStatus,
    FileProcessingStatus,
)
from app.modules.curricularalignmentarchitect.models import (
    BookExtractionRun,
    BookSelectionSession,
    SessionStatus,
)
from app.modules.marketdemandanalyst.models import MDAThreadState


@pytest.fixture
def materials_course(db_session, teacher_auth_headers):
    teacher = db_session.scalar(select(User).where(User.email == "teacher@example.com"))
    course = Course(title="Materials readiness", teacher_id=teacher.id)
    db_session.add(course)
    db_session.commit()
    return course


def _set_materials(db_session, course, extraction_status, file_statuses):
    course.extraction_status = extraction_status
    for index, file_status in enumerate(file_statuses):
        db_session.add(
            CourseFile(
                course_id=course.id,
                filename=f"lecture-{index}.txt",
                blob_path=f"courses/{course.id}/lecture-{index}.txt",
                status=file_status,
            )
        )
    db_session.commit()


@pytest.mark.parametrize(
    ("extraction_status", "file_statuses", "expected_status", "processed_files"),
    [
        (ExtractionStatus.NOT_STARTED, [], "no_materials", 0),
        (ExtractionStatus.FINISHED, [], "no_materials", 0),
        (
            ExtractionStatus.FAILED,
            [FileProcessingStatus.PENDING],
            "processing",
            0,
        ),
        (
            ExtractionStatus.FINISHED,
            [FileProcessingStatus.PROCESSED, FileProcessingStatus.PENDING],
            "processing",
            1,
        ),
        (
            ExtractionStatus.IN_PROGRESS,
            [FileProcessingStatus.PROCESSED, FileProcessingStatus.PROCESSING],
            "processing",
            1,
        ),
        (
            ExtractionStatus.IN_PROGRESS,
            [FileProcessingStatus.PROCESSED],
            "processing",
            1,
        ),
        (
            ExtractionStatus.FINISHED,
            [FileProcessingStatus.FAILED],
            "failed",
            0,
        ),
        (
            ExtractionStatus.FAILED,
            [FileProcessingStatus.PROCESSED],
            "failed",
            1,
        ),
        (
            ExtractionStatus.FINISHED,
            [FileProcessingStatus.PROCESSED, FileProcessingStatus.PROCESSED],
            "ready",
            2,
        ),
    ],
)
def test_materials_readiness_uses_current_stored_file_outcomes(
    client,
    db_session,
    materials_course,
    teacher_auth_headers,
    extraction_status,
    file_statuses,
    expected_status,
    processed_files,
):
    _set_materials(db_session, materials_course, extraction_status, file_statuses)

    response = client.get(
        f"/courses/{materials_course.id}/materials-readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 200
    result = response.json()
    assert result["ready"] is (expected_status == "ready")
    assert result["status"] == expected_status
    assert result["total_files"] == len(file_statuses)
    assert result["processed_files"] == processed_files
    assert result["message"]
    db_session.expire_all()
    assert materials_course.extraction_status == extraction_status
    assert [
        file.status
        for file in db_session.scalars(
            select(CourseFile)
            .where(CourseFile.course_id == materials_course.id)
            .order_by(CourseFile.id)
        )
    ] == file_statuses


def test_materials_readiness_does_not_disclose_another_teachers_course(
    client, db_session, materials_course, teacher_auth_headers
):
    other_teacher = User(
        email="other-teacher@example.com",
        hashed_password="unused",
        role="teacher",
        first_name="Other",
        last_name="Teacher",
    )
    db_session.add(other_teacher)
    db_session.flush()
    materials_course.teacher_id = other_teacher.id
    db_session.commit()

    response = client.get(
        f"/courses/{materials_course.id}/materials-readiness",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 404


def test_materials_readiness_requires_a_teacher(
    client, materials_course, student_auth_headers
):
    response = client.get(
        f"/courses/{materials_course.id}/materials-readiness",
        headers=student_auth_headers,
    )

    assert response.status_code == 403


def test_market_agent_waits_for_every_file_and_final_extraction_state(
    client, db_session, materials_course, teacher_auth_headers, monkeypatch
):
    from app.modules.marketdemandanalyst import routes

    async def stream(*args, **kwargs):
        for item in []:
            yield item

    graph = MagicMock()
    graph.astream = stream
    graph.aget_state = AsyncMock(
        return_value=SimpleNamespace(values={}, next=(), tasks=())
    )
    monkeypatch.setattr(routes, "get_graph", AsyncMock(return_value=(graph, None)))
    _set_materials(
        db_session,
        materials_course,
        ExtractionStatus.FINISHED,
        [FileProcessingStatus.PROCESSED, FileProcessingStatus.PENDING],
    )
    url = f"/courses/{materials_course.id}/market-demand/chat"

    blocked = client.post(
        url, headers=teacher_auth_headers, json={"message": "Analyze"}
    )

    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "materials_not_ready"
    assert db_session.scalar(select(MDAThreadState)) is None

    pending = db_session.scalar(
        select(CourseFile).where(CourseFile.status == FileProcessingStatus.PENDING)
    )
    pending.status = FileProcessingStatus.PROCESSED
    materials_course.extraction_status = ExtractionStatus.IN_PROGRESS
    db_session.commit()
    still_blocked = client.post(
        url, headers=teacher_auth_headers, json={"message": "Analyze"}
    )
    assert still_blocked.status_code == 409
    assert db_session.scalar(select(MDAThreadState)) is None

    materials_course.extraction_status = ExtractionStatus.FINISHED
    db_session.commit()
    allowed = client.post(
        url, headers=teacher_auth_headers, json={"message": "Analyze"}
    )

    assert allowed.status_code == 200
    assert "event: stream_end" in allowed.text
    assert db_session.scalar(select(MDAThreadState)) is not None


@pytest.mark.parametrize(
    ("method", "path", "extra"),
    [
        ("POST", "skill-review/selection-confirmation", {}),
        ("POST", "skill-review/continue-with-available-evidence", {}),
        ("POST", "skill-review/withdrawal-review", {}),
        (
            "POST",
            "integration-approval",
            {"review_digest": "a" * 64, "approved_candidate_ids": []},
        ),
    ],
)
def test_market_workflow_writes_require_ready_materials(
    client, materials_course, teacher_auth_headers, method, path, extra
):
    response = client.request(
        method,
        f"/courses/{materials_course.id}/market-demand/{path}",
        headers=teacher_auth_headers,
        json={
            "run_id": "00000000-0000-0000-0000-000000000001",
            "expected_candidate_revision": 0,
            "expected_selection_revision": 0,
            **extra,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"


def test_chapter_plan_generation_waits_for_materials(
    client, materials_course, teacher_auth_headers
):
    response = client.post(
        f"/courses/{materials_course.id}/chapter-plan/generate",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_normalization_stream_requires_ready_materials(
    client, materials_course, teacher_auth_headers, method
):
    response = client.request(
        method,
        "/normalization/stream",
        params={"course_id": materials_course.id},
        headers=teacher_auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"


def test_book_analysis_does_not_create_a_run_before_materials_are_ready(
    client, db_session, materials_course, teacher_auth_headers, monkeypatch
):
    from app.modules.curricularalignmentarchitect.chunking_analysis import workflow

    monkeypatch.setattr(workflow, "_run_workflow", lambda *_: None)
    response = client.post(
        f"/book-selection/courses/{materials_course.id}/analysis",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"
    assert db_session.scalar(select(BookExtractionRun)) is None


@pytest.mark.parametrize(
    "path",
    [
        "analysis/1/agentic",
        "analysis/1/approve-extraction",
        "analysis/1/chapter-scoring",
        "analysis/1/books/1/recommendations",
        "book-skill-mapping",
        "skill-prerequisites/build",
        "skill-prerequisites/regenerate",
    ],
)
def test_curriculum_agent_launches_cannot_bypass_materials_readiness(
    client, materials_course, teacher_auth_headers, monkeypatch, path
):
    from app.modules.curricularalignmentarchitect.api_routes import (
        book_skill_mapping,
        skill_prerequisites,
    )

    async def finish_stream(course_id, queue):
        await queue.put(None)

    monkeypatch.setattr(book_skill_mapping, "_run_mapping_background", finish_stream)
    monkeypatch.setattr(skill_prerequisites, "_run_background", finish_stream)
    monkeypatch.setattr(
        skill_prerequisites, "schedule_skill_prerequisite_rebuild", lambda *_: None
    )
    response = client.post(
        f"/book-selection/courses/{materials_course.id}/{path}",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"


def test_saved_market_evidence_and_draft_edits_remain_available_when_materials_change(
    client, db_session, teacher_auth_headers
):
    from tests.market_skill_fixtures import seed_review

    course, run, candidates, _, _ = seed_review(
        db_session, client, teacher_auth_headers
    )
    db_session.add(
        CourseFile(
            course_id=course["id"],
            filename="new-lecture.txt",
            blob_path=f"courses/{course['id']}/new-lecture.txt",
            status=FileProcessingStatus.PENDING,
        )
    )
    db_session.commit()
    response = client.get(
        f"/courses/{course['id']}/market-demand/skill-review",
        headers=teacher_auth_headers,
    )
    assert response.status_code == 200
    review = response.json()
    assert review["candidates"][0]["display_name"] == "Python"

    edited = client.put(
        f"/courses/{course['id']}/market-demand/skill-review/draft",
        headers=teacher_auth_headers,
        json={
            "run_id": str(run.id),
            "expected_candidate_revision": review["candidate_revision"],
            "expected_selection_revision": review["selection_revision"],
            "selected_candidate_ids": [],
            "excluded_candidate_ids": [candidates[0]["candidate_id"]],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["excluded_candidate_ids"] == [candidates[0]["candidate_id"]]


@pytest.mark.parametrize("action", ["run", "resume", "rediscover"])
def test_book_discovery_sessions_cannot_bypass_materials_readiness(
    client, db_session, materials_course, teacher_auth_headers, monkeypatch, action
):
    from app.modules.curricularalignmentarchitect.service import BookSelectionService

    for method in ("run_discovery_and_scoring", "resume_scoring", "rediscover_books"):
        monkeypatch.setattr(BookSelectionService, method, AsyncMock())
    session = BookSelectionSession(
        course_id=materials_course.id,
        thread_id="materials-session",
        status=SessionStatus.AWAITING_REVIEW,
    )
    db_session.add(session)
    db_session.commit()

    response = client.post(
        f"/book-selection/sessions/{session.id}/{action}",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "materials_not_ready"
