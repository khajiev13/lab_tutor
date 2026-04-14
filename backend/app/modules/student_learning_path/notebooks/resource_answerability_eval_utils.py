"""Notebook helpers for yes/no resource answerability evaluation with an LLM judge.

This module is intentionally notebook-friendly: it exposes small, composable
functions for loading selected skills from Neo4j, fetching evidence for reading
and video resources, running an LLM judge, and saving experiment artifacts.
"""

from __future__ import annotations

import csv
import html
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from bs4 import BeautifulSoup
from neo4j import Driver, GraphDatabase
from openai import OpenAI
from pydantic import BaseModel, Field

from app.core.settings import Settings

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
READING_MAX_CHARS = 4000
VIDEO_MAX_CHARS = 5000
RESOURCE_EVIDENCE_MAX_CHARS = 1800
JUDGE_MODEL_FALLBACK = "gpt-4.1-mini"
YOUTUBE_PLAYER_RESPONSE_RE = re.compile(
    r"ytInitialPlayerResponse\s*=\s*(\{.+?\})\s*;",
    re.DOTALL,
)
YOUTUBE_CAPTION_TRACKS_RE = re.compile(
    r'"captionTracks":(\[.+?\])',
    re.DOTALL,
)
ProgressCallback = Callable[[dict[str, Any]], None]


class JudgeVerdict(BaseModel):
    answerable: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_strength: Literal["strong", "partial", "weak", "none"]
    supporting_quotes: list[str] = Field(default_factory=list)
    missing_information: str = ""
    reasoning: str


def find_repo_root(start: str | Path | None = None) -> Path:
    current = Path(start or __file__).resolve()
    for path in [current, *current.parents]:
        if (path / "backend").exists() and (path / "frontend").exists():
            return path
    raise FileNotFoundError("Could not locate repo root from notebook helpers")


def load_settings(repo_root: str | Path | None = None) -> Settings:
    root = find_repo_root(repo_root)
    return Settings(_env_file=root / "backend" / ".env")


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _emit_progress(
    progress_callback: ProgressCallback | None,
    **event: Any,
) -> None:
    if progress_callback is None:
        return
    progress_callback(event)


def create_neo4j_driver(
    *,
    repo_root: str | Path | None = None,
    neo4j_uri: str | None = None,
    neo4j_username: str | None = None,
    neo4j_password: str | None = None,
) -> Driver:
    settings = load_settings(repo_root)
    uri = _coalesce(neo4j_uri, settings.neo4j_uri)
    username = _coalesce(neo4j_username, settings.neo4j_username)
    password = _coalesce(neo4j_password, settings.neo4j_password)
    if not uri:
        raise ValueError(
            "Neo4j URI is not configured. Set it in backend/.env or pass neo4j_uri explicitly."
        )
    auth = (username, password) if username else None
    return GraphDatabase.driver(uri, auth=auth)


def get_neo4j_database(
    *,
    repo_root: str | Path | None = None,
    neo4j_database: str | None = None,
) -> str:
    settings = load_settings(repo_root)
    return neo4j_database or settings.neo4j_database


