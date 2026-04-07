from unittest.mock import MagicMock

from app.modules.question_generation import neo4j_repository
from app.modules.question_generation.schemas import GeneratedQuestion


def test_write_questions_does_not_require_existing_question_nodes():
    session = MagicMock()
    session.run.return_value.single.return_value = {"written": 3}

    questions = [
        GeneratedQuestion(
            text="Easy question",
            difficulty="easy",
            options=["A", "B", "C", "D"],
            correct_option="A",
            answer="Because A is correct.",
        ),
        GeneratedQuestion(
            text="Medium question",
            difficulty="medium",
            options=["A", "B", "C", "D"],
            correct_option="B",
            answer="Because B is correct.",
        ),
        GeneratedQuestion(
            text="Hard question",
            difficulty="hard",
            options=["A", "B", "C", "D"],
            correct_option="C",
            answer="Because C is correct.",
        ),
    ]

    written = neo4j_repository.write_questions(
        session,
        "CAP theorem",
        questions,
    )

    query = session.run.call_args.args[0]

    assert written == 3
    assert "MATCH (sk:SKILL {name: $skill_name})" in query
    assert "OPTIONAL MATCH (sk)-[:HAS_QUESTION]->(existing:QUESTION)" in query
    assert "FOREACH (node IN existing_questions | DETACH DELETE node)" in query
