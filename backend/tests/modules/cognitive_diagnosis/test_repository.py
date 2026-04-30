"""Tests for CognitiveDiagnosisRepository (Neo4j layer)."""

from unittest.mock import MagicMock

from app.modules.cognitive_diagnosis.repository import CognitiveDiagnosisRepository


def _make_repo():
    session = MagicMock()
    # run().consume() and run().__iter__() defaults
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter([]))
    run_result.single.return_value = None
    run_result.consume.return_value = None
    session.run.return_value = run_result
    return CognitiveDiagnosisRepository(session), session


class TestGetStudentMastery:
    def test_returns_empty_when_no_rows(self):
        repo, session = _make_repo()
        result = repo.get_student_mastery(user_id=1, course_id=10)
        assert result == []
        session.run.assert_called_once()

    def test_calls_course_query_when_course_id_given(self):
        repo, session = _make_repo()
        repo.get_student_mastery(user_id=42, course_id=7)
        call_args = session.run.call_args
        # First positional arg is the query string
        assert "course_id" in call_args[0][0] or "course_id" in str(call_args)

    def test_calls_generic_query_without_course(self):
        repo, session = _make_repo()
        repo.get_student_mastery(user_id=42)
        call_args = session.run.call_args
        assert "user_id" in str(call_args)


class TestUpsertMasteryBatch:
    def test_calls_run(self):
        repo, session = _make_repo()
        repo.upsert_mastery_batch(
            user_id=1,
            mastery_items=[{"skill_name": "algebra", "mastery": 0.8, "decay": 0.9}],
        )
        session.run.assert_called_once()


class TestGetAllSkillsWithConcepts:
    def test_empty_result(self):
        repo, session = _make_repo()
        result = repo.get_all_skills_with_concepts(course_id=1)
        assert result == []

    def test_row_returned(self):
        repo, session = _make_repo()
        row = {"skill_name": "calculus", "concepts": ["limits"], "chapter": "Ch1"}
        session.run.return_value = [row]
        result = repo.get_all_skills_with_concepts(course_id=1)
        assert len(result) == 1
        assert result[0]["skill_name"] == "calculus"


class TestGetStudentSelectedSkills:
    def test_returns_empty_when_student_has_no_selected_skills(self):
        repo, session = _make_repo()
        session.run.return_value.__iter__ = MagicMock(return_value=iter([]))
        result = repo.get_student_selected_skills(user_id=1, course_id=5)
        assert result == []

    def test_returns_selected_skills(self):
        repo, session = _make_repo()
        row = {"skill_name": "algebra", "concepts": [], "chapter": None}
        session.run.return_value = [row]
        result = repo.get_student_selected_skills(user_id=1, course_id=5)
        assert result[0]["skill_name"] == "algebra"


class TestStudentEventsMethods:
    def test_create_event_calls_run(self):
        repo, session = _make_repo()
        run_result = MagicMock()
        run_result.single.return_value = {
            "id": "evt-1",
            "user_id": 1,
            "date": "2026-01-01",
            "title": "Test",
            "event_type": "study",
            "duration_minutes": None,
            "notes": "",
            "created_at_ts": 1000,
        }
        session.run.return_value = run_result

        event = {
            "date": "2026-01-01",
            "title": "Test",
            "event_type": "study",
            "duration_minutes": None,
            "notes": "",
        }
        repo.create_student_event(user_id=1, event=event)
        session.run.assert_called_once()

    def test_get_events_empty(self):
        repo, session = _make_repo()
        result = repo.get_student_events(user_id=1)
        assert result == []

    def test_delete_event_not_found(self):
        repo, session = _make_repo()
        run_result = MagicMock()
        run_result.single.return_value = {"deleted_count": 0}
        session.run.return_value = run_result
        result = repo.delete_student_event(user_id=1, event_id="missing")
        assert result is False

    def test_delete_event_found(self):
        repo, session = _make_repo()
        run_result = MagicMock()
        run_result.single.return_value = {"deleted_count": 1}
        session.run.return_value = run_result
        result = repo.delete_student_event(user_id=1, event_id="evt-1")
        assert result is True


class TestCreateAnswered:
    def test_calls_run(self):
        repo, session = _make_repo()
        repo.create_answered(user_id=1, question_id="q-abc", answered_right=True)
        session.run.assert_called_once()

    def test_passes_selected_option(self):
        repo, session = _make_repo()
        repo.create_answered(
            user_id=1,
            question_id="q-xyz",
            answered_right=False,
            selected_option="C",
        )
        kwargs = session.run.call_args[1]
        assert kwargs["selected_option"] == "C"
        assert kwargs["answered_right"] is False


class TestUpsertOpenedResource:
    def test_video_resource(self):
        repo, session = _make_repo()
        repo.upsert_opened_resource(user_id=1, resource_id="v1", resource_type="video")
        session.run.assert_called_once()
        query_used = session.run.call_args[0][0]
        assert "VIDEO_RESOURCE" in query_used

    def test_reading_resource(self):
        repo, session = _make_repo()
        repo.upsert_opened_resource(
            user_id=1, resource_id="r1", resource_type="reading"
        )
        session.run.assert_called_once()
        query_used = session.run.call_args[0][0]
        assert "READING_RESOURCE" in query_used
