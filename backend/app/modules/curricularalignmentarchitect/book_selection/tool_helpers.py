from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

from pydantic import BaseModel

from .tool_models import SearchResponse, SearchResultItem, ToolName

_WHITESPACE_RE = re.compile(r"\s+")


def clean_query(query: str, *, max_chars: int) -> str:
    q = _WHITESPACE_RE.sub(" ", (query or "").strip())
    if not q:
        return ""
    if len(q) > max_chars:
        q = q[:max_chars].rstrip()
    return q


def clean_snippet(text: str | None, *, max_chars: int = 320) -> str | None:
    if not text:
        return None
    s = _WHITESPACE_RE.sub(" ", str(text).strip())
    if not s:
        return None
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def json_response(payload: BaseModel) -> str:
    return payload.model_dump_json(exclude_none=True)


def error_response(tool_name: ToolName, query: str, msg: str) -> str:
    return json_response(
        SearchResponse(ok=False, tool=tool_name, query=query, error=msg)
    )


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ValueError(
            f"Missing env var {name}. Set it in your shell or a .env file."
        )
    return val


def http_get_json(url: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "lab-tutor/1.0 (+langchain-tools)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"HTTP request failed: {e}") from e

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Non-JSON response from API: {e}") from e

    if not isinstance(parsed, dict):
        raise RuntimeError("Unexpected API response shape (expected JSON object)")

    return parsed


def normalize_google_books_items(
    payload: dict[str, Any], *, max_results: int
) -> list[SearchResultItem]:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return []

    out: list[SearchResultItem] = []
    for item in items[: max_results if max_results > 0 else len(items)]:
        if not isinstance(item, dict):
            continue

        volume_info = item.get("volumeInfo")
        volume_info = volume_info if isinstance(volume_info, dict) else {}

        title = str(volume_info.get("title") or "").strip()
        subtitle = str(volume_info.get("subtitle") or "").strip()
        authors_raw = volume_info.get("authors")

        title_full = f"{title}: {subtitle}" if subtitle and title else title or subtitle

        authors: str | None = None
        if isinstance(authors_raw, list):
            authors_list = [str(a).strip() for a in authors_raw if a and str(a).strip()]
            if authors_list:
                authors = ", ".join(authors_list)

        description = clean_snippet(volume_info.get("description"), max_chars=320)

        info_link = volume_info.get("infoLink")
        canonical_url = str(info_link).strip() if info_link else None

        if not title_full and canonical_url:
            title_full = canonical_url

        if not title_full:
            continue

        snippet = description
        if authors:
            snippet = (f"By {authors}. " + (description or "")).strip() or None
            snippet = clean_snippet(snippet, max_chars=320)

        out.append(
            SearchResultItem(
                title=title_full,
                url=canonical_url,
                snippet=snippet,
                source="google_books",
                score=None,
            )
        )

    return out


def normalize_tavily_results(
    results: Any, *, max_snippet_chars: int
) -> list[SearchResultItem]:
    if not isinstance(results, list):
        return []

    out: list[SearchResultItem] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip() or None
        content = item.get("content")
        snippet = clean_snippet(
            str(content) if content is not None else None, max_chars=max_snippet_chars
        )
        score = item.get("score")
        score_f: float | None = None
        if isinstance(score, (int, float)):
            score_f = float(score)

        if not title and url:
            title = url
        if not title and not snippet:
            continue

        out.append(
            SearchResultItem(
                title=title or "(tavily result)",
                url=url,
                snippet=snippet,
                source="tavily",
                score=score_f,
            )
        )

    return out


def normalize_ddg_results(
    results: list[dict[str, Any]], *, max_snippet_chars: int = 320
) -> list[SearchResultItem]:
    out: list[SearchResultItem] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("href") or item.get("url") or "").strip() or None
        body = item.get("body") or item.get("snippet") or ""
        snippet = clean_snippet(str(body), max_chars=max_snippet_chars)
        if not title and not url:
            continue
        out.append(
            SearchResultItem(
                title=title or "(ddg result)",
                url=url,
                snippet=snippet,
                source="duckduckgo",
                score=None,
            )
        )
    return out


def normalize_open_library_results(
    docs: list[dict[str, Any]], *, max_results: int = 10
) -> list[SearchResultItem]:
    out: list[SearchResultItem] = []
    for doc in docs[:max_results]:
        if not isinstance(doc, dict):
            continue
        title = str(doc.get("title") or "").strip()
        if not title:
            continue

        authors_raw = doc.get("author_name")
        authors = ", ".join(authors_raw) if isinstance(authors_raw, list) else ""

        year = doc.get("first_publish_year", "")
        key = doc.get("key", "")
        url = f"https://openlibrary.org{key}" if key else None

        isbn_list = doc.get("isbn") or []
        isbn_str = ", ".join(isbn_list[:3]) if isbn_list else "N/A"
        publisher_list = doc.get("publisher") or []
        publisher_str = ", ".join(publisher_list[:2]) if publisher_list else "N/A"

        has_ebook = doc.get("ebook_access", "no_ebook") != "no_ebook"
        ia_list = doc.get("ia") or []
        ia_link = f"https://archive.org/details/{ia_list[0]}" if ia_list else None

        snippet_parts = []
        if authors:
            snippet_parts.append(f"By {authors}.")
        if year:
            snippet_parts.append(f"First published: {year}.")
        snippet_parts.append(f"Publisher: {publisher_str}.")
        snippet_parts.append(f"ISBN: {isbn_str}.")
        if has_ebook:
            snippet_parts.append("E-book available.")
        if ia_link:
            snippet_parts.append(f"IA: {ia_link}")

        out.append(
            SearchResultItem(
                title=title,
                url=ia_link or url,
                snippet=clean_snippet(" ".join(snippet_parts), max_chars=400),
                source="open_library",
                score=None,
            )
        )
    return out
