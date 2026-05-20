from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage


@pytest.mark.anyio
async def test_run_skill_prerequisites_emits_auto_trigger_metadata(monkeypatch):
    from app.modules.curricularalignmentarchitect.skill_prerequisites import (
        service as service_mod,
    )

    events: list[tuple[str, dict]] = []
    saved: list[tuple[int, int]] = []

    class FakeGraph:
        async def astream(self, state, *, stream_mode, config):
            assert state["course_id"] == 11
            assert state["merged_skill_names"] == []
            assert stream_mode == ["custom", "updates"]
            assert config == {"max_concurrency": service_mod.MAX_CONCURRENCY}
            yield (
                "custom",
                {
                    "type": "prerequisite_generated",
                    "final_edges": [
                        {
                            "prerequisite_skill": "A",
                            "dependent_skill": "B",
                            "confidence": "high",
                            "reasoning": "A before B",
                        }
                    ],
                },
            )

    async def collect(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(
        service_mod, "build_skill_prerequisite_graph", lambda: FakeGraph()
    )
    monkeypatch.setattr(
        service_mod,
        "_save_generated_review_draft",
        lambda course_id, generated_edges: saved.append(
            (course_id, len(generated_edges))
        ),
    )

    result = await service_mod.run_skill_prerequisites(
        11,
        trigger_reason="book_skill_mapping",
        auto_triggered=True,
        emit_event=collect,
    )

    assert result is True
    assert events[0] == (
        "prerequisite_started",
        {
            "course_id": 11,
            "trigger_reason": "book_skill_mapping",
            "auto_triggered": True,
        },
    )
    assert events[1][0] == "prerequisite_generated"
    assert events[1][1]["trigger_reason"] == "book_skill_mapping"
    assert events[1][1]["auto_triggered"] is True
    assert events[2][0] == "prerequisite_completed"
    assert events[2][1]["draft_edges"] == 1
    assert saved == [(11, 1)]


@pytest.mark.anyio
async def test_run_skill_prerequisites_marks_review_failed_on_pipeline_error(
    monkeypatch,
):
    from app.modules.curricularalignmentarchitect.skill_prerequisites import (
        service as service_mod,
    )

    events: list[tuple[str, dict]] = []
    failed_reviews: list[int] = []

    class FakeGraph:
        async def astream(self, state, *, stream_mode, config):
            raise RuntimeError("pipeline broke")
            yield  # pragma: no cover

    async def collect(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(
        service_mod, "build_skill_prerequisite_graph", lambda: FakeGraph()
    )
    monkeypatch.setattr(
        service_mod,
        "_mark_review_rebuild_failed",
        lambda course_id: failed_reviews.append(course_id),
    )

    result = await service_mod.run_skill_prerequisites(
        22,
        trigger_reason="manual_regenerate",
        auto_triggered=True,
        emit_event=collect,
    )

    assert result is False
    assert events[0][0] == "prerequisite_started"
    assert events[1][0] == "prerequisite_failed"
    assert events[1][1]["message"] == "pipeline broke"
    assert failed_reviews == [22]


def test_regenerate_route_schedules_without_runtime_error(
    client,
    teacher_auth_headers,
    monkeypatch,
):
    from app.modules.curricularalignmentarchitect.api_routes import (
        skill_prerequisites as routes_mod,
    )

    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        routes_mod,
        "schedule_skill_prerequisite_rebuild",
        lambda course_id, trigger_reason: scheduled.append((course_id, trigger_reason)),
    )

    create_response = client.post(
        "/courses",
        json={
            "title": "Regenerate Route Course",
            "description": "A course for prerequisite regeneration",
        },
        headers=teacher_auth_headers,
    )
    assert create_response.status_code == 201
    course_id = create_response.json()["id"]

    response = client.post(
        f"/book-selection/courses/{course_id}/skill-prerequisites/regenerate",
        headers=teacher_auth_headers,
    )

    assert response.status_code == 202
    assert response.json() == {"message": "Skill prerequisite regeneration scheduled"}
    assert scheduled == [(course_id, "manual_regenerate")]


@pytest.mark.anyio
async def test_agentic_background_schedules_prerequisites_after_book_mapping(
    monkeypatch,
):
    from app.modules.curricularalignmentarchitect.api_routes import (
        agentic_analysis as agentic_mod,
    )
    from app.modules.curricularalignmentarchitect.book_skill_mapping import (
        graph as mapping_graph_mod,
    )

    calls: list[tuple] = []

    class FakeDbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeMappingGraph:
        async def astream(self, state, *, stream_mode, config):
            calls.append(("mapping", state["course_id"], stream_mode, config))
            yield "custom", {"type": "skill_mapping_completed", "written": 4}

    monkeypatch.setattr(agentic_mod, "fresh_db", lambda: FakeDbContext())
    monkeypatch.setattr(agentic_mod, "update_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        agentic_mod,
        "_mark_prerequisites_stale",
        lambda course_id: calls.append(("stale", course_id)),
    )
    monkeypatch.setattr(agentic_mod, "get_chapters_for_book", lambda *_args: [])
    monkeypatch.setattr(
        mapping_graph_mod, "build_book_skill_mapping_graph", lambda: FakeMappingGraph()
    )
    monkeypatch.setattr(
        agentic_mod,
        "schedule_skill_prerequisite_rebuild",
        lambda course_id, trigger_reason: calls.append(
            ("prerequisites", course_id, trigger_reason)
        ),
    )

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    await agentic_mod._run_extraction_background(
        run_id=99,
        course_id=123,
        books_meta=[
            {
                "id": 5,
                "title": "Big Data Systems",
                "blob_path": "courses/123/books/big-data.pdf",
            }
        ],
        course_subject="Big Data",
        queue=queue,
    )

    frames: list[str] = []
    while not queue.empty():
        item = await queue.get()
        if item is not None:
            frames.append(item)

    assert calls[0][0] == "mapping"
    assert calls[1] == ("stale", 123)
    assert calls[2] == ("prerequisites", 123, "book_skill_mapping")
    assert any("event: prerequisite_scheduled" in frame for frame in frames)


@pytest.mark.anyio
async def test_market_stream_schedules_rebuild_when_insertion_results_change(
    monkeypatch,
):
    from app.modules.marketdemandanalyst import routes as routes_mod
    from app.modules.marketdemandanalyst import state as state_mod

    state_mod.restore_state({})
    routes_mod._state_cache.clear()
    scheduled: list[tuple[int, str]] = []

    monkeypatch.setattr(routes_mod, "_persist_state", lambda _thread_id: None)
    monkeypatch.setattr(
        routes_mod,
        "_schedule_skill_prerequisite_rebuild",
        lambda course_id, trigger_reason: scheduled.append((course_id, trigger_reason)),
    )

    tool_call_id = "call-insert-market"
    ai_chunk = AIMessageChunk(content="")
    ai_chunk.tool_call_chunks = [
        {
            "id": tool_call_id,
            "name": "insert_market_skills_to_neo4j",
            "args": "{}",
        }
    ]

    async def astream(*_args, **_kwargs):
        yield ("skill_cleaner:abc",), (ai_chunk, {})
        state_mod.tool_store["insertion_results"] = {"skills_created": 1}
        yield (
            ("skill_cleaner:abc",),
            (
                ToolMessage(
                    content="inserted",
                    tool_call_id=tool_call_id,
                    name="insert_market_skills_to_neo4j",
                ),
                {},
            ),
        )

    graph = SimpleNamespace(astream=astream)

    try:
        frames = [
            frame
            async for frame in routes_mod._sse_stream(
                graph,
                {"course_id": 77},
                {"configurable": {"thread_id": "mda-test-thread"}},
            )
        ]
    finally:
        state_mod.restore_state({})
        routes_mod._state_cache.clear()

    assert scheduled == [(77, "market_demand_insertion")]
    assert any('"stateKey": "insertion_results"' in frame for frame in frames)


def test_market_schedule_marks_gate_complete_and_prerequisites_stale(monkeypatch):
    from app.modules.marketdemandanalyst import routes as routes_mod

    calls: list[tuple] = []

    class FakeDb:
        def commit(self):
            calls.append(("commit",))

        def rollback(self):
            calls.append(("rollback",))

        def close(self):
            calls.append(("close",))

    class FakeReadinessService:
        def __init__(self, db):
            calls.append(("readiness_service", db))

        def mark_market_gate_complete(self, course_id):
            calls.append(("market_complete", course_id))

    class FakeReviewRepository:
        def __init__(self, db):
            calls.append(("review_repo", db))

        def mark_stale(self, course_id):
            calls.append(("stale", course_id))

    fake_db = FakeDb()
    monkeypatch.setattr(routes_mod, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(routes_mod, "CourseReadinessService", FakeReadinessService)
    monkeypatch.setattr(
        routes_mod, "PrerequisiteReviewRepository", FakeReviewRepository
    )
    monkeypatch.setattr(
        routes_mod,
        "schedule_prerequisite_rebuild",
        lambda course_id, trigger_reason: calls.append(
            ("schedule", course_id, trigger_reason)
        ),
    )

    routes_mod._schedule_skill_prerequisite_rebuild(42, "market_demand_insertion")

    assert ("market_complete", 42) in calls
    assert ("stale", 42) in calls
    assert ("commit",) in calls
    assert ("schedule", 42, "market_demand_insertion") in calls
    assert calls.index(("close",)) < calls.index(
        ("schedule", 42, "market_demand_insertion")
    )


def test_market_schedule_skips_rebuild_when_readiness_update_fails(monkeypatch):
    from app.modules.marketdemandanalyst import routes as routes_mod

    calls: list[tuple] = []

    class FakeDb:
        def commit(self):
            calls.append(("commit",))

        def rollback(self):
            calls.append(("rollback",))

        def close(self):
            calls.append(("close",))

    class FailingReadinessService:
        def __init__(self, db):
            calls.append(("readiness_service", db))

        def mark_market_gate_complete(self, course_id):
            calls.append(("market_complete", course_id))
            raise RuntimeError("readiness update failed")

    fake_db = FakeDb()
    monkeypatch.setattr(routes_mod, "SessionLocal", lambda: fake_db)
    monkeypatch.setattr(routes_mod, "CourseReadinessService", FailingReadinessService)
    monkeypatch.setattr(
        routes_mod,
        "schedule_prerequisite_rebuild",
        lambda course_id, trigger_reason: calls.append(
            ("schedule", course_id, trigger_reason)
        ),
    )

    routes_mod._schedule_skill_prerequisite_rebuild(42, "market_demand_insertion")

    assert ("rollback",) in calls
    assert ("close",) in calls
    assert ("schedule", 42, "market_demand_insertion") not in calls
