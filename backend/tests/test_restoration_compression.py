"""Exercise restoration compression through the production ASGI middleware stack."""

import asyncio
import gzip
import json
from functools import partial

import pytest
from fastapi import FastAPI
from starlette.datastructures import Headers
from starlette.responses import Response, StreamingResponse
from starlette.types import ASGIApp, Message, Send

from main import app

LARGE_JSON = json.dumps(
    {
        "tool_result": "Complete evidence — skills and source detail. " * 200,
        "evidence_urls": ["https://example.com/vacancy?id=42&source=original"],
    },
    ensure_ascii=False,
).encode()


def _response_app(response: Response) -> FastAPI:
    # Use main.py's registrations and ordering, including RequestTimingMiddleware.
    probe = FastAPI(middleware=app.user_middleware)

    @probe.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def respond():
        return response

    return probe


async def _wire_request(
    application: ASGIApp,
    path: str,
    *,
    method: str = "GET",
    accept_encoding: str | None = "gzip",
    headers: dict[str, str] | None = None,
    on_send: Send | None = None,
) -> list[Message]:
    request_headers = dict(headers or {})
    if accept_encoding is not None:
        request_headers["Accept-Encoding"] = accept_encoding
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages = []
    request_received = False

    async def receive():
        nonlocal request_received
        if not request_received:
            request_received = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        messages.append(message)
        if on_send is not None:
            await on_send(message)

    await application(scope, receive, send)
    return messages


def _response_parts(messages: list[Message]) -> tuple[Headers, bytes]:
    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    assert start["status"] == 200
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return Headers(raw=start["headers"]), body


@pytest.mark.parametrize("endpoint", ["history", "state", "skill-review"])
@pytest.mark.parametrize("accept_encoding", ["gzip", "br, gzip;q=0.5"])
def test_large_restoration_json_is_gzipped_without_losing_any_bytes(
    endpoint, accept_encoding
):
    probe = _response_app(
        Response(LARGE_JSON, media_type="application/json", headers={"Vary": "Origin"})
    )
    headers, wire_body = _response_parts(
        asyncio.run(
            _wire_request(
                probe,
                f"/courses/42/market-demand/{endpoint}",
                accept_encoding=accept_encoding,
            )
        )
    )

    assert headers["content-encoding"] == "gzip"
    assert len(wire_body) < len(LARGE_JSON) // 2
    assert gzip.decompress(wire_body) == LARGE_JSON
    assert int(headers["content-length"]) == len(wire_body)
    assert headers["content-type"] == "application/json"
    assert set(headers["vary"].split(", ")) == {"Origin", "Accept-Encoding"}


@pytest.mark.parametrize(
    "accept_encoding",
    [None, "identity", "br", "xgzip", "gzip2", "gzip;q=0", "br, gzip; q=0.000"],
)
def test_restoration_json_stays_plain_without_gzip_support(accept_encoding):
    probe = _response_app(
        Response(LARGE_JSON, media_type="application/json", headers={"Vary": "Origin"})
    )
    headers, wire_body = _response_parts(
        asyncio.run(
            _wire_request(
                probe,
                "/courses/42/market-demand/state",
                accept_encoding=accept_encoding,
            )
        )
    )

    assert "content-encoding" not in headers
    assert wire_body == LARGE_JSON
    assert int(headers["content-length"]) == len(LARGE_JSON)
    assert set(headers["vary"].split(", ")) == {"Origin", "Accept-Encoding"}


