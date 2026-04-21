"""Tests for TeacherDigitalTwinService (business logic layer)."""

from unittest.mock import MagicMock

import pytest

from app.modules.teacher_digital_twin.service import TeacherDigitalTwinService


def _driver_with_session(rows=None):
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter(rows or []))
    run_result.single.return_value = None
    session.run.return_value = run_result
    return driver, session


class TestGetSkillDifficulty:
    def test_returns_response_when_empty(self):
        driver, session = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_difficulty(course_id=1)
        assert result.course_id == 1
        assert result.skills == []

    def test_maps_rows(self):
        rows = [
            {
                "skill_name": "calculus",
                "student_count": 5,
                "avg_mastery": 0.6,
                "perceived_difficulty": 0.4,
            }
        ]
        driver, session = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_difficulty(course_id=1)
        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "calculus"


class TestGetSkillPopularity:
    def test_returns_response_when_empty(self):
        driver, session = _driver_with_session([])
        # get_total_students call returns 0
        session.run.return_value.single.return_value = {"total_students": 0}
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_popularity(course_id=1)
        assert result.course_id == 1
        assert result.all_skills == []

    def test_ranks_skills(self):
        rows = [
            {"skill_name": "algebra", "selection_count": 10},
            {"skill_name": "calculus", "selection_count": 5},
        ]
        driver, _ = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_skill_popularity(course_id=1)
        names = [s.skill_name for s in result.all_skills]
        assert "algebra" in names


class TestGetClassMastery:
    def test_returns_empty_class(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_class_mastery(course_id=1)
        assert result.course_id == 1
        assert result.students == []
        assert result.total_students == 0

    def test_maps_student_rows(self):
        rows = [
            {
                "user_id": 42,
                "full_name": "Alice",
                "email": "alice@test.com",
                "selected_skill_count": 3,
                "avg_mastery": 0.7,
                "mastered_count": 2,
                "struggling_count": 0,
            }
        ]
        driver, _ = _driver_with_session(rows)
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_class_mastery(course_id=1)
        assert result.total_students == 1
        assert result.students[0].full_name == "Alice"


class TestGetStudentGroups:
    def test_empty_class(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.get_student_groups(course_id=1)
        assert result.course_id == 1
        assert result.total_groups == 0


class TestRunWhatIf:
    def test_automatic_mode(self):
        from app.modules.teacher_digital_twin.schemas import WhatIfRequest

        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        req = WhatIfRequest(mode="automatic", delta=0.2, top_k=3)
        result = svc.run_what_if(course_id=1, req=req)
        assert result.course_id == 1
        assert result.mode == "automatic"

    def test_manual_mode(self):
        from app.modules.teacher_digital_twin.schemas import WhatIfRequest, WhatIfSkill

        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        req = WhatIfRequest(
            mode="manual",
            skills=[WhatIfSkill(skill_name="algebra", hypothetical_mastery=0.9)],
        )
        result = svc.run_what_if(course_id=1, req=req)
        assert result.mode == "manual"


class TestSimulateSkill:
    def test_returns_response(self):
        driver, _ = _driver_with_session([])
        svc = TeacherDigitalTwinService(driver)
        result = svc.simulate_skill(
            course_id=1, skill_name="algebra", simulated_mastery=0.5
        )
        assert result.skill_name == "algebra"
        assert result.simulated_mastery == pytest.approx(0.5)


class TestGetStudentPortfolio:
    def test_teacher_without_class_permission(self):
        """Teacher who doesn't teach the class gets 403."""
        driver, session = _driver_with_session()
        session.run.return_value.single.return_value = {"teaches": False}
        svc = TeacherDigitalTwinService(driver)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            svc.get_student_portfolio(teacher_id=1, student_id=10, course_id=99)
        assert exc.value.status_code == 403
