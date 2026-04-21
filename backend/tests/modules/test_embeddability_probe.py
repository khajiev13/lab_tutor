import asyncio

import httpx

from app.modules.student_learning_path import embeddability_probe
from app.modules.student_learning_path.embeddability_probe import (
    EmbeddabilityResult,
    parse_headers,
)

# ── parse_headers (pure) ──────────────────────────────────────


def _headers(**kwargs: str) -> httpx.Headers:
    return httpx.Headers(kwargs)


def test_parse_headers_xfo_deny():
    result = parse_headers(_headers(**{"x-frame-options": "DENY"}))
    assert result == EmbeddabilityResult(embeddable=False, reason="xfo_deny")


def test_parse_headers_xfo_deny_case_insensitive():
    result = parse_headers(_headers(**{"x-frame-options": "deny"}))
    assert result == EmbeddabilityResult(embeddable=False, reason="xfo_deny")


def test_parse_headers_xfo_sameorigin():
    result = parse_headers(_headers(**{"x-frame-options": "SAMEORIGIN"}))
    assert result == EmbeddabilityResult(embeddable=False, reason="xfo_sameorigin")


def test_parse_headers_csp_frame_ancestors_none():
    result = parse_headers(
        _headers(**{"content-security-policy": "frame-ancestors 'none'"})
    )
    assert result == EmbeddabilityResult(embeddable=False, reason="csp_frame_ancestors")


def test_parse_headers_csp_frame_ancestors_wildcard():
    result = parse_headers(_headers(**{"content-security-policy": "frame-ancestors *"}))
    assert result == EmbeddabilityResult(embeddable=True)


def test_parse_headers_csp_frame_ancestors_specific_origin():
    result = parse_headers(
        _headers(
            **{
                "content-security-policy": (
                    "default-src 'self'; frame-ancestors https://example.com"
                )
            }
        )
    )
    assert result == EmbeddabilityResult(embeddable=False, reason="csp_frame_ancestors")


def test_parse_headers_no_restrictive_headers():
    result = parse_headers(_headers(**{"content-type": "text/html"}))
    assert result == EmbeddabilityResult(embeddable=True)


def test_parse_headers_empty():
    result = parse_headers(httpx.Headers({}))
    assert result == EmbeddabilityResult(embeddable=True)


def test_parse_headers_csp_without_frame_ancestors():
    result = parse_headers(
        _headers(**{"content-security-policy": "default-src 'self'; script-src 'self'"})
    )
    assert result == EmbeddabilityResult(embeddable=True)


# ── probe_iframe_embeddability (network mocked) ───────────────


def _stub_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        embeddability_probe,
        "_build_client",
        lambda: httpx.AsyncClient(
            transport=transport,
            follow_redirects=True,
        ),
    )


def test_probe_returns_embeddable_when_no_blocking_headers(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"})

    _stub_client(monkeypatch, handler)
    result = asyncio.run(
        embeddability_probe.probe_iframe_embeddability("https://example.com")
    )
    assert result.embeddable is True


def test_probe_returns_not_embeddable_for_xfo_deny(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-frame-options": "DENY", "content-type": "text/html"},
        )

    _stub_client(monkeypatch, handler)
    result = asyncio.run(
        embeddability_probe.probe_iframe_embeddability("https://example.com")
    )
    assert result.embeddable is False
    assert result.reason == "xfo_deny"


def test_probe_falls_back_to_get_when_head_fails(monkeypatch):
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(
            200,
            headers={"x-frame-options": "SAMEORIGIN"},
        )

    _stub_client(monkeypatch, handler)
    result = asyncio.run(
        embeddability_probe.probe_iframe_embeddability("https://example.com")
    )
    assert result.embeddable is False
    assert result.reason == "xfo_sameorigin"
    assert call_count["n"] == 2


def test_probe_returns_network_error_on_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _stub_client(monkeypatch, handler)
    result = asyncio.run(
        embeddability_probe.probe_iframe_embeddability("https://example.com")
    )
    assert result.embeddable is False
    assert result.reason == "probe_network_error"
