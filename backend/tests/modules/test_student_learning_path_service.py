import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.student_learning_path import neo4j_repository
from app.modules.student_learning_path.schemas import BuildSelectedSkillRequest
from app.modules.student_learning_path.service import StudentLearningPathService


def _build_service(monkeypatch):
    driver = MagicMock()
    service = StudentLearningPathService(MagicMock(), driver)
    monkeypatch.setattr(
        service,
        "_validate_enrollment",
        lambda *_args, **_kwargs: None,
    )
    return service


def _stub_background_task(monkeypatch):
    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    return scheduled


def test_build_learning_path_persists_first_time_selected_skills(monkeypatch):
    service = _build_service(monkeypatch)
    scheduled = _stub_background_task(monkeypatch)
    select_calls: list[tuple[list[str], str]] = []

    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(
            side_effect=[
                [],
                [{"name": "Batch Processing", "source": "book"}],
            ]
        ),
    )
    monkeypatch.setattr(
        neo4j_repository,
        "select_skills",
        lambda _session, _student_id, _course_id, skill_names, source: (
            select_calls.append((skill_names, source)) or len(skill_names)
        ),
    )

    run_id, queue = asyncio.run(
        service.build_learning_path(
            11,
            2,
            [
                BuildSelectedSkillRequest(name="Batch Processing", source="book"),
                BuildSelectedSkillRequest(name="Kafka", source="market"),
                BuildSelectedSkillRequest(name="Kafka", source="market"),
            ],
        )
    )

    assert run_id
    assert queue is not None
    assert select_calls == [
        (["Batch Processing"], "book"),
        (["Kafka"], "market"),
    ]
    assert len(scheduled) == 1


def test_build_learning_path_reuses_locked_selection_without_rewriting(monkeypatch):
    service = _build_service(monkeypatch)
    scheduled = _stub_background_task(monkeypatch)
    select_skills = MagicMock()

    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[{"name": "Persisted Skill", "source": "book"}]]),
    )
    monkeypatch.setattr(neo4j_repository, "select_skills", select_skills)

    run_id, queue = asyncio.run(
        service.build_learning_path(
            11,
            2,
            [BuildSelectedSkillRequest(name="Kafka", source="market")],
        )
    )

    assert run_id
    assert queue is not None
    select_skills.assert_not_called()
    assert len(scheduled) == 1


def test_build_learning_path_requires_selection_for_first_time_build(monkeypatch):
    service = _build_service(monkeypatch)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(service.build_learning_path(11, 2, []))

    assert str(exc_info.value) == "Select at least one skill before building"


def test_validate_enrollment_uses_course_id_then_student_id():
    service = StudentLearningPathService(MagicMock(), MagicMock())
    service._course_repo = MagicMock()
    service._course_repo.get_enrollment.return_value = object()

    service._validate_enrollment(4, 2)

    service._course_repo.get_enrollment.assert_called_once_with(2, 4)


def test_validate_enrollment_raises_403_when_student_is_not_enrolled(caplog):
    service = StudentLearningPathService(MagicMock(), MagicMock())
    service._course_repo = MagicMock()
    service._course_repo.get_enrollment.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        service._validate_enrollment(4, 2)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Student is not enrolled in this course"
    assert "student_id=4 course_id=2" in caplog.text
