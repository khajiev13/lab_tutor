"""Real SQL, compiled routing and controlled external transports for priority review."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command
from langgraph_swarm import SwarmState
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings
from app.modules.marketdemandanalyst import graph as graph_module
from app.modules.marketdemandanalyst import state
from app.modules.marketdemandanalyst.models import MarketAnalysisRun, MDAThreadState
from app.modules.marketdemandanalyst.repository import (
    MarketReviewRepository,
    ThreadStateRepository,
)
from app.modules.marketdemandanalyst.review_service import SkillReviewService
from app.modules.marketdemandanalyst.routes import _sse_stream
from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService
from app.modules.marketdemandanalyst.workspace_chat import WorkspaceRuntimeContext
from tests.market_priority_fixtures import seed_priority_case
from tests.modules.test_market_priority_service import ModelTransport


def events(frames):
    return [
        json.loads(frame.split("data: ", 1)[1]) for frame in frames if "data: " in frame
    ]


@pytest.fixture
def flow_case(db_session, client, teacher_auth_headers, monkeypatch):
    from app.modules.marketdemandanalyst.priority_service import SkillPriorityService

    case = seed_priority_case(db_session, client, teacher_auth_headers)
    from app.modules.occupation_reference.models import OnetEvidence

    row = db_session.get(OnetEvidence, case.reference_id)
    row.ratings = {
        "IM": {
            "scale_id": "IM",
            "value": 4.5,
            "minimum": 1,
            "maximum": 5,
            "status": "reported",
            "date": None,
            "quality": {},
        }
    }
    # Return to the real pre-confirmation teacher decision without granting mapping.
    case.run.selection_confirmation = None
    case.run.config = {**case.run.config, "country": "Uzbekistan"}
    db_session.commit()
    case.before = case.teacher_decisions()
    case.factory = sessionmaker(bind=case.engine)
    case.state_service = ThreadStateService(ThreadStateRepository(case.factory))
    case.model = ModelTransport(case)
    case.transport_errors = []
    original_transport = case.model.ainvoke

    async def checked_transport(messages, *, config):
        try:
            return await original_transport(messages, config=config)
        except Exception as exc:
            case.transport_errors.append(repr(exc))
            raise

    case.model.ainvoke = checked_transport
    case.priority = SkillPriorityService(
        session_factory=case.factory, llm_factory=case.model.factory
    )
    case.visited = []
    monkeypatch.setattr(settings, "market_skill_priority_enabled", True)
    monkeypatch.setattr(settings, "llm_agent_model", "gpt-4o-mini")
    from app.modules.marketdemandanalyst import priority_service, tools

    monkeypatch.setattr(
        tools,
        "get_market_source_service",
        lambda: SimpleNamespace(extraction_is_complete=lambda *args: False),
    )

    monkeypatch.setattr(
        priority_service, "get_skill_priority_service", lambda: case.priority
    )
    monkeypatch.setattr(graph_module, "_COMPILED_GRAPH", None)
    monkeypatch.setattr(graph_module, "_LLM_INSTANCE", None)

    class ReviewModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, *args, **kwargs):
            result = super()._generate(messages, *args, **kwargs)
            if result.generations[0].message.content:
                case.visited.append("skill_finder")
            return result

    original_analyst = graph_module.skill_priority_analyst

    async def observed_analyst(
        state: SwarmState, runtime: Runtime[WorkspaceRuntimeContext]
    ) -> Command:
        case.visited.append("skill_priority_analyst")
        return await original_analyst(state, runtime)

    monkeypatch.setattr(graph_module, "skill_priority_analyst", observed_analyst)
    model = ReviewModel(
        responses=[AIMessage(content="Choose skills and Confirm Selection.")]
    )
    monkeypatch.setattr(graph_module, "_create_llm", lambda: model)

    async def saver():
        return MemorySaver()

    monkeypatch.setattr(graph_module, "_get_async_checkpointer", saver)
    # Replace only external extraction work; keep the actual parent handoff and compiled graph.
    from app.modules.marketdemandanalyst.extractor import _return_to_skill_finder

    def extracted(snapshot):
        case.visited.append("skill_extractor")
        return _return_to_skill_finder(snapshot)

    extractor = StateGraph(SwarmState)
    extractor.add_node("completed_extraction", extracted)
    extractor.add_edge(START, "completed_extraction")
    monkeypatch.setattr(graph_module, "skill_extractor_subgraph", extractor.compile())

    async def open_stream(*, start="skill_extractor", bound=None):
        case.lease = await case.state_service.claim(case.thread_id)
        case.bound = bound or await case.state_service.load(case.thread_id)
        case.bound.update(
            course_id=case.scope.course_id,
            teacher_id=case.scope.teacher_id,
            candidate_revision=case.scope.expected_candidate_revision,
        )
        case.bound["extracted_skills"] = deepcopy(case.candidates)
        compiled, _ = await graph_module.get_graph()
        case.compiled = compiled
        case.config = {"configurable": {"thread_id": case.thread_id}}
        model.responses = (
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "start_extraction", "args": {}, "id": "extraction-1"}
                    ],
                )
            ]
            if start == "skill_extractor"
            else []
        ) + [AIMessage(content="Choose skills and Confirm Selection.")]
        return _sse_stream(
            compiled,
            {
                "active_agent": "skill_finder",
                "messages": [HumanMessage(content="Continue with the selected jobs.")],
            },
            case.config,
            bound_state=case.bound,
            lease=case.lease,
            state_service=case.state_service,
            runtime_context=WorkspaceRuntimeContext(
                course_id=case.scope.course_id, teacher_id=case.scope.teacher_id
            ),
        )

    case.open_stream = open_stream
    case.client, case.headers = client, teacher_auth_headers
    yield case
    state.tool_store.clear()


@pytest.mark.anyio
async def test_extraction_runs_priority_before_existing_review(flow_case):
    case = flow_case
    stream = await case.open_stream()
    frames = [frame async for frame in stream]
    saved = case.reload().priority_assessment
    assert saved is not None, frames
    assert saved["status"] == "ready", (
        saved["contexts"],
        saved["error_reasons"],
        saved["results"][:1],
        [item["phase"] for item in case.model.calls],
        case.transport_errors,
    )
    checkpoint = await case.compiled.aget_state(case.config)
    results = [
        m
        for m in checkpoint.values["messages"]
        if isinstance(m, ToolMessage) and m.tool_call_id == "extraction-1"
    ]
    assert len(results) == 1
    assert case.bound["skill_review_change_id"] == saved["assessment_id"]
    assert case.visited == ["skill_extractor", "skill_priority_analyst", "skill_finder"]
    assert checkpoint.values["active_agent"] == "skill_finder"
    assert "ThreadLease" not in repr(checkpoint.values)
    assert "lease" not in case.bound
    assert case.teacher_decisions() == case.before
    assert [item for item in events(frames) if item["type"] == "stream_end"] == [
        {"type": "stream_end", "outcome": "completed"}
    ]
    assert any(item["type"] == "skill_review_changed" for item in events(frames))
    assert "Choose skills" in "".join(item.get("delta", "") for item in events(frames))


@pytest.mark.anyio
async def test_progress_arrives_before_delayed_model_finishes(flow_case):
    case = flow_case
    release = asyncio.Event()

    async def delayed(payload):
        await release.wait()

    case.model.hook = delayed
    stream = await case.open_stream()
    frames = []
    try:
        async with asyncio.timeout(3):
            async for frame in stream:
                frames.append(frame)
                if any(
                    item.get("stateKey") == "skill_priority_status"
                    and item["value"]["status"] == "running"
                    for item in events([frame])
                ):
                    break
        assert not release.is_set()
        assert case.reload().priority_assessment["status"] == "running"
    finally:
        release.set()
        frames.extend([frame async for frame in stream])
    progress = [
        item["value"]
        for item in events(frames)
        if item.get("stateKey") == "skill_priority_status"
    ]
    assert progress[0]["message"] == "Assessing skill importance…"
    assert progress[-1]["status"] == "ready" and progress[-1]["message"] == ""
    assert all(
        set(item) == {"assessment_id", "status", "deadline_at", "message"}
        for item in progress
    )


@pytest.mark.anyio
async def test_priority_timeout_returns_to_existing_review(flow_case):
    case = flow_case
    original = case.model.ainvoke

    async def failed(messages, *, config):
        raise TimeoutError("controlled external timeout")

    case.model.ainvoke = failed
    frames = [frame async for frame in await case.open_stream()]
    assert case.reload().priority_assessment["status"] == "unavailable"
    assert case.teacher_decisions() == case.before
    assert events(frames)[-1] == {"type": "stream_end", "outcome": "completed"}
    assert any("Choose skills" in item.get("delta", "") for item in events(frames))
    case.model.ainvoke = original


@pytest.mark.anyio
async def test_disconnect_finishes_under_original_lease_and_reloads(flow_case):
    from app.modules.marketdemandanalyst.thread_state_service import ThreadBusy

    case = flow_case
    release = asyncio.Event()

    async def delayed(payload):
        await release.wait()

    case.model.hook = delayed
    stream = await case.open_stream()
    try:
        async with asyncio.timeout(3):
            async for frame in stream:
                if any(
                    item.get("stateKey") == "skill_priority_status"
                    and item["value"]["status"] == "running"
                    for item in events([frame])
                ):
                    break
        await stream.aclose()
        with pytest.raises(ThreadBusy):
            await ThreadStateService().claim(case.thread_id)
    finally:
        release.set()
        await asyncio.wait_for(case.lease.finished.wait(), 5)
    restored = await ThreadStateService().load(case.thread_id)
    assert restored["skill_priority_status"]["status"] == "ready"
    assert case.reload().priority_assessment["status"] == "ready"


@pytest.mark.anyio
@pytest.mark.parametrize("expired", [False, True])
async def test_pending_guidance_cannot_be_skipped_after_new_extraction(
    flow_case, expired
):
    case = flow_case
    with case.factory() as db:
        prior = case.assessment.model_copy(deep=True)
        if expired:
            prior.deadline_at = datetime.now(UTC) - timedelta(seconds=1)
        # Compute a valid persisted running fingerprint with the service's owned source inputs.
        inputs = case.priority._read(case.scope)
        case.priority._enrich(inputs, [])
        from app.modules.marketdemandanalyst.priority_service import (
            PROMPT_VERSION,
            configured_priority_model,
        )

        prior.prompt_version = PROMPT_VERSION
        prior.model_id = configured_priority_model()
        prior.input_fingerprint = case.priority._fingerprint(
            inputs, [], prior.release, prior.model_id
        )
        db.get(
            MarketAnalysisRun, case.scope.run_id
        ).priority_assessment = prior.model_dump(mode="json")
        row = db.get(MDAThreadState, case.thread_id)
        row.state_json = {
            **row.state_json,
            "skill_priority_status": {
                "assessment_id": str(prior.assessment_id),
                "status": "running",
                "deadline_at": prior.deadline_at.isoformat(),
                "message": "Assessing skill importance…",
            },
        }
        db.commit()
    frames = [frame async for frame in await case.open_stream(start="skill_finder")]
    saved = case.reload().priority_assessment
    assert saved["assessment_id"] == str(prior.assessment_id)
    assert saved["status"] == ("unavailable" if expired else "ready")
    assert case.visited == [
        "skill_priority_analyst",
        "skill_finder",
    ]  # Recovery never reruns extraction.
    if expired:
        assert not case.model.calls
    assert events(frames)[-1]["outcome"] == "completed"
    assert case.teacher_decisions() == case.before


@pytest.mark.anyio
async def test_review_get_never_calls_model_and_exposes_matching_guidance(flow_case):
    case = flow_case
    _ = [frame async for frame in await case.open_stream()]
    count = len(case.model.calls)
    with case.factory() as db:
        review = SkillReviewService(MarketReviewRepository(db)).get_review(
            case.scope.course_id, case.scope.teacher_id
        )
    assert review.priority_assessment is not None
    assert review.priority_assessment.status == "ready"
    assert review.candidates[0].priority.value == 4.5
    assert review.categories[0].priority.value == 4.5
    from app.modules.marketdemandanalyst.tools import get_skills_by_category

    with state.bind_tool_store(case.bound):
        advice = json.loads(get_skills_by_category.invoke({}))
    assert advice["priority_assessment"]["assessment_id"] == str(
        review.priority_assessment.assessment_id
    )
    assert advice["candidates"][0]["priority"]["value"] == 4.5
    assert len(case.model.calls) == count
    response = case.client.get(
        f"/courses/{case.scope.course_id}/market-demand/skill-review",
        headers=case.headers,
    )
    assert response.status_code == 200
    assert response.json()["priority_assessment"]["status"] == "ready"
    assert len(case.model.calls) == count


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["disabled", "membership", "meaning", "policy"])
async def test_changed_inputs_never_expose_sortable_priority(
    flow_case, mutation, monkeypatch
):
    case = flow_case
    _ = [frame async for frame in await case.open_stream()]
    assert case.reload().priority_assessment is not None
    with case.factory() as db:
        run = db.get(MarketAnalysisRun, case.scope.run_id)
        if mutation == "disabled":
            monkeypatch.setattr(settings, "market_skill_priority_enabled", False)
        elif mutation == "membership":
            thread = db.get(MDAThreadState, case.thread_id)
            thread.state_json = {**thread.state_json, "job_groups": {"Other": [0]}}
        elif mutation == "meaning":
            manifest = deepcopy(run.candidate_manifest)
            manifest["candidates"][0]["display_name"] = "Different competency"
            run.candidate_manifest = manifest
        else:
            run.priority_assessment = {
                **run.priority_assessment,
                "policy_version": "old",
            }
        db.commit()
        review = SkillReviewService(MarketReviewRepository(db)).get_review(
            case.scope.course_id, case.scope.teacher_id
        )
        assert all(candidate.priority is None for candidate in review.candidates)
        assert all(category.priority is None for category in review.categories)
        assert (
            review.priority_assessment is None
            if mutation == "disabled"
            else review.priority_assessment.status == "stale"
        )


@pytest.mark.anyio
async def test_removed_evidence_redacts_priority_explanation(flow_case):
    case = flow_case
    _ = [frame async for frame in await case.open_stream()]
    with case.factory() as db:
        run = db.get(MarketAnalysisRun, case.scope.run_id)
        assessment = deepcopy(run.priority_assessment)
        assessment["results"][0]["explanation"] = "COPIED PRIVATE SOURCE"
        assessment["contexts"][0]["rationale"] = "COPIED PRIVATE SOURCE"
        assessment["references"][0]["definition"] = "COPIED PRIVATE SOURCE"
        run.priority_assessment = assessment
        db.commit()
        MarketReviewRepository(db).purge_vacancy_content(
            UUID(next(iter(case.snapshots))), reason="Provider removed posting"
        )
        db.commit()
    saved = case.reload().priority_assessment
    assert saved["status"] == "stale"
    assert "COPIED PRIVATE SOURCE" not in json.dumps(saved)
    assert saved["summaries"] == {"candidates": {}, "categories": {}}


@pytest.mark.anyio
@pytest.mark.parametrize("legacy", [False, True])
async def test_disabled_and_legacy_flows_keep_existing_review(
    flow_case, monkeypatch, legacy
):
    case = flow_case
    bound = await case.state_service.load(case.thread_id)
    if legacy:
        bound.pop("run_id")
    else:
        monkeypatch.setattr(settings, "market_skill_priority_enabled", False)
    frames = [frame async for frame in await case.open_stream(bound=bound)]
    assert case.reload().priority_assessment is None
    assert not case.model.calls
    assert events(frames)[-1] == {"type": "stream_end", "outcome": "completed"}
    assert any("Choose skills" in item.get("delta", "") for item in events(frames))


@pytest.mark.anyio
async def test_unknown_custom_data_never_becomes_teacher_text_or_status():
    class CustomGraph:
        async def astream(self, *args, **kwargs):
            yield (), "custom", {"model_json": "PRIVATE MODEL CHAIN"}
            yield (
                (),
                "custom",
                {
                    "type": "skill_priority_status",
                    "value": {
                        "status": "running",
                        "assessment_id": "invalid",
                        "deadline_at": "invalid",
                        "message": "PRIVATE MODEL CHAIN",
                    },
                },
            )
            yield (
                ("skill_finder:review",),
                "messages",
                (AIMessage(content="Review the existing checklist."), {}),
            )

    frames = [
        frame
        async for frame in _sse_stream(
            CustomGraph(),
            {},
            {"configurable": {"thread_id": "custom-only"}},
            bound_state={},
        )
    ]
    assert "PRIVATE MODEL CHAIN" not in "".join(frames)
    assert events(frames)[-1] == {"type": "stream_end", "outcome": "completed"}
    assert any(
        item.get("delta") == "Review the existing checklist." for item in events(frames)
    )


@pytest.mark.anyio
async def test_real_chat_route_supplies_owned_context_before_priority(
    flow_case, monkeypatch
):
    case = flow_case
    monkeypatch.setattr(settings, "hh_user_agent", "LabTutor test transport")
    monkeypatch.setattr(settings, "hh_access_token", SecretStr("test-access"))
    # The request uses the real graph and ordinary HTTP chat setup, without an
    # explicit contextual-review attachment or a manually constructed runtime.
    monkeypatch.setattr(
        "app.modules.marketdemandanalyst.routes.get_graph", graph_module.get_graph
    )
    case.lease = None
    model_entered = []
    original = case.model.ainvoke

    async def record(messages, *, config):
        model_entered.append(True)
        return await original(messages, config=config)

    case.model.ainvoke = record
    # Build the graph and prescribe the external Skill Finder response.
    compiled, llm = await graph_module.get_graph()
    llm.responses = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "start_extraction", "args": {}, "id": "route-extract"}
            ],
        ),
        AIMessage(content="Choose skills and Confirm Selection."),
    ]
    await compiled.aupdate_state(
        {"configurable": {"thread_id": case.thread_id}},
        {
            "active_agent": "skill_finder",
            "messages": [HumanMessage(content="Earlier selected work")],
        },
        as_node="skill_finder",
    )
    # TestClient owns its own loop; transport assertions deliberately only rely
    # on durable SQL/lease facts across that boundary.
    response = await asyncio.to_thread(
        case.client.post,
        f"/courses/{case.scope.course_id}/market-demand/chat",
        json={"message": "Extract skills"},
        headers=case.headers,
    )
    assert response.status_code == 200, response.text
    assert '"outcome": "completed"' in response.text, response.text
    assert case.reload().priority_assessment is not None
    assert model_entered
    assert case.reload().priority_assessment["status"] == "ready", case.transport_errors


@pytest.mark.anyio
async def test_recovered_pending_extraction_tool_call_is_completed_once(flow_case):
    case = flow_case
    lease = await case.state_service.claim(case.thread_id)

    async def interrupted(payload):
        if payload["phase"] == "score":
            raise asyncio.CancelledError()

    case.model.hook = interrupted
    try:
        with pytest.raises(asyncio.CancelledError):
            await case.priority.assess(case.scope, lease)
        raw = case.reload().priority_assessment
        bound = await case.state_service.load(case.thread_id)
        bound["skill_priority_status"] = {
            "assessment_id": raw["assessment_id"],
            "status": "running",
            "deadline_at": raw["deadline_at"],
            "message": "Assessing skill importance…",
        }
        await case.state_service.save(lease, bound)
    finally:
        await case.state_service.release(lease)
    case.model.hook = None
    compiled, _ = await graph_module.get_graph()
    config = {"configurable": {"thread_id": case.thread_id}}
    await compiled.aupdate_state(
        config,
        {
            "active_agent": "skill_finder",
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "start_extraction",
                            "args": {},
                            "id": "orphan-extraction",
                        }
                    ],
                )
            ],
        },
        as_node="skill_finder",
    )

    async def verify_pairing_before_analyst(payload):
        current = await compiled.aget_state(config)
        assert any(
            isinstance(message, ToolMessage)
            and message.tool_call_id == "orphan-extraction"
            for message in current.values["messages"]
        )

    case.model.hook = verify_pairing_before_analyst
    frames = [frame async for frame in await case.open_stream(start="skill_finder")]
    assert events(frames)[-1] == {"type": "stream_end", "outcome": "completed"}, frames
    assert case.reload().priority_assessment["status"] == "ready", case.transport_errors
    checkpoint = await compiled.aget_state(config)
    messages = checkpoint.values["messages"]
    assert (
        len(
            [
                message
                for message in messages
                if isinstance(message, ToolMessage)
                and message.tool_call_id == "orphan-extraction"
            ]
        )
        == 1
    )
    assert case.visited == ["skill_priority_analyst", "skill_finder"]


@pytest.mark.anyio
async def test_stale_analyst_cannot_restore_a_replaced_active_run(flow_case):
    from uuid import uuid4

    case = flow_case
    replacement = str(uuid4())
    changed = False

    async def replaced(payload):
        nonlocal changed
        if changed or payload["phase"] != "score":
            return
        changed = True
        with case.factory() as db:
            thread = db.get(MDAThreadState, case.thread_id)
            thread.state_json = {
                "run_id": replacement,
                "course_id": case.scope.course_id,
            }
            db.commit()

    case.model.hook = replaced
    frames = [frame async for frame in await case.open_stream()]
    with case.factory() as db:
        assert (
            db.get(MDAThreadState, case.thread_id).state_json["run_id"] == replacement
        )
    assert events(frames)[-1]["type"] == "stream_end"
    assert case.teacher_decisions() == case.before
