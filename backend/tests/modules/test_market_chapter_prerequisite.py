"""Mapping prerequisites through real SQL, graph queries, and Swarm checkpoints."""

import json
from copy import deepcopy
from functools import partial

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from pydantic import SecretStr

from app.core.settings import settings
from app.modules.marketdemandanalyst import tools
from app.modules.marketdemandanalyst.state import bind_tool_store
from tests.market_skill_fixtures import seed_review

pytest_plugins = [
    "tests.fixtures.market_skill_graph",
    "tests.modules.test_market_workspace_chat",
    "tests.modules.test_market_llm_transport",
]


@pytest.fixture
def mapping_course(db_session, client, teacher_auth_headers, graph_driver, monkeypatch):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("SQL", "ETL")
    )
    run.config = {**run.config, "country": "Uzbekistan", "onet_release": None}
    db_session.commit()
    monkeypatch.setattr(settings, "hh_user_agent", "chapter-tests")
    monkeypatch.setattr(settings, "hh_access_token", SecretStr("test-only"))
    with graph_driver.session(database="neo4j") as session:
        session.run("CREATE (:CLASS {id: $id})", id=course["id"]).consume()
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    state = {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    return course, run, candidates, service, state


def add_chapter(driver, course_id):
    with driver.session(database="neo4j") as session:
        session.run(
            "MATCH (c:CLASS {id: $id}) "
            "CREATE (c)-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER "
            "{id: 'chapter-1', title: 'Data pipelines', chapter_index: 1})",
            id=course_id,
        ).consume()


@pytest.mark.parametrize("ready", [False, True])
def test_mapping_save_requires_existing_chapters_without_changing_selection(
    mapping_course, graph_driver, ready
):
    course, run, candidates, service, state = mapping_course
    if ready:
        add_chapter(graph_driver, course["id"])
    before = deepcopy(state)
    selected = list(run.selected_candidate_ids)
    with bind_tool_store(state):
        result = tools.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "candidate_id": c["candidate_id"],
                            "name": c["display_name"],
                            "status": "gap",
                            "target_chapter": "Data pipelines",
                        }
                        for c in candidates
                    ]
                )
            }
        )
    review = service.get_review(course["id"], course["teacher_id"])
    assert [
        str(candidate_id) for candidate_id in review.selected_candidate_ids
    ] == selected
    if ready:
        assert "Saved mapping proposals for 2" in result
        assert {r["candidate_id"] for r in state["curriculum_mapping"]} == set(selected)
    else:
        assert "Build Chapters" in result
        assert state == before
        assert "curriculum_mapping" not in service._repo.load_active_snapshot(
            service.thread_id(course["id"], course["teacher_id"])
        )


@pytest.mark.parametrize("resume", [False, True])
def test_mapping_handoff_and_checkpoint_resume_stop_before_model_without_chapters(
    mapping_course, client, live_graph, resume
):
    course, run, _, service, state = mapping_course
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    config = {"configurable": {"thread_id": thread}}
    checkpoint(thread)
    if resume:
        client.portal.call(
            partial(
                graph.aupdate_state,
                config,
                {"active_agent": "curriculum_mapper"},
                as_node="supervisor",
            )
        )
    else:
        model.replies.append(
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "map-now",
                        "name": "transfer_to_curriculum_mapper",
                        "args": {},
                    }
                ],
            )
        )
    before = deepcopy(state)
    with bind_tool_store(state):
        result = client.portal.call(
            graph.ainvoke,
            {"messages": [HumanMessage(content="Map my selected skills")]},
            config,
        )
    assert "Build Chapters" in result["messages"][-1].content
    assert result["active_agent"] == "supervisor"
    assert len(model.calls) == (0 if resume else 1)
    assert state == before
    assert run.selected_candidate_ids == [
        r["candidate_id"] for r in state["curated_skills"]
    ]


def test_supervisor_can_recheck_chapters_and_continue_with_same_selected_ids(
    mapping_course, graph_driver, client, live_graph
):
    course, run, _, service, state = mapping_course
    add_chapter(graph_driver, course["id"])
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)
    model.replies.extend(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "check", "name": "list_chapters", "args": {}}],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "map", "name": "transfer_to_curriculum_mapper", "args": {}}
                ],
            ),
            AIMessage(content="Ready to map these selected skills."),
        ]
    )
    before = deepcopy(state)
    with bind_tool_store(state):
        result = client.portal.call(
            graph.ainvoke,
            {"messages": [HumanMessage(content="Chapters are built. Retry mapping.")]},
            {"configurable": {"thread_id": thread}},
        )
    assert "list_chapters" in model.calls[0][1]
    assert "Course has 1 chapters" in str(result["messages"])
    assert result["active_agent"] == "curriculum_mapper"
    assert state == before
    assert run.selected_candidate_ids == [
        r["candidate_id"] for r in state["curated_skills"]
    ]


