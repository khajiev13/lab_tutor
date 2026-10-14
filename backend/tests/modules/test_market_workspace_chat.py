"""Restricted entry through the real swarm and PostgreSQL checkpoints."""

import json
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


def test_explain_related_programming_and_missing_etl_is_read_only(
    db_session, client, teacher_auth_headers, live_graph
):
    from app.modules.marketdemandanalyst.schemas import (
        SkillReviewDraft,
        SkillReviewRevision,
    )
    from app.modules.occupation_reference.models import OnetOccupation
    from tests.modules.test_market_workspace_context import seed_onet

    course, run, candidates, service, _ = seed_review(
        db_session, client, teacher_auth_headers, labels=("SQL", "ETL"), mixed=True
    )
    evidence = seed_onet(db_session)[0]
    evidence.ratings = {
        "IM": {
            "scale_id": "IM",
            "value": 3.38,
            "minimum": 1,
            "maximum": 5,
            "status": "reported",
        }
    }
    occupation = db_session.get(OnetOccupation, ("30.0", "15-1252.00"))
    occupation.title = "Software Developers"
    run.config = {
        **run.config,
        "onet_release": "30.0",
        "selected_onet_occupations": [
            {"soc_code": "15-1252.00", "title": "Software Developers"}
        ],
    }
    manifest = deepcopy(run.candidate_manifest)
    manifest["candidates"][0]["onet_associations"] = [
        {
            "relation": "related",
            "evidence": {
                "id": str(evidence.id),
                "release": "30.0",
                "soc_code": "15-1252.00",
                "family": "transferable",
                "element_id": evidence.element_id,
            },
        }
    ]
    run.candidate_manifest = manifest
    db_session.commit()
    service.save_draft(
        course["id"],
        course["teacher_id"],
        SkillReviewDraft(
            run_id=run.id,
            expected_candidate_revision=1,
            expected_selection_revision=1,
            selected_candidate_ids=[candidates[0]["candidate_id"]],
            excluded_candidate_ids=[candidates[1]["candidate_id"]],
        ),
    )
    service.confirm_selection(
        course["id"],
        course["teacher_id"],
        SkillReviewRevision(
            run_id=run.id,
            expected_candidate_revision=1,
            expected_selection_revision=2,
        ),
    )
    model, _, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    before = deepcopy(
        (
            run.selected_candidate_ids,
            run.excluded_candidate_ids,
            run.selection_confirmation,
            run.publication_revision,
            run.approved_references,
            run.integration_review,
        )
    )
    repo = MarketReviewRepository(db_session)
    snapshot = deepcopy(repo.load_active_snapshot(thread))
    reply = "O*NET 30.0 reports Programming importance 3.38/5 for Software Developers. This related descriptor gives context for SQL, not an official SQL rating. ETL importance is unavailable. Teaching suggestion: use the SQL posting evidence to discuss curriculum fit and keep the explicit ETL exclusion."

    def explain_current_bundle():
        messages, tools = model.calls[-1]
        assert tools == []
        bundle = json.loads(messages[1].content.split("\n", 1)[1])
        by_name = {row["display_name"]: row for row in bundle["candidates"]}
        association = by_name["SQL"]["onet_associations"][0]
        assert association["relation"] == "related"
        assert association["evidence"]["label"] == "Programming"
        assert association["evidence"]["ratings"]["IM"]["value"] == 3.38
        assert association["evidence"]["occupation_title"] == "Software Developers"
        assert association["evidence"]["release"] == "30.0"
        assert by_name["ETL"]["onet_associations"] == []
        return AIMessage(content=reply)

    model.replies.append(explain_current_bundle)
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": "Explain SQL and ETL importance",
            "workspace_context": context(
                run_id=str(run.id),
                expected_selection_revision=2,
                candidate_ids=[row["candidate_id"] for row in candidates],
                occupation_codes=["15-1252.00"],
                metric="IM",
            ),
        },
    )
    assert response.status_code == 200, response.text
    assert state(thread).values["messages"][-1].content == reply
    assert len(reply.split()) <= 180
    db_session.expire_all()
    assert (
        run.selected_candidate_ids,
        run.excluded_candidate_ids,
        run.selection_confirmation,
        run.publication_revision,
        run.approved_references,
        run.integration_review,
    ) == before
    assert repo.load_active_snapshot(thread) == snapshot


