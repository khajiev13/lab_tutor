from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
from typing import Literal

from langchain.tools import tool

from .tool_helpers import (
    clean_query,
    error_response,
    http_get_json,
    json_response,
    normalize_ddg_results,
    normalize_google_books_items,
    normalize_open_library_results,
    normalize_tavily_results,
    require_env,
)
from .tool_models import SearchResponse, SearchResultItem, ToolName


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
    """Search Google Books (Volumes API) and return normalized results."""

    tool_name: Literal["googlebooksqueryrun"] = "googlebooksqueryrun"

    q = clean_query(query, max_chars=120)
    if not q:
        return error_response(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        api_key = require_env("GOOGLE_BOOKS_API_KEY")

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
            params["langRestrict"] = clean_query(lang_restrict, max_chars=16)

        url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
            params
        )
        payload = http_get_json(url)

        results = normalize_google_books_items(payload, max_results=max_results_clamped)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Google Books API for this query.")

        return json_response(
            SearchResponse(
                ok=True, tool=tool_name, query=q, results=results, warnings=warnings
            )
        )
    except Exception as e:  # noqa: BLE001
        return error_response(tool_name, query=q, msg=str(e))


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
    """Search the web with Tavily and return normalized results."""

    tool_name: Literal["tavily_search"] = "tavily_search"

    q = clean_query(query, max_chars=200)
    if not q:
        return error_response(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        require_env("TAVILY_API_KEY")

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
            params = {
                "api_key": os.getenv("TAVILY_API_KEY") or "",
                "query": q,
                "max_results": str(max(1, min(int(max_results), 20))),
                "search_depth": search_depth,
                "include_raw_content": "true" if include_raw_content else "false",
                "include_answer": "true" if include_answer else "false",
            }
            url = "https://api.tavily.com/search?" + urllib.parse.urlencode(params)
            raw = http_get_json(url)
            results_raw = raw.get("results") if isinstance(raw, dict) else None

        results = normalize_tavily_results(results_raw, max_snippet_chars=max_snippet_chars)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Tavily for this query.")

        return json_response(
            SearchResponse(
                ok=True, tool=tool_name, query=q, results=results, warnings=warnings
            )
        )
    except Exception as e:  # noqa: BLE001
        return error_response(tool_name, query=q, msg=str(e))


@tool
def duckduckgo_search(
    query: str,
    *,
    max_results: int = 10,
) -> str:
    """Search the web using DuckDuckGo. No API key required."""

    tool_name: ToolName = "duckduckgo_search"

    q = clean_query(query, max_chars=200)
    if not q:
        return error_response(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError as import_err:
            return error_response(
                tool_name,
                query=q,
                msg=f"duckduckgo-search package not installed. Install with: uv add duckduckgo-search ({import_err})",
            )

        max_results_clamped = max(1, min(int(max_results), 20))

        with DDGS() as ddgs:
            raw_results = list(ddgs.text(q, max_results=max_results_clamped))

        results = normalize_ddg_results(raw_results)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by DuckDuckGo for this query.")

        return json_response(
            SearchResponse(
                ok=True, tool=tool_name, query=q, results=results, warnings=warnings
            )
        )
    except Exception as e:  # noqa: BLE001
        return error_response(tool_name, query=q, msg=str(e))


@tool
def open_library_search(
    query: str,
    *,
    max_results: int = 5,
) -> str:
    """Search Open Library for books. No API key required."""

    tool_name: ToolName = "open_library_search"

    q = clean_query(query, max_chars=150)
    if not q:
        return error_response(tool_name, query="", msg="Query is empty after cleanup.")

    try:
        max_results_clamped = max(1, min(int(max_results), 10))
        params = {
            "q": q,
            "limit": str(max_results_clamped),
            "fields": "key,title,author_name,first_publish_year,isbn,publisher,"
            "ebook_access,ia,number_of_pages_median",
        }
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(params)
        payload = http_get_json(url, timeout_s=20.0)

        docs = payload.get("docs", [])
        results = normalize_open_library_results(docs, max_results=max_results_clamped)
        warnings: list[str] = []
        if not results:
            warnings.append("No results returned by Open Library for this query.")

        return json_response(
            SearchResponse(
                ok=True, tool=tool_name, query=q, results=results, warnings=warnings
            )
        )
    except Exception as e:  # noqa: BLE001
        return error_response(tool_name, query=q, msg=str(e))


_DOWNLOAD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "..",
    "data",
    "books",
)


def _sanitize_filename(name: str, *, max_len: int = 80) -> str:
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
    """Download a file (PDF, EPUB, etc.) from a URL and save it locally."""

    tool_name: ToolName = "download_file_from_url"

    url = (url or "").strip()
    if not url:
        return error_response(tool_name, query="", msg="URL is empty.")

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

            if "text/html" in content_type and "pdf" not in url.lower():
                return json_response(
                    SearchResponse(
                        ok=False,
                        tool=tool_name,
                        query=url,
                        error=f"URL returned HTML, not a file. Content-Type: {content_type}",
                    )
                )

            max_bytes = 200 * 1024 * 1024
            data = resp.read(max_bytes)

        if not data:
            return error_response(tool_name, query=url, msg="Empty response from URL.")

        ext = ".pdf"
        if "epub" in content_type or url.lower().endswith(".epub"):
            ext = ".epub"
        elif "djvu" in content_type or url.lower().endswith(".djvu"):
            ext = ".djvu"

        is_pdf = data[:5] == b"%PDF-"
        if ext == ".pdf" and not is_pdf:
            if data[:4] == b"PK\x03\x04":
                ext = ".epub"
            elif b"<html" in data[:500].lower() or b"<!doctype" in data[:500].lower():
                return json_response(
                    SearchResponse(
                        ok=False,
                        tool=tool_name,
                        query=url,
                        error="Downloaded content is an HTML page, not a PDF/book file.",
                    )
                )

        if not filename:
            path_part = urllib.parse.urlparse(url).path
            base = os.path.basename(path_part)
            filename = os.path.splitext(base)[0] if base and "." in base else "download"
        filename = _sanitize_filename(filename)
        full_path = os.path.join(_DOWNLOAD_DIR, f"{filename}{ext}")

        counter = 1
        while os.path.exists(full_path):
            full_path = os.path.join(_DOWNLOAD_DIR, f"{filename}_{counter}{ext}")
            counter += 1

        with open(full_path, "wb") as f:
            f.write(data)

        file_size = len(data)
        abs_path = os.path.abspath(full_path)

        return json_response(
            SearchResponse(
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
            )
        )
    except Exception as e:  # noqa: BLE001
        return error_response(tool_name, query=url, msg=str(e))


TOOLS = [tavily_search, googlebooksqueryrun]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

DOWNLOAD_SEARCH_TOOLS = [duckduckgo_search, tavily_search, open_library_search]
DOWNLOAD_SEARCH_TOOLS_BY_NAME = {t.name: t for t in DOWNLOAD_SEARCH_TOOLS}

DOWNLOAD_TOOLS = [
    duckduckgo_search,
    tavily_search,
    open_library_search,
    download_file_from_url,
]
DOWNLOAD_TOOLS_BY_NAME = {t.name: t for t in DOWNLOAD_TOOLS}
