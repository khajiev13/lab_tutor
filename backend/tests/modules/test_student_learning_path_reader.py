import asyncio
from unittest.mock import MagicMock

import httpx

from app.modules.student_learning_path import reader_extractor


def _stub_async_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        reader_extractor,
        "_build_async_client",
        lambda: httpx.AsyncClient(transport=transport, follow_redirects=True),
    )


def test_extract_reading_markdown_returns_markdown_for_html(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><article>Batch systems</article></body></html>",
        )

    _stub_async_client(monkeypatch, handler)
    monkeypatch.setattr(
        reader_extractor.trafilatura,
        "extract",
        lambda *_args, **_kwargs: "# Batch Systems\n\n" + ("A" * 240),
    )

    result = asyncio.run(
        reader_extractor.extract_reading_markdown("https://example.com/reading")
    )

    assert result.status == "ready"
    assert result.content_markdown.startswith("# Batch Systems")


def test_extract_reading_markdown_rejects_non_html_content(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.7",
        )

    extract = MagicMock()
    _stub_async_client(monkeypatch, handler)
    monkeypatch.setattr(reader_extractor.trafilatura, "extract", extract)

    result = asyncio.run(
        reader_extractor.extract_reading_markdown("https://example.com/reading.pdf")
    )

    assert result.status == "failed"
    assert result.error_code == "non_html"
    extract.assert_not_called()


def test_extract_reading_markdown_handles_timeout(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _stub_async_client(monkeypatch, handler)

    result = asyncio.run(
        reader_extractor.extract_reading_markdown("https://example.com/reading")
    )

    assert result.status == "failed"
    assert result.error_code == "timeout"


def test_extract_reading_markdown_rejects_oversized_responses(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"a" * (reader_extractor.MAX_HTML_BYTES + 1),
        )

    extract = MagicMock()
    _stub_async_client(monkeypatch, handler)
    monkeypatch.setattr(reader_extractor.trafilatura, "extract", extract)

    result = asyncio.run(
        reader_extractor.extract_reading_markdown("https://example.com/reading")
    )

    assert result.status == "failed"
    assert result.error_code == "too_large"
    extract.assert_not_called()


def test_extract_reading_markdown_rejects_too_short_extractions(monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><article>Short article</article></body></html>",
        )

    _stub_async_client(monkeypatch, handler)
    monkeypatch.setattr(
        reader_extractor.trafilatura,
        "extract",
        lambda *_args, **_kwargs: "Too short",
    )

    result = asyncio.run(
        reader_extractor.extract_reading_markdown("https://example.com/reading")
    )

    assert result.status == "failed"
    assert result.error_code == "too_short"
