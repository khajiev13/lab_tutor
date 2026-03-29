"""
Tests for Market Demand Analyst SSE streaming endpoint.

We mock the LangGraph swarm (`get_graph`) so tests don't depend on
an LLM or Neo4j.  Instead we feed synthetic (ns, msg, metadata) tuples
and assert the SSE frames emitted to the client.
"""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.modules.auth.models import User, UserRole
from app.modules.marketdemandanalyst.models import MDAThreadState

# ── Helpers ──────────────────────────────────────────────────


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE text into a list of {event, data} dicts."""
    events = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            raw_data = "\n".join(data_lines)
            try:
                events.append({"event": event_type, "data": json.loads(raw_data)})
            except json.JSONDecodeError:
                events.append({"event": event_type, "data": raw_data})
    return events


def _make_ai_chunk(content: str = "", tool_call_chunks=None):
    """Create an AIMessageChunk with optional tool_call_chunks."""
    chunk = AIMessageChunk(content=content)
    if tool_call_chunks:
        chunk.tool_call_chunks = tool_call_chunks
    return chunk


def _mock_astream(events_list):
    """Create an async iterator from a list of (ns, (msg, metadata)) tuples."""

    async def _astream(*args, **kwargs):
        for item in events_list:
            yield item

    return _astream


def _create_course(client, headers, *, title="Market Demand Test Course") -> int:
    response = client.post(
        "/courses",
        json={"title": title, "description": "Course used by market demand tests"},
        headers=headers,
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def _create_teacher_headers(
    client,
    *,
    email: str,
    first_name: str = "Teacher",
    last_name: str = "Two",
) -> dict[str, str]:
    password = "password"
    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
            "role": UserRole.TEACHER.value,
        },
    )
    response = client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(db_session, email: str) -> int:
    return db_session.execute(select(User.id).where(User.email == email)).scalar_one()


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_tool_store():
    """Clear tool_store and route state cache between tests."""
    import app.modules.marketdemandanalyst.routes as routes_mod
    import app.modules.marketdemandanalyst.state as state_mod

    state_mod.tool_store.clear()
    routes_mod._state_cache.clear()
    yield
    state_mod.tool_store.clear()
    routes_mod._state_cache.clear()


@pytest.fixture
def auth_client(client, teacher_auth_headers):
    """Return (TestClient, auth_headers) for convenience."""
    return client, teacher_auth_headers


# ── Tests: Authentication ────────────────────────────────────


class TestChatAuth:
    def test_unauthenticated_chat_returns_401(self, client):
        resp = client.post(
            "/courses/1/market-demand/chat",
            json={"message": "hello"},
        )
        assert resp.status_code == 401

    def test_unauthenticated_state_returns_401(self, client):
        resp = client.get("/courses/1/market-demand/state")
        assert resp.status_code == 401


# ── Tests: SSE Stream ───────────────────────────────────────


class TestChatSSE:
    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_returns_sse_content_type(self, mock_get_graph, auth_client):
        client, headers = auth_client
        course_id = _create_course(client, headers)
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hi"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_returns_thread_id_header(self, mock_get_graph, auth_client):
        client, headers = auth_client
        course_id = _create_course(client, headers)
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hi"},
            headers=headers,
        )
        assert resp.headers.get("x-thread-id")

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_stream_end_always_emitted(self, mock_get_graph, auth_client):
        client, headers = auth_client
        course_id = _create_course(client, headers)
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hi"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]
        assert "stream_end" in event_types

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_text_tokens_streamed(self, mock_get_graph, auth_client):
        """Agent text is emitted as agent_start → text_delta → text_done."""
        client, headers = auth_client
        course_id = _create_course(client, headers)

        ns = ("job_analyst:abc123",)
        events_from_graph = [
            (ns, (_make_ai_chunk("Hello "), {})),
            (ns, (_make_ai_chunk("world"), {})),
        ]

        mock_g = MagicMock()
        mock_g.astream = _mock_astream(events_from_graph)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hi"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        assert "agent_start" in event_types
        assert "text_delta" in event_types
        assert "text_done" in event_types

        # Validate agent_start content
        agent_start = next(e for e in events if e["event"] == "agent_start")
        assert agent_start["data"]["agent"] == "job_analyst"

        # Validate text deltas contain our tokens
        deltas = [e["data"]["delta"] for e in events if e["event"] == "text_delta"]
        assert "Hello " in deltas
        assert "world" in deltas

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_tool_call_events(self, mock_get_graph, auth_client):
        """Tool calls produce tool_start and tool_end events."""
        client, headers = auth_client
        course_id = _create_course(client, headers)

        ns = ("job_analyst:abc123",)
        tc_id = str(uuid.uuid4())

        ai_with_tool = _make_ai_chunk(
            content="",
            tool_call_chunks=[
                {"id": tc_id, "name": "fetch_jobs", "args": '{"query": "python"}'}
            ],
        )
        tool_result = ToolMessage(
            content='{"count": 42}',
            tool_call_id=tc_id,
            name="fetch_jobs",
        )

        events_from_graph = [
            (ns, (ai_with_tool, {})),
            (ns, (tool_result, {})),
        ]

        mock_g = MagicMock()
        mock_g.astream = _mock_astream(events_from_graph)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "fetch jobs"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        assert "tool_start" in event_types
        assert "tool_end" in event_types

        tool_start = next(e for e in events if e["event"] == "tool_start")
        assert tool_start["data"]["toolName"] == "fetch_jobs"
        assert tool_start["data"]["toolCallId"] == tc_id

        tool_end = next(e for e in events if e["event"] == "tool_end")
        assert tool_end["data"]["toolCallId"] == tc_id
        assert tool_end["data"]["status"] == "success"

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_tool_args_accumulated_across_chunks(self, mock_get_graph, auth_client):
        """Args streamed across multiple chunks are accumulated and emitted via tool_args_update."""
        client, headers = auth_client
        course_id = _create_course(client, headers)

        ns = ("job_analyst:abc123",)
        tc_id = str(uuid.uuid4())

        # First chunk: has id, name, and partial args
        chunk1 = _make_ai_chunk(
            content="",
            tool_call_chunks=[
                {
                    "id": tc_id,
                    "name": "fetch_jobs",
                    "args": '{"search_terms":',
                    "index": 0,
                }
            ],
        )
        # Subsequent chunks: no id/name, only args and index
        chunk2 = _make_ai_chunk(
            content="",
            tool_call_chunks=[
                {"id": None, "name": None, "args": ' "Data Engineer",', "index": 0}
            ],
        )
        chunk3 = _make_ai_chunk(
            content="",
            tool_call_chunks=[
                {"id": None, "name": None, "args": ' "location": "SF"}', "index": 0}
            ],
        )
        tool_result = ToolMessage(
            content='{"count": 42}',
            tool_call_id=tc_id,
            name="fetch_jobs",
        )

        events_from_graph = [
            (ns, (chunk1, {})),
            (ns, (chunk2, {})),
            (ns, (chunk3, {})),
            (ns, (tool_result, {})),
        ]

        mock_g = MagicMock()
        mock_g.astream = _mock_astream(events_from_graph)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "fetch jobs"},
            headers=headers,
        )
        events = _parse_sse(resp.text)

        # tool_args_update should contain the fully accumulated args
        args_updates = [e for e in events if e["event"] == "tool_args_update"]
        assert len(args_updates) == 1
        assert args_updates[0]["data"]["toolCallId"] == tc_id
        assert args_updates[0]["data"]["args"]["search_terms"] == "Data Engineer"
        assert args_updates[0]["data"]["args"]["location"] == "SF"

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_agent_switch_emits_text_done_then_agent_start(
        self, mock_get_graph, auth_client
    ):
        """When the active agent changes, text_done for previous agent is emitted first."""
        client, headers = auth_client
        course_id = _create_course(client, headers)

        events_from_graph = [
            (("job_analyst:abc",), (_make_ai_chunk("job text"), {})),
            (("skill_extractor:def",), (_make_ai_chunk("skill text"), {})),
        ]

        mock_g = MagicMock()
        mock_g.astream = _mock_astream(events_from_graph)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "go"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        event_types = [e["event"] for e in events]

        # Should see two agent_starts
        agent_starts = [e for e in events if e["event"] == "agent_start"]
        assert len(agent_starts) == 2
        assert agent_starts[0]["data"]["agent"] == "job_analyst"
        assert agent_starts[1]["data"]["agent"] == "skill_extractor"

        # text_done for first agent should come before second agent_start
        text_done_idx = event_types.index("text_done")
        second_start_idx = len(event_types) - 1 - event_types[::-1].index("agent_start")
        assert text_done_idx < second_start_idx

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_state_update_emitted_on_tool_store_change(
        self, mock_get_graph, auth_client
    ):
        """When a tool writes to tool_store, a state_update SSE event is emitted."""
        import app.modules.marketdemandanalyst.state as state_mod

        client, headers = auth_client
        course_id = _create_course(client, headers)
        ns = ("job_analyst:abc",)
        tc_id = str(uuid.uuid4())

        ai_with_tool = _make_ai_chunk(
            content="",
            tool_call_chunks=[{"id": tc_id, "name": "fetch_jobs", "args": "{}"}],
        )

        # Simulate tool_store mutation during graph execution
        async def streaming_side_effect(*args, **kwargs):
            yield (ns, (ai_with_tool, {}))
            # Simulate the tool writing to tool_store
            state_mod.tool_store["fetched_jobs"] = [{"title": "Python Dev"}]
            tool_result = ToolMessage(
                content='[{"title": "Python Dev"}]',
                tool_call_id=tc_id,
                name="fetch_jobs",
            )
            yield (ns, (tool_result, {}))

        mock_g = MagicMock()
        mock_g.astream = streaming_side_effect
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "fetch"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        state_updates = [e for e in events if e["event"] == "state_update"]

        assert len(state_updates) >= 1
        fetched_update = next(
            (e for e in state_updates if e["data"]["stateKey"] == "fetched_jobs"),
            None,
        )
        assert fetched_update is not None
        assert fetched_update["data"]["value"] == [{"title": "Python Dev"}]

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_thread_id_is_course_scoped(self, mock_get_graph, auth_client, db_session):
        """Thread ids are derived from the teacher+course pair, not the request body."""
        client, headers = auth_client
        course_id = _create_course(client, headers)
        teacher_id = _get_user_id(db_session, "teacher@example.com")
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hi"},
            headers=headers,
        )
        assert resp.headers.get("x-thread-id") == f"mda-{teacher_id}-course-{course_id}"

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_empty_message_accepted(self, mock_get_graph, auth_client):
        """An empty message (initial greeting) doesn't error."""
        client, headers = auth_client
        course_id = _create_course(client, headers)
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": ""},
            headers=headers,
        )
        assert resp.status_code == 200


