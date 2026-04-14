import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status

from app.modules.student_learning_path import neo4j_repository
from app.modules.student_learning_path.schemas import BuildSelectedSkillRequest
from app.modules.student_learning_path.service import StudentLearningPathService


def _build_service(
    monkeypatch,
    *,
    min_skills: int = 20,
    max_skills: int = 35,
    is_default: bool = True,
):
    driver = MagicMock()
    service = StudentLearningPathService(MagicMock(), driver)
    monkeypatch.setattr(
        service,
        "_validate_enrollment",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.modules.student_learning_path.service.CourseGraphRepository",
        lambda session: SimpleNamespace(
            get_skill_selection_range=lambda *, course_id: {
                "min_skills": min_skills,
                "max_skills": max_skills,
                "is_default": is_default,
            }
        ),
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

    market_skills = [f"Kafka {index}" for index in range(1, 20)]
    requested_skills = [
        BuildSelectedSkillRequest(name="Batch Processing", source="book"),
        *[
            BuildSelectedSkillRequest(name=skill_name, source="market")
            for skill_name in market_skills
        ],
        BuildSelectedSkillRequest(name=market_skills[0], source="market"),
    ]

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
            requested_skills,
        )
    )

    assert run_id
    assert queue is not None
    assert select_calls == [
        (["Batch Processing"], "book"),
        (market_skills, "market"),
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


def test_build_learning_path_rejects_first_time_build_below_course_minimum(monkeypatch):
    service = _build_service(monkeypatch, min_skills=2, max_skills=4, is_default=False)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            service.build_learning_path(
                11,
                2,
                [BuildSelectedSkillRequest(name="Batch Processing", source="book")],
            )
        )

    assert str(exc_info.value) == "Select between 2 and 4 skills before building"


def test_build_learning_path_rejects_first_time_build_above_course_maximum(monkeypatch):
    service = _build_service(monkeypatch, min_skills=1, max_skills=2, is_default=False)
    monkeypatch.setattr(
        neo4j_repository,
        "get_selected_skills",
        MagicMock(side_effect=[[]]),
    )

    with pytest.raises(ValueError) as exc_info:
        asyncio.run(
            service.build_learning_path(
                11,
                2,
                [
                    BuildSelectedSkillRequest(name="Batch Processing", source="book"),
                    BuildSelectedSkillRequest(name="Kafka", source="market"),
                    BuildSelectedSkillRequest(name="SQL", source="market"),
                ],
            )
        )

    assert str(exc_info.value) == "Select between 1 and 2 skills before building"


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
