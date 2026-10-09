"""Regression tests for detached, task-local market agent state."""

import asyncio
from contextlib import suppress

import pytest

from app.modules.marketdemandanalyst import state


@pytest.fixture(autouse=True)
def clear_thread_cache():
    from app.modules.marketdemandanalyst import routes

    routes._state_cache.clear()
    state.tool_store.clear()
    yield
    routes._state_cache.clear()
    state.tool_store.clear()


def test_snapshot_and_restore_detach_nested_provider_payloads():
    state.tool_store.clear()
    state.tool_store["fetched_jobs"] = [{"details": {"tags": ["Python"]}}]
    snapshot = state.snapshot_state()
    state.tool_store["fetched_jobs"][0]["details"]["tags"].append("SQL")
    assert snapshot["fetched_jobs"][0]["details"]["tags"] == ["Python"]
    state.restore_state(snapshot)
    snapshot["fetched_jobs"][0]["details"]["tags"].append("Java")
    assert state.tool_store["fetched_jobs"][0]["details"]["tags"] == ["Python"]


@pytest.mark.anyio
async def test_parallel_courses_and_sync_workers_keep_bound_state():
    entered = asyncio.Event()
    other_entered = asyncio.Event()

    async def first():
        with state.bind_tool_store({"course_id": 11}):
            entered.set()
            await other_entered.wait()
            await asyncio.to_thread(
                state.tool_store.__setitem__, "course_title", "First"
            )
            return state.snapshot_state()

    async def second():
        await entered.wait()
        with state.bind_tool_store({"course_id": 22}):
            other_entered.set()
            await asyncio.to_thread(
                state.tool_store.__setitem__, "course_title", "Second"
            )
            return state.snapshot_state()

    first_result, second_result = await asyncio.gather(first(), second())
    assert (first_result["course_id"], first_result["course_title"]) == (11, "First")
    assert (second_result["course_id"], second_result["course_title"]) == (22, "Second")


@pytest.mark.anyio
async def test_run_guard_rejects_overlap_and_releases_after_failure():
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    service = ThreadStateService()
    lease = await service.claim("guard-course")
    try:
        with pytest.raises(ThreadBusy):
            await service.claim("guard-course")
    finally:
        await service.release(lease)
    second = await service.claim("guard-course")
    await service.release(second)


@pytest.mark.anyio
async def test_ordered_writes_and_deleted_thread_cannot_be_recreated():
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    service = ThreadStateService()
    lease = await service.claim("ordered-course")
    first = {"course_id": 11, "fetched_jobs": [{"title": "Old"}]}
    queued = service.save(lease, first)
    first["fetched_jobs"][0]["title"] = "Mutated"
    latest = service.save(lease, {"course_id": 11, "fetched_jobs": [{"title": "New"}]})
    await queued
    await latest
    fresh = ThreadStateService()
    assert (await fresh.load("ordered-course"))["fetched_jobs"] == [{"title": "New"}]
    await service.release(lease)
    await service.delete("ordered-course")
    await service.save(lease, {"fetched_jobs": [{"title": "Late worker"}]})
    assert await service.load("ordered-course") is None


@pytest.mark.anyio
async def test_disconnect_keeps_guard_until_late_tool_finishes_and_persists(db_session):
    from langchain_core.messages import AIMessageChunk, ToolMessage

    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    worker_continue = asyncio.Event()
    service = ThreadStateService()
    lease = await service.claim("disconnect-course")

    class Graph:
        async def astream(self, *args, **kwargs):
            yield ("supervisor:test",), (AIMessageChunk(content="Working"), {})
            await worker_continue.wait()
            await asyncio.to_thread(
                state.tool_store.__setitem__, "fetched_jobs", [{"title": "Completed"}]
            )
            yield (
                ("supervisor:test",),
                (ToolMessage(content="done", tool_call_id="late"), {}),
            )

    stream = _sse_stream(
        Graph(),
        {"course_id": 11},
        {"configurable": {"thread_id": "disconnect-course"}},
        bound_state={"course_id": 11},
        lease=lease,
        state_service=service,
    )
    await anext(stream)
    await stream.aclose()
    with pytest.raises(ThreadBusy):
        await service.claim("disconnect-course")
    worker_continue.set()
    await asyncio.wait_for(lease.finished.wait(), 5)
    restored = await service.load("disconnect-course")
    assert restored["fetched_jobs"] == [{"title": "Completed"}]
    second = await service.claim("disconnect-course")
    await service.release(second)


