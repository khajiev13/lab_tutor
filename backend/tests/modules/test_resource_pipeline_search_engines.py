from app.core.resource_pipeline.schemas import CandidateResource
from app.core.resource_pipeline.search_engines import (
    deduplicate_candidates,
    resolve_embedded_video_candidates,
)


def test_candidate_resource_extracts_youtube_ids_for_common_url_shapes():
    watch_candidate = CandidateResource(
        title="Watch",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        snippet="watch",
        source_engine="serper",
    )
    short_candidate = CandidateResource(
        title="Short",
        url="https://youtu.be/dQw4w9WgXcQ",
        snippet="short",
        source_engine="duckduckgo",
    )
    embed_candidate = CandidateResource(
        title="Embed",
        url="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
        snippet="embed",
        source_engine="tavily",
    )

    assert watch_candidate.video_id == "dQw4w9WgXcQ"
    assert short_candidate.video_id == "dQw4w9WgXcQ"
    assert embed_candidate.video_id == "dQw4w9WgXcQ"


def test_deduplicate_candidates_merges_metadata_across_engines():
    first = CandidateResource(
        title="Apache Spark Tutorial",
        url="https://example.com/spark?utm_source=test",
        snippet="Short snippet",
        search_content="Short snippet",
        source_engine="serper",
        search_metadata=[{"engine": "serper", "payload": {"rank": 1}}],
    )
    second = CandidateResource(
        title="Apache Spark Tutorial",
        url="https://www.example.com/spark",
        snippet="A much longer snippet with more detail",
        search_content="A much longer snippet with more detail from another engine",
        source_engine="duckduckgo",
        search_metadata=[{"engine": "duckduckgo", "payload": {"rank": 2}}],
    )

    deduped = deduplicate_candidates([first, second], blacklist_domains=set())

    assert len(deduped) == 1
    assert deduped[0].snippet == "A much longer snippet with more detail"
    assert deduped[0].search_content == (
        "A much longer snippet with more detail from another engine"
    )
    assert deduped[0].source_engines == ["serper", "duckduckgo"]
    assert len(deduped[0].search_metadata) == 2


def test_resolve_embedded_video_candidates_promotes_embedded_youtube_url(
    monkeypatch,
):
    candidate = CandidateResource(
        title="Spark optimization walkthrough",
        url="https://blog.example.com/spark-video",
        snippet="Blog post with an embedded video",
        search_content="Blog post with an embedded video",
        source_engine="serper",
        search_metadata=[{"engine": "serper", "payload": {"rank": 1}}],
    )

    monkeypatch.setattr(
        "app.core.resource_pipeline.search_engines._extract_page_snapshot",
        lambda _url: {
            "page_title": "Spark optimization walkthrough",
            "page_description": "This page embeds a YouTube walkthrough for Spark optimization.",
            "youtube_url": "https://www.youtube.com/embed/abc123xyz99",
        },
    )

    resolved = resolve_embedded_video_candidates([candidate], max_candidates=1)

    assert len(resolved) == 1
    assert resolved[0].url == "https://www.youtube.com/embed/abc123xyz99"
    assert resolved[0].video_id == "abc123xyz99"
    assert resolved[0].domain == "youtube.com"
    assert resolved[0].search_result_url == "https://blog.example.com/spark-video"
    assert len(resolved[0].search_metadata) == 2