@pytest.mark.parametrize("error", [ServiceUnavailable, SessionExpired])
def test_unavailable_graph_stops_mapping_with_retry_and_preserves_shortlist(
    mapping_course, client, live_graph, monkeypatch, error
):
    course, _, _, service, state = mapping_course
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)

    def unavailable(**kwargs):
        raise error("test connection unavailable")

    monkeypatch.setattr(tools, "_get_neo4j_driver", unavailable)
    model.replies.append(
        AIMessage(
            content="",
            tool_calls=[
                {"id": "map", "name": "transfer_to_curriculum_mapper", "args": {}}
            ],
        )
    )
    before = deepcopy(state)
    with bind_tool_store(state):
        result = client.portal.call(
            graph.ainvoke,
            {"messages": [HumanMessage(content="Map my skills")]},
            {"configurable": {"thread_id": thread}},
        )
        saved = tools.save_curriculum_mapping.invoke({"mapping_json": "[]"})
    assert "Retry" in result["messages"][-1].content
    assert "Retry" in saved
    assert len(model.calls) == 1
    assert result["active_agent"] == "supervisor"
    assert state == before


def test_ordinary_chat_reports_missing_chapters_and_keeps_confirmed_selection(
    mapping_course, client, teacher_auth_headers, live_graph
):
    course, run, _, service, _ = mapping_course
    model, _, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)
    selected = list(run.selected_candidate_ids)
    model.replies.append(
        AIMessage(
            content="",
            tool_calls=[
                {"id": "map", "name": "transfer_to_curriculum_mapper", "args": {}}
            ],
        )
    )
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={"message": "Map my selected skills"},
    )
    assert response.status_code == 200, response.text
    assert "Build Chapters" in response.text
    assert "event: error" not in response.text
    agent_starts = [
        json.loads(block.split("data: ", 1)[1])["agent"]
        for block in response.text.split("\n\n")
        if block.startswith("event: agent_start\n")
    ]
    assert agent_starts and set(agent_starts) == {"supervisor"}
    assert len(model.calls) == 1
    review = service.get_review(course["id"], course["teacher_id"])
    assert [
        str(candidate_id) for candidate_id in review.selected_candidate_ids
    ] == selected
    assert checkpoint(thread).values["active_agent"] == "supervisor"


def test_skill_review_can_continue_without_chapters(mapping_course, client, live_graph):
    course, _, _, service, state = mapping_course
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)
    model.replies.append(AIMessage(content="Review the extracted skills."))
    before = deepcopy(state)
    with bind_tool_store(state):
        result = client.portal.call(
            graph.ainvoke,
            {
                "messages": [HumanMessage(content="Review skills before mapping")],
                "active_agent": "skill_finder",
            },
            {"configurable": {"thread_id": thread}},
        )
    assert result["messages"][-1].content == "Review the extracted skills."
    assert "start_extraction" in model.calls[0][1]
    assert state == before


def test_current_state_rechecks_saved_chapters_without_mapping_or_selection_changes(
    mapping_course, graph_driver
):
    course, run, _, service, state = mapping_course
    before = deepcopy(state)
    selected = list(run.selected_candidate_ids)
    with bind_tool_store(state):
        missing = tools.show_current_state.invoke({})
        add_chapter(graph_driver, course["id"])
        ready = tools.show_current_state.invoke({})
    assert "Build Chapters" in missing
    assert "Live chapter readiness: ready" in ready
    assert "saved course chapters exist" in ready
    assert "Curriculum mapping rows: 0" in missing
    assert "Curriculum mapping rows: 0" in ready
    assert "2 skills awaiting mapping" in ready
    assert "Build Chapters" not in ready
    assert state == before
    review = service.get_review(course["id"], course["teacher_id"])
    assert [
        str(candidate_id) for candidate_id in review.selected_candidate_ids
    ] == selected


@pytest.mark.parametrize("error", [ServiceUnavailable, SessionExpired])
def test_current_state_does_not_claim_missing_chapters_when_graph_is_unavailable(
    mapping_course, graph_driver, monkeypatch, error
):
    course, _, _, _, state = mapping_course
    add_chapter(graph_driver, course["id"])
    before = deepcopy(state)

    def unavailable(**kwargs):
        raise error("test connection unavailable")

    monkeypatch.setattr(tools, "_get_neo4j_driver", unavailable)
    with bind_tool_store(state):
        result = tools.show_current_state.invoke({})
    assert "Could not check course chapters" in result
    assert "Retry" in result
    assert "Build Chapters" not in result
    assert "Live chapter readiness: ready" not in result
    assert state == before