def test_chat_setup_failure_releases_execution_guard(
    client, teacher_auth_headers, monkeypatch
):
    from unittest.mock import AsyncMock

    from app.modules.marketdemandanalyst import routes

    response = client.post(
        "/courses", json={"title": "Setup guard"}, headers=teacher_auth_headers
    )
    assert response.status_code == 201
    course_id = response.json()["id"]
    get_graph = AsyncMock(side_effect=RuntimeError("graph setup failed"))
    monkeypatch.setattr(routes, "get_graph", get_graph)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="graph setup failed"):
            client.post(
                f"/courses/{course_id}/market-demand/chat",
                json={"message": "Hello"},
                headers=teacher_auth_headers,
            )


def test_chat_and_state_are_isolated_across_owned_courses(
    client, teacher_auth_headers, monkeypatch
):
    from unittest.mock import AsyncMock

    from langchain_core.messages import ToolMessage

    from app.modules.marketdemandanalyst import routes

    first = client.post(
        "/courses", json={"title": "First"}, headers=teacher_auth_headers
    ).json()["id"]
    second = client.post(
        "/courses", json={"title": "Second"}, headers=teacher_auth_headers
    ).json()["id"]

    class Graph:
        aget_state = AsyncMock()

        async def astream(self, input_data, **kwargs):
            state.tool_store["fetched_jobs"] = [{"title": input_data["course_title"]}]
            yield (
                ("supervisor:test",),
                (ToolMessage(content="done", tool_call_id="jobs"), {}),
            )

    monkeypatch.setattr(routes, "get_graph", AsyncMock(return_value=(Graph(), None)))
    for course_id in (first, second):
        response = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "Search"},
            headers=teacher_auth_headers,
        )
        assert response.status_code == 200
    first_state = client.get(
        f"/courses/{first}/market-demand/state", headers=teacher_auth_headers
    ).json()
    second_state = client.get(
        f"/courses/{second}/market-demand/state", headers=teacher_auth_headers
    ).json()
    assert first_state["fetched_jobs"] == [{"title": "First"}]
    assert second_state["fetched_jobs"] == [{"title": "Second"}]
    assert first_state["run_id"] != second_state["run_id"]


@pytest.mark.anyio
async def test_guard_and_state_reads_are_authoritative_across_service_instances(
    db_session,
):
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    first = ThreadStateService()
    second = ThreadStateService()
    lease = await first.claim("shared-process-course")
    try:
        with pytest.raises(ThreadBusy):
            await second.claim("shared-process-course")
        await first.save(lease, {"course_id": 11})
    finally:
        await first.release(lease)
    assert (await second.load("shared-process-course"))["course_id"] == 11
    lease = await first.claim("shared-process-course")
    try:
        await first.save(lease, {"course_id": 22})
    finally:
        await first.release(lease)
    assert (await second.load("shared-process-course"))["course_id"] == 22
    result = await second.load("shared-process-course")
    result["course_id"] = 99
    assert (await second.load("shared-process-course"))["course_id"] == 22


