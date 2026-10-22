"""Generated plans retain every source document and commit atomically."""

import json
from copy import deepcopy

import httpx
import pytest

from app.core.settings import settings
from app.modules.curricularalignmentarchitect.curriculum_planning import service
from app.modules.curricularalignmentarchitect.curriculum_planning.repository import (
    ChapterPlanRepository,
)
from app.modules.curricularalignmentarchitect.curriculum_planning.schemas import (
    ChapterPlan,
)

pytest_plugins = ["tests.fixtures.market_skill_graph"]


@pytest.fixture
def planner(graph_driver):
    with graph_driver.session(database="neo4j") as session:
        session.run(
            "CREATE (c:CLASS {id: 501}) WITH c "
            "UNWIND range(0, 37) AS i "
            "CREATE (c)-[:HAS_DOCUMENT]->(:TEACHER_UPLOADED_DOCUMENT "
            "{id: 'doc-' + toString(i), source_filename: 'Lecture ' + toString(i), "
            "topic: 'Big data topic ' + toString(i)})"
        ).consume()
        yield service.TeacherCurriculumPlanner(session)


def complete_plan():
    return {
        "chapters": [
            {
                "number": 1,
                "title": "Foundations",
                "description": "Core concepts",
                "learning_objectives": ["Explain data systems"],
                "prerequisites": [],
                "assigned_documents": [f"doc-{i}" for i in range(19)],
            },
            {
                "number": 2,
                "title": "Processing",
                "description": "Distributed processing",
                "learning_objectives": ["Process data"],
                "prerequisites": ["Foundations"],
                "assigned_documents": [f"doc-{i}" for i in range(19, 38)],
            },
        ]
    }


@pytest.fixture
def provider(monkeypatch):
    replies, requests = [], []
    monkeypatch.setattr(settings, "llm_api_key", "test-only")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_model", "deepseek-v4.1-flash")

    def send(_client, request, **kwargs):
        requests.append(json.loads(request.content))
        body = replies.pop(0)
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chapter-test",
                "created": 0,
                "model": "test",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(body)},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx.Client, "send", send)
    return replies, requests


@pytest.mark.parametrize(
    "model,thinking",
    [
        ("deepseek-v4.1-flash", {"thinking": {"type": "disabled"}}),
        ("qwen3.5-plus", {"enable_thinking": False}),
        ("gpt-4o-mini", {}),
    ],
)
def test_generate_covers_all_38_documents_with_bounded_json_request(
    planner, provider, monkeypatch, model, thinking
):
    replies, requests = provider
    monkeypatch.setattr(settings, "llm_model", model)
    replies.append(complete_plan())
    result = planner.generate_plan(501, "Big Data")
    saved = planner.get_plan(501)
    assert len(saved.all_documents) == 38
    assert saved.unassigned_documents == result.unassigned_documents == []
    assert len({d for c in saved.chapters for d in c.assigned_documents}) == 38
    assert len(requests) == 1
    request = requests[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["stream"] is False
    assert request.get("max_completion_tokens", request.get("max_tokens")) <= 8192
    assert {
        k: request[k] for k in ("thinking", "enable_thinking") if k in request
    } == thinking


@pytest.mark.parametrize(
    "invalid", ["missing", "duplicate", "unknown", "title", "prerequisite", "number"]
)
def test_invalid_generated_plan_gets_one_correction_before_saving(
    planner, provider, invalid
):
    replies, requests = provider
    bad = complete_plan()
    if invalid == "missing":
        bad["chapters"][0]["assigned_documents"].pop()
    elif invalid == "duplicate":
        bad["chapters"][1]["assigned_documents"].append("doc-0")
    elif invalid == "unknown":
        bad["chapters"][0]["assigned_documents"][0] = "another-course-document"
    elif invalid == "title":
        bad["chapters"][1]["title"] = "Foundations"
    elif invalid == "prerequisite":
        bad["chapters"][0]["prerequisites"] = ["Processing"]
    else:
        bad["chapters"][1]["number"] = 1
    replies.extend([bad, complete_plan()])
    result = planner.generate_plan(501, "Big Data")
    assert len(requests) == 2
    assert result.unassigned_documents == []
    assert [c.title for c in result.chapters] == ["Foundations", "Processing"]
    assert planner.get_plan(501) == result


def test_unrepairable_plan_preserves_existing_chapters_and_document_links(
    planner, provider
):
    old = [
        ChapterPlan(
            number=1,
            title="Existing chapter",
            description="Keep it",
            assigned_documents=["doc-0"],
        )
    ]
    planner.save_plan(501, old)
    before = planner.get_plan(501)
    replies, requests = provider
    bad = complete_plan()
    bad["chapters"][0]["assigned_documents"].pop()
    replies.extend([bad, deepcopy(bad)])
    with pytest.raises(ValueError, match="complete|assign|document"):
        planner.generate_plan(501, "Big Data")
    assert len(requests) == 2
    assert planner.get_plan(501) == before


def test_repository_replacement_rolls_back_if_a_chapter_write_fails(planner):
    repo: ChapterPlanRepository = planner.repo
    repo.save_plan(
        501,
        [
            ChapterPlan(
                number=1,
                title="Existing",
                description="Keep it",
                assigned_documents=["doc-0"],
            )
        ],
    )
    before = repo.get_plan(501)
    invalid = ChapterPlan.model_construct(
        number=2,
        title="Broken",
        description={"not": "a graph property"},
        assigned_documents=[],
    )
    with pytest.raises(Exception, match="Property|property"):
        repo.save_plan(
            501,
            [
                ChapterPlan(
                    number=1,
                    title="Replacement",
                    description="New",
                    assigned_documents=["doc-1"],
                ),
                invalid,
            ],
        )
    assert repo.get_plan(501) == before
