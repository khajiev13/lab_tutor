import asyncio
import json

import httpx
import pytest

from app.core.settings import settings
from app.modules.marketdemandanalyst import extractor, graph, priority_service


@pytest.fixture
def completion_requests(monkeypatch):
    """Capture serialized requests while retaining the real LangChain/OpenAI clients."""
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        completion = {
            "id": "test-completion",
            "created": 0,
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "[]"},
                    "finish_reason": "stop",
                }
            ],
            "object": "chat.completion",
        }
        if body.get("stream"):
            completion["object"] = "chat.completion.chunk"
            completion["choices"][0]["delta"] = completion["choices"][0].pop("message")
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/event-stream"},
                content=f"data: {json.dumps(completion)}\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(200, request=request, json=completion)

    def send(_client, request, **_kwargs):
        return respond(request)

    async def async_send(_client, request, **_kwargs):
        return respond(request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", async_send)
    monkeypatch.setenv("LAB_TUTOR_LLM_API_KEY", "test-only")
    monkeypatch.setenv("LAB_TUTOR_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setattr(settings, "llm_api_key", "test-only")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.invalid/v1")
    return requests


@pytest.mark.parametrize(
    ("model", "expected_options"),
    [
        ("deepseek-v4.1-flash", {"thinking": {"type": "disabled"}}),
        ("qwen3.5-plus", {}),
    ],
)
def test_extraction_serializes_model_specific_thinking_options(
    monkeypatch, completion_requests, model, expected_options
):
    monkeypatch.setenv("LAB_TUTOR_LLM_MODEL", model)

    response = extractor._get_extraction_llm(timeout_seconds=90).invoke(
        "Extract skills"
    )

    assert response.content == "[]"
    assert len(completion_requests) == 1
    request = completion_requests[0]
    assert request["model"] == model
    assert request["stream"] is False
    assert "extra_body" not in request
    assert {
        key: request[key] for key in ("thinking", "enable_thinking") if key in request
    } == expected_options


@pytest.mark.parametrize(
    ("model", "expected_options"),
    [
        ("deepseek-v4.1-flash", {"thinking": {"type": "disabled"}}),
        ("qwen3.5-plus", {"enable_thinking": False}),
    ],
)
def test_swarm_stream_serializes_model_specific_thinking_options(
    monkeypatch, completion_requests, model, expected_options
):
    monkeypatch.setattr(settings, "llm_agent_model", model)

    response = asyncio.run(graph._create_llm().ainvoke("Find skills"))

    assert response.content == "[]"
    assert len(completion_requests) == 1
    request = completion_requests[0]
    assert request["model"] == model
    assert request["stream"] is True
    assert "extra_body" not in request
    assert {
        key: request[key] for key in ("thinking", "enable_thinking") if key in request
    } == expected_options


@pytest.mark.parametrize(
    ("extraction_model", "priority_model", "expected_options"),
    [
        (
            "deepseek-v4.1-flash",
            "qwen3.5-plus",
            {"enable_thinking": False},
        ),
        (
            "qwen3.5-plus",
            "deepseek-v4.1-flash",
            {"thinking": {"type": "disabled"}},
        ),
    ],
)
def test_priority_override_replaces_extraction_thinking_options(
    monkeypatch,
    completion_requests,
    extraction_model,
    priority_model,
    expected_options,
):
    monkeypatch.setenv("LAB_TUTOR_LLM_MODEL", extraction_model)
    monkeypatch.setattr(settings, "market_skill_priority_model", priority_model)

    response = priority_service._get_priority_llm().invoke("Assess skills")

    assert response.content == "[]"
    assert len(completion_requests) == 1
    request = completion_requests[0]
    assert request["model"] == priority_model
    assert request["response_format"] == {"type": "json_object"}
    assert {
        key: request[key] for key in ("thinking", "enable_thinking") if key in request
    } == expected_options


def test_evidenced_extraction_serializes_json_mode_and_output_bound(
    monkeypatch, completion_requests
):
    monkeypatch.setenv("LAB_TUTOR_LLM_MODEL", "deepseek-v4.1-flash")
    result = extractor._extract_evidenced_job(
        {
            "snapshot_id": "posting-1",
            "demand_identity": "provider:1",
            "description": "Build data pipelines.",
        }
    )
    assert result["assessments"][0]["status"] == "full"
    assert len(completion_requests) == 1
    request = completion_requests[0]
    assert request["response_format"] == {"type": "json_object"}
    assert request["stream"] is False
    assert request.get("max_completion_tokens", request.get("max_tokens")) == 6000
    assert request["thinking"] == {"type": "disabled"}