@pytest.mark.anyio
async def test_cancelled_save_waiter_does_not_release_guard_before_real_sql_write(
    db_session,
):
    import threading

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    entered = threading.Event()
    proceed = threading.Event()
    completed = threading.Event()

    class DelayedRepository(ThreadStateRepository):
        def save(self, thread_id, snapshot):
            entered.set()
            try:
                assert proceed.wait(5)
                super().save(thread_id, snapshot)
            finally:
                completed.set()

    service = ThreadStateService(DelayedRepository(SessionLocal))
    lease = await service.claim("cancelled-save")
    waiter = service.save(lease, {"course_id": 33})
    assert await asyncio.to_thread(entered.wait, 5)
    waiter.cancel()
    release = asyncio.create_task(service.release(lease))
    try:
        with pytest.raises(ThreadBusy):
            await ThreadStateService().claim("cancelled-save")
    finally:
        proceed.set()
        try:
            await release
        finally:
            assert await asyncio.to_thread(completed.wait, 5)
    assert (await ThreadStateService().load("cancelled-save"))["course_id"] == 33


@pytest.mark.anyio
async def test_skill_review_change_emits_coherent_revision_invalidation():
    import json
    from uuid import uuid4

    from langchain_core.messages import ToolMessage

    from app.modules.marketdemandanalyst.routes import _sse_stream

    run_id = str(uuid4())
    bound = {"run_id": run_id, "candidate_revision": 1}

    class Graph:
        async def astream(self, *args, **kwargs):
            state.tool_store["candidate_revision"] = 2
            state.tool_store["selection_revision"] = 3
            state.tool_store["publication_revision"] = 4
            yield (
                ("supervisor:test",),
                (ToolMessage(content="review updated", tool_call_id="review"), {}),
            )

    frames = [frame async for frame in _sse_stream(Graph(), {}, {}, bound_state=bound)]
    changes = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if frame.startswith("event: skill_review_changed")
    ]
    assert changes == [
        {
            "type": "skill_review_changed",
            "run_id": run_id,
            "candidate_revision": 2,
            "selection_revision": 3,
            "publication_revision": 4,
        }
    ]


@pytest.mark.anyio
async def test_final_persistence_failure_terminates_stream_and_releases_guard(
    db_session,
):
    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    class FailedAcknowledgement(ThreadStateRepository):
        def save(self, thread_id, snapshot):
            super().save(thread_id, snapshot)
            raise RuntimeError("persistence acknowledgement failed")

    class Graph:
        async def astream(self, *args, **kwargs):
            for item in ():
                yield item

    service = ThreadStateService(FailedAcknowledgement(SessionLocal))
    lease = await service.claim("failed-final-save")
    stream = _sse_stream(
        Graph(),
        {},
        {"configurable": {"thread_id": "failed-final-save"}},
        bound_state={"course_id": 11},
        lease=lease,
        state_service=service,
    )

    async def collect():
        return [frame async for frame in stream]

    try:
        frames = await asyncio.wait_for(collect(), 5)
        assert frames[-1].startswith("event: stream_end")
        assert lease.finished.is_set()
        next_service = ThreadStateService()
        next_lease = await next_service.claim("failed-final-save")
        await next_service.release(next_lease)
    finally:
        await stream.aclose()


@pytest.mark.anyio
async def test_disconnected_producer_survives_garbage_collection_until_completion(
    db_session,
):
    import gc
    import weakref

    from langchain_core.messages import AIMessageChunk

    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    worker_refs = []

    class Graph:
        async def astream(self, *args, **kwargs):
            yield ("supervisor:test",), (AIMessageChunk(content="Working"), {})
            continuation = asyncio.Future()
            worker_refs.append(
                (weakref.ref(asyncio.current_task()), weakref.ref(continuation))
            )
            await continuation
            state.tool_store["course_title"] = "Late completion"

    service = ThreadStateService()
    lease = await service.claim("retained-producer")
    stream = _sse_stream(
        Graph(),
        {},
        {},
        bound_state={"course_id": 11},
        lease=lease,
        state_service=service,
    )
    try:
        await anext(stream)
        await stream.aclose()
        gc.collect()
        producer_ref, continuation_ref = worker_refs[0]
        assert producer_ref() is not None, (
            "Disconnected execution lost its producer before completion"
        )
        continuation_ref().set_result(None)
        await asyncio.wait_for(lease.finished.wait(), 5)
        assert (await service.load("retained-producer"))[
            "course_title"
        ] == "Late completion"
    finally:
        await stream.aclose()
        if lease.active:
            await service.release(lease)


