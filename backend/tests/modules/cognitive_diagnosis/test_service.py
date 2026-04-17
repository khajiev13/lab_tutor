"""Tests for CognitiveDiagnosisService (business logic layer)."""

from unittest.mock import MagicMock

import pytest

from app.modules.cognitive_diagnosis.service import CognitiveDiagnosisService


def _driver_with_session(rows: list[dict] | None = None):
    """Return a mocked Neo4j driver whose session.run() yields `rows`."""
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    if rows is None:
        rows = []

    # Create a mock result that iterates like a list but also supports .consume()
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter(rows))
    run_result.single.return_value = rows[0] if rows else None
    run_result.consume.return_value = MagicMock()

    session.run.return_value = run_result
    return driver, session


class TestGetMastery:
    def test_returns_mastery_response(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.get_mastery(user_id=1, course_id=10)
        assert result.user_id == 1
        assert result.skills == []

    def test_maps_rows_to_skill_mastery(self):
        rows = [
            {
                "skill_name": "algebra",
                "mastery": 0.75,
                "decay": 0.9,
                "status": "at",
                "attempt_count": 3,
                "correct_count": 2,
                "last_practice_ts": None,
                "model_version": "arcd_v2",
            }
        ]
        driver, session = _driver_with_session(rows)
        svc = CognitiveDiagnosisService(driver)
        result = svc.get_mastery(user_id=1, course_id=10)
        assert len(result.skills) == 1
        assert result.skills[0].skill_name == "algebra"
        assert result.skills[0].mastery == pytest.approx(0.75)


class TestGeneratePath:
    def test_returns_path_response(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.generate_path(user_id=1, course_id=10, path_length=5)
        assert result.user_id == 1
        assert isinstance(result.steps, list)

    def test_path_length_respected(self):
        # When no skills are selected the path is empty
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.generate_path(user_id=1, course_id=10, path_length=3)
        assert result.path_length <= 3


class TestReviewSession:
    def test_returns_review_response(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.review_session(user_id=1, course_id=10, top_k=5)
        assert result.user_id == 1
        assert isinstance(result.pco_skills, list)


class TestGetPortfolio:
    def test_returns_portfolio_response(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.get_portfolio(user_id=1, course_id=10)
        assert result.user_id == 1


class TestLogInteraction:
    def test_calls_through(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        # Should not raise even with no matching Neo4j nodes
        svc.log_interaction(
            user_id=1,
            question_id="q1",
            is_correct=True,
            recompute_mastery=False,
        )

    def test_with_recompute_mastery(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        svc.log_interaction(
            user_id=1,
            question_id="q2",
            is_correct=False,
            recompute_mastery=True,
        )


class TestLogEngagement:
    def test_reading(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        svc.log_engagement(
            user_id=1,
            resource_id="r1",
            resource_type="reading",
            progress=0.5,
        )

    def test_video(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        svc.log_engagement(
            user_id=1,
            resource_id="v1",
            resource_type="video",
            progress=1.0,
        )


class TestStudentEvents:
    def test_create_event(self):
        driver, session = _driver_with_session()
        run_result = MagicMock()
        run_result.single.return_value = {
            "id": "evt-abc",
            "user_id": 1,
            "date": "2026-01-01",
            "title": "Study session",
            "event_type": "study",
            "duration_minutes": 60,
            "notes": "",
            "created_at_ts": 1000,
        }
        session.run.return_value = run_result

        from app.modules.cognitive_diagnosis.schemas import StudentEventCreate

        ev = StudentEventCreate(
            date="2026-01-01",
            title="Study session",
            event_type="study",
            duration_minutes=60,
        )
        svc = CognitiveDiagnosisService(driver)
        result = svc.create_student_event(user_id=1, event=ev)
        assert result["user_id"] == 1

    def test_get_events_empty(self):
        driver, session = _driver_with_session([])
        svc = CognitiveDiagnosisService(driver)
        result = svc.get_student_events(user_id=1)
        assert result == []

    def test_delete_event_not_found(self):
        driver, session = _driver_with_session()
        run_result = MagicMock()
        run_result.single.return_value = {"deleted_count": 0}
        session.run.return_value = run_result
        svc = CognitiveDiagnosisService(driver)
        result = svc.delete_student_event(user_id=1, event_id="nope")
        assert result is False
