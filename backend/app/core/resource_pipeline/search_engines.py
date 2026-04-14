"""Multi-engine search: Tavily, DuckDuckGo, Serper with parallel fan-out."""

from __future__ import annotations

import html
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Any

from app.core.settings import settings

from .schemas import CandidateResource, extract_youtube_video_id

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  URL normalization + dedup
# ═══════════════════════════════════════════════════════════════

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "ref",
    "source",
}

_MAX_SNIPPET_CHARS = 500
_MAX_SEARCH_CONTENT_CHARS = 4000
_MAX_METADATA_STRING_CHARS = 4000
_MAX_METADATA_ITEMS = 25
_MAX_PAGE_BYTES = 250_000
_VIDEO_EMBED_RESOLVE_LIMIT = 12
_YOUTUBE_URL_RE = re.compile(
    r"""https?://(?:www\.)?(?:youtube(?:-nocookie)?\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)[^"'&<>\s]+""",
    re.IGNORECASE,
)


def _truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text[:max_chars]


def _sanitize_metadata(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value, _MAX_METADATA_STRING_CHARS)
    if isinstance(value, dict):
        items = list(value.items())[:_MAX_METADATA_ITEMS]
        return {str(k): _sanitize_metadata(v) for k, v in items}
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata(v) for v in value[:_MAX_METADATA_ITEMS]]
    return _truncate(str(value), _MAX_METADATA_STRING_CHARS)


def _build_metadata_entry(engine: str, raw_item: dict[str, Any]) -> dict[str, Any]:
    return {"engine": engine, "payload": _sanitize_metadata(raw_item)}


def _build_candidate(
    *,
    title: str,
    url: str,
    snippet: str,
    source_engine: str,
    raw_item: dict[str, Any],
    search_content: str = "",
    search_result_url: str = "",
) -> CandidateResource:
    return CandidateResource(
        title=title,
        url=url,
        snippet=_truncate(snippet, _MAX_SNIPPET_CHARS),
        search_content=_truncate(search_content or snippet, _MAX_SEARCH_CONTENT_CHARS),
        source_engine=source_engine,
        search_metadata=[_build_metadata_entry(source_engine, raw_item)],
        search_result_url=search_result_url or url,
    )


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.replace("www.", "")
    params = urllib.parse.parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items() if k not in _TRACKING_PARAMS}
    clean_query = (
        urllib.parse.urlencode(clean_params, doseq=True) if clean_params else ""
    )
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunparse(("https", netloc, path, "", clean_query, ""))


def deduplicate_candidates(
    candidates: list[CandidateResource],
    blacklist_domains: set[str],
) -> list[CandidateResource]:
    unique_by_url: dict[str, CandidateResource] = {}
    ordered: list[CandidateResource] = []
    for c in candidates:
        norm = normalize_url(c.url)
        domain = urllib.parse.urlparse(norm).netloc
        if domain in blacklist_domains or not c.title or not c.url:
            continue
        existing = unique_by_url.get(norm)
        if existing is not None:
            existing.merge(c)
            continue
        unique_by_url[norm] = c
        ordered.append(c)
    return ordered


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_title = False
        self.title = ""
        self.meta: dict[str, str] = {}
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()
        if tag == "title":
            self._inside_title = True
            return
        if tag == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            content = attr_map.get("content", "")
            if key and content:
                self.meta[key] = content
            return
        if tag in {"iframe", "embed", "a"}:
            url = attr_map.get("src") or attr_map.get("href") or ""
            if url:
                self.urls.append(url)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title and data.strip():
            self.title += data.strip()


def _canonical_youtube_url(url: str) -> str:
    video_id = extract_youtube_video_id(url)
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _fetch_page_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        content_type = resp.headers.get("Content-Type", "")
        if content_type and "text/html" not in content_type.lower():
            return ""
        raw = resp.read(_MAX_PAGE_BYTES)
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="ignore")


