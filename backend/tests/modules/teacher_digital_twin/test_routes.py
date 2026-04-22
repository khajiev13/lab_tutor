"""Integration tests for /teacher-twin/* routes (TestClient + JWT + mocked Neo4j)."""

from unittest.mock import MagicMock

from app.core.neo4j import get_neo4j_driver
from main import app


def _neo4j_override(rows=None, single_return=None):
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    run_result = MagicMock()
    run_result.__iter__ = MagicMock(return_value=iter(rows or []))
    run_result.single.return_value = single_return
    run_result.consume.return_value = MagicMock()
    session.run.return_value = run_result
    return (lambda: driver), session


# ---------------------------------------------------------------------------
# Auth + role guard tests
# ---------------------------------------------------------------------------


class TestAuthGuards:
    """All /teacher-twin/* routes require TEACHER role."""

    def test_skill_difficulty_requires_auth(self, client):
        r = client.get("/teacher-twin/1/skill-difficulty")
        assert r.status_code == 401

    def test_class_mastery_requires_auth(self, client):
        r = client.get("/teacher-twin/1/class-mastery")
        assert r.status_code == 401

    def test_student_groups_requires_auth(self, client):
        r = client.get("/teacher-twin/1/student-groups")
        assert r.status_code == 401

    def test_what_if_requires_auth(self, client):
        r = client.post("/teacher-twin/1/what-if", json={})
        assert r.status_code == 401

    def test_simulate_skill_requires_auth(self, client):
        r = client.post(
            "/teacher-twin/1/simulate-skill", json={"skill_name": "algebra"}
        )
        assert r.status_code == 401

    def test_student_cannot_access_teacher_routes(self, client, student_auth_headers):
        r = client.get("/teacher-twin/1/skill-difficulty", headers=student_auth_headers)
        assert r.status_code in (401, 403)

    def test_skill_popularity_requires_auth(self, client):
        r = client.get("/teacher-twin/1/skill-popularity")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Neo4j unavailable → 503
# ---------------------------------------------------------------------------


class TestNeo4jUnavailable:
    def test_skill_difficulty_503(self, client, teacher_auth_headers):
        app.dependency_overrides[get_neo4j_driver] = lambda: None
        try:
            r = client.get(
                "/teacher-twin/1/skill-difficulty", headers=teacher_auth_headers
            )
            assert r.status_code == 503
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_class_mastery_503(self, client, teacher_auth_headers):
        app.dependency_overrides[get_neo4j_driver] = lambda: None
        try:
            r = client.get(
                "/teacher-twin/1/class-mastery", headers=teacher_auth_headers
            )
            assert r.status_code == 503
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


# ---------------------------------------------------------------------------
# Happy-path — empty Neo4j
# ---------------------------------------------------------------------------


class TestSkillDifficulty:
    def test_empty_class(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/teacher-twin/1/skill-difficulty", headers=teacher_auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert "skills" in data
            assert data["skills"] == []
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_skills_returned(self, client, teacher_auth_headers):
        rows = [
            {
                "skill_name": "calculus",
                "student_count": 5,
                "avg_mastery": 0.6,
                "perceived_difficulty": 0.4,
                "prereq_count": 2,
                "downstream_count": 3,
                "pco_risk_ratio": 0.2,
            }
        ]
        factory, _ = _neo4j_override(rows)
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/teacher-twin/1/skill-difficulty", headers=teacher_auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert len(data["skills"]) == 1
            assert data["skills"][0]["skill_name"] == "calculus"
            assert data["skills"][0]["prereq_count"] == 2
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestSkillPopularity:
    def test_empty(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/teacher-twin/1/skill-popularity", headers=teacher_auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert "all_skills" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestClassMastery:
    def test_empty_class(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/teacher-twin/1/class-mastery", headers=teacher_auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert data["students"] == []
            assert data["total_students"] == 0
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestStudentGroups:
    def test_empty_groups(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/teacher-twin/1/student-groups", headers=teacher_auth_headers
            )
            assert r.status_code == 200
            data = r.json()
            assert data["total_groups"] == 0
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestWhatIf:
    def test_automatic_mode(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/teacher-twin/1/what-if",
                json={
                    "mode": "automatic",
                    "preferences": {
                        "intervention_intensity": 0.75,
                        "focus": "broad_support",
                        "max_skills": 3,
                    },
                },
                headers=teacher_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["mode"] == "automatic"
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_manual_mode(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/teacher-twin/1/what-if",
                json={
                    "mode": "manual",
                    "skills": [{"skill_name": "algebra", "hypothetical_mastery": 0.9}],
                },
                headers=teacher_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["mode"] == "manual"
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestSimulateSkill:
    def test_single_skill(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/teacher-twin/1/simulate-skill",
                json={"skill_name": "algebra", "simulated_mastery": 0.5},
                headers=teacher_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert data["skill_name"] == "algebra"
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_multi_skills(self, client, teacher_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/teacher-twin/1/simulate-skills",
                json={
                    "skills": [
                        {"skill_name": "algebra"},
                        {"skill_name": "calculus"},
                    ]
                },
                headers=teacher_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert "skill_results" in data or "mode" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestStudentDrilldown:
    def test_portfolio_requires_teaches_class(self, client, teacher_auth_headers):
        """Teacher not teaching the class gets 403."""
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value
        run_result = MagicMock()
        run_result.__iter__ = MagicMock(return_value=iter([]))
        run_result.single.return_value = {"teaches": False}
        session.run.return_value = run_result
        app.dependency_overrides[get_neo4j_driver] = lambda: driver
        try:
            r = client.get(
                "/teacher-twin/99/student/10/portfolio",
                headers=teacher_auth_headers,
            )
            assert r.status_code == 403
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_twin_requires_teaches_class(self, client, teacher_auth_headers):
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value
        run_result = MagicMock()
        run_result.__iter__ = MagicMock(return_value=iter([]))
        run_result.single.return_value = {"teaches": False}
        session.run.return_value = run_result
        app.dependency_overrides[get_neo4j_driver] = lambda: driver
        try:
            r = client.get(
                "/teacher-twin/99/student/10/twin",
                headers=teacher_auth_headers,
            )
            assert r.status_code == 403
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)
