import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.student_learning_path import routes


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