def test_small_restoration_json_stays_plain():
    body = b'{"messages":[]}'
    probe = _response_app(Response(body, media_type="application/json"))
    headers, wire_body = _response_parts(
        asyncio.run(_wire_request(probe, "/courses/42/market-demand/history"))
    )

    assert "content-encoding" not in headers
    assert "vary" not in headers
    assert wire_body == body
    assert int(headers["content-length"]) == len(body)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/courses/42/market-demand/history"),
        ("DELETE", "/courses/42/market-demand/history"),
        ("PUT", "/courses/42/market-demand/skill-review/draft"),
        ("POST", "/courses/42/market-demand/chat"),
        ("GET", "/courses/42/market-demand/skill-review/postings/123"),
        ("GET", "/courses/42/market-demand/state/extra"),
        ("GET", "/courses/42/market-demand/history-extra"),
        ("GET", "/other/courses/42/market-demand/state"),
        ("POST", "/auth/jwt/login"),
        ("POST", "/courses/42/presentations"),
        ("GET", "/health"),
    ],
)
def test_other_paths_and_methods_are_unchanged(method, path):
    probe = _response_app(Response(LARGE_JSON, media_type="application/json"))
    headers, wire_body = _response_parts(
        asyncio.run(_wire_request(probe, path, method=method))
    )

    assert "content-encoding" not in headers
    assert "vary" not in headers
    assert wire_body == LARGE_JSON
    assert int(headers["content-length"]) == len(LARGE_JSON)


def test_pre_encoded_restoration_response_is_not_compressed_again():
    encoded = gzip.compress(json.dumps({"numbers": list(range(2048))}).encode())
    probe = _response_app(
        Response(
            encoded,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Vary": "Origin"},
        )
    )
    headers, wire_body = _response_parts(
        asyncio.run(_wire_request(probe, "/courses/42/market-demand/state"))
    )

    assert wire_body == encoded
    assert int(headers["content-length"]) == len(encoded)
    assert headers["content-encoding"] == "gzip"
    assert headers["vary"] == "Origin"


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/courses/42/market-demand/state"),
        ("POST", "/courses/42/market-demand/chat"),
    ],
)
def test_sse_headers_and_first_chunk_arrive_before_stream_completion(method, path):
    async def exercise_stream():
        release = asyncio.Event()
        first_received = asyncio.Event()
        messages = []
        first_chunk = b"data: first\n\n"
        last_chunk = b"data: last\n\n"

        async def chunks():
            yield first_chunk
            await release.wait()
            yield last_chunk

        async def observe(message):
            messages.append(message)
            if message.get("body") == first_chunk:
                first_received.set()

        probe = _response_app(
            StreamingResponse(chunks(), media_type="text/event-stream")
        )
        task = asyncio.create_task(
            _wire_request(probe, path, method=method, on_send=observe)
        )
        try:
            await asyncio.wait_for(first_received.wait(), timeout=1)
            assert not task.done()
            headers, body = _response_parts(messages)
            assert "content-encoding" not in headers
            assert "vary" not in headers
            assert body == first_chunk
            assert messages[0]["type"] == "http.response.start"
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=1)
        assert _response_parts(messages)[1] == first_chunk + last_chunk

    asyncio.run(exercise_stream())


def test_authenticated_state_restores_complete_postgres_payload_with_gzip(
    db_session, client, teacher_auth_headers
):
    from app.core.database import async_engine
    from app.modules.marketdemandanalyst.models import MDAThreadState

    response = client.post(
        "/courses",
        json={"title": "Compressed restoration"},
        headers=teacher_auth_headers,
    )
    assert response.status_code == 201
    course = response.json()
    jobs = [
        {
            "title": f"Evidence vacancy {index}",
            "description": "Complete original evidence. " * 100,
            "url": f"https://example.com/vacancy/{index}?source=original",
        }
        for index in range(20)
    ]
    stored_state = {"fetched_jobs": jobs, "course_id": course["id"]}
    thread = MDAThreadState(
        thread_id=f"mda-{course['teacher_id']}-course-{course['id']}",
        state_json=stored_state,
    )
    db_session.add(thread)
    db_session.commit()

    path = f"/courses/{course['id']}/market-demand/state"
    request = partial(_wire_request, app, path, headers=teacher_auth_headers)
    try:
        plain_headers, plain_body = _response_parts(
            client.portal.call(partial(request, accept_encoding="identity"))
        )
        gzip_headers, wire_body = _response_parts(client.portal.call(request))

        assert "content-encoding" not in plain_headers
        assert gzip_headers["content-encoding"] == "gzip"
        assert gzip.decompress(wire_body) == plain_body
        assert len(wire_body) < len(plain_body) // 2
        assert json.loads(plain_body)["fetched_jobs"] == jobs
        db_session.refresh(thread)
        assert thread.state_json == stored_state
    finally:
        client.portal.call(async_engine.dispose)