# ── Tests: State Endpoint ────────────────────────────────────


class TestGetState:
    def test_returns_all_tracked_keys(self, client, teacher_auth_headers):
        course_id = _create_course(client, teacher_auth_headers)
        resp = client.get(
            f"/courses/{course_id}/market-demand/state",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = [
            "course_id",
            "course_title",
            "course_description",
            "fetched_jobs",
            "job_groups",
            "selected_jobs",
            "extracted_skills",
            "total_jobs_for_extraction",
            "existing_graph_skills",
            "existing_concepts",
            "curriculum_mapping",
            "selected_for_insertion",
            "skill_concepts",
            "insertion_results",
        ]
        for key in expected_keys:
            assert key in data

    def test_empty_state_has_null_values(self, client, teacher_auth_headers):
        course_id = _create_course(client, teacher_auth_headers)
        resp = client.get(
            f"/courses/{course_id}/market-demand/state",
            headers=teacher_auth_headers,
        )
        data = resp.json()
        assert data["course_id"] == course_id
        assert data["course_title"] == "Market Demand Test Course"
        assert data["course_description"] == "Course used by market demand tests"
        for key, value in data.items():
            if key.startswith("course_"):
                continue
            assert value is None

    def test_state_is_isolated_per_course(
        self, client, teacher_auth_headers, db_session
    ):
        course_a = _create_course(client, teacher_auth_headers, title="Course A")
        course_b = _create_course(client, teacher_auth_headers, title="Course B")
        teacher_id = _get_user_id(db_session, "teacher@example.com")
        db_session.add(
            MDAThreadState(
                thread_id=f"mda-{teacher_id}-course-{course_a}",
                state_json={
                    "course_id": course_a,
                    "course_title": "Course A",
                    "fetched_jobs": [{"title": "Backend Engineer"}],
                },
            )
        )
        db_session.commit()

        resp_a = client.get(
            f"/courses/{course_a}/market-demand/state",
            headers=teacher_auth_headers,
        )
        resp_b = client.get(
            f"/courses/{course_b}/market-demand/state",
            headers=teacher_auth_headers,
        )

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert resp_a.json()["fetched_jobs"] == [{"title": "Backend Engineer"}]
        assert resp_b.json()["fetched_jobs"] is None
        assert resp_b.json()["course_id"] == course_b


# ── Tests: SSE Helper Functions ──────────────────────────────


class TestSSEHelpers:
    def test_sse_format(self):
        from app.modules.marketdemandanalyst.routes import _sse

        result = _sse("test_event", {"key": "value"})
        assert result.startswith("event: test_event\n")
        assert "data:" in result
        assert result.endswith("\n\n")
        # data should be valid JSON with type field injected
        data_line = [line for line in result.split("\n") if line.startswith("data:")][0]
        parsed = json.loads(data_line.split(":", 1)[1])
        assert parsed == {"type": "test_event", "key": "value"}

    def test_resolve_agent_with_namespace(self):
        from app.modules.marketdemandanalyst.routes import _resolve_agent

        assert _resolve_agent(("job_analyst:abc123",)) == "job_analyst"
        assert _resolve_agent(("skill_extractor:def",)) == "skill_extractor"
        assert _resolve_agent(()) == "unknown"

    def test_snapshot_state_reflects_tool_store(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.state import snapshot_state

        state_mod.tool_store["extracted_skills"] = [{"name": "Python", "frequency": 10}]
        snapshot = snapshot_state()
        assert snapshot["extracted_skills"] == [{"name": "Python", "frequency": 10}]
        assert snapshot["fetched_jobs"] is None

    def test_restore_state_overwrites_tool_store(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.state import restore_state

        state_mod.tool_store["fetched_jobs"] = [{"title": "Old"}]
        state_mod.tool_store["some_extra_key"] = "leftover"

        restore_state(
            {
                "fetched_jobs": [{"title": "New"}],
                "extracted_skills": [{"name": "Go"}],
            }
        )

        assert state_mod.tool_store.get("fetched_jobs") == [{"title": "New"}]
        assert state_mod.tool_store.get("extracted_skills") == [{"name": "Go"}]
        # Extra keys not in STATE_KEYS are cleared
        assert "some_extra_key" not in state_mod.tool_store

    def test_pipeline_summary_empty(self):
        from app.modules.marketdemandanalyst.state import pipeline_summary

        result = pipeline_summary()
        assert "Pipeline not started" in result
        assert "NEXT: Fetch jobs" in result

    def test_pipeline_summary_mid_pipeline(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.state import pipeline_summary

        state_mod.tool_store["fetched_jobs"] = [{"title": "Dev"}] * 10
        state_mod.tool_store["job_groups"] = {"Dev": [0, 1, 2]}
        state_mod.tool_store["selected_jobs"] = [{"title": "Dev"}] * 5

        result = pipeline_summary()
        assert "10 jobs" in result
        assert "Selected 5 jobs" in result
        assert "NEXT: Extract skills" in result

    def test_pipeline_summary_complete(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.state import pipeline_summary

        state_mod.tool_store["insertion_results"] = {
            "skills": 3,
            "job_postings": 10,
        }

        result = pipeline_summary()
        assert "Pipeline COMPLETE" in result

    def test_pipeline_summary_requires_complete_mapping(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.state import pipeline_summary

        state_mod.tool_store["course_id"] = 2
        state_mod.tool_store["course_title"] = "Big Data"
        state_mod.tool_store["curated_skills"] = [
            {"name": "Skill A"},
            {"name": "Skill B"},
        ]
        state_mod.tool_store["curriculum_mapping"] = [
            {"name": "Skill A", "status": "covered"}
        ]

        result = pipeline_summary()

        assert "Teacher curated 2 skills" in result
        assert "Mapping coverage: 1/2 curated skills accounted for" in result
        assert "NEXT: Map curated skills to curriculum" in result

    def test_extract_agent_from_message(self):
        from langchain_core.messages import AIMessage

        from app.modules.marketdemandanalyst.routes import _extract_agent_from_message

        msg_named = AIMessage(content="hi", name="supervisor")
        assert _extract_agent_from_message(msg_named) == "supervisor"

        msg_unnamed = AIMessage(content="hi")
        assert _extract_agent_from_message(msg_unnamed) == "unknown"


# ── Tests: History Endpoint ──────────────────────────────────


class TestHistoryEndpoint:
    def test_unauthenticated_history_returns_401(self, client):
        resp = client.get("/courses/1/market-demand/history")
        assert resp.status_code == 401

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_empty_history(self, mock_get_graph, client, teacher_auth_headers):
        course_id = _create_course(client, teacher_auth_headers)
        mock_g = MagicMock()
        mock_state = MagicMock()
        mock_state.values = {}
        mock_g.aget_state = AsyncMock(return_value=mock_state)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.get(
            f"/courses/{course_id}/market-demand/history",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["messages"] == []
        assert "threadId" in data

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_history_converts_messages(
        self, mock_get_graph, client, teacher_auth_headers
    ):
        course_id = _create_course(client, teacher_auth_headers)
        mock_g = MagicMock()
        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                HumanMessage(content="hello", id="h1"),
                AIMessage(content="hi there", name="supervisor", id="a1"),
            ]
        }
        mock_g.aget_state = AsyncMock(return_value=mock_state)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.get(
            f"/courses/{course_id}/market-demand/history",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "hello"
        assert data["messages"][1]["role"] == "agent"
        assert data["messages"][1]["agent"] == "supervisor"
        assert data["messages"][1]["agentDisplayName"] == "Supervisor"

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_history_merges_same_agent_messages(
        self, mock_get_graph, client, teacher_auth_headers
    ):
        """Consecutive AI messages from the same agent are merged."""
        course_id = _create_course(client, teacher_auth_headers)
        mock_g = MagicMock()
        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                AIMessage(content="part one ", name="supervisor", id="a1"),
                AIMessage(content="part two", name="supervisor", id="a2"),
            ]
        }
        mock_g.aget_state = AsyncMock(return_value=mock_state)
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.get(
            f"/courses/{course_id}/market-demand/history",
            headers=teacher_auth_headers,
        )
        data = resp.json()
        # Two consecutive supervisor messages should be merged into one
        agent_msgs = [m for m in data["messages"] if m["role"] == "agent"]
        assert len(agent_msgs) == 1
        assert agent_msgs[0]["content"] == "part one part two"


# ── Tests: Delete Endpoint ───────────────────────────────────


class TestDeleteEndpoint:
    def test_unauthenticated_delete_returns_401(self, client):
        resp = client.delete("/courses/1/market-demand/history")
        assert resp.status_code == 401

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_delete_returns_status(self, mock_get_graph, client, teacher_auth_headers):
        course_id = _create_course(client, teacher_auth_headers)
        mock_g = MagicMock()
        mock_checkpointer = MagicMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_g.checkpointer = mock_checkpointer
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.delete(
            f"/courses/{course_id}/market-demand/history",
            headers=teacher_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert "threadId" in data

    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_delete_clears_tool_store(
        self, mock_get_graph, client, teacher_auth_headers
    ):
        import app.modules.marketdemandanalyst.state as state_mod

        course_id = _create_course(client, teacher_auth_headers)
        state_mod.tool_store["fetched_jobs"] = [{"title": "Dev"}]

        mock_g = MagicMock()
        mock_g.checkpointer = None
        mock_get_graph.return_value = (mock_g, MagicMock())

        client.delete(
            f"/courses/{course_id}/market-demand/history",
            headers=teacher_auth_headers,
        )
        assert len(state_mod.tool_store) == 0


class TestSelectJobsByGroup:
    def test_select_jobs_by_group_all_selects_every_group(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.tools import select_jobs_by_group

        state_mod.tool_store["fetched_jobs"] = [
            {"title": "Job 1"},
            {"title": "Job 2"},
            {"title": "Job 3"},
        ]
        state_mod.tool_store["job_groups"] = {
            "Data Engineer": [0, 1],
            "Analytics Engineer": [2],
        }

        result = select_jobs_by_group.invoke({"group_names": "all"})

        assert "Selected 3 jobs from all 2 groups" in result
        assert len(state_mod.tool_store["selected_jobs"]) == 3

    def test_select_jobs_by_group_every_group_selects_every_group(self):
        import app.modules.marketdemandanalyst.state as state_mod
        from app.modules.marketdemandanalyst.tools import select_jobs_by_group

        state_mod.tool_store["fetched_jobs"] = [
            {"title": "Job 1"},
            {"title": "Job 2"},
        ]
        state_mod.tool_store["job_groups"] = {
            "Machine Learning Engineer": [0],
            "Data Scientist": [1],
        }

        result = select_jobs_by_group.invoke({"group_names": "every group"})

        assert "Selected 2 jobs from all 2 groups" in result
        assert len(state_mod.tool_store["selected_jobs"]) == 2


class TestCourseScopedContext:
    @patch("app.modules.marketdemandanalyst.routes.get_graph")
    def test_chat_seeds_course_context(
        self, mock_get_graph, client, teacher_auth_headers
    ):
        import app.modules.marketdemandanalyst.state as state_mod

        course_id = _create_course(client, teacher_auth_headers, title="Big Data")
        mock_g = MagicMock()
        mock_g.astream = _mock_astream([])
        mock_get_graph.return_value = (mock_g, MagicMock())

        resp = client.post(
            f"/courses/{course_id}/market-demand/chat",
            json={"message": "hello"},
            headers=teacher_auth_headers,
        )

        assert resp.status_code == 200
        assert state_mod.tool_store["course_id"] == course_id
        assert state_mod.tool_store["course_title"] == "Big Data"
        assert state_mod.tool_store["course_description"] == (
            "Course used by market demand tests"
        )

    def test_other_teacher_cannot_access_course(self, client, teacher_auth_headers):
        course_id = _create_course(client, teacher_auth_headers)
        other_headers = _create_teacher_headers(client, email="teacher2@example.com")

        resp = client.get(
            f"/courses/{course_id}/market-demand/state",
            headers=other_headers,
        )

        assert resp.status_code == 404


class TestCourseScopedQueries:
    def test_get_chapter_details_scopes_lookup_to_course(self, monkeypatch):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["course_id"] = 2
        state_mod.tool_store["course_title"] = "Big Data"

        session = MagicMock()
        session.run.return_value = []

        class _SessionCtx:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(tools_mod, "_neo4j_session", lambda: _SessionCtx())

        tools_mod.get_chapter_details.invoke({"chapter_indices": "1"})

        query, params = session.run.call_args.args
        assert "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->" in query
        assert "INCLUDES_DOCUMENT" in query
        assert "TEACHES_CONCEPT" not in query
        assert params["course_id"] == 2

    def test_check_skills_coverage_accepts_json_array_and_uses_document_concepts(
        self, monkeypatch
    ):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["course_id"] = 2

        session = MagicMock()
        session.run.return_value = []

        class _SessionCtx:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(tools_mod, "_neo4j_session", lambda: _SessionCtx())

        tools_mod.check_skills_coverage.invoke(
            {
                "skill_names": json.dumps(
                    ["Implement APIs with OpenAI, Anthropic, Google"]
                )
            }
        )

        query, params = session.run.call_args.args
        assert params["names"] == ["Implement APIs with OpenAI, Anthropic, Google"]
        assert "INCLUDES_DOCUMENT" in query
        assert "TEACHES_CONCEPT" not in query
        assert (
            "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(ms:MARKET_SKILL)"
            in query
        )

    def test_load_existing_skills_includes_book_and_market_skills(self, monkeypatch):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["course_id"] = 2

        session = MagicMock()
        session.run.return_value = []

        class _SessionCtx:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(tools_mod, "_neo4j_session", lambda: _SessionCtx())

        tools_mod.load_existing_skills_for_chapters.invoke(
            {"chapter_titles": json.dumps(["Foundations of Big Data"])}
        )

        query, params = session.run.call_args.args
        assert params["titles"] == ["Foundations of Big Data"]
        assert "BOOK_SKILL" in query
        assert "MARKET_SKILL" in query

    def test_insert_market_skills_uses_course_scoped_identity(self, monkeypatch):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["course_id"] = 2
        state_mod.tool_store["skill_concepts"] = {
            "Query and analyze data using SQL": {
                "chapter_title": "Data Storage",
                "category": "database",
                "frequency": 3,
                "demand_pct": 33.3,
                "priority": "high",
                "status": "gap",
                "rationale": "",
                "reasoning": "",
                "existing_concepts": [],
                "new_concepts": [],
                "source_job_urls": [],
            }
        }
        state_mod.tool_store["selected_jobs"] = []

        session = MagicMock()

        class _SessionCtx:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(tools_mod, "_neo4j_session", lambda: _SessionCtx())

        result = tools_mod.insert_market_skills_to_neo4j.invoke({})

        assert "Knowledge Map updated successfully" in result
        queries = [call.args[0] for call in session.run.call_args_list]
        params_list = [call.args[1] for call in session.run.call_args_list]
        assert any(
            "MERGE (s:MARKET_SKILL:SKILL {name: $name})" in query for query in queries
        )
        assert any(
            "s.course_id = coalesce(s.course_id, $course_id)" in query
            for query in queries
        )
        assert any(
            params.get("course_id") == 2
            for params in params_list
            if isinstance(params, dict)
        )

    def test_delete_market_skills_all_scopes_to_current_course(self, monkeypatch):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["course_id"] = 2

        session = MagicMock()
        delete_result = MagicMock()
        delete_result.single.return_value = {"deleted": 1}
        orphan_jobs = MagicMock()
        orphan_jobs.single.return_value = {"orphans": 0}
        orphan_concepts = MagicMock()
        orphan_concepts.single.return_value = {"orphan_concepts": 0}
        session.run.side_effect = [delete_result, orphan_jobs, orphan_concepts]

        class _SessionCtx:
            def __enter__(self):
                return session

            def __exit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(tools_mod, "_neo4j_session", lambda: _SessionCtx())

        result = tools_mod.delete_market_skills.invoke({"skill_names": "all"})

        assert "course 2" in result
        query, params = session.run.call_args_list[0].args
        assert (
            "MATCH (cl:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)<-[:MAPPED_TO]-(s:MARKET_SKILL)"
            in query
        )
        assert params["course_id"] == 2


class TestDatabaseResilience:
    def test_get_owned_course_retries_with_fresh_session(self, monkeypatch):
        import app.modules.marketdemandanalyst.routes as routes_mod

        teacher = SimpleNamespace(id=7)
        course = SimpleNamespace(id=2, teacher_id=7)

        primary_db = MagicMock()
        primary_bind = MagicMock()
        primary_db.get_bind.return_value = primary_bind
        primary_db.get.side_effect = OperationalError(
            "SELECT 1",
            {},
            Exception("server closed the connection unexpectedly"),
        )

        retry_db = MagicMock()
        retry_db.get.return_value = course
        monkeypatch.setattr(routes_mod, "SessionLocal", lambda: retry_db)

        result = routes_mod._get_owned_course(2, teacher, primary_db)

        assert result is course
        primary_db.rollback.assert_called_once()
        primary_bind.dispose.assert_called_once()
        retry_db.close.assert_called_once()

    def test_get_owned_course_returns_503_after_retry_failure(self, monkeypatch):
        import app.modules.marketdemandanalyst.routes as routes_mod

        teacher = SimpleNamespace(id=7)
        primary_db = MagicMock()
        primary_bind = MagicMock()
        primary_db.get_bind.return_value = primary_bind
        primary_db.get.side_effect = OperationalError(
            "SELECT 1",
            {},
            Exception("server closed the connection unexpectedly"),
        )

        retry_db = MagicMock()
        retry_db.get.side_effect = OperationalError(
            "SELECT 1",
            {},
            Exception("server closed the connection unexpectedly"),
        )
        monkeypatch.setattr(routes_mod, "SessionLocal", lambda: retry_db)

        with pytest.raises(HTTPException) as exc_info:
            routes_mod._get_owned_course(2, teacher, primary_db)

        assert exc_info.value.status_code == 503
        assert "Database is temporarily unavailable" in exc_info.value.detail
        retry_db.close.assert_called_once()

    @pytest.mark.anyio
    async def test_load_persisted_state_returns_none_after_retries(self, monkeypatch):
        import app.modules.marketdemandanalyst.routes as routes_mod

        routes_mod._state_cache.clear()

        class BrokenAsyncSession:
            async def __aenter__(self):
                raise RuntimeError("database unavailable")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        monkeypatch.setattr(
            routes_mod, "AsyncSessionLocal", lambda: BrokenAsyncSession()
        )

        result = await routes_mod._load_persisted_state("thread-xyz")

        assert result is None
        assert routes_mod._state_cache["thread-xyz"] is None


class TestCurriculumMappingValidation:
    def test_save_curriculum_mapping_requires_every_curated_skill(self):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["curated_skills"] = [
            {"name": "Skill A", "category": "cloud"},
            {"name": "Skill B", "category": "database"},
        ]
        state_mod.tool_store["extracted_skills"] = [
            {"name": "Skill A", "category": "cloud"},
            {"name": "Skill B", "category": "database"},
        ]

        result = tools_mod.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "name": "Skill A",
                            "category": "cloud",
                            "status": "covered",
                            "target_chapter": "",
                            "priority": "high",
                            "reasoning": "Already taught",
                        }
                    ]
                )
            }
        )

        assert (
            "Curriculum mapping must account for every curated skill exactly once."
            in result
        )
        assert "Missing curated skills (1): Skill B" in result
        assert "curriculum_mapping" not in state_mod.tool_store

    def test_save_curriculum_mapping_sets_mapped_skills_and_clears_downstream_state(
        self,
    ):
        import app.modules.marketdemandanalyst.state as state_mod
        import app.modules.marketdemandanalyst.tools as tools_mod

        state_mod.tool_store["curated_skills"] = [
            {"name": "Skill A", "category": "cloud"},
            {"name": "Skill B", "category": "database"},
            {"name": "Skill C", "category": "devops"},
        ]
        state_mod.tool_store["extracted_skills"] = [
            {"name": "Skill A", "category": "cloud"},
            {"name": "Skill B", "category": "database"},
            {"name": "Skill C", "category": "devops"},
        ]
        state_mod.tool_store["final_skills"] = ["stale"]
        state_mod.tool_store["selected_for_insertion"] = [{"name": "stale"}]
        state_mod.tool_store["skill_concepts"] = {"stale": {}}
        state_mod.tool_store["insertion_results"] = {"skills": 1}
        state_mod.tool_store["_cleaned_results"] = [{"chapter": "stale"}]

        result = tools_mod.save_curriculum_mapping.invoke(
            {
                "mapping_json": json.dumps(
                    [
                        {
                            "name": "Skill A",
                            "category": "cloud",
                            "status": "covered",
                            "target_chapter": "",
                            "priority": "high",
                            "reasoning": "Already taught",
                        },
                        {
                            "name": "Skill B",
                            "category": "database",
                            "status": "gap",
                            "target_chapter": "Chapter 2",
                            "priority": "medium",
                            "reasoning": "Fits storage chapter",
                        },
                        {
                            "name": "Skill C",
                            "category": "devops",
                            "status": "new_topic_needed",
                            "target_chapter": "Chapter 5",
                            "priority": "medium",
                            "reasoning": "Useful extension",
                        },
                    ]
                )
            }
        )

        assert "Curriculum mapping saved for 3 curated skills" in result
        assert "Skills requiring insertion: 2" in result
        assert state_mod.tool_store["mapped_skills"] == {
            "Chapter 2": ["Skill B"],
            "Chapter 5": ["Skill C"],
        }
        assert "final_skills" not in state_mod.tool_store
        assert "selected_for_insertion" not in state_mod.tool_store
        assert "skill_concepts" not in state_mod.tool_store
        assert "insertion_results" not in state_mod.tool_store
        assert "_cleaned_results" not in state_mod.tool_store
