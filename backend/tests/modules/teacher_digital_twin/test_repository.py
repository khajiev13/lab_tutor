"""Tests for TeacherDigitalTwinRepository (Neo4j layer)."""

from unittest.mock import MagicMock

from app.modules.teacher_digital_twin.repository import TeacherDigitalTwinRepository


def _make_repo():
    session = MagicMock()
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter([]))
    run_result.single.return_value = None
    session.run.return_value = run_result
    return TeacherDigitalTwinRepository(session), session


class TestTeacherTeachesClass:
    def test_returns_false_when_no_record(self):
        repo, session = _make_repo()
        result = repo.teacher_teaches_class(teacher_id=1, course_id=10)
        assert result is False

    def test_returns_true_when_teaches(self):
        repo, session = _make_repo()
        session.run.return_value.single.return_value = {"teaches": True}
        result = repo.teacher_teaches_class(teacher_id=1, course_id=10)
        assert result is True


class TestGetSkillDifficulty:
    def test_empty_returns_empty_list(self):
        repo, session = _make_repo()
        result = repo.get_skill_difficulty(course_id=1)
        assert result == []

    def test_row_returned(self):
        repo, session = _make_repo()
        session.run.return_value = [
            {
                "skill_name": "calculus",
                "student_count": 5,
                "attempted_count": 4,
                "avg_mastery": 0.6,
                "perceived_difficulty": 0.4,
            }
        ]
        result = repo.get_skill_difficulty(course_id=1)
        assert len(result) == 1
        assert result[0]["skill_name"] == "calculus"
        assert result[0]["attempted_count"] == 4

    def test_cypher_returns_attempted_count_and_orders_unattempted_last(self):
        # Pin the Cypher's behavior: the query must surface an attempted_count
        # field and sort skills with no attempts at the end. If the underlying
        # query is rewritten, this guards against silently dropping that
        # filter and regressing the chart that ranks "Top Difficult Skills".
        repo, _ = _make_repo()
        from app.modules.teacher_digital_twin.repository import GET_SKILL_DIFFICULTY

        cypher = GET_SKILL_DIFFICULTY
        assert "attempted_count" in cypher
        assert "perceived_difficulty" in cypher
        assert "CASE WHEN attempted_count = 0 THEN 1 ELSE 0 END" in cypher
        # Ensure the Cypher doesn't accidentally fall back to the legacy
        # avg-over-all-students formulation, which made selected-but-unattempted
        # skills look maximally difficult.
        assert "1.0 - attempted_avg_mastery" in cypher


class TestGetSkillPopularity:
    def test_empty(self):
        repo, session = _make_repo()
        result = repo.get_skill_popularity(course_id=1)
        assert result == []

    def test_rows_returned(self):
        repo, session = _make_repo()
        session.run.return_value = [{"skill_name": "algebra", "selection_count": 10}]
        result = repo.get_skill_popularity(course_id=1)
        assert result[0]["skill_name"] == "algebra"


class TestGetTotalStudents:
    def test_returns_zero_when_no_record(self):
        repo, session = _make_repo()
        result = repo.get_total_students(course_id=1)
        assert result == 0

    def test_returns_count(self):
        repo, session = _make_repo()
        session.run.return_value.single.return_value = {"total_students": 15}
        result = repo.get_total_students(course_id=1)
        assert result == 15


class TestGetClassMastery:
    def test_empty(self):
        repo, session = _make_repo()
        result = repo.get_class_mastery(course_id=1)
        assert result == []

    def test_row_returned(self):
        repo, session = _make_repo()
        session.run.return_value = [
            {
                "user_id": 42,
                "full_name": "Alice Student",
                "email": "alice@test.com",
                "selected_skill_count": 3,
                "skill_masteries": [0.5, 0.7, 0.3],
            }
        ]
        result = repo.get_class_mastery(course_id=1)
        assert result[0]["user_id"] == 42


class TestGetStudentPcoCount:
    def test_returns_zero_when_no_record(self):
        repo, session = _make_repo()
        result = repo.get_student_pco_count(user_id=1)
        assert result == 0

    def test_returns_count(self):
        repo, session = _make_repo()
        session.run.return_value.single.return_value = {"pco_count": 3}
        result = repo.get_student_pco_count(user_id=1)
        assert result == 3


class TestGetClassSkillMastery:
    def test_empty(self):
        repo, session = _make_repo()
        result = repo.get_class_skill_mastery(course_id=1)
        assert result == []


class TestGetSkillCoSelection:
    def test_empty(self):
        repo, session = _make_repo()
        result = repo.get_skill_co_selection(course_id=1, skill_names=["algebra"])
        assert result == []
