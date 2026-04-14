import json
from types import SimpleNamespace

from app.modules.student_learning_path.notebooks import (
    generate_resource_answerability_notebook,
)
from app.modules.student_learning_path.notebooks import (
    resource_answerability_eval_utils as eval_utils,
)


class _StubCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


class _StubClient:
    def __init__(self, content: str) -> None:
        self.chat = SimpleNamespace(completions=_StubCompletions(content))


class _FakeRecord:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def data(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, records: list[_FakeRecord]) -> None:
        self.records = records
        self.queries: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, params: dict):
        self.queries.append((query, params))
        return self.records


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self, *, database: str):
        return self._session


def test_judge_question_uses_yes_no_json_mode_and_hides_correct_option():
    verdict_payload = json.dumps(
        {
            "answerable": True,
            "confidence": 0.91,
            "evidence_strength": "strong",
            "supporting_quotes": [
                "CAP concerns consistency and availability trade-offs."
            ],
            "missing_information": "",
            "reasoning": "The evidence explicitly identifies the correct trade-off.",
        }
    )
    client = _StubClient(verdict_payload)

    verdict = eval_utils.judge_question(
        client,
        model="deepseek-chat",
        skill={"name": "CAP theorem", "skill_type": "book", "source": "book"},
        question={
            "text": "Which trade-off is associated with partition tolerance?",
            "options": [
                "Latency",
                "Consistency vs availability",
                "Storage size",
                "CPU load",
            ],
            "correct_option": "B",
        },
        modality="readings",
        evidence_text="CAP theorem discusses trade-offs between consistency and availability.",
    )

    assert verdict.answerable is True
    request_kwargs = client.chat.completions.calls[0]
    assert request_kwargs["response_format"] == {"type": "json_object"}
    prompt_text = "\n".join(
        message["content"] for message in request_kwargs["messages"]
    )
    assert "Correct Option:" not in prompt_text
    assert "single valid JSON object" in request_kwargs["messages"][0]["content"]
    assert '"answerable": true or false' in request_kwargs["messages"][0]["content"]


def test_run_answerability_experiment_records_yes_no_answerability(monkeypatch):
    bundle = {
        "course_id": 1,
        "student": {"id": 10, "email": "student@example.com"},
        "skills": [
            {
                "name": "CAP theorem",
                "skill_type": "book",
                "source": "book",
                "questions": [
                    {
                        "id": "q1",
                        "text": "Which trade-off is associated with partition tolerance?",
                        "difficulty": "medium",
                        "correct_option": "B",
                        "options": [
                            "Latency",
                            "Consistency vs availability",
                            "Storage size",
                            "CPU load",
                        ],
                    }
                ],
                "readings": [
                    {
                        "title": "CAP explainer",
                        "url": "https://example.com/cap",
                        "resource_type": "article",
                        "final_score": 0.9,
                        "concepts_covered": ["CAP theorem"],
                        "evidence": {
                            "content_text": "CAP theorem forces a trade-off between consistency and availability under partition.",
                            "content_source": "html",
                        },
                    }
                ],
                "videos": [],
            }
        ],
    }

    monkeypatch.setattr(
        eval_utils,
        "judge_question",
        lambda *args, **kwargs: eval_utils.JudgeVerdict(
            answerable=True,
            confidence=0.88,
            evidence_strength="strong",
            supporting_quotes=["trade-off between consistency and availability"],
            missing_information="",
            reasoning="The evidence directly states the trade-off.",
        ),
    )

    rows = eval_utils.run_answerability_experiment(
        bundle,
        client=object(),
        model="deepseek-chat",
        modalities=("readings",),
        max_workers=2,
    )

    assert len(rows) == 1
    assert rows[0]["answerable"] is True
    assert rows[0]["usable_evidence"] is True
    assert rows[0]["used_resource_count"] == 1
    assert rows[0]["evidence_chars"] > 0
    assert "CAP theorem" in rows[0]["evidence_preview"]


def test_run_answerability_experiment_abstains_without_usable_evidence(monkeypatch):
    bundle = {
        "course_id": 1,
        "student": {"id": 10, "email": "student@example.com"},
        "skills": [
            {
                "name": "Empty evidence skill",
                "skill_type": "market",
                "source": "job_posting",
                "questions": [
                    {
                        "id": "q-empty",
                        "text": "What does CI/CD stand for?",
                        "difficulty": "easy",
                        "correct_option": "A",
                        "options": [
                            "Continuous Integration and Continuous Delivery",
                            "Centralized Infrastructure and Container Deployment",
                            "Code Inspection and Change Detection",
                            "Continuous Iteration and Code Debugging",
                        ],
                    }
                ],
                "readings": [
                    {
                        "title": "Blank result",
                        "url": "https://example.com/blank",
                        "resource_type": "article",
                        "final_score": 0.1,
                        "concepts_covered": [],
                        "evidence": {"content_text": "", "content_source": "none"},
                    }
                ],
                "videos": [],
            }
        ],
    }

    def _unexpected_call(*args, **kwargs):
        raise AssertionError("judge_question should not run when evidence is empty")

    monkeypatch.setattr(eval_utils, "judge_question", _unexpected_call)

    rows = eval_utils.run_answerability_experiment(
        bundle,
        client=object(),
        model="deepseek-chat",
        modalities=("readings",),
        max_workers=2,
    )

    assert len(rows) == 1
    assert rows[0]["answerable"] is False
    assert rows[0]["usable_evidence"] is False
    assert rows[0]["missing_information"] == (
        "No usable evidence was available for this modality after hydration."
    )
    assert "No usable evidence" in rows[0]["reasoning"]


