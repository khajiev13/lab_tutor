import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.student_learning_path import routes
from app.modules.student_learning_path.schemas import (
    QuizSubmitRequest,
    ResourceOpenRequest,
)


def _mock_driver_with_session():
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = False
    return driver, session


def test_skill_banks_route_returns_data_for_enrolled_student_with_mismatched_ids(
    monkeypatch,
):
    driver, session = _mock_driver_with_session()
    captured: dict[str, tuple[int, int]] = {}

    def fake_get_enrollment(self, course_id, student_id):
        captured["args"] = (course_id, student_id)
        return object()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        fake_get_enrollment,
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.neo4j_repository.get_student_skill_banks",
        lambda _session, _student_id, _course_id: {
            "book_skill_banks": [],
            "market_skill_bank": [],
            "selected_skill_names": [],
            "interested_posting_urls": [],
            "peer_selection_counts": {},
            "selection_range": {
                "min_skills": 20,
                "max_skills": 35,
                "is_default": True,
            },
            "prerequisite_edges": [],
        },
    )

    response = routes.get_skill_banks(
        course_id=1,
        student=SimpleNamespace(id=2),
        db=MagicMock(),
        driver=driver,
    )

    assert captured["args"] == (1, 2)
    assert response["selected_skill_names"] == []
    assert driver.session.called
    assert session is not None


def test_skill_banks_route_raises_403_for_unenrolled_student(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.get_skill_banks(
            course_id=1,
            student=SimpleNamespace(id=2),
            db=MagicMock(),
            driver=driver,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Student is not enrolled in this course"


def test_learning_path_route_returns_data_for_enrolled_student_with_mismatched_ids(
    monkeypatch,
):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.neo4j_repository.get_learning_path",
        lambda _session, _student_id, _course_id: {
            "course_id": 1,
            "course_title": "Path Course",
            "chapters": [],
            "total_selected_skills": 0,
            "skills_with_resources": 0,
        },
    )

    response = routes.get_learning_path(
        course_id=1,
        student=SimpleNamespace(id=2),
        db=MagicMock(),
        driver=driver,
    )

    assert response["course_id"] == 1


def test_build_route_returns_202_for_enrolled_student_with_mismatched_ids(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.neo4j_repository.get_selected_skills",
        lambda _session, _student_id, _course_id: [
            {"name": "Persisted Skill", "source": "book"}
        ],
    )

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    response = asyncio.run(
        routes.build_learning_path(
            course_id=1,
            student=SimpleNamespace(id=2),
            db=MagicMock(),
            driver=driver,
            body=None,
        )
    )

    assert response["status"] == "started"
    assert len(scheduled) == 1


def test_get_chapter_quiz_route_returns_quiz_for_enrolled_student(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.StudentLearningPathService.get_chapter_quiz",
        lambda self, student_id, course_id, chapter_index: {
            "course_id": course_id,
            "chapter_index": chapter_index,
            "chapter_title": "Foundations",
            "questions": [
                {
                    "id": "q-1",
                    "skill_name": "Batch Processing",
                    "text": "Q1",
                    "options": ["A", "B", "C", "D"],
                }
            ],
            "previous_answers": {},
        },
    )

    response = routes.get_chapter_quiz(
        course_id=1,
        chapter_index=1,
        student=SimpleNamespace(id=2),
        db=MagicMock(),
        driver=driver,
    )

    assert response["chapter_title"] == "Foundations"


def test_get_chapter_quiz_route_returns_400_for_locked_chapter(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.StudentLearningPathService.get_chapter_quiz",
        lambda self, student_id, course_id, chapter_index: (_ for _ in ()).throw(
            ValueError("Chapter quiz is locked")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.get_chapter_quiz(
            course_id=1,
            chapter_index=2,
            student=SimpleNamespace(id=2),
            db=MagicMock(),
            driver=driver,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_submit_chapter_quiz_route_returns_404_when_quiz_missing(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.StudentLearningPathService.submit_chapter_quiz",
        lambda self, student_id, course_id, chapter_index, payload: (
            _ for _ in ()
        ).throw(
            HTTPException(status.HTTP_404_NOT_FOUND, detail="Chapter quiz not found")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.submit_chapter_quiz(
            course_id=1,
            chapter_index=1,
            body=QuizSubmitRequest(
                answers=[{"question_id": "q-1", "selected_option": "A"}]
            ),
            student=SimpleNamespace(id=2),
            db=MagicMock(),
            driver=driver,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


def test_record_resource_open_route_returns_204_and_delegates(monkeypatch):
    driver, _ = _mock_driver_with_session()
    called = {}

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )

    def fake_record_resource_open(self, student_id, course_id, payload):
        called["args"] = (student_id, course_id, payload)

    monkeypatch.setattr(
        "app.modules.student_learning_path.service.StudentLearningPathService.record_resource_open",
        fake_record_resource_open,
    )

    response = routes.record_resource_open(
        course_id=1,
        body=ResourceOpenRequest(
            resource_type="reading",
            url="https://example.com/reading",
        ),
        student=SimpleNamespace(id=2),
        db=MagicMock(),
        driver=driver,
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert called["args"][0] == 2
    assert called["args"][1] == 1
    assert str(called["args"][2].url) == "https://example.com/reading"


def test_submit_chapter_quiz_route_returns_results(monkeypatch):
    driver, _ = _mock_driver_with_session()

    monkeypatch.setattr(
        "app.modules.courses.repository.CourseRepository.get_enrollment",
        lambda self, course_id, student_id: object(),
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.StudentLearningPathService.submit_chapter_quiz",
        lambda self, student_id, course_id, chapter_index, payload: {
            "chapter_index": chapter_index,
            "results": [
                {
                    "question_id": "q-1",
                    "skill_name": "Batch Processing",
                    "selected_option": "A",
                    "answered_right": True,
                    "correct_option": "A",
                }
            ],
            "skills_known": ["Batch Processing"],
        },
    )

    response = routes.submit_chapter_quiz(
        course_id=1,
        chapter_index=1,
        body=QuizSubmitRequest(
            answers=[{"question_id": "q-1", "selected_option": "A"}]
        ),
        student=SimpleNamespace(id=2),
        db=MagicMock(),
        driver=driver,
    )

    assert response["skills_known"] == ["Batch Processing"]


def test_record_resource_open_endpoint_requires_student_role(
    client,
    teacher_auth_headers,
):
    response = client.post(
        "/student-learning-path/1/resources/open",
        headers=teacher_auth_headers,
        json={
            "resource_type": "reading",
            "url": "https://example.com/reading",
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
