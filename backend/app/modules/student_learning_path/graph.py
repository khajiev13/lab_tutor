"""LangGraph pipeline for building personalized student learning paths.

Fan-in/fan-out architecture using Send API:
1. load_selected_skills — reads selected skills, checks resource status
2. fan_out_skills — returns [Send("process_skill", {...})] per skill needing work
3. process_skill — the worker: TRA → VCE → question generation per skill
4. synthesize — aggregates results
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send
from neo4j import Driver as Neo4jDriver
from typing_extensions import TypedDict

from app.core.resource_pipeline.neo4j_repository import write_resources
from app.core.resource_pipeline.schemas import SkillProfile
from app.core.settings import settings
from app.modules.question_generation.neo4j_repository import (
    has_questions,
    write_questions,
)
from app.modules.question_generation.service import generate_questions_for_skill
from app.modules.textualresourceanalyst.config import (
    RELATIONSHIP as READING_RELATIONSHIP,
)
from app.modules.textualresourceanalyst.config import (
    RESOURCE_LABEL as READING_LABEL,
)
from app.modules.textualresourceanalyst.service import fetch_readings_for_skill
from app.modules.visualcontentevaluator.config import (
    RELATIONSHIP as VIDEO_RELATIONSHIP,
)
from app.modules.visualcontentevaluator.config import (
    RESOURCE_LABEL as VIDEO_LABEL,
)
from app.modules.visualcontentevaluator.service import fetch_videos_for_skill

from . import neo4j_repository

logger = logging.getLogger(__name__)


# ── State Schemas ─────────────────────────────────────────────


class BuildState(TypedDict):
    """Top-level state for the learning path build graph."""

    student_id: int
    course_id: int
    neo4j_driver: Neo4jDriver  # Passed through for workers to use
    skills_to_process: list[dict]
    results: Annotated[list[dict], operator.add]  # Fan-in accumulator


class SkillWorkerInput(TypedDict):
    """Per-skill worker input (via Send)."""

    skill: dict  # SkillProfile-like dict
    course_id: int
    neo4j_driver: Neo4jDriver
    needs_reading: bool
    needs_video: bool
    needs_questions: bool
    worker_index: int
    total_skills: int


# ── Nodes ─────────────────────────────────────────────────────


def _format_question_error(exc: Exception) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    detail = " ".join(detail.split())
    if len(detail) > 180:
        detail = detail[:177] + "..."
    return f"Question generation failed: {detail}"


def load_selected_skills(state: BuildState) -> dict:
    """Load selected skills and check which need resources/questions."""
    driver = state["neo4j_driver"]

    with driver.session(database=settings.neo4j_database) as session:
        selected = neo4j_repository.get_selected_skills(
            session, state["student_id"], state["course_id"]
        )
        skill_names = [s["name"] for s in selected]
        resource_status = neo4j_repository.get_skill_resource_status(
            session, skill_names
        )

    skills_to_process = []
    for s in selected:
        name = s["name"]
        status = resource_status.get(name, {})
        skills_to_process.append(
            {
                **s,
                "needs_reading": not status.get("has_readings", False),
                "needs_video": not status.get("has_videos", False),
                "needs_questions": not status.get("has_questions", False),
            }
        )

    logger.info(
        "Loaded %d selected skills, %d need work",
        len(selected),
        sum(
            1
            for s in skills_to_process
            if s["needs_reading"] or s["needs_video"] or s["needs_questions"]
        ),
    )

    return {"skills_to_process": skills_to_process}


def fan_out_skills(state: BuildState) -> list[Send]:
    """Fan out to parallel workers via Send API."""
    sends = []
    total = len(state["skills_to_process"])

    for i, skill in enumerate(state["skills_to_process"]):
        needs_work = (
            skill["needs_reading"] or skill["needs_video"] or skill["needs_questions"]
        )
        if not needs_work:
            # Still send to produce a skip result for the accumulator
            pass

        sends.append(
            Send(
                "process_skill",
                SkillWorkerInput(
                    skill=skill,
                    course_id=state["course_id"],
                    neo4j_driver=state["neo4j_driver"],
                    needs_reading=skill["needs_reading"],
                    needs_video=skill["needs_video"],
                    needs_questions=skill["needs_questions"],
                    worker_index=i,
                    total_skills=total,
                ),
            )
        )

    return sends


def process_skill(state: SkillWorkerInput) -> dict:
    """Worker: fetch readings, videos, generate questions for ONE skill."""
    writer = get_stream_writer()
    skill = state["skill"]
    driver = state["neo4j_driver"]
    skill_name = skill["name"]
    idx = state["worker_index"]
    total = state["total_skills"]

    result = {
        "skill_name": skill_name,
        "readings_added": 0,
        "videos_added": 0,
        "questions_added": 0,
        "question_error": "",
        "skipped": False,
    }

    needs_any = (
        state["needs_reading"] or state["needs_video"] or state["needs_questions"]
    )
    if not needs_any:
        result["skipped"] = True
        writer(
            {
                "type": "skill_progress",
                "skill_name": skill_name,
                "phase": "skipped",
                "detail": "Resources already exist",
                "skills_completed": idx + 1,
                "total_skills": total,
            }
        )
        return {"results": [result]}

    # Build SkillProfile from dict
    skill_profile = SkillProfile(
        name=skill_name,
        skill_type=skill.get("skill_type", "book"),
        description=skill.get("description", ""),
        chapter_title=skill.get("chapter_title", ""),
        chapter_summary=skill.get("chapter_summary", ""),
        chapter_index=skill.get("chapter_index", 0),
        concepts=skill.get("concepts", []),
        course_level=skill.get("course_level", "bachelor"),
    )

    # 1. Readings
    if state["needs_reading"]:
        writer(
            {
                "type": "skill_progress",
                "skill_name": skill_name,
                "phase": "reading",
                "detail": "Fetching reading resources...",
                "skills_completed": idx,
                "total_skills": total,
            }
        )
        try:
            readings = fetch_readings_for_skill(skill_profile)
            if readings:
                with driver.session(database=settings.neo4j_database) as session:
                    write_resources(
                        session,
                        skill_name,
                        skill_profile.skill_type,
                        readings,
                        READING_LABEL,
                        READING_RELATIONSHIP,
                    )
                result["readings_added"] = len(readings)
        except Exception:
            logger.warning("Reading pipeline failed for %s", skill_name, exc_info=True)

    # 2. Videos
    if state["needs_video"]:
        writer(
            {
                "type": "skill_progress",
                "skill_name": skill_name,
                "phase": "video",
                "detail": "Fetching video resources...",
                "skills_completed": idx,
                "total_skills": total,
            }
        )
        try:
            videos = fetch_videos_for_skill(skill_profile)
            if videos:
                with driver.session(database=settings.neo4j_database) as session:
                    write_resources(
                        session,
                        skill_name,
                        skill_profile.skill_type,
                        videos,
                        VIDEO_LABEL,
                        VIDEO_RELATIONSHIP,
                    )
                result["videos_added"] = len(videos)
        except Exception:
            logger.warning("Video pipeline failed for %s", skill_name, exc_info=True)

    # 3. Questions
    if state["needs_questions"]:
        writer(
            {
                "type": "skill_progress",
                "skill_name": skill_name,
                "phase": "question",
                "detail": "Generating questions...",
                "skills_completed": idx,
                "total_skills": total,
            }
        )
        try:
            # Double-check hasn't been generated by another concurrent worker
            with driver.session(database=settings.neo4j_database) as session:
                if not has_questions(session, skill_name):
                    questions = generate_questions_for_skill(
                        skill_name,
                        skill_profile.description,
                        skill_profile.concepts,
                        skill_profile.course_level,
                    )
                    written = write_questions(session, skill_name, questions)
                    if written != len(questions):
                        raise RuntimeError(
                            f"Question persistence mismatch for {skill_name}: "
                            f"wrote {written} of {len(questions)} questions"
                        )
                    result["questions_added"] = written
        except Exception as exc:
            error_detail = _format_question_error(exc)
            result["question_error"] = error_detail
            writer(
                {
                    "type": "skill_progress",
                    "skill_name": skill_name,
                    "phase": "question_error",
                    "detail": error_detail,
                    "skills_completed": idx,
                    "total_skills": total,
                }
            )
            logger.warning("Question gen failed for %s", skill_name, exc_info=True)

    done_detail = (
        f"Readings: {result['readings_added']}, "
        f"Videos: {result['videos_added']}, "
        f"Questions: {result['questions_added']}"
    )
    if result["question_error"]:
        done_detail = f"{done_detail} ({result['question_error']})"

    writer(
        {
            "type": "skill_progress",
            "skill_name": skill_name,
            "phase": "done",
            "detail": done_detail,
            "skills_completed": idx + 1,
            "total_skills": total,
        }
    )

    return {"results": [result]}


def synthesize(state: BuildState) -> dict:
    """Fan-in: aggregate results from all workers."""
    results = state.get("results", [])
    summary = {
        "total_skills": len(results),
        "readings_added": sum(r.get("readings_added", 0) for r in results),
        "videos_added": sum(r.get("videos_added", 0) for r in results),
        "questions_added": sum(r.get("questions_added", 0) for r in results),
        "skipped": sum(1 for r in results if r.get("skipped")),
    }
    logger.info(
        "Build complete: %d skills, %d readings, %d videos, %d questions, %d skipped",
        summary["total_skills"],
        summary["readings_added"],
        summary["videos_added"],
        summary["questions_added"],
        summary["skipped"],
    )
    return {"results": results}


# ── Graph Construction ────────────────────────────────────────


def build_learning_path_graph():
    """Construct and compile the learning path build graph."""
    return (
        StateGraph(BuildState)
        .add_node(
            "load_skills",
            load_selected_skills,
        )
        .add_node(
            "process_skill",
            process_skill,
            retry=RetryPolicy(max_attempts=2, initial_interval=2.0),
        )
        .add_node("synthesize", synthesize)
        .add_edge(START, "load_skills")
        .add_conditional_edges("load_skills", fan_out_skills, ["process_skill"])
        .add_edge("process_skill", "synthesize")
        .add_edge("synthesize", END)
        .compile()
    )


# Compiled graph singleton
learning_path_graph = build_learning_path_graph()
