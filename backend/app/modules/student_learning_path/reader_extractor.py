"""Remote reading fetch and markdown extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import SimpleNamespace
from typing import Literal

import httpx

try:
    import trafilatura  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - exercised in container fallback
    trafilatura = SimpleNamespace(extract=lambda *_args, **_kwargs: None)

MAX_HTML_BYTES = 3 * 1024 * 1024
MIN_MARKDOWN_CHAR_COUNT = 200
REQUEST_TIMEOUT_SECONDS = 20.0
ACCEPTED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class ReaderExtractionSuccess:
    content_markdown: str
    status: Literal["ready"] = "ready"


@dataclass(frozen=True, slots=True)
class ReaderExtractionFailure:
    error_code: str
    error_message: str
    status: Literal["failed"] = "failed"


ReaderExtractionResult = ReaderExtractionSuccess | ReaderExtractionFailure


def _build_async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
    )


def _failure(error_code: str, error_message: str) -> ReaderExtractionFailure:
    return ReaderExtractionFailure(
        error_code=error_code,
        error_message=error_message,
    )


async def extract_reading_markdown(url: str) -> ReaderExtractionResult:
    """Fetch a reading URL and extract article markdown."""

    try:
        async with _build_async_client() as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                media_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if media_type not in ACCEPTED_CONTENT_TYPES:
                    return _failure(
                        "non_html",
                        "This source is not an HTML article that can be shown in-app.",
                    )

                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_HTML_BYTES:
                    return _failure(
                        "too_large",
                        "This source is too large to extract in-app.",
                    )

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_HTML_BYTES:
                        return _failure(
                            "too_large",
                            "This source is too large to extract in-app.",
                        )

                encoding = response.encoding or "utf-8"
    except httpx.TimeoutException:
        return _failure(
            "timeout",
            "This source took too long to respond.",
        )
    except httpx.HTTPStatusError as exc:
        return _failure(
            "http_error",
            f"This source returned an HTTP {exc.response.status_code} response.",
        )
    except httpx.HTTPError:
        return _failure(
            "network_error",
            "We could not fetch this source right now.",
        )

    extracted_markdown = trafilatura.extract(
        bytes(body).decode(encoding, errors="ignore"),
        output_format="markdown",
        include_formatting=True,
        include_links=True,
    )
    if not extracted_markdown:
        return _failure(
            "empty",
            "We could not extract readable article content from this source.",
        )

    cleaned_markdown = extracted_markdown.strip()
    if len(re.sub(r"\s+", "", cleaned_markdown)) < MIN_MARKDOWN_CHAR_COUNT:
        return _failure(
            "too_short",
            "We could not extract enough readable article content from this source.",
        )

    return ReaderExtractionSuccess(content_markdown=cleaned_markdown)