@pytest.mark.parametrize("intent", ["explain", "propose_selection"])
def test_current_evidence_review_does_not_feed_prior_unfounded_prose_to_model(
    db_session, client, teacher_auth_headers, live_graph, intent
):
    course, run, candidates, service, _ = seed_review(
        db_session, client, teacher_auth_headers
    )
    model, graph, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    config = {"configurable": {"thread_id": thread}}
    state(thread)
    previous_claim = "A level of 4.12 proves independent senior-level coding."
    model.replies.extend(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "old-handoff",
                        "name": "transfer_to_skill_finder",
                        "args": {},
                    }
                ],
            ),
            AIMessage(content=previous_claim),
        ]
    )
    client.portal.call(
        graph.ainvoke,
        {"messages": [HumanMessage(content="Earlier occupation question")]},
        config,
    )
    before = state(thread)
    repo = MarketReviewRepository(db_session)
    snapshot = deepcopy(repo.load_active_snapshot(thread))
    selections = deepcopy((run.selected_candidate_ids, run.excluded_candidate_ids))
    question = "Explain the currently attached skill evidence."
    model.replies.append(AIMessage(content="Current evidence only; no level anchors."))
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={
            "message": question,
            "workspace_context": context(
                run_id=str(run.id),
                focused_candidate_id=candidates[0]["candidate_id"],
                intent=intent,
            ),
        },
    )
    assert response.status_code == 200, response.text
    messages, tools = model.calls[-1]
    assert [m.content for m in messages if isinstance(m, HumanMessage)] == [question]
    assert previous_claim not in str(messages)
    assert not any(isinstance(m, (AIMessage, ToolMessage)) for m in messages)
    assert "Required: Python." in str(messages)
    assert tools == ([] if intent == "explain" else ["propose_skill_selection"])
    after = state(thread)
    assert previous_claim in [m.content for m in after.values["messages"]]
    assert after.values["active_agent"] == before.values["active_agent"]
    db_session.expire_all()
    assert repo.load_active_snapshot(thread) == snapshot
    assert (run.selected_candidate_ids, run.excluded_candidate_ids) == selections


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
    from tests.modules.test_market_demand import _parse_sse

    denied = [e["data"] for e in _parse_sse(response.text) if e["event"] == "tool_end"]
    assert denied and denied[0]["status"] == "error"
    restored = client.get(
        f"/courses/{course['id']}/market-demand/history", headers=teacher_auth_headers
    ).json()
    calls = [tc for m in restored["messages"] for tc in m["toolCalls"]]
    assert calls[0]["status"] == "error"
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
    from tests.modules.test_market_demand import _parse_sse

    frames = _parse_sse(response.text)
    error = next(e["data"] for e in frames if e["event"] == "error")
    assert error["code"] == "context_stale"
    assert "Refresh context" in error["recovery"]
    assert frames[-1]["data"]["outcome"] == "failed"
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


def test_context_identity_redacted_history_and_evidence_assistant(
    db_session, client, teacher_auth_headers, live_graph
):
    import json

    from tests.modules.test_market_demand import _parse_sse

    course, run, candidates, service, _ = seed_review(
        db_session, client, teacher_auth_headers
    )
    model, _, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    url = f"/courses/{course['id']}/market-demand"
    for _ in range(2):
        model.replies.append(AIMessage(content="Collected sample evidence."))
        response = client.post(
            url + "/chat",
            headers=teacher_auth_headers,
            json={
                "message": "Explain this skill",
                "workspace_context": context(
                    run_id=str(run.id),
                    focused_candidate_id=candidates[0]["candidate_id"],
                ),
            },
        )
        frames = _parse_sse(response.text)
        resolved = next(e["data"] for e in frames if e["event"] == "context_resolved")
        assert frames[-1]["data"]["outcome"] == "completed"
        starts = [e["data"] for e in frames if e["event"] == "agent_start"]
        assert starts and all(e["agent"] == "workspace_review" for e in starts)
        assert starts[0]["displayName"] == "Evidence assistant"
        restored = client.get(url + "/history", headers=teacher_auth_headers).json()
        users = [m for m in restored["messages"] if m["role"] == "user"]
        assert users[-1]["id"] == resolved["messageId"]
        assert users[-1]["workspace_context"] == resolved["workspace_context"]
        assert "Required: Python." not in json.dumps(users[-1]["workspace_context"])
        assert restored["outcome"] == "unknown"
        assert restored["messages"][-1]["agentDisplayName"] == "Evidence assistant"
    assert len(users) == 2 and users[0]["id"] != users[1]["id"]
    raw = state(thread).values["messages"]
    assert all(m.id for m in raw if isinstance(m, HumanMessage))
    assert "workspace_context" in raw[0].additional_kwargs
    assert "Required: Python." not in str(raw)
    repo = MarketReviewRepository(db_session)
    repo.purge_vacancy_content(
        candidates[0]["evidence_references"][0]["snapshot_id"], reason="test"
    )
    repo.commit()
    history = client.get(url + "/history", headers=teacher_auth_headers).json()
    assert "Required: Python." not in json.dumps(history)
    evidence = client.get(
        url
        + "/skill-review/postings/"
        + candidates[0]["evidence_references"][0]["snapshot_id"],
        headers=teacher_auth_headers,
    )
    assert evidence.status_code == 200, evidence.text
    assert evidence.json()["status"] == "purged"
    assert evidence.json()["description_text"] is None
    assert evidence.json()["original_description"] is None
    assert evidence.json()["raw_payload"] == {}
    assert "Required: Python." not in evidence.text


