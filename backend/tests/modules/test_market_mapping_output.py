"""Mapper output limits through the real client, graph and durable stores."""

import json
from copy import deepcopy

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app.core.settings import settings
from app.modules.marketdemandanalyst import graph as graph_module
from app.modules.marketdemandanalyst import tools
from app.modules.marketdemandanalyst.routes import _sse_stream
from tests.market_skill_fixtures import seed_review
from tests.modules.test_market_demand import _parse_sse

pytest_plugins = ["tests.fixtures.market_skill_graph"]


@pytest.fixture
def large_mapping(db_session, client, teacher_auth_headers, course_chapters):
    course, run, candidates, service, revision = seed_review(
        db_session,
        client,
        teacher_auth_headers,
        labels=tuple(
            f"Design and maintain data pipeline competency {i}" for i in range(139)
        ),
    )
    course_chapters(course["id"])
    fields = service.load_confirmed_selection(
        course["id"], course["teacher_id"], revision
    )
    state = {**fields, "course_id": course["id"], "teacher_id": course["teacher_id"]}
    mapping = [
        {
            "candidate_id": candidate["candidate_id"],
            "name": candidate["display_name"],
            "category": "data_engineering",
            "status": "gap",
            "target_chapter": "Programming",
            "related_concepts": ["data integration", "data quality", "data pipelines"],
            "priority": "high",
            "reasoning": "The saved chapter covers programming foundations needed to implement reliable data pipelines and validate their output.",
        }
        for candidate in candidates
    ]
    arguments = json.dumps({"mapping_json": json.dumps(mapping)})
    assert len(arguments) > 60_000  # Well beyond the observed ~16k-character cutoff.
    return course, run, candidates, service, state, arguments


@pytest.fixture
def mapper_provider(client, monkeypatch):
    """Only replace HTTP; keep streaming parsing, tools and checkpoints real."""
    requests = []
    replies = []
    save_calls = []
    original = tools.save_curriculum_mapping.func

    def record_save(*args, **kwargs):
        save_calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(tools.save_curriculum_mapping, "func", record_save)

    async def send(_client, request, **_kwargs):
        assert request.url.host == "mapper.invalid"
        body = json.loads(request.content)
        requests.append(body)
        outstanding = set()
        for message in body["messages"]:
            if message["role"] == "assistant":
                outstanding.update(call["id"] for call in message.get("tool_calls", []))
            elif message["role"] == "tool":
                outstanding.discard(message["tool_call_id"])
            elif message["role"] == "user":
                assert not outstanding, "Unanswered truncated tool call reached a retry"
        assert not outstanding, "Provider received invalid tool-call history"
        arguments, finish_reason = replies.pop(0) if replies else (None, "stop")
        # Reproduce the gateway default when the literal supported option is absent.
        if arguments and finish_reason == "budget":
            enough_output = body.get("max_tokens", 4096) >= 20_000
            arguments = arguments if enough_output else arguments[:16_096]
            finish_reason = "tool_calls" if enough_output else "length"
        deltas = []
        if arguments is not None:
            for index in range(0, len(arguments), 1024):
                call = {
                    "index": 0,
                    "function": {"arguments": arguments[index : index + 1024]},
                }
                if index == 0:
                    call.update(id=f"mapping-{len(requests)}", type="function")
                    call["function"]["name"] = "save_curriculum_mapping"
                deltas.append({"tool_calls": [call]})
        else:
            deltas.append({"content": "Mapping response finished."})
        deltas.append({})
        events = []
        for index, delta in enumerate(deltas):
            chunk = {
                "id": f"completion-{len(requests)}",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": finish_reason
                        if index == len(deltas) - 1
                        else None,
                    }
                ],
            }
            events.append(f"data: {json.dumps(chunk)}\n\n")
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/event-stream"},
            content="".join(events) + "data: [DONE]\n\n",
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    monkeypatch.setattr(settings, "llm_api_key", "test-only")
    monkeypatch.setattr(settings, "llm_base_url", "https://mapper.invalid/v1")
    monkeypatch.setattr(settings, "llm_agent_model", "deepseek-v4.1-flash")
    monkeypatch.setattr(graph_module, "_COMPILED_GRAPH", None)
    monkeypatch.setattr(graph_module, "_LLM_INSTANCE", None)
    graph, _ = client.portal.call(graph_module.get_graph)
    threads = set()

    def stream(state, service, text="Map the confirmed skills"):
        thread = service.thread_id(state["course_id"], state["teacher_id"])
        threads.add(thread)

        async def collect():
            return "".join(
                [
                    frame
                    async for frame in _sse_stream(
                        graph,
                        {
                            "messages": [HumanMessage(content=text)],
                            "active_agent": "curriculum_mapper",
                        },
                        {"configurable": {"thread_id": thread}},
                        bound_state=state,
                    )
                ]
            )

        return _parse_sse(client.portal.call(collect))

    yield replies, requests, stream, save_calls
    for thread in threads:
        client.portal.call(graph.checkpointer.adelete_thread, thread)


