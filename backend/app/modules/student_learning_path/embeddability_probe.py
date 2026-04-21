"""Iframe embeddability probe — checks X-Frame-Options / CSP headers server-side."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

PROBE_TIMEOUT_SECONDS = 5.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class EmbeddabilityResult:
    embeddable: bool
    reason: (
        Literal[
            "xfo_deny",
            "xfo_sameorigin",
            "csp_frame_ancestors",
            "probe_http_error",
            "probe_network_error",
        ]
        | None
    ) = None


def parse_headers(headers: httpx.Headers) -> EmbeddabilityResult:
    """Determine iframe embeddability from response headers (pure, testable)."""
    xfo = headers.get("x-frame-options", "").strip().upper()
    if xfo == "DENY":
        return EmbeddabilityResult(embeddable=False, reason="xfo_deny")
    if xfo == "SAMEORIGIN":
        return EmbeddabilityResult(embeddable=False, reason="xfo_sameorigin")

    csp = headers.get("content-security-policy", "")
    for directive in csp.split(";"):
        parts = directive.strip().split()
        if not parts or parts[0].lower() != "frame-ancestors":
            continue
        tokens = [t.lower() for t in parts[1:]]
        if "*" in tokens:
            return EmbeddabilityResult(embeddable=True)
        return EmbeddabilityResult(embeddable=False, reason="csp_frame_ancestors")

    return EmbeddabilityResult(embeddable=True)


def _build_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=True,
        headers={
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "User-Agent": DEFAULT_USER_AGENT,
        },
        timeout=httpx.Timeout(PROBE_TIMEOUT_SECONDS),
    )


async def probe_iframe_embeddability(url: str) -> EmbeddabilityResult:
    """Probe a URL to determine if iframe embedding is permitted."""
    try:
        async with _build_client() as client:
            try:
                head_response = await client.head(url)
                if head_response.status_code < 400:
                    return parse_headers(head_response.headers)
            except httpx.HTTPError:
                pass

            async with client.stream("GET", url) as get_response:
                return parse_headers(get_response.headers)

    except httpx.HTTPError:
        return EmbeddabilityResult(embeddable=False, reason="probe_network_error")
    except Exception:
        return EmbeddabilityResult(embeddable=False, reason="probe_network_error")
