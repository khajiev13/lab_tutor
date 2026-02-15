from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from langchain.tools import tool


class SearchResultItem(BaseModel):
    """A single normalized search result."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field("", description="Human-readable page/book title")
    url: str | None = Field(None, description="Canonical URL, if available")
    snippet: str | None = Field(None, description="Short cleaned snippet")
    source: str = Field("", description="Source system identifier")
    score: float | None = Field(None, description="Relevance score, if provided by the API")


class SearchResponse(BaseModel):
    """Standard tool response envelope.

    Tools should *always* return this object (serialized to JSON) so the LLM
    can reliably parse success vs failure.
    """

    model_config = ConfigDict(extra="ignore")

    ok: bool = Field(..., description="True when the request succeeded")
    tool: Literal[
        "tavily_search", "googlebooksqueryrun",
        "duckduckgo_search", "open_library_search", "download_file_from_url",
    ] = Field(
        ..., description="Tool identifier"
    )
    query: str = Field(..., description="Final cleaned query used")
    results: list[SearchResultItem] = Field(default_factory=list)
    error: str | None = Field(default=None, description="Error message when ok=False")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings")


_WHITESPACE_RE = re.compile(r"\s+")


def _clean_query(query: str, *, max_chars: int) -> str:
    """Normalize whitespace and clamp length.

    Rationale: LLMs sometimes produce long, multi-line prompts; most search APIs
    behave best with a single-line query. We also clamp query size to reduce the
    chance of exceeding URL limits or getting low-precision results.
    """

    q = _WHITESPACE_RE.sub(" ", (query or "").strip())
    if not q:
        return ""
    if len(q) > max_chars:
        q = q[:max_chars].rstrip()
    return q


def _clean_snippet(text: str | None, *, max_chars: int = 320) -> str | None:
    if not text:
        return None
    s = _WHITESPACE_RE.sub(" ", str(text).strip())
    if not s:
        return None
    if len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def _json_response(payload: BaseModel) -> str:
    """Return compact JSON for ToolMessage(content=...)."""

    return payload.model_dump_json(exclude_none=True)


_ToolName = Literal[
    "tavily_search", "googlebooksqueryrun",
    "duckduckgo_search", "open_library_search", "download_file_from_url",
]


def _error(tool_name: _ToolName, query: str, msg: str) -> str:
    return _json_response(SearchResponse(ok=False, tool=tool_name, query=query, error=msg))


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise ValueError(f"Missing env var {name}. Set it in your shell or a .env file.")
    return val


def _http_get_json(url: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
    """Small stdlib HTTP GET helper.

    We avoid `requests` (not a declared dependency) and keep this file portable.
    """

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


def _normalize_google_books_items(payload: dict[str, Any], *, query: str, max_results: int) -> list[SearchResultItem]:
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

        if subtitle and title:
            title_full = f"{title}: {subtitle}"
        else:
            title_full = title or subtitle

        authors: str | None = None
        if isinstance(authors_raw, list):
            authors_list = [str(a).strip() for a in authors_raw if a and str(a).strip()]
            if authors_list:
                authors = ", ".join(authors_list)

        description = _clean_snippet(volume_info.get("description"), max_chars=320)

        info_link = volume_info.get("infoLink")
        canonical_url = str(info_link).strip() if info_link else None

        if not title_full and canonical_url:
            title_full = canonical_url

        if not title_full:
            continue

        snippet = description
        if authors:
            snippet = (f"By {authors}. " + (description or "")).strip() or None
            snippet = _clean_snippet(snippet, max_chars=320)

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


def _normalize_tavily_results(results: Any, *, query: str, max_snippet_chars: int) -> list[SearchResultItem]:
    if not isinstance(results, list):
        return []

    out: list[SearchResultItem] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip() or None
        content = item.get("content")
        snippet = _clean_snippet(str(content) if content is not None else None, max_chars=max_snippet_chars)
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


@tool
def googlebooksqueryrun(
    query: str,
    *,
    max_results: int = 10,
    start_index: int = 0,
    print_type: Literal["all", "books", "magazines"] = "books",
    order_by: Literal["relevance", "newest"] = "relevance",
    lang_restrict: str | None = None,
) -> str:
    """Search Google Books (Volumes API) and return normalized results.

    Use this tool when you need *book candidates* (textbooks, editions, authors)
    rather than generic web pages.

    Query guidance (important):
    - Keep the query short and book-like: ideally 3–12 words (<= 120 characters).
    - Prefer exact book titles in quotes, optionally add an author: e.g.
      "Designing Data-Intensive Applications" Kleppmann
    - Avoid multi-sentence prompts, newlines, or long keyword dumps; they reduce precision.
    - If you must include course context, add 1 niche term only (e.g., "Big Data" Spark).

    Environment:
    - Requires `GOOGLE_BOOKS_API_KEY`.

    Args:
        query: Search string for the `q` parameter.
        max_results: Max results to return (1-20 recommended).
        start_index: Pagination start (0-based).
        print_type: Filter results.
        order_by: Sorting.
        lang_restrict: Optional BCP-47 / ISO language code (e.g., "en").

    Returns:
        JSON string of `SearchResponse` with `results` as normalized items.
    """

    tool_name: Literal["googlebooksqueryrun"] = "googlebooksqueryrun"

    q = _clean_query(query, max_chars=120)
    if not q:
        return _error(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        api_key = _require_env("GOOGLE_BOOKS_API_KEY")

        # Defensive bounds.
        max_results_clamped = max(1, min(int(max_results), 20))
        start_index_clamped = max(0, int(start_index))

        params: dict[str, str] = {
            "q": q,
            "key": api_key,
            "maxResults": str(max_results_clamped),
            "startIndex": str(start_index_clamped),
            "printType": print_type,
            "orderBy": order_by,
        }
        if lang_restrict:
            params["langRestrict"] = _clean_query(lang_restrict, max_chars=16)

        url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(params)
        payload = _http_get_json(url)

        results = _normalize_google_books_items(payload, query=q, max_results=max_results_clamped)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Google Books API for this query.")

        return _json_response(
            SearchResponse(ok=True, tool=tool_name, query=q, results=results, warnings=warnings)
        )
    except Exception as e:  # noqa: BLE001
        return _error(tool_name, query=q, msg=str(e))


@tool
def tavily_search(
    query: str,
    *,
    max_results: int = 10,
    search_depth: Literal["basic", "advanced"] = "basic",
    include_raw_content: bool = False,
    include_answer: bool = False,
    max_snippet_chars: int = 320,
) -> str:
    """Search the web with Tavily and return normalized results.

    Use this tool when you want *web pages* that may mention a course syllabus,
    reading list, or a specific textbook adoption.

    Query guidance (important):
    - Be specific and single-purpose (5–15 words is ideal).
    - Prefer intent phrases like: "<book title> textbook syllabus", "<course> reading list".
    - Avoid long multi-line prompts; keep it <= 200 characters.

    Environment:
    - Requires `TAVILY_API_KEY`.

    Args:
        query: Web search query.
        max_results: Number of results to return (1-20 recommended).
        search_depth: "basic" is cheaper/faster; "advanced" is deeper.
        include_raw_content: If True, Tavily may include longer content fields.
        include_answer: If True, Tavily may include a synthesized answer.
        max_snippet_chars: Max snippet length in returned results.

    Returns:
        JSON string of `SearchResponse` with normalized items.
    """

    tool_name: Literal["tavily_search"] = "tavily_search"

    q = _clean_query(query, max_chars=200)
    if not q:
        return _error(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        _require_env("TAVILY_API_KEY")

        # Prefer official client when available.
        try:
            from tavily import TavilyClient  # type: ignore

            client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
            raw = client.search(
                q,
                max_results=max(1, min(int(max_results), 20)),
                search_depth=search_depth,
                include_raw_content=include_raw_content,
                include_answer=include_answer,
            )
            results_raw = raw.get("results") if isinstance(raw, dict) else None
        except Exception:
            # Fallback to direct HTTP if the client import/call fails.
            # NOTE: Tavily also supports POST, but GET works for simple query usage.
            params = {
                "api_key": os.getenv("TAVILY_API_KEY") or "",
                "query": q,
                "max_results": str(max(1, min(int(max_results), 20))),
                "search_depth": search_depth,
                "include_raw_content": "true" if include_raw_content else "false",
                "include_answer": "true" if include_answer else "false",
            }
            url = "https://api.tavily.com/search?" + urllib.parse.urlencode(params)
            raw = _http_get_json(url)
            results_raw = raw.get("results") if isinstance(raw, dict) else None

        results = _normalize_tavily_results(results_raw, query=q, max_snippet_chars=max_snippet_chars)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Tavily for this query.")

        return _json_response(
            SearchResponse(ok=True, tool=tool_name, query=q, results=results, warnings=warnings)
        )
    except Exception as e:  # noqa: BLE001
        return _error(tool_name, query=q, msg=str(e))


# ═══════════════════════════════════════════════════════════════
# DuckDuckGo Search (no API key required)
# ═══════════════════════════════════════════════════════════════


def _normalize_ddg_results(results: list[dict[str, Any]], *, max_snippet_chars: int = 320) -> list[SearchResultItem]:
    out: list[SearchResultItem] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("href") or item.get("url") or "").strip() or None
        body = item.get("body") or item.get("snippet") or ""
        snippet = _clean_snippet(str(body), max_chars=max_snippet_chars)
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


@tool
def duckduckgo_search(
    query: str,
    *,
    max_results: int = 10,
) -> str:
    """Search the web using DuckDuckGo. No API key required.

    Excellent for finding PDF download links, open-access books, and
    resources that other search engines may not surface.

    Supports filetype queries like: "<title> filetype:pdf"

    Query guidance:
    - Keep queries short (3-15 words).
    - Use filetype:pdf to find PDF links.
    - Use site: to restrict to specific domains.

    Args:
        query: Search query string.
        max_results: Max results to return (1-20).

    Returns:
        JSON string of SearchResponse with normalized items.
    """
    tool_name: _ToolName = "duckduckgo_search"

    q = _clean_query(query, max_chars=200)
    if not q:
        return _error(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError as import_err:
            return _error(
                tool_name, 
                query=q, 
                msg=f"duckduckgo-search package not installed. Install with: uv add duckduckgo-search ({import_err})"
            )

        max_results_clamped = max(1, min(int(max_results), 20))

        with DDGS() as ddgs:
            raw_results = list(ddgs.text(q, max_results=max_results_clamped))

        results = _normalize_ddg_results(raw_results)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by DuckDuckGo for this query.")

        return _json_response(
            SearchResponse(ok=True, tool=tool_name, query=q, results=results, warnings=warnings)
        )
    except Exception as e:  # noqa: BLE001
        return _error(tool_name, query=q, msg=str(e))


# ═══════════════════════════════════════════════════════════════
# Open Library Search (no API key required)
# ═══════════════════════════════════════════════════════════════


def _normalize_open_library_results(
    docs: list[dict[str, Any]],
    *,
    max_results: int = 10,
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

        # Build snippet with metadata
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
                snippet=_clean_snippet(" ".join(snippet_parts), max_chars=400),
                source="open_library",
                score=None,
            )
        )
    return out


@tool
def open_library_search(
    query: str,
    *,
    max_results: int = 5,
) -> str:
    """Search Open Library for books. No API key required.

    Returns book metadata including ISBNs, publishers, and Internet Archive
    links where books may be available for borrowing or reading.

    Best for: finding specific editions, ISBNs, and open-access lending links.

    Args:
        query: Book title and/or author to search for.
        max_results: Max results to return (1-10).

    Returns:
        JSON string of SearchResponse with normalized items.
    """
    tool_name: _ToolName = "open_library_search"

    q = _clean_query(query, max_chars=150)
    if not q:
        return _error(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        max_results_clamped = max(1, min(int(max_results), 10))
        params = {
            "q": q,
            "limit": str(max_results_clamped),
            "fields": "key,title,author_name,first_publish_year,isbn,publisher,"
                       "ebook_access,ia,number_of_pages_median",
        }
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
        payload = _http_get_json(url, timeout_s=20.0)

        docs = payload.get("docs", [])
        results = _normalize_open_library_results(docs, max_results=max_results_clamped)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Open Library for this query.")

        return _json_response(
            SearchResponse(ok=True, tool=tool_name, query=q, results=results, warnings=warnings)
        )
    except Exception as e:  # noqa: BLE001
        return _error(tool_name, query=q, msg=str(e))


# ═══════════════════════════════════════════════════════════════
# download_file_from_url — deterministic PDF downloader
# ═══════════════════════════════════════════════════════════════

_DOWNLOAD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "data", "books",
)


def _sanitize_filename(name: str, *, max_len: int = 80) -> str:
    """Convert a book title into a safe filename."""
    safe = re.sub(r"[^\w\s-]", "", name.strip())
    safe = re.sub(r"\s+", "_", safe)
    if len(safe) > max_len:
        safe = safe[:max_len]
    return safe or "book"


@tool
def download_file_from_url(
    url: str,
    *,
    filename: str = "",
    timeout_s: float = 60.0,
) -> str:
    """Download a file (PDF, EPUB, etc.) from a URL and save it locally.

    Validates that the response is a real file (checks Content-Type and
    magic bytes for PDF). Saves to backend/data/books/.

    Args:
        url: Direct download URL for the file.
        filename: Optional filename (without extension). If empty, derived from URL.
        timeout_s: Download timeout in seconds.

    Returns:
        JSON string with download result (ok, file_path, file_size, content_type).
    """
    tool_name: _ToolName = "download_file_from_url"

    url = (url or "").strip()
    if not url:
        return _error(tool_name, query="", msg="URL is empty.")

    try:
        os.makedirs(_DOWNLOAD_DIR, exist_ok=True)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/pdf,application/epub+zip,*/*",
            },
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            content_length = resp.headers.get("Content-Length")

            # Reject obvious HTML pages
            if "text/html" in content_type and "pdf" not in url.lower():
                return _json_response(SearchResponse(
                    ok=False, tool=tool_name, query=url,
                    error=f"URL returned HTML, not a file. Content-Type: {content_type}",
                ))

            # Read content (limit to 200MB)
            max_bytes = 200 * 1024 * 1024
            data = resp.read(max_bytes)

        if not data:
            return _error(tool_name, query=url, msg="Empty response from URL.")

        # Determine extension from content type or URL
        ext = ".pdf"
        if "epub" in content_type or url.lower().endswith(".epub"):
            ext = ".epub"
        elif "djvu" in content_type or url.lower().endswith(".djvu"):
            ext = ".djvu"

        # Validate PDF magic bytes if we expect PDF
        is_pdf = data[:5] == b"%PDF-"
        if ext == ".pdf" and not is_pdf:
            # Maybe it's still a valid file but not PDF
            if data[:4] == b"PK\x03\x04":  # ZIP/EPUB
                ext = ".epub"
            elif b"<html" in data[:500].lower() or b"<!doctype" in data[:500].lower():
                return _json_response(SearchResponse(
                    ok=False, tool=tool_name, query=url,
                    error="Downloaded content is an HTML page, not a PDF/book file.",
                ))

        # Build filename
        if not filename:
            # Try to extract from URL path
            path_part = urllib.parse.urlparse(url).path
            base = os.path.basename(path_part)
            if base and "." in base:
                filename = os.path.splitext(base)[0]
            else:
                filename = "download"
        filename = _sanitize_filename(filename)
        full_path = os.path.join(_DOWNLOAD_DIR, f"{filename}{ext}")

        # Avoid overwriting
        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(_DOWNLOAD_DIR, f"{filename}_{counter}{ext}")
            counter += 1

        with open(full_path, "wb") as f:
            f.write(data)

        file_size = len(data)
        abs_path = os.path.abspath(full_path)

        return _json_response(SearchResponse(
            ok=True,
            tool=tool_name,
            query=url,
            results=[
                SearchResultItem(
                    title=f"Downloaded: {os.path.basename(abs_path)}",
                    url=abs_path,
                    snippet=(
                        f"Saved to: {abs_path} | "
                        f"Size: {file_size / 1024:.1f} KB | "
                        f"Content-Type: {content_type} | "
                        f"Is PDF: {is_pdf}"
                    ),
                    source="local_download",
                )
            ],
        ))
    except Exception as e:  # noqa: BLE001
        return _error(tool_name, query=url, msg=str(e))


# ═══════════════════════════════════════════════════════════════
# Tool exports
# ═══════════════════════════════════════════════════════════════

# Original scoring/discovery tools
TOOLS = [tavily_search, googlebooksqueryrun]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

# Download-phase tools (search for PDF links)
DOWNLOAD_SEARCH_TOOLS = [duckduckgo_search, tavily_search, open_library_search]
DOWNLOAD_SEARCH_TOOLS_BY_NAME = {t.name: t for t in DOWNLOAD_SEARCH_TOOLS}

# All download tools (search + download)
DOWNLOAD_TOOLS = [duckduckgo_search, tavily_search, open_library_search, download_file_from_url]
DOWNLOAD_TOOLS_BY_NAME = {t.name: t for t in DOWNLOAD_TOOLS}