@pytest.mark.anyio
async def test_cancelled_delete_keeps_guard_until_real_sql_finishes(db_session):
    import threading

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    entered = threading.Event()
    proceed = threading.Event()
    completed = threading.Event()

    class DelayedDeletion(ThreadStateRepository):
        def delete(self, thread_id):
            entered.set()
            try:
                assert proceed.wait(5)
                super().delete(thread_id)
            finally:
                completed.set()

    service = ThreadStateService(DelayedDeletion(SessionLocal))
    competitor = ThreadStateService()
    deletion = asyncio.create_task(service.delete("cancelled-delete"))
    unexpected_lease = None
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        deletion.cancel()
        with pytest.raises(asyncio.CancelledError):
            await deletion
        with suppress(ThreadBusy):
            unexpected_lease = await competitor.claim("cancelled-delete")
        assert unexpected_lease is None, (
            "Deletion guard released before its SQL worker completed"
        )
    finally:
        proceed.set()
        assert await asyncio.to_thread(completed.wait, 5)
        if unexpected_lease is not None:
            await competitor.release(unexpected_lease)


@pytest.mark.anyio
async def test_cancelled_guard_acquisition_releases_late_postgres_lock():
    import threading

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    entered = threading.Event()
    proceed = threading.Event()
    released = threading.Event()

    class DelayedRepository(ThreadStateRepository):
        def acquire(self, thread_id):
            entered.set()
            assert proceed.wait(3)
            return super().acquire(thread_id)

        def release(self, connection, thread_id):
            try:
                return super().release(connection, thread_id)
            finally:
                released.set()

    service = ThreadStateService(DelayedRepository(SessionLocal))
    # External timer bounds the regression even if synchronous acquisition blocks
    # the event loop before it can observe cancellation.
    timer = threading.Timer(2, proceed.set)
    timer.start()
    claim = asyncio.create_task(service.claim("cancelled-acquisition-course"))
    try:
        await asyncio.to_thread(entered.wait, 3)
        claim.cancel()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await claim
        assert await asyncio.to_thread(released.wait, 3)
        competitor = ThreadStateService()
        lease = await competitor.claim("cancelled-acquisition-course")
        await competitor.release(lease)
    finally:
        proceed.set()
        timer.cancel()
        if claim.done() and not claim.cancelled() and claim.exception() is None:
            await service.release(claim.result())


@pytest.mark.anyio
async def test_guard_io_does_not_block_unrelated_event_loop_work():
    import threading

    from app.core.database import SessionLocal
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService

    loop = asyncio.get_running_loop()
    heartbeat = threading.Event()
    progressed = []

    class ObservedRepository(ThreadStateRepository):
        def acquire(self, thread_id):
            loop.call_soon_threadsafe(heartbeat.set)
            progressed.append(heartbeat.wait(1))
            return super().acquire(thread_id)

        def release(self, connection, thread_id):
            heartbeat.clear()
            loop.call_soon_threadsafe(heartbeat.set)
            progressed.append(heartbeat.wait(1))
            return super().release(connection, thread_id)

    service = ThreadStateService(ObservedRepository(SessionLocal))
    lease = await service.claim("responsive-guard-course")
    await service.release(lease)
    assert progressed == [True, True]