def test_streamed_139_candidate_mapping_is_saved_atomically(
    large_mapping, mapper_provider, graph_driver
):
    course, run, _, service, state, arguments = large_mapping
    replies, requests, stream, _ = mapper_provider
    replies.extend([(arguments, "budget"), (None, "stop")])

    frames = stream(state, service)

    assert frames[-1]["data"]["outcome"] == "completed", frames[-2:]
    saved = service._repo.load_active_snapshot(
        service.thread_id(course["id"], course["teacher_id"])
    )
    assert len(saved.get("curriculum_mapping") or []) == 139
    assert {row["candidate_id"] for row in saved["curriculum_mapping"]} == set(
        run.selected_candidate_ids
    )
    assert all(row["evidence_references"] for row in saved["curriculum_mapping"])
    assert saved["selection_confirmation"] == state["selection_confirmation"]
    assert len(requests) == 2
    assert requests[0]["max_tokens"] >= 20_000
    assert requests[0]["thinking"] == {"type": "disabled"}
    review = service.get_review(course["id"], course["teacher_id"])
    assert review.publication_revision == 0
    assert not review.approved_references
    with graph_driver.session(database="neo4j") as session:
        assert (
            session.run("MATCH (s:CAREER_SKILL) RETURN count(s) AS count").single()[
                "count"
            ]
            == 0
        )


@pytest.mark.parametrize("partial_json", [True, False])
def test_length_finish_never_executes_tools_and_a_new_turn_can_retry(
    large_mapping, mapper_provider, partial_json
):
    course, run, _, service, state, arguments = large_mapping
    replies, requests, stream, save_calls = mapper_provider
    replies.append((arguments[:16_096] if partial_json else arguments, "length"))
    before = deepcopy(state)

    frames = stream(state, service)

    error = next((frame["data"] for frame in frames if frame["event"] == "error"), None)
    assert error is not None, frames[-2:]
    assert error["code"] == "execution_failed"
    assert "output limit" in error["message"].lower()
    assert "preserved" in error["recovery"].lower()
    assert frames[-1]["data"]["outcome"] == "failed"
    assert len(requests) == 1
    assert not save_calls
    assert state == before
    saved = service._repo.load_active_snapshot(
        service.thread_id(course["id"], course["teacher_id"])
    )
    assert not saved.get("curriculum_mapping")
    assert saved["selection_confirmation"] == before["selection_confirmation"]
    assert run.publication_revision == 0

    replies.extend([(arguments, "budget"), (None, "stop")])
    retried = stream(state, service, "Retry the saved confirmed selection")
    assert retried[-1]["data"]["outcome"] == "completed", retried[-2:]
    assert len(requests) == 3
    assert len(save_calls) == 1
    saved = service._repo.load_active_snapshot(
        service.thread_id(course["id"], course["teacher_id"])
    )
    assert len(saved["curriculum_mapping"]) == 139
    assert {row["candidate_id"] for row in saved["curriculum_mapping"]} == set(
        run.selected_candidate_ids
    )
