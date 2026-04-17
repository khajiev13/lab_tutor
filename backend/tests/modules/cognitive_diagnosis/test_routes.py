"""Integration tests for /diagnosis/* routes (TestClient + JWT + mocked Neo4j)."""

from unittest.mock import MagicMock

from app.core.neo4j import get_neo4j_driver
from main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _neo4j_override(run_return=None):
    """Return an override factory and the inner session mock."""
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    rows = run_return if run_return is not None else []
    result_mock = MagicMock()
    result_mock.__iter__ = MagicMock(return_value=iter(rows))
    result_mock.single.return_value = rows[0] if rows else None
    result_mock.consume.return_value = MagicMock()
    session.run.return_value = result_mock
    return (lambda: driver), session


# ---------------------------------------------------------------------------
# Auth guard tests (no Neo4j needed)
# ---------------------------------------------------------------------------


class TestAuthGuards:
    """All /diagnosis/ routes require STUDENT role."""

    def test_mastery_get_requires_auth(self, client):
        r = client.get("/diagnosis/mastery/1")
        assert r.status_code == 401

    def test_mastery_post_requires_auth(self, client):
        r = client.post("/diagnosis/mastery/1")
        assert r.status_code == 401

    def test_path_requires_auth(self, client):
        r = client.get("/diagnosis/path/1")
        assert r.status_code == 401

    def test_review_requires_auth(self, client):
        r = client.post("/diagnosis/review/1", json={"top_k": 3})
        assert r.status_code == 401

    def test_exercise_requires_auth(self, client):
        r = client.post("/diagnosis/exercise", json={"skill_name": "algebra"})
        assert r.status_code == 401

    def test_portfolio_requires_auth(self, client):
        r = client.get("/diagnosis/portfolio/1")
        assert r.status_code == 401

    def test_student_events_get_requires_auth(self, client):
        r = client.get("/diagnosis/student-events")
        assert r.status_code == 401

    def test_student_events_post_requires_auth(self, client):
        r = client.post(
            "/diagnosis/student-events",
            json={"date": "2026-01-01", "title": "x", "event_type": "study"},
        )
        assert r.status_code == 401

    def test_teacher_cannot_access_student_routes(self, client, teacher_auth_headers):
        # Teacher token should be rejected on student-only endpoints
        r = client.get("/diagnosis/mastery/1", headers=teacher_auth_headers)
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Neo4j unavailable → 503
# ---------------------------------------------------------------------------


class TestNeo4jUnavailable:
    def test_mastery_get_503_when_no_neo4j(self, client, student_auth_headers):
        app.dependency_overrides[get_neo4j_driver] = lambda: None
        try:
            r = client.get("/diagnosis/mastery/1", headers=student_auth_headers)
            assert r.status_code == 503
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_path_503_when_no_neo4j(self, client, student_auth_headers):
        app.dependency_overrides[get_neo4j_driver] = lambda: None
        try:
            r = client.get("/diagnosis/path/1", headers=student_auth_headers)
            assert r.status_code == 503
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


# ---------------------------------------------------------------------------
# Happy-path with mocked Neo4j
# ---------------------------------------------------------------------------


class TestMasteryEndpoints:
    def test_get_mastery_empty(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get("/diagnosis/mastery/1", headers=student_auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert "skills" in data
            assert data["skills"] == []
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_get_mastery_with_skills(self, client, student_auth_headers):
        rows = [
            {
                "skill_name": "algebra",
                "mastery": 0.7,
                "decay": 0.9,
                "status": "at",
                "attempt_count": 2,
                "correct_count": 1,
                "last_practice_ts": None,
                "model_version": "arcd_v2",
            }
        ]
        factory, session = _neo4j_override(rows)
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get("/diagnosis/mastery/1", headers=student_auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert len(data["skills"]) == 1
            assert data["skills"][0]["skill_name"] == "algebra"
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_post_mastery_returns_mastery_response(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post("/diagnosis/mastery/1", headers=student_auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert "skills" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestPathEndpoint:
    def test_get_path_empty(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get("/diagnosis/path/1", headers=student_auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert "steps" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_path_length_param(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get(
                "/diagnosis/path/1?path_length=3", headers=student_auth_headers
            )
            assert r.status_code == 200
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestReviewEndpoint:
    def test_review_default_top_k(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/diagnosis/review/1",
                json={"top_k": 3},
                headers=student_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert "pco_skills" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestExerciseEndpoint:
    def test_exercise_empty_neo4j(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/diagnosis/exercise",
                json={"skill_name": "algebra", "context": ""},
                headers=student_auth_headers,
            )
            assert r.status_code == 200
            data = r.json()
            assert "skill_name" in data
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestPortfolioEndpoint:
    def test_portfolio_empty(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get("/diagnosis/portfolio/1", headers=student_auth_headers)
            assert r.status_code == 200
            data = r.json()
            assert data["user_id"] is not None
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestStudentEventsEndpoints:
    def test_list_events_empty(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.get("/diagnosis/student-events", headers=student_auth_headers)
            assert r.status_code == 200
            assert r.json()["events"] == []
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_create_event(self, client, student_auth_headers):
        run_result = MagicMock()
        run_result.single.return_value = {
            "id": "evt-test",
            "user_id": 1,
            "date": "2026-01-15",
            "title": "Exam Prep",
            "event_type": "exam",
            "duration_minutes": 120,
            "notes": "",
            "created_at_ts": 1000,
        }
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = run_result
        app.dependency_overrides[get_neo4j_driver] = lambda: driver
        try:
            r = client.post(
                "/diagnosis/student-events",
                json={
                    "date": "2026-01-15",
                    "title": "Exam Prep",
                    "event_type": "exam",
                    "duration_minutes": 120,
                },
                headers=student_auth_headers,
            )
            assert r.status_code == 201
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_create_event_invalid_type(self, client, student_auth_headers):
        factory, _ = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/diagnosis/student-events",
                json={
                    "date": "2026-01-15",
                    "title": "Party",
                    "event_type": "party",
                },
                headers=student_auth_headers,
            )
            assert r.status_code == 422
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_delete_event_not_found(self, client, student_auth_headers):
        run_result = MagicMock()
        run_result.single.return_value = {"deleted_count": 0}
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value = run_result
        app.dependency_overrides[get_neo4j_driver] = lambda: driver
        try:
            r = client.delete(
                "/diagnosis/student-events/missing-id",
                headers=student_auth_headers,
            )
            assert r.status_code == 404
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)


class TestInteractionEndpoints:
    def test_log_interaction(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/diagnosis/interactions",
                json={
                    "question_id": "q-001",
                    "answered_right": True,
                    "selected_option": "A",
                },
                headers=student_auth_headers,
            )
            assert r.status_code == 201
            assert r.json()["logged"] is True
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)

    def test_log_engagement(self, client, student_auth_headers):
        factory, session = _neo4j_override([])
        app.dependency_overrides[get_neo4j_driver] = factory
        try:
            r = client.post(
                "/diagnosis/engagements",
                json={"resource_id": "r-001", "resource_type": "reading"},
                headers=student_auth_headers,
            )
            assert r.status_code == 201
            assert r.json()["logged"] is True
        finally:
            app.dependency_overrides.pop(get_neo4j_driver, None)
