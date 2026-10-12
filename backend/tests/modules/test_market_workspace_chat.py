"""Restricted entry through the real swarm and PostgreSQL checkpoints."""

from copy import deepcopy

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.modules.marketdemandanalyst import graph as graph_module
from app.modules.marketdemandanalyst.repository import MarketReviewRepository
from tests.market_skill_fixtures import seed_review
from tests.modules.test_market_workspace_context import context


class ScriptedModel(BaseChatModel):
    replies: list = Field(default_factory=list)
    calls: list = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "workspace-provider-double"

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=[tool.name for tool in tools])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        outstanding = set()
        for message in messages:
            if isinstance(message, AIMessage):
                outstanding.update(
                    call["id"]
                    for call in [*message.tool_calls, *message.invalid_tool_calls]
                )
            elif isinstance(message, ToolMessage):
                outstanding.discard(message.tool_call_id)
            elif isinstance(message, HumanMessage):
                assert not outstanding, "Unmatched calls leaked into next workflow"
        assert not outstanding, "Provider received unfinished tool history"
        self.calls.append((deepcopy(messages), kwargs.get("tools", [])))
        reply = self.replies.pop(0)
        if callable(reply):
            reply = reply()
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])


@pytest.fixture
def live_graph(client, monkeypatch):
    model = ScriptedModel()
    monkeypatch.setattr(graph_module, "_create_llm", lambda: model)
    monkeypatch.setattr(graph_module, "_COMPILED_GRAPH", None)
    monkeypatch.setattr(graph_module, "_LLM_INSTANCE", None)
    monkeypatch.setattr(graph_module, "_ASYNC_CHECKPOINTER", None)
    monkeypatch.setattr(graph_module, "_CONN_POOL", None)
    graph, _ = client.portal.call(graph_module.get_graph)
    threads = set()

    def state(thread):
        threads.add(thread)
        return client.portal.call(
            graph.aget_state, {"configurable": {"thread_id": thread}}
        )

    yield model, graph, state

    async def cleanup():
        for thread in threads:
            await graph.checkpointer.adelete_thread(thread)
        await graph_module._CONN_POOL.close()
        from app.core.database import async_engine

        await async_engine.dispose()

    client.portal.call(cleanup)


def test_workflow_explain_workflow_preserves_active_agent_and_sql(
    db_session, client, teacher_auth_headers, live_graph
):
    course, run, candidates, _, _ = seed_review(
        db_session, client, teacher_auth_headers
    )
    model, graph, state = live_graph
    # Derive the actual persisted thread from the service contract.
    from app.modules.marketdemandanalyst.review_service import SkillReviewService

    thread = SkillReviewService.thread_id(course["id"], course["teacher_id"])
    config = {"configurable": {"thread_id": thread}}
    state(thread)
    model.replies.extend(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "handoff-1", "name": "transfer_to_skill_finder", "args": {}}
                ],
            ),
            AIMessage(content="Workflow ready"),
        ]
    )
    client.portal.call(
        graph.ainvoke, {"messages": [HumanMessage(content="Start workflow")]}, config
    )
    before = state(thread)
    repo = MarketReviewRepository(db_session)
    before_snapshot = deepcopy(repo.load_active_snapshot(thread))
    before_config = deepcopy(run.config)
    before_selection = deepcopy(
        (run.selected_candidate_ids, run.excluded_candidate_ids)
    )

    def detached_reply():
        assert not db_session.in_transaction(), (
            "Context SQL transaction held across inference"
        )
        return AIMessage(content="This is evidence from the collected sample.")

    model.replies.append(detached_reply)
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Explain this skill",
            "workspace_context": context(
                run_id=str(run.id), focused_candidate_id=candidates[0]["candidate_id"]
            ),
        },
    )
    assert response.status_code == 200, response.text
    after = state(thread)
    assert model.calls[-1][1] == [], "Explain must expose zero tools"
    assert (
        after.values["active_agent"] == before.values["active_agent"] == "skill_finder"
    )
    assert after.next == ()
    db_session.expire_all()
    assert run.config == before_config
    assert (run.selected_candidate_ids, run.excluded_candidate_ids) == before_selection
    assert repo.load_active_snapshot(thread) == before_snapshot
    assert set(after.values) <= {"messages", "active_agent"}
    assert "Required: Python." not in str(after.values)
    assert "Required: Python." in str(model.calls[-1][0])
    model.replies.append(AIMessage(content="Workflow continues"))
    client.portal.call(
        graph.ainvoke, {"messages": [HumanMessage(content="Continue workflow")]}, config
    )
    assert "fetch_jobs" in model.calls[-1][1]
    final = state(thread)
    assert [
        m.content for m in final.values["messages"] if isinstance(m, HumanMessage)
    ] == ["Start workflow", "Explain this skill", "Continue workflow"]