@pytest.mark.anyio
async def test_cancelled_real_langchain_tool_drains_before_final_snapshot(monkeypatch):
    import threading
    from unittest.mock import AsyncMock

    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import MemorySaver

    from app.modules.marketdemandanalyst import graph as graph_module
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    entered = threading.Event()
    proceed = threading.Event()
    cancelled = asyncio.Event()

    @tool
    def slow_owned_tool() -> str:
        """Complete one delayed state mutation."""
        entered.set()
        assert proceed.wait(5)
        state.tool_store["fetched_jobs"] = [{"title": "Completed after cancellation"}]
        return "done"

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "slow_owned_tool", "args": {}, "id": "slow"}],
            ),
            AIMessage(content="Done"),
        ]
    )
    monkeypatch.setattr(graph_module, "_COMPILED_GRAPH", None)
    monkeypatch.setattr(graph_module, "_LLM_INSTANCE", None)
    monkeypatch.setattr(graph_module, "_create_llm", lambda: model)
    monkeypatch.setattr(
        graph_module, "_get_async_checkpointer", AsyncMock(return_value=MemorySaver())
    )
    monkeypatch.setattr(graph_module, "SUPERVISOR_TOOLS", [slow_owned_tool])
    compiled, _ = await graph_module.get_graph()

    class ObservedGraph:
        async def astream(self, *args, **kwargs):
            try:
                async for item in compiled.astream(*args, **kwargs):
                    yield item
            except asyncio.CancelledError:
                cancelled.set()
                raise

    service = ThreadStateService()
    lease = await service.claim("cancelled-real-tool-course")
    stream = _sse_stream(
        ObservedGraph(),
        {"messages": [("user", "Run the tool")]},
        {"configurable": {"thread_id": lease.thread_id}},
        bound_state={"course_id": 11},
        lease=lease,
        state_service=service,
    )

    async def consume():
        async for _ in stream:
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
        assert (await service.load(lease.thread_id))["fetched_jobs"] == [
            {"title": "Completed after cancellation"}
        ]
    finally:
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        await asyncio.wait_for(consumer, 5)


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["merge", "normalize"])
async def test_cancelled_actual_extractor_node_drains_late_state(stage, monkeypatch):
    import json
    import threading
    from types import SimpleNamespace

    from app.modules.embeddings.embedding_service import EmbeddingService
    from app.modules.marketdemandanalyst import extractor
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import (
        ThreadBusy,
        ThreadStateService,
    )

    entered = threading.Event()
    proceed = threading.Event()
    cancelled = asyncio.Event()
    raw = [{"name": f"Implement skill {i}", "category": "tool"} for i in range(11)]
    merged = [
        {
            "name": "Implement merged skill",
            "category": "tool",
            "frequency": 11,
            "merged_from": [item["name"] for item in raw],
        },
        {
            "name": "Deploy another skill",
            "category": "tool",
            "frequency": 1,
            "merged_from": [raw[0]["name"]],
        },
    ]

    class FakeLLM:
        def __init__(self, merging):
            self.merging = merging

        def invoke(self, *args, **kwargs):
            if self.merging and stage == "merge":
                entered.set()
                assert proceed.wait(5)
            return SimpleNamespace(content=json.dumps(merged if self.merging else raw))

    def embed(self, names):
        if stage == "normalize":
            entered.set()
            assert proceed.wait(5)
        return [[1.0, 0.0], [0.0, 1.0]]

    monkeypatch.setattr(
        extractor,
        "_get_extraction_llm",
        lambda timeout_seconds=120: FakeLLM(timeout_seconds == 45),
    )
    monkeypatch.setattr(EmbeddingService, "embed_documents", embed)

    class ObservedGraph:
        async def astream(self, *args, **kwargs):
            try:
                async for item in extractor.skill_extractor_subgraph.astream(
                    *args, **kwargs
                ):
                    yield item
            except asyncio.CancelledError:
                cancelled.set()
                raise

    service = ThreadStateService()
    lease = await service.claim(f"cancelled-extractor-{stage}")
    bound = {
        "selected_jobs": [{"title": "Engineer", "url": "https://example.test/job"}]
    }
    stream = _sse_stream(
        ObservedGraph(),
        {"skills": []},
        {"configurable": {"thread_id": lease.thread_id}},
        bound_state=bound,
        lease=lease,
        state_service=service,
    )

    async def consume():
        async for _ in stream:
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
        persisted = await service.load(lease.thread_id)
        if stage == "merge":
            assert "implement merged skill" in persisted["skill_job_urls"]
        else:
            assert persisted["extracted_skills"][0]["name"] == "Implement merged skill"
    finally:
        proceed.set()
        await asyncio.wait_for(lease.finished.wait(), 5)
        await asyncio.wait_for(consumer, 5)
