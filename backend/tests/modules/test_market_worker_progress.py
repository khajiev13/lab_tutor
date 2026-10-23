"""A stuck autonomous worker must fail explicitly before an unbounded tool loop."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.modules.marketdemandanalyst.routes import _sse_stream
from tests.modules.test_market_chapter_prerequisite import add_chapter
from tests.modules.test_market_demand import _parse_sse

pytest_plugins = ["tests.modules.test_market_chapter_prerequisite"]


@pytest.mark.parametrize(
    "agent,tool,args",
    [
        ("curriculum_mapper", "get_chapter_details", {"chapter_indices": "1"}),
        ("skill_cleaner", "finalize_cleaned_skills", {}),
    ],
)
def test_repeated_worker_tools_emit_actionable_failure_and_new_turn_can_continue(
    mapping_course, graph_driver, client, live_graph, agent, tool, args
):
    course, run, candidates, service, state = mapping_course
    add_chapter(graph_driver, course["id"])
    state["curriculum_mapping"] = [
        {
            "candidate_id": row["candidate_id"],
            "name": row["display_name"],
            "status": "gap",
            "target_chapter": "Data pipelines",
        }
        for row in candidates
    ]
    before = deepcopy(state)
    model, graph, checkpoint = live_graph
    thread = service.thread_id(course["id"], course["teacher_id"])
    checkpoint(thread)
    config = {"configurable": {"thread_id": thread}}
    model.replies.extend(
        [
            AIMessage(
                content="", tool_calls=[{"id": f"read-{i}", "name": tool, "args": args}]
            )
            for i in range(4)
        ]
        + [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "end", "name": "transfer_to_supervisor", "args": {}}
                ],
            ),
            AIMessage(content="Finished"),
        ]
    )

    async def collect(message):
        return "".join(
            [
                frame
                async for frame in _sse_stream(
                    graph,
                    {
                        "messages": [HumanMessage(content=message)],
                        "active_agent": agent,
                    },
                    config,
                    bound_state=state,
                )
            ]
        )

    frames = _parse_sse(client.portal.call(collect, "Prepare the confirmed skills"))
    error = next((frame["data"] for frame in frames if frame["event"] == "error"), None)
    assert error is not None, frames
    assert error["code"] == "worker_stalled"
    assert tool in error["message"]
    assert "confirmed" in error["recovery"].lower()
    assert frames[-1]["data"]["outcome"] == "failed"
    assert len(model.calls) == 3
    assert state["selected_candidate_ids"] == before["selected_candidate_ids"]
    assert state["curriculum_mapping"] == before["curriculum_mapping"]
    assert run.publication_revision == 0

    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.worker_progress import WorkerStalledError

    with bind_tool_store(state), pytest.raises(WorkerStalledError):
        client.portal.call(graph.ainvoke, None, config)
    assert len(model.calls) == 3  # Same failed task cannot silently restart its budget.

    model.replies[:] = [
        AIMessage(
            content="", tool_calls=[{"id": "new-read", "name": tool, "args": args}]
        ),
        AIMessage(
            content="",
            tool_calls=[
                {"id": "new-end", "name": "transfer_to_supervisor", "args": {}}
            ],
        ),
        AIMessage(content="Ready to continue"),
    ]
    retried = _parse_sse(client.portal.call(collect, "Try the saved work again"))
    assert retried[-1]["data"]["outcome"] == "completed"
    assert not any(frame["event"] == "error" for frame in retried)


@pytest.mark.parametrize(
    "change", ["arguments", "result", "progress", "agent", "human"]
)
def test_changed_work_does_not_trigger_stall(change):
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.worker_progress import worker_progress

    state = {"messages": [HumanMessage(content="Map", id="task")]}
    saved = {"selected_candidate_ids": ["confirmed"]}
    with bind_tool_store(saved):
        for index in range(5):
            agent = f"worker-{index}" if change == "agent" else "curriculum_mapper"
            if change == "human":
                state["messages"].append(
                    HumanMessage(content="Continue", id=f"task-{index}")
                )
            if change == "progress":
                saved["_cleaned_results"] = [{"chapter": f"Chapter {index}"}]
            args = {"chapter_indices": str(index) if change == "arguments" else "1"}
            state["messages"].extend(
                [
                    AIMessage(
                        content="",
                        name=agent,
                        id=f"round-{index}",
                        tool_calls=[
                            {
                                "id": str(index),
                                "name": "get_chapter_details",
                                "args": args,
                            }
                        ],
                    ),
                    ToolMessage(
                        content=f"Details {index}"
                        if change == "result"
                        else "Same details",
                        name="get_chapter_details",
                        tool_call_id=str(index),
                    ),
                ]
            )
            state["worker_progress"] = worker_progress(state, agent)
        assert state["worker_progress"]["count"] == 1


def test_ui_change_ids_and_replayed_hook_do_not_hide_repeated_tool_rounds():
    from app.modules.marketdemandanalyst.state import bind_tool_store
    from app.modules.marketdemandanalyst.worker_progress import (
        WorkerStalledError,
        worker_progress,
    )

    state = {"messages": [HumanMessage(content="Clean", id="task")]}
    saved = {}
    with bind_tool_store(saved):
        for index in range(3):
            saved["skill_review_change_id"] = str(index)
            state["messages"].extend(
                [
                    AIMessage(
                        content="",
                        name="skill_cleaner",
                        id=f"round-{index}",
                        tool_calls=[
                            {
                                "id": str(index),
                                "name": "finalize_cleaned_skills",
                                "args": {},
                            }
                        ],
                    ),
                    ToolMessage(
                        content="Clean candidate_id first", tool_call_id=str(index)
                    ),
                ]
            )
            if index == 2:
                with pytest.raises(WorkerStalledError):
                    worker_progress(state, "skill_cleaner")
            else:
                state["worker_progress"] = worker_progress(state, "skill_cleaner")
                assert (
                    worker_progress(state, "skill_cleaner") == state["worker_progress"]
                )