def create_llm_client(
    *,
    repo_root: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[OpenAI, str]:
    settings = load_settings(repo_root)
    resolved_api_key = _coalesce(api_key, settings.llm_api_key)
    resolved_base_url = _coalesce(base_url, settings.llm_base_url)
    if not resolved_api_key:
        raise ValueError(
            "LLM API key is not configured. Set it in backend/.env or pass api_key explicitly."
        )
    client = OpenAI(api_key=resolved_api_key, base_url=resolved_base_url, timeout=120)
    model = settings.llm_model or JUDGE_MODEL_FALLBACK
    return client, model


def list_courses(
    driver: Driver,
    *,
    database: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = """
    MATCH (c:CLASS)
    RETURN c.id AS course_id,
           coalesce(c.title, '') AS title,
           coalesce(c.description, '') AS description,
           c.extraction_status AS extraction_status,
           size([(c)<-[:ENROLLED_IN_CLASS]-(:USER:STUDENT) | 1]) AS enrolled_students
    ORDER BY course_id DESC
    LIMIT $limit
    """
    with driver.session(database=database) as session:
        return [record.data() for record in session.run(query, {"limit": int(limit)})]


def list_students_with_selected_skills(
    driver: Driver,
    *,
    database: str,
    course_id: int | None = None,
    limit: int = 20,
    only_course_path_skills: bool = True,
) -> list[dict[str, Any]]:
    course_filter = ""
    params: dict[str, Any] = {"limit": int(limit)}
    if course_id is not None:
        if only_course_path_skills:
            course_filter = """
            MATCH (u)-[:ENROLLED_IN_CLASS]->(:CLASS {id: $course_id})
            WHERE EXISTS {
                MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                      <-[:MAPPED_TO]-(sk)
            }
            """
        else:
            course_filter = """
            MATCH (u)-[:ENROLLED_IN_CLASS]->(:CLASS {id: $course_id})
            WHERE EXISTS {
                MATCH (:CLASS {id: $course_id})-[:CANDIDATE_BOOK]->(:BOOK)
                      -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
            } OR EXISTS {
                MATCH (:CLASS {id: $course_id})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                      <-[:MAPPED_TO]-(sk)
            }
            """
        params["course_id"] = int(course_id)

    query = f"""
    MATCH (u:USER:STUDENT)-[:SELECTED_SKILL]->(sk:SKILL)
    {course_filter}
    RETURN u.id AS student_id,
           coalesce(u.email, '') AS email,
           count(DISTINCT sk) AS skill_count
    ORDER BY skill_count DESC, email ASC
    LIMIT $limit
    """
    with driver.session(database=database) as session:
        return [record.data() for record in session.run(query, params)]


def load_selected_skill_bundle(
    driver: Driver,
    *,
    database: str,
    course_id: int,
    student_id: int | None = None,
    student_email: str | None = None,
    limit_skills: int | None = None,
    only_course_path_skills: bool = True,
) -> dict[str, Any]:
    if not student_id and not student_email:
        raise ValueError("Provide either student_id or student_email")

    if student_id is not None:
        student_match = "MATCH (u:USER:STUDENT {id: $student_id})"
        student_params: dict[str, Any] = {"student_id": int(student_id)}
    else:
        student_match = "MATCH (u:USER:STUDENT {email: $student_email})"
        student_params = {"student_email": str(student_email)}

    skill_projection = """
    sk {
        .name,
        .description,
        source: sel.source,
        skill_type: CASE WHEN sk:BOOK_SKILL THEN 'book' ELSE 'market' END,
        course_level: coalesce(sk.course_level, 'bachelor'),
        chapter_index: chapter_index,
        chapter_title: chapter_title,
        concepts: [(sk)-[:REQUIRES_CONCEPT]->(c:CONCEPT) | c {
            .name,
            .description
        }],
        questions: COLLECT {
            MATCH (sk)-[:HAS_QUESTION]->(q:QUESTION)
            RETURN q {
                .id,
                .text,
                .difficulty,
                .answer,
                correct_option: q.correct_option,
                options: coalesce(q.options, [])
            } AS question
            ORDER BY CASE q.difficulty
                WHEN 'easy' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'hard' THEN 2
                ELSE 9
            END
        },
        readings: [(sk)-[:HAS_READING]->(rr:READING_RESOURCE) | rr {
            .title, .url,
            domain: coalesce(rr.domain, ''),
            snippet: coalesce(rr.snippet, ''),
            search_content: coalesce(rr.search_content, ''),
            search_result_url: coalesce(rr.search_result_url, ''),
            search_result_domain: coalesce(rr.search_result_domain, ''),
            source_engine: coalesce(rr.source_engine, ''),
            source_engines: coalesce(rr.source_engines, []),
            search_metadata_json: coalesce(rr.search_metadata_json, '[]'),
            resource_type: coalesce(rr.resource_type, ''),
            final_score: coalesce(rr.final_score, 0.0),
            concepts_covered: coalesce(rr.concepts_covered, [])
        }],
        videos: [(sk)-[:HAS_VIDEO]->(vr:VIDEO_RESOURCE) | vr {
            .title, .url,
            domain: coalesce(vr.domain, ''),
            snippet: coalesce(vr.snippet, ''),
            search_content: coalesce(vr.search_content, ''),
            video_id: coalesce(vr.video_id, ''),
            search_result_url: coalesce(vr.search_result_url, ''),
            search_result_domain: coalesce(vr.search_result_domain, ''),
            source_engine: coalesce(vr.source_engine, ''),
            source_engines: coalesce(vr.source_engines, []),
            search_metadata_json: coalesce(vr.search_metadata_json, '[]'),
            resource_type: coalesce(vr.resource_type, ''),
            final_score: coalesce(vr.final_score, 0.0),
            concepts_covered: coalesce(vr.concepts_covered, [])
        }]
    }
    """

    if only_course_path_skills:
        query = f"""
        {student_match}
        MATCH (u)-[:ENROLLED_IN_CLASS]->(:CLASS {{id: $course_id}})
        MATCH (u)-[sel:SELECTED_SKILL]->(sk:SKILL)
        MATCH (:CLASS {{id: $course_id}})-[:HAS_COURSE_CHAPTER]->(ch:COURSE_CHAPTER)
              <-[:MAPPED_TO]-(sk)
        WITH u, sel, sk,
             min(ch.chapter_index) AS raw_chapter_index,
             head([title IN collect(ch.title) WHERE title IS NOT NULL | title]) AS raw_chapter_title
        WITH u, sel, sk,
             coalesce(raw_chapter_index, 9999) AS chapter_index,
             coalesce(raw_chapter_title, '') AS chapter_title
        RETURN u {{ .id, .email }} AS student,
               {skill_projection} AS skill
        ORDER BY skill.chapter_index, skill.skill_type, skill.name
        """
    else:
        query = f"""
        {student_match}
        MATCH (u)-[:ENROLLED_IN_CLASS]->(:CLASS {{id: $course_id}})
        MATCH (u)-[sel:SELECTED_SKILL]->(sk:SKILL)
        WHERE EXISTS {{
            MATCH (:CLASS {{id: $course_id}})-[:CANDIDATE_BOOK]->(:BOOK)
                  -[:HAS_CHAPTER]->(:BOOK_CHAPTER)-[:HAS_SKILL]->(sk)
        }} OR EXISTS {{
            MATCH (:CLASS {{id: $course_id}})-[:HAS_COURSE_CHAPTER]->(:COURSE_CHAPTER)
                  <-[:MAPPED_TO]-(sk)
        }}
        WITH u, sel, sk, 9999 AS chapter_index, '' AS chapter_title
        RETURN u {{ .id, .email }} AS student,
               {skill_projection} AS skill
        ORDER BY skill.skill_type, skill.name
        """
    params = {"course_id": int(course_id), **student_params}
    with driver.session(database=database) as session:
        rows = [record.data() for record in session.run(query, params)]

    if not rows:
        raise ValueError("No selected skills found for the given student/course")

    student = rows[0]["student"]
    skills = [row["skill"] for row in rows]
    if limit_skills is not None:
        skills = skills[: int(limit_skills)]

    return {
        "course_id": int(course_id),
        "student": student,
        "skill_count": len(skills),
        "skills": skills,
    }


def backfill_missing_questions(
    driver: Driver,
    *,
    database: str,
    bundle: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    from app.modules.question_generation.neo4j_repository import write_questions
    from app.modules.question_generation.service import generate_questions_for_skill

    updated_bundle = json.loads(json.dumps(bundle))
    missing_skills = [
        skill for skill in updated_bundle["skills"] if not skill.get("questions", [])
    ]
    total = len(missing_skills)
    completed = 0
    generated_skills: list[str] = []
    failed_skills: list[dict[str, str]] = []

    _emit_progress(
        progress_callback,
        phase="backfill_questions",
        stage="start",
        completed=completed,
        total=total,
        message=f"Preparing to backfill questions for {total} skills",
    )

    if not missing_skills:
        _emit_progress(
            progress_callback,
            phase="backfill_questions",
            stage="complete",
            completed=completed,
            total=total,
            message="No missing questions detected",
        )
        return {
            "bundle": updated_bundle,
            "generated_skills": generated_skills,
            "failed_skills": failed_skills,
        }

    with driver.session(database=database) as session:
        for skill in missing_skills:
            skill_name = skill.get("name", "")
            _emit_progress(
                progress_callback,
                phase="backfill_questions",
                stage="item_start",
                completed=completed,
                total=total,
                skill_name=skill_name,
                message=f"Generating questions for skill '{skill_name}'",
            )
            try:
                questions = generate_questions_for_skill(
                    skill_name,
                    skill.get("description", ""),
                    skill.get("concepts", []),
                    skill.get("course_level", "bachelor"),
                )
                write_questions(session, skill_name, questions)
                skill["questions"] = [question.model_dump() for question in questions]
                generated_skills.append(skill_name)
                completed += 1
                _emit_progress(
                    progress_callback,
                    phase="backfill_questions",
                    stage="item_complete",
                    completed=completed,
                    total=total,
                    skill_name=skill_name,
                    message=f"Generated {len(questions)} questions for skill '{skill_name}'",
                )
            except Exception as exc:
                completed += 1
                error_detail = " ".join(str(exc).split()) or exc.__class__.__name__
                failed_skills.append(
                    {
                        "skill_name": skill_name,
                        "error": error_detail,
                    }
                )
                _emit_progress(
                    progress_callback,
                    phase="backfill_questions",
                    stage="item_error",
                    completed=completed,
                    total=total,
                    skill_name=skill_name,
                    message=f"Question backfill failed for skill '{skill_name}': {error_detail}",
                )

    _emit_progress(
        progress_callback,
        phase="backfill_questions",
        stage="complete",
        completed=completed,
        total=total,
        message=(
            f"Question backfill finished: {len(generated_skills)} generated, "
            f"{len(failed_skills)} failed"
        ),
    )
    return {
        "bundle": updated_bundle,
        "generated_skills": generated_skills,
        "failed_skills": failed_skills,
    }


def summarize_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for skill in bundle["skills"]:
        summary.append(
            {
                "skill_name": skill["name"],
                "skill_type": skill.get("skill_type", ""),
                "selection_source": skill.get("source", ""),
                "chapter_index": skill.get("chapter_index"),
                "chapter_title": skill.get("chapter_title", ""),
                "question_count": len(skill.get("questions", [])),
                "reading_count": len(skill.get("readings", [])),
                "video_count": len(skill.get("videos", [])),
            }
        )
    return summary


def _clean_text(text: str, *, max_chars: int) -> str:
    compact = " ".join(text.split())
    return compact[:max_chars]


def fetch_reading_evidence(
    resource: dict[str, Any],
    *,
    timeout_seconds: int = 20,
    max_chars: int = READING_MAX_CHARS,
) -> dict[str, Any]:
    url = resource.get("url") or resource.get("search_result_url") or ""
    if not url:
        return {
            "fetch_status": "missing_url",
            "content_text": "",
            "content_source": "none",
        }

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type:
                fallback = _clean_text(
                    "\n".join(
                        [
                            resource.get("search_content", ""),
                            resource.get("snippet", ""),
                        ]
                    ),
                    max_chars=max_chars,
                )
                return {
                    "fetch_status": "non_html_fallback",
                    "content_text": fallback,
                    "content_source": "search_metadata",
                }
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            paragraphs = [
                p.get_text(" ", strip=True)
                for p in soup.find_all(["p", "li"], limit=80)
            ]
            body_text = "\n".join(text for text in paragraphs if text)
            combined = _clean_text(
                "\n".join(
                    part
                    for part in [title, resource.get("search_content", ""), body_text]
                    if part
                ),
                max_chars=max_chars,
            )
            return {
                "fetch_status": "ok",
                "content_text": combined,
                "content_source": "html",
            }
    except Exception:
        fallback = _clean_text(
            "\n".join(
                [
                    resource.get("search_content", ""),
                    resource.get("snippet", ""),
                ]
            ),
            max_chars=max_chars,
        )
        return {
            "fetch_status": "fallback",
            "content_text": fallback,
            "content_source": "search_metadata",
        }


def _fetch_youtube_watch_page(video_id: str, timeout_seconds: int) -> str:
    url = f"https://www.youtube.com/watch?v={video_id}&hl=en"
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers=headers,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _extract_caption_track_url(page_html: str) -> str:
    match = YOUTUBE_PLAYER_RESPONSE_RE.search(page_html)
    player_response: dict[str, Any] | None = None
    if match:
        try:
            player_response = json.loads(match.group(1))
        except json.JSONDecodeError:
            player_response = None
    if player_response is None:
        tracks_match = YOUTUBE_CAPTION_TRACKS_RE.search(page_html)
        if tracks_match:
            try:
                track_list = json.loads(tracks_match.group(1))
                if track_list:
                    return track_list[0].get("baseUrl", "")
            except json.JSONDecodeError:
                return ""
        return ""

    captions = (
        player_response.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )
    if not captions:
        return ""

    english_tracks = [
        track
        for track in captions
        if str(track.get("languageCode", "")).startswith("en")
    ]
    chosen = english_tracks[0] if english_tracks else captions[0]
    return str(chosen.get("baseUrl", ""))


def _fetch_youtube_transcript_text(
    caption_url: str,
    *,
    timeout_seconds: int,
    max_chars: int,
) -> str:
    if not caption_url:
        return ""
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers=headers,
    ) as client:
        response = client.get(caption_url)
        response.raise_for_status()
    root = ET.fromstring(response.text)
    lines = []
    for node in root.findall(".//text"):
        if node.text:
            lines.append(html.unescape(node.text))
    return _clean_text("\n".join(lines), max_chars=max_chars)


def fetch_video_evidence(
    resource: dict[str, Any],
    *,
    timeout_seconds: int = 20,
    max_chars: int = VIDEO_MAX_CHARS,
) -> dict[str, Any]:
    video_id = resource.get("video_id", "")
    search_fallback = _clean_text(
        "\n".join(
            [
                resource.get("search_content", ""),
                resource.get("snippet", ""),
            ]
        ),
        max_chars=max_chars,
    )
    if not video_id:
        return {
            "fetch_status": "missing_video_id",
            "content_text": search_fallback,
            "content_source": "search_metadata",
            "transcript_available": False,
        }

    try:
        page_html = _fetch_youtube_watch_page(video_id, timeout_seconds)
        caption_url = _extract_caption_track_url(page_html)
        transcript = _fetch_youtube_transcript_text(
            caption_url,
            timeout_seconds=timeout_seconds,
            max_chars=max_chars,
        )
        if transcript:
            return {
                "fetch_status": "ok",
                "content_text": transcript,
                "content_source": "youtube_transcript",
                "transcript_available": True,
            }
    except Exception:
        pass

    return {
        "fetch_status": "fallback",
        "content_text": search_fallback,
        "content_source": "search_metadata",
        "transcript_available": False,
    }


def materialize_bundle_evidence(
    bundle: dict[str, Any],
    *,
    reading_timeout_seconds: int = 20,
    video_timeout_seconds: int = 20,
    max_workers: int = 8,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    hydrated = json.loads(json.dumps(bundle))
    resource_jobs = [
        ("reading", skill, reading)
        for skill in hydrated["skills"]
        for reading in skill.get("readings", [])
    ] + [
        ("video", skill, video)
        for skill in hydrated["skills"]
        for video in skill.get("videos", [])
    ]
    total = len(resource_jobs)
    completed = 0

    _emit_progress(
        progress_callback,
        phase="hydrate",
        stage="start",
        completed=completed,
        total=total,
        message=f"Preparing to hydrate {total} resources",
    )

    if total == 0:
        _emit_progress(
            progress_callback,
            phase="hydrate",
            stage="complete",
            completed=completed,
            total=total,
            message="Finished hydrating 0 resources",
        )
        return hydrated

    worker_count = max(1, min(int(max_workers), total))

    if worker_count == 1:
        for resource_kind, skill, resource in resource_jobs:
            resource_title = (
                resource.get("title", "") or resource.get("url", "") or "Untitled"
            )
            _emit_progress(
                progress_callback,
                phase="hydrate",
                stage="item_start",
                completed=completed,
                total=total,
                skill_name=skill.get("name", ""),
                resource_kind=resource_kind,
                resource_title=resource_title,
                message=(
                    f"Fetching {resource_kind} for skill '{skill.get('name', '')}': "
                    f"{resource_title}"
                ),
            )
            if resource_kind == "reading":
                resource["evidence"] = fetch_reading_evidence(
                    resource,
                    timeout_seconds=reading_timeout_seconds,
                )
                fetch_status = resource["evidence"].get("fetch_status", "")
            else:
                resource["evidence"] = fetch_video_evidence(
                    resource,
                    timeout_seconds=video_timeout_seconds,
                )
                fetch_status = resource["evidence"].get("fetch_status", "")
            completed += 1
            _emit_progress(
                progress_callback,
                phase="hydrate",
                stage="item_complete",
                completed=completed,
                total=total,
                skill_name=skill.get("name", ""),
                resource_kind=resource_kind,
                resource_title=resource_title,
                fetch_status=fetch_status,
                message=(
                    f"Completed {resource_kind} for skill '{skill.get('name', '')}' "
                    f"with status '{fetch_status}'"
                ),
            )
    else:
        future_map = {}
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for resource_kind, skill, resource in resource_jobs:
                resource_title = (
                    resource.get("title", "") or resource.get("url", "") or "Untitled"
                )
                _emit_progress(
                    progress_callback,
                    phase="hydrate",
                    stage="item_start",
                    completed=completed,
                    total=total,
                    skill_name=skill.get("name", ""),
                    resource_kind=resource_kind,
                    resource_title=resource_title,
                    message=(
                        f"Queueing {resource_kind} for skill '{skill.get('name', '')}': "
                        f"{resource_title}"
                    ),
                )
                if resource_kind == "reading":
                    future = executor.submit(
                        fetch_reading_evidence,
                        resource,
                        timeout_seconds=reading_timeout_seconds,
                    )
                else:
                    future = executor.submit(
                        fetch_video_evidence,
                        resource,
                        timeout_seconds=video_timeout_seconds,
                    )
                future_map[future] = (resource_kind, skill, resource, resource_title)

            for future in as_completed(future_map):
                resource_kind, skill, resource, resource_title = future_map[future]
                resource["evidence"] = future.result()
                fetch_status = resource["evidence"].get("fetch_status", "")
                completed += 1
                _emit_progress(
                    progress_callback,
                    phase="hydrate",
                    stage="item_complete",
                    completed=completed,
                    total=total,
                    skill_name=skill.get("name", ""),
                    resource_kind=resource_kind,
                    resource_title=resource_title,
                    fetch_status=fetch_status,
                    message=(
                        f"Completed {resource_kind} for skill '{skill.get('name', '')}' "
                        f"with status '{fetch_status}'"
                    ),
                )

    _emit_progress(
        progress_callback,
        phase="hydrate",
        stage="complete",
        completed=completed,
        total=total,
        message=f"Finished hydrating {completed} resources",
    )
    return hydrated


def _resource_evidence_block(
    resource: dict[str, Any],
    *,
    max_chars: int = RESOURCE_EVIDENCE_MAX_CHARS,
) -> str:
    evidence = resource.get("evidence", {})
    content_text = _clean_text(evidence.get("content_text", ""), max_chars=max_chars)
    lines = [
        f"Title: {resource.get('title', '')}",
        f"URL: {resource.get('url', '')}",
        f"Type: {resource.get('resource_type', '')}",
        f"Final Score: {resource.get('final_score', 0.0)}",
        f"Concepts Covered: {', '.join(resource.get('concepts_covered', []))}",
        f"Evidence Source: {evidence.get('content_source', 'unknown')}",
        f"Evidence Text: {content_text}",
    ]
    return "\n".join(lines)


def build_modality_evidence(
    skill: dict[str, Any],
    modality: Literal["readings", "videos", "combined"],
) -> tuple[str, list[dict[str, Any]]]:
    readings = skill.get("readings", [])
    videos = skill.get("videos", [])
    if modality == "readings":
        selected = readings[:3]
    elif modality == "videos":
        selected = videos[:3]
    else:
        selected = readings[:2] + videos[:2]
    evidence_text = "\n\n---\n\n".join(
        _resource_evidence_block(resource) for resource in selected
    )
    return evidence_text, selected


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return text


def _has_usable_evidence(resources: list[dict[str, Any]]) -> bool:
    return any(
        str(resource.get("evidence", {}).get("content_text", "")).strip()
        for resource in resources
    )


def judge_question(
    client: OpenAI,
    *,
    model: str,
    skill: dict[str, Any],
    question: dict[str, Any],
    modality: Literal["readings", "videos", "combined"],
    evidence_text: str,
) -> JudgeVerdict:
    system_prompt = """You are a rigorous educational evaluation judge.

You are given:
- a target skill
- one multiple-choice question generated from the skill metadata
- evidence from retrieved learning resources

Your job is to decide whether the provided evidence contains enough information
for a student to answer the question correctly using ONLY that evidence.

Rules:
- Use ONLY the provided evidence.
- Be strict. Do not use outside knowledge, guessing, or plausibility.
- answerable must be true only if the evidence contains enough information to justify
  a correct answer.
- If answerable is false, explain what information is missing or insufficient.
- supporting_quotes should contain short verbatim evidence snippets when possible.

Return a single valid JSON object with exactly this structure:
{
  "answerable": true or false,
  "confidence": 0.0-1.0,
  "evidence_strength": "strong" | "partial" | "weak" | "none",
  "supporting_quotes": ["..."],
  "missing_information": "brief explanation of what is absent or insufficient; empty string if answerable is true",
  "reasoning": "brief explanation"
}
"""

    user_prompt = f"""
Skill Name: {skill.get("name", "")}
Skill Type: {skill.get("skill_type", "")}
Selection Source: {skill.get("source", "")}
Question Modality: {modality}

Question:
{question.get("text", "")}

Options:
A. {question.get("options", ["", "", "", ""])[0]}
B. {question.get("options", ["", "", "", ""])[1]}
C. {question.get("options", ["", "", "", ""])[2]}
D. {question.get("options", ["", "", "", ""])[3]}

Evidence:
{evidence_text}
"""
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_completion_tokens=1200,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content or ""
    return JudgeVerdict.model_validate_json(_strip_json_fence(content))


def run_answerability_experiment(
    bundle: dict[str, Any],
    *,
    client: OpenAI,
    model: str,
    modalities: tuple[Literal["readings", "videos", "combined"], ...] = (
        "readings",
        "videos",
        "combined",
    ),
    max_workers: int = 4,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    student = bundle.get("student", {})
    jobs = [
        (skill, question, modality)
        for skill in bundle["skills"]
        for question in skill.get("questions", [])
        for modality in modalities
    ]
    total = len(jobs)
    completed = 0

    _emit_progress(
        progress_callback,
        phase="judge",
        stage="start",
        completed=completed,
        total=total,
        message=f"Preparing to judge {total} question-modality pairs",
    )

    if total == 0:
        _emit_progress(
            progress_callback,
            phase="judge",
            stage="complete",
            completed=completed,
            total=total,
            message="Finished judging 0 question-modality pairs",
        )
        return []

    def _run_single_job(
        skill: dict[str, Any],
        question: dict[str, Any],
        modality: Literal["readings", "videos", "combined"],
    ) -> dict[str, Any]:
        evidence_text, used_resources = build_modality_evidence(skill, modality)
        has_usable_evidence = _has_usable_evidence(used_resources)
        evidence_preview = evidence_text[:1200]
        if has_usable_evidence:
            verdict = judge_question(
                client,
                model=model,
                skill=skill,
                question=question,
                modality=modality,
                evidence_text=evidence_text,
            )
        else:
            verdict = JudgeVerdict(
                answerable=False,
                confidence=0.0,
                evidence_strength="none",
                supporting_quotes=[],
                missing_information=(
                    "No usable evidence was available for this modality after hydration."
                ),
                reasoning=(
                    "No usable evidence was available for this modality after hydration, "
                    "so the judge abstained without making a model call."
                ),
            )
        return {
            "student_id": student.get("id"),
            "student_email": student.get("email", ""),
            "course_id": bundle.get("course_id"),
            "skill_name": skill.get("name", ""),
            "skill_type": skill.get("skill_type", ""),
            "selection_source": skill.get("source", ""),
            "question_id": question.get("id", ""),
            "question_text": question.get("text", ""),
            "difficulty": question.get("difficulty", ""),
            "correct_option": question.get("correct_option", ""),
            "modality": modality,
            "answerable": verdict.answerable,
            "confidence": verdict.confidence,
            "evidence_strength": verdict.evidence_strength,
            "supporting_quotes": verdict.supporting_quotes,
            "missing_information": verdict.missing_information,
            "reasoning": verdict.reasoning,
            "usable_evidence": has_usable_evidence,
            "used_resource_count": len(used_resources),
            "evidence_chars": len(evidence_text),
            "evidence_preview": evidence_preview,
            "used_resource_titles": [
                resource.get("title", "") for resource in used_resources
            ],
            "used_resource_urls": [
                resource.get("url", "") for resource in used_resources
            ],
        }

    rows: list[dict[str, Any] | None] = [None] * total
    worker_count = max(1, min(int(max_workers), total))

    if worker_count == 1:
        for index, (skill, question, modality) in enumerate(jobs):
            _emit_progress(
                progress_callback,
                phase="judge",
                stage="item_start",
                completed=completed,
                total=total,
                skill_name=skill.get("name", ""),
                question_id=question.get("id", ""),
                modality=modality,
                message=(
                    f"Judging {modality} evidence for skill '{skill.get('name', '')}' "
                    f"and question '{question.get('id', '') or question.get('text', '')[:60]}'"
                ),
            )
            row = _run_single_job(skill, question, modality)
            rows[index] = row
            completed += 1
            _emit_progress(
                progress_callback,
                phase="judge",
                stage="item_complete",
                completed=completed,
                total=total,
                skill_name=skill.get("name", ""),
                question_id=question.get("id", ""),
                modality=modality,
                answerable=row["answerable"],
                evidence_strength=row["evidence_strength"],
                message=(
                    f"Completed {modality} judgment for skill '{skill.get('name', '')}': "
                    f"answerable={row['answerable']}, "
                    f"strength={row['evidence_strength']}"
                ),
            )
    else:
        future_map = {}
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for index, (skill, question, modality) in enumerate(jobs):
                _emit_progress(
                    progress_callback,
                    phase="judge",
                    stage="item_start",
                    completed=completed,
                    total=total,
                    skill_name=skill.get("name", ""),
                    question_id=question.get("id", ""),
                    modality=modality,
                    message=(
                        f"Queueing {modality} judgment for skill '{skill.get('name', '')}' "
                        f"and question '{question.get('id', '') or question.get('text', '')[:60]}'"
                    ),
                )
                future = executor.submit(_run_single_job, skill, question, modality)
                future_map[future] = (index, skill, question, modality)

            for future in as_completed(future_map):
                index, skill, question, modality = future_map[future]
                row = future.result()
                rows[index] = row
                completed += 1
                _emit_progress(
                    progress_callback,
                    phase="judge",
                    stage="item_complete",
                    completed=completed,
                    total=total,
                    skill_name=skill.get("name", ""),
                    question_id=question.get("id", ""),
                    modality=modality,
                    answerable=row["answerable"],
                    evidence_strength=row["evidence_strength"],
                    message=(
                        f"Completed {modality} judgment for skill '{skill.get('name', '')}': "
                        f"answerable={row['answerable']}, "
                        f"strength={row['evidence_strength']}"
                    ),
                )

    _emit_progress(
        progress_callback,
        phase="judge",
        stage="complete",
        completed=completed,
        total=total,
        message=f"Finished judging {completed} question-modality pairs",
    )
    return [row for row in rows if row is not None]


def summarize_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "overall": {
                "judgments": 0,
                "answerable_yes_count": 0,
                "answerable_no_count": 0,
                "answerable_rate": 0.0,
            },
            "by_modality": [],
            "by_skill_type": [],
            "by_difficulty": [],
            "by_modality_and_difficulty": [],
        }

    def _group(group_key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(str(row[group_key]), []).append(row)
        output = []
        for value, group_rows in sorted(groups.items()):
            count = len(group_rows)
            answerable_yes = sum(1 for row in group_rows if row["answerable"])
            output.append(
                {
                    group_key: value,
                    "judgments": count,
                    "answerable_yes_count": answerable_yes,
                    "answerable_no_count": count - answerable_yes,
                    "answerable_rate": answerable_yes / count,
                }
            )
        return output

    total = len(rows)
    answerable_total = sum(1 for row in rows if row["answerable"])
    by_modality_and_difficulty: list[dict[str, Any]] = []
    combo_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        combo_groups.setdefault(
            (str(row["modality"]), str(row["difficulty"])), []
        ).append(row)
    for (modality, difficulty), group_rows in sorted(combo_groups.items()):
        count = len(group_rows)
        answerable_yes = sum(1 for row in group_rows if row["answerable"])
        by_modality_and_difficulty.append(
            {
                "modality": modality,
                "difficulty": difficulty,
                "judgments": count,
                "answerable_yes_count": answerable_yes,
                "answerable_no_count": count - answerable_yes,
                "answerable_rate": answerable_yes / count,
            }
        )
    return {
        "overall": {
            "judgments": total,
            "answerable_yes_count": answerable_total,
            "answerable_no_count": total - answerable_total,
            "answerable_rate": answerable_total / total,
        },
        "by_modality": _group("modality"),
        "by_skill_type": _group("skill_type"),
        "by_difficulty": _group("difficulty"),
        "by_modality_and_difficulty": by_modality_and_difficulty,
    }


def save_artifacts(
    *,
    repo_root: str | Path | None,
    bundle: dict[str, Any],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    artifact_prefix: str = "resource_answerability",
) -> dict[str, str]:
    root = find_repo_root(repo_root)
    notebook_dir = (
        root / "backend" / "app" / "modules" / "student_learning_path" / "notebooks"
    )
    artifact_dir = notebook_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    bundle_path = artifact_dir / f"{artifact_prefix}_{timestamp}_bundle.json"
    rows_json_path = artifact_dir / f"{artifact_prefix}_{timestamp}_judgments.json"
    rows_csv_path = artifact_dir / f"{artifact_prefix}_{timestamp}_judgments.csv"
    summary_path = artifact_dir / f"{artifact_prefix}_{timestamp}_summary.json"

    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    rows_json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    if rows:
        fieldnames = list(rows[0].keys())
        with rows_csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        rows_csv_path.write_text("", encoding="utf-8")

    return {
        "bundle_json": str(bundle_path),
        "judgments_json": str(rows_json_path),
        "judgments_csv": str(rows_csv_path),
        "summary_json": str(summary_path),
    }
