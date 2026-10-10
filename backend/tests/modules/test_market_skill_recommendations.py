"""Agent advice uses durable diffs and never acts as a teacher decision."""

import json
from uuid import uuid4

import pytest
from test_market_skill_review import active_review, draft_body, review_url


def test_proposal_preserves_exclusions_official_ratings_and_versions(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    from copy import deepcopy
    from pathlib import Path

    from app.modules.occupation_reference.importer import parse_release
    from app.modules.occupation_reference.models import OnetEvidence, OnetRelease
    from app.modules.occupation_reference.repository import (
        OccupationReferenceRepository,
    )
    from app.modules.occupation_reference.service import OccupationReferenceService

    catalog = OccupationReferenceRepository(db_session)
    catalog.import_release(
        parse_release(Path(__file__).parents[1] / "fixtures" / "onet" / "31.0", "31.0"),
        activate=True,
    )
    official = next(
        row
        for row in catalog.get_evidence("31.0", ["15-2051.00"])
        if row.family == "transferable"
    )
    official_id = official.id
    original_ratings, original_rows = (
        deepcopy(official.ratings),
        deepcopy(official.source_rows),
    )
    evidence = next(
        row
        for row in OccupationReferenceService(catalog).get_skill_evidence(
            course["id"], course["teacher_id"], "31.0", ["15-2051.00"]
        )
        if row.id == official_id
    )
    run = db_session.get(MarketAnalysisRun, run_id)
    manifest = deepcopy(run.candidate_manifest)
    manifest["candidates"][0]["onet_associations"] = [
        {"relation": "broader", "evidence": evidence.model_dump(mode="json")}
    ]
    run.candidate_manifest = manifest
    db_session.commit()
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], [ids[1]]),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    state = {
        "run_id": str(run_id),
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
    }
    with bind_tool_store(state):
        result = tools.propose_skill_selection.invoke(
            {
                "changes_json": json.dumps(
                    [
                        {
                            "candidate_id": ids[1],
                            "action": "add",
                            "reason": "Teacher requested communication practice",
                        }
                    ]
                )
            }
        )
    assert "proposal" in result.lower()
    review = client.get(base, headers=teacher_auth_headers).json()
    assert review["selected_candidate_ids"] == [ids[0]]
    assert review["excluded_candidate_ids"] == [ids[1]]
    assert review["selection_revision"] == 1
    proposal = review["recommendations"][0]
    assert (
        proposal["candidate_revision"] == 1 and proposal["base_selection_revision"] == 1
    )
    assert proposal["changes"] == [
        {
            "candidate_id": ids[1],
            "action": "add",
            "reason": "Teacher requested communication practice",
        }
    ]
    db_session.expire_all()
    assert db_session.get(MarketAnalysisRun, run_id).selection_confirmation is None
    assert (
        review["candidates"][0]["onet_associations"][0]["evidence"]["ratings"]["IM"][
            "status"
        ]
        == "suppressed"
    )
    # Teacher can explicitly accept a change, including overriding an exclusion.
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, ids, [], 1),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    after = client.get(base, headers=teacher_auth_headers).json()
    assert after["recommendations"][0] == proposal
    assert (
        after["candidates"][0]["onet_associations"][0]["evidence"]["release"] == "31.0"
    )
    assert (
        after["candidates"][0]["onet_associations"][0]["evidence"]["ratings"]
        == original_ratings
    )
    db_session.expire_all()
    official = db_session.get(OnetEvidence, official_id)
    assert (
        official.release == "31.0"
        and official.ratings == original_ratings
        and official.source_rows == original_rows
    )
    assert db_session.get(OnetRelease, "31.0").status == "ready"