def test_context_rejects_unfinished_checkpoint_without_model_or_checkpoint_mutation(
    db_session, client, teacher_auth_headers, live_graph
):
    course, run, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, graph, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    config = {"configurable": {"thread_id": thread}}
    model.replies.append(RuntimeError("provider interrupted"))
    with pytest.raises(RuntimeError, match="provider interrupted"):
        client.portal.call(
            graph.ainvoke, {"messages": [HumanMessage(content="Workflow")]}, config
        )
    before = state(thread)
    assert before.next
    count = len(model.calls)
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={"message": "Explain", "workspace_context": context(run_id=str(run.id))},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "workflow_recovery_required"
    assert len(model.calls) == count
    assert state(thread) == before


@pytest.mark.parametrize("intent", ["explain", "propose_selection"])
@pytest.mark.parametrize(
    "tool_name", ["fetch_jobs", "delete_conversation", "insert_market_skills_to_neo4j"]
)
def test_fabricated_mutating_calls_do_nothing_and_leave_valid_next_workflow(
    db_session, client, teacher_auth_headers, live_graph, monkeypatch, intent, tool_name
):
    from app.modules.marketdemandanalyst.job_sources import JobSourceService

    provider_calls = []
    monkeypatch.setattr(
        JobSourceService, "fetch", lambda *a, **k: provider_calls.append(k)
    )
    course, run, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, graph, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    repo = MarketReviewRepository(db_session)
    before = deepcopy(repo.load_active_snapshot(thread))
    model.replies.append(
        AIMessage(
            content="", tool_calls=[{"id": "fabricated", "name": tool_name, "args": {}}]
        )
    )
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Do it",
            "workspace_context": context(run_id=str(run.id), intent=intent),
        },
    )
    assert response.status_code == 200, response.text
    assert model.calls[-1][1] == (
        [] if intent == "explain" else ["propose_skill_selection"]
    )
    assert provider_calls == []
    db_session.expire_all()
    assert repo.load_active_snapshot(thread) == before
    assert run.recommendations == []
    snapshot = state(thread)
    assert snapshot.next == ()
    assert any(
        isinstance(m, ToolMessage)
        and m.tool_call_id == "fabricated"
        and m.status == "error"
        for m in snapshot.values["messages"]
    )
    model.replies.append(AIMessage(content="Workflow can continue"))
    client.portal.call(
        graph.ainvoke,
        {"messages": [HumanMessage(content="Continue workflow")]},
        {"configurable": {"thread_id": thread}},
    )
    assert "transfer_to_skill_finder" in model.calls[-1][1]
    assert state(thread).values["messages"][-1].content == "Workflow can continue"


def test_proposal_commits_immutable_diff_preserves_exclusions_and_fresh_sql_snapshot(
    db_session, client, teacher_auth_headers, live_graph
):
    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.schemas import SkillReviewDraft

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("Python", "Communication")
    )
    cid = candidates[1]["candidate_id"]
    service.save_draft(
        course["id"],
        course["teacher_id"],
        SkillReviewDraft(
            **revision.model_dump(),
            selected_candidate_ids=[candidates[0]["candidate_id"]],
            excluded_candidate_ids=[cid],
        ),
    )
    model, _, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    before_selection = (
        deepcopy(run.selected_candidate_ids),
        deepcopy(run.excluded_candidate_ids),
        run.selection_revision,
    )

    def concurrent_snapshot():
        with SessionLocal() as db:
            repo = MarketReviewRepository(db)
            current = repo.load_active_snapshot(thread)
            current["course_title"] = "Newer committed snapshot during inference"
            repo.save_configuration_snapshot(thread, current)
            repo.commit()
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "proposal",
                    "name": "propose_skill_selection",
                    "args": {
                        "changes": [
                            {
                                "candidate_id": cid,
                                "action": "add",
                                "reason": "Supported evidence merits teacher review.",
                            }
                        ],
                        "expected_selection_revision": 999,
                        "teacher_id": 999,
                    },
                }
            ],
        )

    model.replies.append(concurrent_snapshot)
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Suggest changes",
            "workspace_context": context(
                run_id=str(run.id),
                intent="propose_selection",
                expected_selection_revision=2,
            ),
        },
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert len(run.recommendations) == 1
    proposal = run.recommendations[0]
    assert proposal["candidate_revision"] == 1
    assert proposal["base_selection_revision"] == 2
    assert proposal["changes"][0]["candidate_id"] == cid
    assert (
        run.selected_candidate_ids,
        run.excluded_candidate_ids,
        run.selection_revision,
    ) == before_selection
    saved = MarketReviewRepository(db_session).load_active_snapshot(thread)
    assert saved["skill_review_change_id"] == proposal["id"]
    assert saved["course_title"] == "Newer committed snapshot during inference"
    assert state(thread).next == ()
    assert "skill_review_changed" in response.text