def _extract_page_snapshot(url: str) -> dict[str, str]:
    try:
        page_html = _fetch_page_html(url)
    except Exception:
        logger.debug("Failed to fetch page snapshot for %s", url, exc_info=True)
        return {}

    if not page_html:
        return {}

    parser = _PageMetadataParser()
    try:
        parser.feed(page_html)
    except Exception:
        logger.debug("Failed to parse page snapshot for %s", url, exc_info=True)

    normalized_html = html.unescape(page_html).replace("\\/", "/")
    urls = parser.urls + _YOUTUBE_URL_RE.findall(normalized_html)

    canonical_youtube_url = ""
    for raw_url in urls:
        canonical_youtube_url = _canonical_youtube_url(raw_url)
        if canonical_youtube_url:
            break

    title = _truncate(
        parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title,
        300,
    )
    description = _truncate(
        parser.meta.get("description")
        or parser.meta.get("og:description")
        or parser.meta.get("twitter:description"),
        _MAX_SEARCH_CONTENT_CHARS,
    )
    return {
        "page_title": title,
        "page_description": description,
        "youtube_url": canonical_youtube_url,
    }


def _enrich_video_candidate(candidate: CandidateResource) -> CandidateResource:
    if candidate.video_id:
        return candidate

    search_result_url = candidate.search_result_url or candidate.url
    search_result_domain = urllib.parse.urlparse(search_result_url).netloc.replace(
        "www.", ""
    )
    if search_result_domain in {"youtube.com", "youtu.be", "m.youtube.com"}:
        return candidate

    snapshot = _extract_page_snapshot(search_result_url)
    if not snapshot:
        return candidate

    page_title = snapshot.get("page_title", "")
    page_description = snapshot.get("page_description", "")
    canonical_youtube_url = snapshot.get("youtube_url", "")

    if page_description:
        merged_parts = [part for part in [candidate.search_content] if part]
        if page_description not in candidate.search_content:
            merged_parts.append(page_description)
        merged_content = "\n".join(merged_parts)
        candidate.search_content = _truncate(merged_content, _MAX_SEARCH_CONTENT_CHARS)
        if not candidate.snippet:
            candidate.snippet = _truncate(page_description, _MAX_SNIPPET_CHARS)
    if page_title and not candidate.title:
        candidate.title = page_title

    resolver_payload = {
        "page_title": page_title,
        "page_description": page_description,
        "search_result_url": search_result_url,
    }

    if canonical_youtube_url:
        candidate.search_result_url = search_result_url
        candidate.search_result_domain = search_result_domain
        candidate.url = canonical_youtube_url
        candidate.domain = urllib.parse.urlparse(candidate.url).netloc.replace(
            "www.", ""
        )
        candidate.video_id = extract_youtube_video_id(candidate.url)
        resolver_payload["youtube_url"] = canonical_youtube_url

    candidate.search_metadata.append(
        {"engine": "page_resolver", "payload": _sanitize_metadata(resolver_payload)}
    )
    return candidate


def resolve_embedded_video_candidates(
    candidates: list[CandidateResource],
    *,
    max_candidates: int = _VIDEO_EMBED_RESOLVE_LIMIT,
) -> list[CandidateResource]:
    """Resolve wrapper pages to canonical YouTube URLs when a page embeds a video."""
    if not candidates:
        return []

    resolved = list(candidates)
    target_indexes = [
        idx for idx, candidate in enumerate(resolved) if not candidate.video_id
    ][:max_candidates]
    if not target_indexes:
        return resolved

    with ThreadPoolExecutor(max_workers=min(4, len(target_indexes))) as executor:
        future_map = {
            executor.submit(_enrich_video_candidate, resolved[idx]): idx
            for idx in target_indexes
        }
        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                resolved[idx] = future.result()
            except Exception:
                logger.debug(
                    "Embedded video resolution failed for %s",
                    resolved[idx].url,
                    exc_info=True,
                )
    return resolved


# ═══════════════════════════════════════════════════════════════
#  Search engine wrappers
# ═══════════════════════════════════════════════════════════════