def test_model_failure_has_sanitized_error_and_failed_terminal(
    db_session, client, teacher_auth_headers, live_graph
):
    from tests.modules.test_market_demand import _parse_sse

    course, run, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, _, state = live_graph
    state(service.thread_id(course["id"], course["teacher_id"]))
    model.replies.append(RuntimeError("provider key SECRET with SQL details"))
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={"message": "Explain", "workspace_context": context(run_id=str(run.id))},
    )
    frames = _parse_sse(response.text)
    error = next(e["data"] for e in frames if e["event"] == "error")
    assert error["code"] == "execution_failed"
    assert error["message"] and error["recovery"]
    assert "SECRET" not in response.text and "SQL details" not in response.text
    assert frames[-1]["data"]["outcome"] == "failed"


def test_final_checkpoint_failure_does_not_claim_completed_reply(
    db_session, client, teacher_auth_headers, live_graph, monkeypatch
):
    from tests.modules.test_market_demand import _parse_sse

    course, run, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, graph, state = live_graph
    state(service.thread_id(course["id"], course["teacher_id"]))
    original_put = graph.checkpointer.aput

    async def fail_reply_checkpoint(config, checkpoint, metadata, versions):
        messages = checkpoint["channel_values"].get("messages", [])
        if messages and isinstance(messages[-1], AIMessage):
            raise RuntimeError("checkpoint credential SECRET")
        return await original_put(config, checkpoint, metadata, versions)

    monkeypatch.setattr(graph.checkpointer, "aput", fail_reply_checkpoint)
    model.replies.append(AIMessage(content="A reply is not terminal proof."))
    response = client.post(
        f"/courses/{course['id']}/market-demand/chat",
        headers=teacher_auth_headers,
        json={"message": "Explain", "workspace_context": context(run_id=str(run.id))},
    )
    frames = _parse_sse(response.text)
    assert frames[-1]["data"]["outcome"] == "failed"
    assert any(e["event"] == "error" for e in frames)
    assert "SECRET" not in response.text


def test_detached_real_graph_reply_restores_unknown_without_terminal_proof(
    db_session, client, teacher_auth_headers, live_graph
):
    import asyncio
    import threading

    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    course, _, _, service, _ = seed_review(db_session, client, teacher_auth_headers)
    model, graph, state = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    state(thread)
    entered, proceed = threading.Event(), threading.Event()

    def delayed_reply():
        entered.set()
        assert proceed.wait(5)
        return AIMessage(content="Reply checkpointed after detachment")

    model.replies.append(delayed_reply)
    owner = ThreadStateService()

    async def detach():
        lease = await owner.claim(thread)
        stream = _sse_stream(
            graph,
            {
                "messages": [
                    HumanMessage(id="detached-user", content="Continue workflow")
                ]
            },
            {"configurable": {"thread_id": thread}},
            bound_state={},
            lease=lease,
            state_service=owner,
        )
        # The real model is blocked before token output, so cancellation of only
        # the browser waiter must retain the producer and its PostgreSQL lease.
        waiter = asyncio.create_task(anext(stream))
        assert await asyncio.to_thread(entered.wait, 3)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        await stream.aclose()
        return lease

    lease = client.portal.call(detach)
    try:
        observed = client.portal.call(ThreadStateService().execution_status, thread)
        assert observed.status == "busy"
    finally:
        proceed.set()
        client.portal.call(asyncio.wait_for, lease.finished.wait(), 5)
    assert (
        state(thread).values["messages"][-1].content
        == "Reply checkpointed after detachment"
    )
    response = client.get(
        f"/courses/{course['id']}/market-demand/history", headers=teacher_auth_headers
    )
    restored = response.json()
    assert restored["outcome"] == "unknown"
    assert restored["messages"][0]["id"] == "detached-user"
    assert restored["messages"][-1]["content"] == "Reply checkpointed after detachment"
    assert "outcome" not in state(thread).values