def test_proposal_rejects_revision_that_became_stale_during_model_call(
    db_session, client, teacher_auth_headers, live_graph
):
    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.review_service import SkillReviewService
    from app.modules.marketdemandanalyst.schemas import SkillReviewDraft

    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers
    )
    model, _, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    cid = candidates[0]["candidate_id"]

    def advance_revision():
        with SessionLocal() as db:
            current = SkillReviewService(MarketReviewRepository(db))
            current.save_draft(
                course["id"],
                course["teacher_id"],
                SkillReviewDraft(
                    **revision.model_dump(),
                    selected_candidate_ids=[],
                    excluded_candidate_ids=[cid],
                ),
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "stale-proposal",
                    "name": "propose_skill_selection",
                    "args": {
                        "changes": [
                            {
                                "candidate_id": cid,
                                "action": "add",
                                "reason": "Evidence supports it.",
                            }
                        ]
                    },
                }
            ],
        )

    model.replies.append(advance_revision)
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Suggest",
            "workspace_context": context(
                run_id=str(run.id), intent="propose_selection"
            ),
        },
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert run.recommendations == []
    assert run.selection_revision == 2
    assert run.selected_candidate_ids == []
    assert run.excluded_candidate_ids == [cid]
    checkpoint = state(thread)
    assert checkpoint.next == ("workspace_review",)
    assert "reload before saving" in checkpoint.tasks[0].error
    snapshot = MarketReviewRepository(db_session).load_active_snapshot(thread)
    assert snapshot["selection_revision"] == 2
    assert snapshot["excluded_candidate_ids"] == [cid]
    model.replies.append(AIMessage(content="Refreshed explanation"))
    retry = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Explain current revision",
            "workspace_context": context(
                run_id=str(run.id),
                expected_selection_revision=2,
            ),
        },
    )
    assert retry.status_code == 200, retry.text
    assert state(thread).next == ()
    assert state(thread).values["messages"][-1].content == "Refreshed explanation"
    model.replies.append(AIMessage(content="Workflow after failed proposal"))
    graph = graph_module._COMPILED_GRAPH
    client.portal.call(
        graph.ainvoke,
        {"messages": [HumanMessage(content="Continue workflow")]},
        {"configurable": {"thread_id": thread}},
    )
    assert "transfer_to_skill_finder" in model.calls[-1][1]
    assert [
        m.content
        for m in state(thread).values["messages"]
        if isinstance(m, HumanMessage)
    ] == [
        "Suggest",
        "Explain current revision",
        "Continue workflow",
    ]


def test_reference_chat_does_not_create_run_or_sql_snapshot(
    db_session, client, teacher_auth_headers, live_graph
):
    from sqlalchemy import func, select

    from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
    from app.modules.marketdemandanalyst.review_service import SkillReviewService
    from tests.modules.test_market_workspace_context import seed_onet

    course = client.post(
        "/courses", json={"title": "Reference only"}, headers=teacher_auth_headers
    ).json()
    seed_onet(db_session)
    model, _, state = live_graph
    thread = SkillReviewService.thread_id(course["id"], course["teacher_id"])
    state(thread)
    model.replies.append(AIMessage(content="Reference explanation"))
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Explain importance",
            "workspace_context": {
                "kind": "occupation_reference",
                "version": 1,
                "intent": "explain",
                "release": "30.0",
                "occupation_codes": ["15-1252.00"],
                "element_ids": [],
                "metric": "IM",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert model.calls[-1][1] == []
    assert db_session.scalar(select(func.count()).select_from(MarketAnalysisRun)) == 0
    assert db_session.get(MDAThreadState, thread) is None
    assert state(thread).next == ()


def test_malformed_tool_call_does_not_poison_the_next_workflow(
    db_session, client, teacher_auth_headers, live_graph
):
    course, run, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, graph, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    model.replies.append(
        AIMessage(
            content="",
            invalid_tool_calls=[
                {
                    "id": "malformed",
                    "name": "fetch_jobs",
                    "args": "{",
                    "error": "invalid JSON",
                }
            ],
        )
    )
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={"message": "Explain", "workspace_context": context(run_id=str(run.id))},
    )
    assert response.status_code == 200
    model.replies.append(AIMessage(content="Workflow remains usable"))
    client.portal.call(
        graph.ainvoke,
        {"messages": [HumanMessage(content="Continue workflow")]},
        {"configurable": {"thread_id": thread}},
    )
    assert state(thread).next == ()
    assert state(thread).values["messages"][-1].content == "Workflow remains usable"
