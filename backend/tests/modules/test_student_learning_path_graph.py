from unittest.mock import MagicMock

from app.modules.student_learning_path import graph as learning_path_graph


def test_process_skill_emits_question_error_event(monkeypatch):
    events: list[dict] = []

    monkeypatch.setattr(learning_path_graph, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(
        learning_path_graph, "has_questions", lambda session, skill_name: False
    )
    monkeypatch.setattr(
        learning_path_graph,
        "generate_questions_for_skill",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("DeepSeek returned invalid JSON object")
        ),
    )

    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    session.run.return_value = []

    result = learning_path_graph.process_skill(
        {
            "skill": {
                "name": "Distributed systems trade-offs",
                "description": "Understand distributed systems trade-offs.",
                "skill_type": "book",
                "concepts": [{"name": "CAP theorem", "description": "Trade-off model"}],
            },
            "course_id": 1,
            "neo4j_driver": driver,
            "needs_reading": False,
            "needs_video": False,
            "needs_questions": True,
            "worker_index": 0,
            "total_skills": 1,
        }
    )

    worker_result = result["results"][0]
    assert worker_result["questions_added"] == 0
    assert worker_result["question_error"].startswith("Question generation failed:")

    question_error_event = next(
        event for event in events if event.get("phase") == "question_error"
    )
    assert "invalid JSON object" in question_error_event["detail"]

    done_event = next(event for event in events if event.get("phase") == "done")
    assert "Question generation failed:" in done_event["detail"]


def test_process_skill_emits_question_error_when_persistence_writes_too_few(
    monkeypatch,
):
    events: list[dict] = []

    monkeypatch.setattr(learning_path_graph, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(
        learning_path_graph, "has_questions", lambda session, skill_name: False
    )
    monkeypatch.setattr(
        learning_path_graph,
        "generate_questions_for_skill",
        lambda *args, **kwargs: [
            MagicMock(),
            MagicMock(),
            MagicMock(),
        ],
    )
    monkeypatch.setattr(
        learning_path_graph, "write_questions", lambda *args, **kwargs: 0
    )

    driver = MagicMock()

    result = learning_path_graph.process_skill(
        {
            "skill": {
                "name": "Distributed systems trade-offs",
                "description": "Understand distributed systems trade-offs.",
                "skill_type": "book",
                "concepts": [{"name": "CAP theorem", "description": "Trade-off model"}],
            },
            "course_id": 1,
            "neo4j_driver": driver,
            "needs_reading": False,
            "needs_video": False,
            "needs_questions": True,
            "worker_index": 0,
            "total_skills": 1,
        }
    )

    worker_result = result["results"][0]
    assert worker_result["questions_added"] == 0
    assert "persistence mismatch" in worker_result["question_error"].lower()

    question_error_event = next(
        event for event in events if event.get("phase") == "question_error"
    )
    assert "wrote 0 of 3 questions" in question_error_event["detail"]
