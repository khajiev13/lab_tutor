"""Parallel cleaning must retain every confirmed chapter in SQL and memory."""

import asyncio
from copy import deepcopy
from threading import Barrier, Event

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from app.modules.marketdemandanalyst import tools
from app.modules.marketdemandanalyst.state import bind_tool_store
from tests.market_skill_fixtures import seed_review

pytest_plugins = ["tests.fixtures.market_skill_graph"]


def test_parallel_chapters_keep_every_candidate_and_exact_confirmation(
    db_session, client, teacher_auth_headers, graph_driver, monkeypatch
):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("SQL", "ETL", "Storage")
    )
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    titles = ["Acquisition", "Processing", "Storage"]
    mapping = [
        {
            "candidate_id": row["candidate_id"],
            "name": row["display_name"],
            "status": "gap",
            "target_chapter": title,
        }
        for row, title in zip(candidates, titles, strict=True)
    ]
    fields = service.save_mapping_state(
        course["id"],
        course["teacher_id"],
        revision,
        {"curriculum_mapping": mapping, "_cleaned_results": None},
    )
    state = {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    original_confirmation = deepcopy(run.selection_confirmation)
    original_persist = tools._persist_durable_mapping
    barrier = Barrier(len(titles))

    def hold_legacy_replacements(fields):
        # Force every old whole-list writer to capture the same empty baseline.
        if "_cleaned_results" in fields:
            barrier.wait(timeout=5)
        return original_persist(fields)

    monkeypatch.setattr(tools, "_persist_durable_mapping", hold_legacy_replacements)
    builder = StateGraph(MessagesState)
    builder.add_node(
        "tools", ToolNode(tools.owned_sync_tools([tools.compare_and_clean]))
    )
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    with bind_tool_store(state):
        response = client.portal.call(
            graph.ainvoke,
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": str(i),
                                "name": "compare_and_clean",
                                "args": {"chapter_title": title},
                            }
                            for i, title in enumerate(titles)
                        ],
                    )
                ]
            },
        )
        outputs = [
            m.content for m in response["messages"] if isinstance(m, ToolMessage)
        ]
        assert len(outputs) == 3 and all(
            str(value).startswith("Reviewed 1") for value in outputs
        )
        db_session.expire_all()
        saved = service._repo.load_active_snapshot(
            service.thread_id(course["id"], course["teacher_id"])
        )
        assert {row["chapter"] for row in saved["_cleaned_results"]} == set(titles)
        assert {row["chapter"] for row in state["_cleaned_results"]} == set(titles)
        assert "Finalized 3" in tools.finalize_cleaned_skills.invoke({})
    db_session.expire_all()
    assert run.selected_candidate_ids == [row["candidate_id"] for row in candidates]
    assert run.selection_confirmation == original_confirmation
    assert run.selection_revision == 1 and run.publication_revision == 0