@pytest.mark.parametrize(
    "changes",
    [
        [{"candidate_id": str(uuid4()), "action": "add", "reason": "foreign"}],
        [{"candidate_id": str(uuid4()), "action": "approve", "reason": "publish"}],
        [],
    ],
)
def test_invalid_agent_proposal_cannot_mutate_selection(
    db_session, client, teacher_auth_headers, monkeypatch, changes
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    assert (
        client.get(review_url(course), headers=teacher_auth_headers).status_code == 200
    )
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    with bind_tool_store(
        {
            "run_id": str(run_id),
            "teacher_id": course["teacher_id"],
            "course_id": course["id"],
        }
    ):
        tools.propose_skill_selection.invoke({"changes_json": json.dumps(changes)})
    review = client.get(review_url(course), headers=teacher_auth_headers).json()
    assert review["recommendations"] == [] and review["selected_candidate_ids"] == []


def test_model_approval_loads_only_exact_teacher_confirmation(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], [ids[1]]),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    state = {
        "run_id": str(run_id),
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
    }
    with bind_tool_store(state):
        tools.approve_skill_selection.invoke(
            {"selection_json": json.dumps(["Communication"])}
        )
        assert not state.get("curated_skills")
    assert (
        client.post(
            base + "/selection-confirmation",
            json={
                "run_id": str(run_id),
                "expected_candidate_revision": 1,
                "expected_selection_revision": 1,
            },
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    with bind_tool_store(state):
        tools.approve_skill_selection.invoke(
            {"selection_json": json.dumps(["Communication"])}
        )
    assert [s["candidate_id"] for s in state["curated_skills"]] == [ids[0]]
    assert state["curated_skills"][0]["name"] == "Python"
    assert not state.get("selected_for_insertion")
    db_session.expire_all()
    assert db_session.get(MarketAnalysisRun, run_id).publication_revision == 0


@pytest.mark.anyio
async def test_actual_toolnode_persists_proposal_before_coherent_sse(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    builder = StateGraph(MessagesState)
    builder.add_node(
        "tools", ToolNode(tools.owned_sync_tools(tools.SKILL_FINDER_TOOLS))
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    node = builder.compile()
    args = {
        "changes_json": json.dumps(
            [{"candidate_id": ids[0], "action": "add", "reason": "Relevant foundation"}]
        )
    }

    diagnostics = []

    class Graph:
        async def astream(self, *unused, **kwargs):
            try:
                result = await node.ainvoke(
                    {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "propose_skill_selection",
                                        "args": args,
                                        "id": "propose",
                                    }
                                ],
                            )
                        ]
                    }
                )
            except Exception as exc:
                diagnostics.append(str(exc))
                raise
            for message in result["messages"]:
                diagnostics.append(message.content)
                yield (("skill_finder:test",), (message, {}))

    bound = {
        "run_id": str(run_id),
        "candidate_revision": 1,
        "selection_revision": 0,
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
    }
    service = ThreadStateService()
    lease = await service.claim(f"mda-{course['teacher_id']}-course-{course['id']}")
    frames = [
        frame
        async for frame in _sse_stream(
            Graph(),
            {},
            {"configurable": {"thread_id": lease.thread_id}},
            bound_state=bound,
            lease=lease,
            state_service=service,
        )
    ]
    changes = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if frame.startswith("event: skill_review_changed")
    ]
    assert changes == [
        {
            "type": "skill_review_changed",
            "run_id": str(run_id),
            "candidate_revision": 1,
            "selection_revision": 0,
            "publication_revision": 0,
        }
    ], diagnostics
    state_updates = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if frame.startswith("event: state_update")
    ]
    assert not any(
        event["stateKey"] in {"selected_candidate_ids", "excluded_candidate_ids"}
        for event in state_updates
    )
    durable = client.get(review_url(course), headers=teacher_auth_headers).json()
    assert durable["recommendations"][0]["changes"][0]["candidate_id"] == ids[0]
    assert durable["selected_candidate_ids"] == []


def test_stale_confirmation_cannot_drive_mapping(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], []),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/selection-confirmation",
            json={
                "run_id": str(run_id),
                "expected_candidate_revision": 1,
                "expected_selection_revision": 1,
            },
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[1]], [ids[0]], 1),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    state = {
        "run_id": str(run_id),
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
        "curated_skills": [{"candidate_id": ids[0]}],
    }
    with bind_tool_store(state):
        result = tools.approve_skill_selection.invoke(
            {"selection_json": json.dumps(["Python"])}
        )
    assert "confirm" in result.lower()
    assert not state.get("curated_skills")


