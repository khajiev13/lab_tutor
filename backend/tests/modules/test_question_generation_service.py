import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.question_generation import service as question_service


def _question_payload() -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "text": "What does CAP stand for in distributed systems?",
                    "difficulty": "easy",
                    "options": [
                        "Consistency, Availability, Partition tolerance",
                        "Concurrency, Accuracy, Performance",
                        "Caching, Access, Processing",
                        "Clustering, Analytics, Persistence",
                    ],
                    "correct_option": "A",
                    "answer": "CAP refers to consistency, availability, and partition tolerance.",
                },
                {
                    "text": "Which trade-off is most associated with partition tolerance in a NoSQL system?",
                    "difficulty": "medium",
                    "options": [
                        "Lower hardware cost",
                        "Choosing between consistency and availability during failures",
                        "Removing indexes from every table",
                        "Forcing all writes to be synchronous",
                    ],
                    "correct_option": "B",
                    "answer": "Partition tolerance usually forces a trade-off between consistency and availability when the network is partitioned.",
                },
                {
                    "text": "Which design choice best reflects a BASE-oriented distributed database under frequent network partitions?",
                    "difficulty": "hard",
                    "options": [
                        "Rejecting all writes until every replica is reachable",
                        "Guaranteeing serializable transactions across all regions",
                        "Favoring eventual consistency to keep the system available",
                        "Replacing replication with a single-node deployment",
                    ],
                    "correct_option": "C",
                    "answer": "BASE-oriented systems often favor eventual consistency to maintain availability under partition conditions.",
                },
            ]
        }
    )


class _StubCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content),
                )
            ]
        )


class _StubClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_StubCompletions(content))


def test_generate_questions_for_skill_uses_json_mode_and_parses_fences(monkeypatch):
    client = _StubClient(f"```json\n{_question_payload()}\n```")
    monkeypatch.setattr(question_service, "_get_client", lambda: client)
    monkeypatch.setattr(question_service.settings, "llm_model", "deepseek-v3.2")

    questions = question_service.generate_questions_for_skill(
        "Distributed system trade-offs",
        "Understand key distributed systems trade-offs.",
        [{"name": "CAP theorem", "description": "Trade-offs under partitions"}],
        "bachelor",
    )

    assert len(questions) == 3
    assert [question.difficulty for question in questions] == ["easy", "medium", "hard"]

    request_kwargs = client.chat.completions.calls[0]
    assert request_kwargs["response_format"] == {"type": "json_object"}
    assert request_kwargs["temperature"] == 0
    assert '"questions"' in question_service.SYSTEM_PROMPT
    assert '"correct_option"' in question_service.SYSTEM_PROMPT
    assert "single valid JSON object" in question_service.SYSTEM_PROMPT


def test_generate_questions_for_skill_raises_on_invalid_schema(monkeypatch):
    invalid_payload = json.dumps(
        {
            "questions": [
                {
                    "text": "Only one malformed question",
                    "difficulty": "easy",
                    "options": ["A", "B", "C", "D"],
                    "correct_option": "A",
                    "answer": "Malformed because there are not three questions.",
                }
            ]
        }
    )
    client = _StubClient(invalid_payload)
    monkeypatch.setattr(question_service, "_get_client", lambda: client)

    with pytest.raises(ValidationError):
        question_service.generate_questions_for_skill(
            "Malformed skill",
            "Skill for invalid schema testing.",
            [],
            "bachelor",
        )