def search_tavily(
    query: str,
    max_results: int = 7,
    *,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> list[CandidateResource]:
    api_key = settings.tavily_api_key
    if not api_key:
        return []
    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        kwargs: dict = {"max_results": max_results, "search_depth": "basic"}
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        raw = client.search(query, **kwargs)
        return [
            _build_candidate(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content") or "",
                search_content=item.get("content") or "",
                source_engine="tavily",
                raw_item=item,
            )
            for item in (raw.get("results") or [])
        ]
    except Exception:
        logger.warning("Tavily search failed for query: %s", query[:80], exc_info=True)
        return []


def search_duckduckgo(
    query: str,
    max_results: int = 7,
    *,
    site_suffix: str = "",
    video_only: bool = False,
) -> list[CandidateResource]:
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            if video_only:
                raw = list(
                    ddgs.videos(
                        query, license_videos="youtube", max_results=max_results
                    )
                )
                return [
                    _build_candidate(
                        title=item.get("title", ""),
                        url=item.get("content", ""),
                        snippet=item.get("description", ""),
                        search_content=item.get("description", ""),
                        source_engine="duckduckgo",
                        raw_item=item,
                    )
                    for item in raw
                ]
            filtered_query = f"{query} {site_suffix}".strip()
            raw = list(ddgs.text(filtered_query, max_results=max_results))
            return [
                _build_candidate(
                    title=item.get("title", ""),
                    url=item.get("href", item.get("url", "")),
                    snippet=item.get("body", item.get("snippet", "")),
                    search_content=item.get("body", item.get("snippet", "")),
                    source_engine="duckduckgo",
                    raw_item=item,
                )
                for item in raw
            ]
    except Exception:
        logger.warning(
            "DuckDuckGo search failed for query: %s", query[:80], exc_info=True
        )
        return []


def search_serper(
    query: str,
    max_results: int = 7,
    *,
    site_suffix: str = "",
    video_only: bool = False,
) -> list[CandidateResource]:
    api_key = settings.serper_api_key
    if not api_key:
        return []
    try:
        if video_only:
            filtered_query = f"site:youtube.com {query}".strip()
        else:
            filtered_query = f"{query} {site_suffix}".strip()
        url = "https://google.serper.dev/search"
        payload = json.dumps({"q": filtered_query, "num": max_results}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return [
            _build_candidate(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
                search_content=item.get("snippet", ""),
                source_engine="serper",
                raw_item=item,
            )
            for item in data.get("organic", [])[:max_results]
        ]
    except Exception:
        logger.warning("Serper search failed for query: %s", query[:80], exc_info=True)
        return []


# ═══════════════════════════════════════════════════════════════
#  Fan-out across all engines
# ═══════════════════════════════════════════════════════════════


def _build_site_exclusion_suffix(exclude_sites: list[str]) -> str:
    return " ".join(f"-site:{d}" for d in exclude_sites)


def search_all_engines(
    query: str,
    *,
    blacklist_domains: set[str],
    exclude_sites: list[str],
    tavily_include_domains: list[str] | None = None,
    max_per_engine: int = 7,
    video_only: bool = False,
) -> list[CandidateResource]:
    """Run a single query across all 3 search engines in parallel."""
    site_suffix = _build_site_exclusion_suffix(exclude_sites)

    engines = [
        (
            "tavily",
            lambda: search_tavily(
                query,
                max_per_engine,
                include_domains=tavily_include_domains,
                exclude_domains=list(blacklist_domains)
                if not tavily_include_domains
                else None,
            ),
        ),
        (
            "duckduckgo",
            lambda: search_duckduckgo(
                query, max_per_engine, site_suffix=site_suffix, video_only=video_only
            ),
        ),
        (
            "serper",
            lambda: search_serper(
                query, max_per_engine, site_suffix=site_suffix, video_only=video_only
            ),
        ),
    ]

    results: list[CandidateResource] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fn): name for name, fn in engines}
        for future in as_completed(futures):
            try:
                results.extend(future.result())
            except Exception:
                logger.warning(
                    "Search engine %s failed", futures[future], exc_info=True
                )
    return results


def search_for_skill(
    queries: list[str],
    *,
    blacklist_domains: set[str],
    exclude_sites: list[str],
    tavily_include_domains: list[str] | None = None,
    resolve_video_pages: bool = False,
    video_only: bool = False,
) -> list[CandidateResource]:
    """Run all queries for one skill, deduplicate results."""
    all_candidates: list[CandidateResource] = []
    for query in queries:
        hits = search_all_engines(
            query,
            blacklist_domains=blacklist_domains,
            exclude_sites=exclude_sites,
            tavily_include_domains=tavily_include_domains,
            video_only=video_only,
        )
        all_candidates.extend(hits)
        time.sleep(0.3)  # rate limit courtesy
    unique = deduplicate_candidates(all_candidates, blacklist_domains)
    if resolve_video_pages:
        unique = deduplicate_candidates(
            resolve_embedded_video_candidates(unique),
            blacklist_domains,
        )
    return unique
