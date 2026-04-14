from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.modules.courses.curriculum_schemas import SkillSelectionRangeUpdate
from app.modules.courses.curriculum_service import CurriculumService


def _build_service(*, owner_id: int = 7) -> CurriculumService:
    repo = MagicMock()
    repo.get_by_id.return_value = SimpleNamespace(id=2, teacher_id=owner_id)
    service = CurriculumService(repo, MagicMock())
    service._graph_repo = MagicMock()
    service._course_graph_repo = MagicMock()
    service._graph_repo.get_teacher_transcripts.return_value = []
    service._graph_repo.get_book_skill_bank.return_value = []
    service._graph_repo.get_market_skill_bank.return_value = []
    return service


def test_get_skill_banks_includes_selection_range():
    service = _build_service()
    service._course_graph_repo.get_skill_selection_range.return_value = {
        "min_skills": 12,
        "max_skills": 24,
        "is_default": False,
    }

    result = service.get_skill_banks(
        course_id=2,
        teacher=SimpleNamespace(id=7),
    )

    assert result.selection_range.min_skills == 12
    assert result.selection_range.max_skills == 24
    assert result.selection_range.is_default is False


def test_update_skill_selection_range_requires_course_owner():
    service = _build_service(owner_id=9)

    with pytest.raises(HTTPException) as exc_info:
        service.update_skill_selection_range(
            teacher=SimpleNamespace(id=7),
            course_id=2,
            min_skills=10,
            max_skills=20,
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Not authorized to view this course curriculum"


def test_update_skill_selection_range_writes_and_returns_saved_range():
    service = _build_service()
    service._course_graph_repo.get_skill_selection_range.return_value = {
        "min_skills": 15,
        "max_skills": 25,
        "is_default": False,
    }

    result = service.update_skill_selection_range(
        teacher=SimpleNamespace(id=7),
        course_id=2,
        min_skills=15,
        max_skills=25,
    )

    service._course_graph_repo.set_skill_selection_range.assert_called_once_with(
        course_id=2,
        min_skills=15,
        max_skills=25,
    )
    assert result.min_skills == 15
    assert result.max_skills == 25
    assert result.is_default is False


def test_skill_selection_range_update_validates_bounds():
    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=30, max_skills=20)

    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=0, max_skills=20)

    with pytest.raises(ValidationError):
        SkillSelectionRangeUpdate(min_skills=10, max_skills=201)
