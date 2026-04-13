from unittest.mock import MagicMock

from app.modules.student_learning_path.service import StudentLearningPathService
from main import app


def test_build_route_returns_400_when_first_time_build_has_no_selections(
    client,
    student_auth_headers,
    monkeypatch,
):
    async def fake_build_learning_path(
        self, student_id, course_id, selected_skills=None
    ):
        raise ValueError("Select at least one skill before building")

    previous_driver = getattr(app.state, "neo4j_driver", None)
    app.state.neo4j_driver = MagicMock()
    monkeypatch.setattr(
        StudentLearningPathService,
        "build_learning_path",
        fake_build_learning_path,
    )

    try:
        response = client.post(
            "/student-learning-path/1/build",
            headers=student_auth_headers,
        )
    finally:
        app.state.neo4j_driver = previous_driver

    assert response.status_code == 400
    assert response.json()["detail"] == "Select at least one skill before building"