def test_summarize_results_reports_yes_no_answerability():
    rows = [
        {
            "modality": "readings",
            "skill_type": "book",
            "difficulty": "easy",
            "answerable": True,
        },
        {
            "modality": "readings",
            "skill_type": "book",
            "difficulty": "medium",
            "answerable": True,
        },
        {
            "modality": "videos",
            "skill_type": "market",
            "difficulty": "hard",
            "answerable": False,
        },
    ]

    summary = eval_utils.summarize_results(rows)

    assert summary["overall"]["answerable_rate"] == 2 / 3
    assert summary["overall"]["answerable_yes_count"] == 2
    assert summary["overall"]["answerable_no_count"] == 1

    by_modality = {row["modality"]: row for row in summary["by_modality"]}
    assert by_modality["readings"]["answerable_yes_count"] == 2
    assert by_modality["videos"]["answerable_rate"] == 0.0

    by_modality_and_difficulty = {
        (row["modality"], row["difficulty"]): row
        for row in summary["by_modality_and_difficulty"]
    }
    assert by_modality_and_difficulty[("readings", "easy")]["answerable_rate"] == 1.0
    assert by_modality_and_difficulty[("videos", "hard")]["answerable_rate"] == 0.0


def test_materialize_bundle_evidence_hydrates_resources_in_parallel(monkeypatch):
    bundle = {
        "skills": [
            {
                "name": "Skill A",
                "readings": [{"title": "Reading A", "url": "https://example.com/a"}],
                "videos": [
                    {
                        "title": "Video A",
                        "url": "https://example.com/v",
                        "video_id": "abc",
                    }
                ],
            }
        ]
    }

    monkeypatch.setattr(
        eval_utils,
        "fetch_reading_evidence",
        lambda resource, **kwargs: {
            "fetch_status": "ok",
            "content_text": f"reading:{resource['title']}",
            "content_source": "html",
        },
    )
    monkeypatch.setattr(
        eval_utils,
        "fetch_video_evidence",
        lambda resource, **kwargs: {
            "fetch_status": "ok",
            "content_text": f"video:{resource['title']}",
            "content_source": "youtube_transcript",
        },
    )

    hydrated = eval_utils.materialize_bundle_evidence(bundle, max_workers=2)

    skill = hydrated["skills"][0]
    assert skill["readings"][0]["evidence"]["content_text"] == "reading:Reading A"
    assert skill["videos"][0]["evidence"]["content_text"] == "video:Video A"


def test_load_selected_skill_bundle_defaults_to_course_path_scope():
    session = _FakeSession(
        [
            _FakeRecord(
                {
                    "student": {"id": 5, "email": "student@example.com"},
                    "skill": {
                        "name": "CAP theorem",
                        "description": "Trade-offs in distributed systems.",
                        "source": "book",
                        "skill_type": "book",
                        "course_level": "bachelor",
                        "chapter_index": 1,
                        "chapter_title": "Distributed Systems",
                        "concepts": [],
                        "questions": [],
                        "readings": [],
                        "videos": [],
                    },
                }
            )
        ]
    )
    driver = _FakeDriver(session)

    bundle = eval_utils.load_selected_skill_bundle(
        driver,
        database="neo4j",
        course_id=1,
        student_id=5,
    )

    query, params = session.queries[0]
    assert params["course_id"] == 1
    assert "HAS_COURSE_CHAPTER" in query
    assert "CANDIDATE_BOOK" not in query
    assert bundle["skill_count"] == 1
    assert bundle["skills"][0]["chapter_title"] == "Distributed Systems"


def test_generated_notebook_uses_yes_no_answerability_language():
    notebook = generate_resource_answerability_notebook.build_notebook()
    markdown_text = "\n".join(
        cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "markdown"
    )
    code_text = "\n".join(
        cell["source"] for cell in notebook["cells"] if cell["cell_type"] == "code"
    )

    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile(cell["source"], "<notebook-cell>", "exec")

    assert "Answerable Rate" in markdown_text
    assert "yes/no" in markdown_text.lower()
    assert "verification of the known correct answer" not in markdown_text
    assert "answerable_rate" in code_text
    assert "support_rate" not in code_text
    assert "predicted_option" not in code_text
