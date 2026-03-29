"""Multi-engine search: Tavily, DuckDuckGo, Serper with parallel fan-out."""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.settings import settings

from .schemas import CandidateResource

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
    seen_urls: set[str] = set()
    unique: list[CandidateResource] = []
    for c in candidates:
        norm = normalize_url(c.url)
        domain = urllib.parse.urlparse(norm).netloc
        if norm in seen_urls or domain in blacklist_domains or not c.title or not c.url:
            continue
        seen_urls.add(norm)
        unique.append(c)
    return unique


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
            CandidateResource(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=(item.get("content") or "")[:500],
                source_engine="tavily",
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
) -> list[CandidateResource]:
    try:
        from duckduckgo_search import DDGS

        filtered_query = f"{query} {site_suffix}".strip()
        with DDGS() as ddgs:
            raw = list(ddgs.text(filtered_query, max_results=max_results))
        return [
            CandidateResource(
                title=item.get("title", ""),
                url=item.get("href", item.get("url", "")),
                snippet=(item.get("body", item.get("snippet", "")))[:500],
                source_engine="duckduckgo",
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
) -> list[CandidateResource]:
    api_key = settings.serper_api_key
    if not api_key:
        return []
    try:
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
            CandidateResource(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=(item.get("snippet", ""))[:500],
                source_engine="serper",
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
            lambda: search_duckduckgo(query, max_per_engine, site_suffix=site_suffix),
        ),
        (
            "serper",
            lambda: search_serper(query, max_per_engine, site_suffix=site_suffix),
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
) -> list[CandidateResource]:
    """Run all queries for one skill, deduplicate results."""
    all_candidates: list[CandidateResource] = []
    for query in queries:
        hits = search_all_engines(
            query,
            blacklist_domains=blacklist_domains,
            exclude_sites=exclude_sites,
            tavily_include_domains=tavily_include_domains,
        )
        all_candidates.extend(hits)
        time.sleep(0.3)  # rate limit courtesy
    return deduplicate_candidates(all_candidates, blacklist_domains)