@pytest.mark.parametrize(
    "agent,required",
    [
        ("curriculum_mapper", True),
        ("skill_cleaner", True),
        ("concept_linker", True),
        ("supervisor", False),
        ("skill_finder", False),
    ],
)
def test_worker_tool_choice_reaches_actual_provider_request(
    mapping_course,
    graph_driver,
    client,
    completion_requests,
    monkeypatch,
    agent,
    required,
):
    from app.modules.marketdemandanalyst import graph as graph_module

    course, _, _, service, state = mapping_course
    add_chapter(graph_driver, course["id"])
    monkeypatch.setattr(settings, "llm_agent_model", "deepseek-v4.1-flash")
    monkeypatch.setattr(graph_module, "_COMPILED_GRAPH", None)
    monkeypatch.setattr(graph_module, "_LLM_INSTANCE", None)
    graph, _ = client.portal.call(graph_module.get_graph)
    thread = service.thread_id(course["id"], course["teacher_id"])
    try:
        with bind_tool_store(state):
            client.portal.call(
                graph.ainvoke,
                {"messages": [HumanMessage(content="Continue")], "active_agent": agent},
                {"configurable": {"thread_id": thread}},
            )
        assert len(completion_requests) == 1
        request = completion_requests[0]
        assert request.get("tool_choice", "auto") == (
            "required" if required else "auto"
        )
        assert request["stream"] is True
        if required:
            assert "transfer_to_supervisor" in {
                row["function"]["name"] for row in request["tools"]
            }
    finally:
        client.portal.call(graph.checkpointer.adelete_thread, thread)


def test_autonomous_workers_prepare_review_without_publishing_or_changing_selection(
    mapping_course, graph_driver, client, live_graph, monkeypatch
):
    from types import SimpleNamespace

    course, _, candidates, service, state = mapping_course
    add_chapter(graph_driver, course["id"])
    selected = [row["candidate_id"] for row in candidates]
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)
    monkeypatch.setattr(
        tools,
        "_get_extraction_llm",
        lambda: SimpleNamespace(
            invoke=lambda *args, **kwargs: AIMessage(
                content=json.dumps({"existing_concepts": [], "new_concepts": []})
            )
        ),
    )
    mapping = [
        {
            "candidate_id": row["candidate_id"],
            "name": row["display_name"],
            "status": "gap",
            "target_chapter": "Data pipelines",
        }
        for row in candidates
    ]
    steps = [
        ("transfer_to_curriculum_mapper", {}),
        ("get_curated_skills", {}),
        ("list_chapters", {}),
        ("save_curriculum_mapping", {"mapping_json": json.dumps(mapping)}),
        ("transfer_to_skill_cleaner", {}),
        ("load_mapped_skills", {}),
        ("compare_and_clean", {"chapter_title": "Data pipelines"}),
        ("finalize_cleaned_skills", {}),
        ("transfer_to_concept_linker", {}),
        ("extract_concepts_for_skills", {}),
        # Even an erroneous model publication attempt cannot bypass teacher approval.
        ("insert_market_skills_to_neo4j", {}),
        ("transfer_to_supervisor", {}),
    ]
    model.replies.extend(
        [
            AIMessage(
                content="", tool_calls=[{"id": f"step-{i}", "name": name, "args": args}]
            )
            for i, (name, args) in enumerate(steps)
        ]
        + [AIMessage(content="Your integration review is ready.")]
    )
    with bind_tool_store(state):
        result = client.portal.call(
            graph.ainvoke,
            {"messages": [HumanMessage(content="Map my confirmed skills")]},
            {"configurable": {"thread_id": thread}},
        )
    review = service.get_review(course["id"], course["teacher_id"])
    assert review.integration_review is not None, str(result["messages"])
    assert {row["candidate_id"] for row in review.integration_review["items"]} == set(
        selected
    )
    assert {row["candidate_id"] for row in state["curriculum_mapping"]} == set(selected)
    assert {row["candidate_id"] for row in state["selected_for_insertion"]} == set(
        selected
    )
    assert [str(value) for value in review.selected_candidate_ids] == selected
    assert review.publication_revision == 0
    assert not review.approved_references
    assert "approval through the review API is required" in str(result["messages"])
    assert result["active_agent"] == "supervisor"
    with graph_driver.session(database="neo4j") as session:
        assert (
            session.run(
                "MATCH (skill:CAREER_SKILL) RETURN count(skill) AS count"
            ).single()["count"]
            == 0
        )
    assert model.tool_choices == ["auto", *(["required"] * 11), "auto"]