def test_failed_proposal_snapshot_write_does_not_acknowledge_or_persist_advice(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    monkeypatch.setattr(
        tools,
        "SessionLocal",
        lambda: Session(bind=db_session.get_bind()),
        raising=False,
    )
    state = {
        "run_id": str(run_id),
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
    }

    def fail_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE mda_thread_state"):
            raise RuntimeError("simulated proposal snapshot failure")

    event.listen(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    try:
        with bind_tool_store(state):
            result = tools.propose_skill_selection.invoke(
                {
                    "changes_json": json.dumps(
                        [
                            {
                                "candidate_id": ids[0],
                                "action": "add",
                                "reason": "Foundation",
                            }
                        ]
                    )
                }
            )
        assert "failed" in result.lower()
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", fail_snapshot)
    assert not state.get("skill_review_change_id")
    assert (
        client.get(review_url(course), headers=teacher_auth_headers).json()[
            "recommendations"
        ]
        == []
    )


@pytest.mark.anyio
async def test_cancelled_actual_proposal_tool_drains_sql_commit_before_final_snapshot(
    db_session, client, teacher_auth_headers, monkeypatch
):
    import asyncio
    import threading

    from langchain_core.messages import AIMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    builder = StateGraph(MessagesState)
    builder.add_node(
        "tools", ToolNode(tools.owned_sync_tools(tools.SKILL_FINDER_TOOLS))
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    compiled = builder.compile()
    entered, proceed = threading.Event(), threading.Event()
    cancelled = asyncio.Event()

    def delay_snapshot(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE mda_thread_state"):
            entered.set()
            assert proceed.wait(5)

    event.listen(db_session.get_bind(), "before_cursor_execute", delay_snapshot)

    class Graph:
        async def astream(self, *args, **kwargs):
            try:
                result = await compiled.ainvoke(
                    {
                        "messages": [
                            AIMessage(
                                content="",
                                tool_calls=[
                                    {
                                        "name": "propose_skill_selection",
                                        "args": {
                                            "changes_json": json.dumps(
                                                [
                                                    {
                                                        "candidate_id": ids[0],
                                                        "action": "add",
                                                        "reason": "Foundation",
                                                    }
                                                ]
                                            )
                                        },
                                        "id": "proposal",
                                    }
                                ],
                            )
                        ]
                    }
                )
                for message in result["messages"]:
                    yield (("skill_finder:test",), (message, {}))
            except asyncio.CancelledError:
                cancelled.set()
                raise

    service = ThreadStateService()
    lease = await service.claim(f"mda-{course['teacher_id']}-course-{course['id']}")
    bound = {
        "run_id": str(run_id),
        "candidate_revision": 1,
        "selection_revision": 0,
        "teacher_id": course["teacher_id"],
        "course_id": course["id"],
    }
    stream = _sse_stream(
        Graph(),
        {},
        {"configurable": {"thread_id": lease.thread_id}},
        bound_state=bound,
        lease=lease,
        state_service=service,
    )

    async def consume():
        async for _unused in stream:
            pass

    consumer = asyncio.create_task(consume())
    try:
        assert await asyncio.to_thread(entered.wait, 3)
        lease.producer.cancel()
        await asyncio.wait_for(cancelled.wait(), 3)
        with pytest.raises(ThreadBusy):
            await ThreadStateService().claim(lease.thread_id)
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        restored = await service.load(lease.thread_id)
        assert restored["skill_review_change_id"] == bound["skill_review_change_id"]
        durable = client.get(review_url(course), headers=teacher_auth_headers).json()
        assert durable["recommendations"][0]["changes"][0]["candidate_id"] == ids[0]
        assert (
            durable["selected_candidate_ids"] == []
            and durable["publication_revision"] == 0
        )
    finally:
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        await asyncio.wait_for(consumer, 5)
        event.remove(db_session.get_bind(), "before_cursor_execute", delay_snapshot)


def test_candidate_refresh_invalidates_mapping_shortlist_reader(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.models import MarketAnalysisRun
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], []),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    assert (
        client.post(
            base + "/selection-confirmation",
            json={
                "run_id": str(run_id),
                "expected_candidate_revision": 1,
                "expected_selection_revision": 1,
            },
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    db_session.expire_all()
    run = db_session.get(MarketAnalysisRun, run_id)
    run.candidate_revision += 1
    run.selection_confirmation = None
    db_session.commit()
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    with bind_tool_store(
        {
            "run_id": str(run_id),
            "teacher_id": course["teacher_id"],
            "course_id": course["id"],
            "curated_skills": [{"candidate_id": ids[0], "name": "Python"}],
        }
    ):
        result = tools.get_curated_skills.invoke({})
        assert not tools.tool_store.get("curated_skills")
        assert "confirm" in result.lower()


def test_actual_advice_reader_exposes_current_ids_and_decisions_without_mutation(
    db_session, client, teacher_auth_headers, monkeypatch
):
    from sqlalchemy.orm import Session

    from app.modules.marketdemandanalyst import tools
    from app.modules.marketdemandanalyst.state import bind_tool_store

    course, run_id, ids = active_review(db_session, client, teacher_auth_headers)
    base = review_url(course)
    assert (
        client.put(
            base + "/draft",
            json=draft_body(run_id, [ids[0]], [ids[1]]),
            headers=teacher_auth_headers,
        ).status_code
        == 200
    )
    before = client.get(base, headers=teacher_auth_headers).json()
    monkeypatch.setattr(
        tools, "SessionLocal", lambda: Session(bind=db_session.get_bind())
    )
    with bind_tool_store(
        {
            "run_id": str(run_id),
            "teacher_id": course["teacher_id"],
            "course_id": course["id"],
            "extracted_skills": [
                {
                    "name": "Forged cache",
                    "category": "technical",
                    "candidate_id": str(uuid4()),
                }
            ],
        }
    ):
        result = tools.get_skills_by_category.invoke({})
    assert ids[0] in result and ids[1] in result
    data = json.loads(result)
    assert data["selected_candidate_ids"] == [ids[0]] and data[
        "excluded_candidate_ids"
    ] == [ids[1]]
    assert data["candidate_revision"] == 1 and data["selection_revision"] == 1
    assert {c["display_name"] for c in data["candidates"]} == {
        "Python",
        "Communication",
    }
    assert "identity_key" not in result
    assert client.get(base, headers=teacher_auth_headers).json() == before