@pytest.fixture
def two_chapters(db_session, client, teacher_auth_headers, graph_driver, monkeypatch):
    course, run, candidates, service, revision = seed_review(
        db_session, client, teacher_auth_headers, labels=("SQL", "ETL")
    )
    monkeypatch.setattr(tools, "_get_neo4j_driver", lambda **kwargs: graph_driver)
    mapping = [
        {
            "candidate_id": row["candidate_id"],
            "name": row["display_name"],
            "status": "gap",
            "target_chapter": title,
        }
        for row, title in zip(candidates, ("A", "B"), strict=True)
    ]
    fields = service.save_mapping_state(
        course["id"],
        course["teacher_id"],
        revision,
        {"curriculum_mapping": mapping, "_cleaned_results": None},
    )
    state = {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    return course, candidates, service, revision, state


def test_delayed_committed_result_cannot_overwrite_later_memory(
    two_chapters, client, db_session, monkeypatch
):
    from app.modules.marketdemandanalyst.review_service import SkillReviewService

    course, _, service, _, state = two_chapters
    first_committed, second_started, second_committed, release_first = (
        Event() for _ in range(4)
    )
    save = SkillReviewService.save_cleaned_chapter
    load_selection = tools._durable_selection_tool

    def delay_return(self, *args):
        fields = save(self, *args)
        if args[-1]["chapter"] == "A":
            first_committed.set()
            assert release_first.wait(5)
        else:
            second_committed.set()
        return fields

    def mark_started(*args, **kwargs):
        if first_committed.is_set() and not release_first.is_set():
            second_started.set()
        return load_selection(*args, **kwargs)

    monkeypatch.setattr(SkillReviewService, "save_cleaned_chapter", delay_return)
    monkeypatch.setattr(tools, "_durable_selection_tool", mark_started)
    tool = tools.owned_sync_tools([tools.compare_and_clean])[0]

    async def race():
        first = asyncio.create_task(tool.ainvoke({"chapter_title": "A"}))
        assert await asyncio.to_thread(first_committed.wait, 5)
        second = asyncio.create_task(tool.ainvoke({"chapter_title": "B"}))
        try:
            assert await asyncio.to_thread(second_started.wait, 5)
            # A has committed but not published. B must not overtake that publication.
            assert not await asyncio.to_thread(second_committed.wait, 0.1)
        finally:
            release_first.set()
        return await asyncio.gather(first, second)

    with bind_tool_store(state):
        assert all(value.startswith("Reviewed 1") for value in client.portal.call(race))
        assert {row["chapter"] for row in state["_cleaned_results"]} == {"A", "B"}
        assert "Finalized 2" in tools.finalize_cleaned_skills.invoke({})
    db_session.expire_all()
    saved = service._repo.load_active_snapshot(
        service.thread_id(course["id"], course["teacher_id"])
    )
    assert {row["chapter"] for row in saved["_cleaned_results"]} == {"A", "B"}


def test_chapter_retry_replaces_only_its_result_and_invalid_save_preserves_state(
    two_chapters,
):
    course, candidates, service, revision, state = two_chapters
    with bind_tool_store(state):
        for title in ("A", "B", "A"):
            assert tools.compare_and_clean.invoke({"chapter_title": title}).startswith(
                "Reviewed 1"
            )
    thread = service.thread_id(course["id"], course["teacher_id"])
    before = service._repo.load_active_snapshot(thread)
    assert len(before["_cleaned_results"]) == 2
    invalid = {
        "chapter": "A",
        "kept": [candidates[1]["candidate_id"]],
        "dropped": [],
        "details": {
            "kept": [{"candidate_id": candidates[1]["candidate_id"]}],
            "dropped": [],
        },
    }
    with pytest.raises(HTTPException, match="current candidate"):
        service.save_cleaned_chapter(
            course["id"], course["teacher_id"], revision, invalid
        )
    service.rollback()
    assert service._repo.load_active_snapshot(thread) == before
    stale = revision.model_copy(update={"expected_selection_revision": 0})
    with pytest.raises(HTTPException, match="has changed"):
        service.save_cleaned_chapter(
            course["id"], course["teacher_id"], stale, before["_cleaned_results"][0]
        )
    service.rollback()
    assert service._repo.load_active_snapshot(thread) == before


def test_leased_sse_snapshot_cannot_erase_a_concurrent_chapter(
    two_chapters, client, db_session, monkeypatch
):
    from app.modules.marketdemandanalyst.repository import ThreadStateRepository
    from app.modules.marketdemandanalyst.routes import _sse_stream
    from app.modules.marketdemandanalyst.thread_state_service import ThreadStateService
    from tests.modules.test_market_demand import _parse_sse

    course, _, service, _, state = two_chapters
    captured, allow_save, written, second_done = (Event() for _ in range(4))
    save = ThreadStateRepository.save
    intercepted = False

    def pause_snapshot(self, thread, snapshot):
        nonlocal intercepted
        chapters = {row["chapter"] for row in snapshot.get("_cleaned_results") or []}
        if chapters == {"A"} and not intercepted:
            intercepted = True
            captured.set()
            assert allow_save.wait(5)
            save(self, thread, snapshot)
            written.set()
        else:
            save(self, thread, snapshot)

    monkeypatch.setattr(ThreadStateRepository, "save", pause_snapshot)
    tool = tools.owned_sync_tools([tools.compare_and_clean])[0]

    class InterleavedGraph:
        async def astream(self, *_args, **_kwargs):
            first = await tool.ainvoke({"chapter_title": "A"})

            async def remaining():
                assert await asyncio.to_thread(captured.wait, 5)

                async def second():
                    result = await tool.ainvoke({"chapter_title": "B"})
                    second_done.set()
                    return result

                task = asyncio.create_task(second())
                try:
                    # Old snapshot writes permit B to commit before stale A is written.
                    await asyncio.to_thread(second_done.wait, 0.1)
                finally:
                    allow_save.set()
                assert await asyncio.to_thread(written.wait, 5)
                assert (await task).startswith("Reviewed 1")
                assert (await tool.ainvoke({"chapter_title": "A"})).startswith(
                    "Reviewed 1"
                )

            pending = asyncio.create_task(remaining())
            yield (
                (),
                "messages",
                (
                    ToolMessage(
                        content=first, name="compare_and_clean", tool_call_id="A"
                    ),
                    {"langgraph_node": "tools"},
                ),
            )
            await pending

    async def stream():
        owner = ThreadStateService()
        thread = service.thread_id(course["id"], course["teacher_id"])
        lease = await owner.claim(thread)
        frames = [
            frame
            async for frame in _sse_stream(
                InterleavedGraph(),
                {},
                {"configurable": {"thread_id": thread}},
                bound_state=state,
                lease=lease,
                state_service=owner,
            )
        ]
        return "".join(frames)

    frames = _parse_sse(client.portal.call(stream))
    assert frames[-1]["data"]["outcome"] == "completed", frames
    db_session.expire_all()
    saved = service._repo.load_active_snapshot(
        service.thread_id(course["id"], course["teacher_id"])
    )
    assert {row["chapter"] for row in saved["_cleaned_results"]} == {"A", "B"}
    assert {row["chapter"] for row in state["_cleaned_results"]} == {"A", "B"}
