from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.database import SessionLocal
from app.core.neo4j import create_neo4j_driver
from app.modules.courses.repository import CourseRepository

from .graph import build_skill_prerequisite_graph
from .review_repository import PrerequisiteReviewRepository
from .review_service import Neo4jPrerequisiteReviewRepository, PrerequisiteReviewService
from .schemas import PrerequisiteDraftEdge

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 10

EventSink = Callable[[str, dict], Awaitable[None]]

_running_course_ids: set[int] = set()
_running_lock = asyncio.Lock()


def _initial_state(course_id: int) -> dict:
    return {
        "course_id": course_id,
        "merged_skill_names": [],
        "prereq_edges": [],
        "final_edges": [],
        "_clusterable_skills": [],
    }


async def _emit(
    emit_event: EventSink | None,
    event_type: str,
    payload: dict,
) -> None:
    if emit_event is not None:
        await emit_event(event_type, payload)


async def _reserve_course(course_id: int) -> bool:
    async with _running_lock:
        if course_id in _running_course_ids:
            return False
        _running_course_ids.add(course_id)
        return True


async def _release_course(course_id: int) -> None:
    async with _running_lock:
        _running_course_ids.discard(course_id)


async def run_skill_prerequisites(
    course_id: int,
    *,
    trigger_reason: str = "manual",
    auto_triggered: bool = False,
    emit_event: EventSink | None = None,
) -> bool:
    """Run the skill prerequisite graph once for a course.

    Returns False when the run is skipped or fails. The graph itself owns
    Neo4j reads/writes; this service only provides shared orchestration.
    """

    event_context = {
        "course_id": course_id,
        "trigger_reason": trigger_reason,
        "auto_triggered": auto_triggered,
    }
    if not await _reserve_course(course_id):
        await _emit(
            emit_event,
            "prerequisite_skipped",
            {**event_context, "reason": "already_running"},
        )
        logger.info(
            "Skipping prerequisite rebuild for course %s; a run is already active",
            course_id,
        )
        return False

    await _emit(emit_event, "prerequisite_started", event_context)
    try:
        graph = build_skill_prerequisite_graph()
        generated_edges: list[PrerequisiteDraftEdge] = []
        async for mode, chunk in graph.astream(
            _initial_state(course_id),
            stream_mode=["custom", "updates"],
            config={"max_concurrency": MAX_CONCURRENCY},
        ):
            if mode != "custom":
                continue
            payload = dict(chunk) if isinstance(chunk, dict) else {"value": chunk}
            event_type = str(payload.get("type") or "prerequisite_progress")
            if event_type == "prerequisite_generated":
                generated_edges = _draft_edges_from_generated_payload(payload)
            payload.setdefault("course_id", course_id)
            payload["trigger_reason"] = trigger_reason
            payload["auto_triggered"] = auto_triggered
            await _emit(emit_event, event_type, payload)
        _save_generated_review_draft(course_id, generated_edges)
        await _emit(
            emit_event,
            "prerequisite_completed",
            {**event_context, "draft_edges": len(generated_edges)},
        )
        return True
    except Exception as exc:
        logger.exception("Skill prerequisite pipeline failed for course %d", course_id)
        await _emit(
            emit_event,
            "prerequisite_failed",
            {**event_context, "message": str(exc)[:500]},
        )
        try:
            _mark_review_rebuild_failed(course_id)
        except Exception:
            logger.exception(
                "Failed to clear prerequisite rebuilding flag for course %d",
                course_id,
            )
        return False
    finally:
        await _release_course(course_id)


def schedule_skill_prerequisite_rebuild(
    course_id: int,
    trigger_reason: str,
) -> asyncio.Task[bool]:
    """Schedule a best-effort prerequisite rebuild without blocking the caller."""

    return asyncio.create_task(
        run_skill_prerequisites(
            course_id,
            trigger_reason=trigger_reason,
            auto_triggered=True,
        )
    )


def _draft_edges_from_generated_payload(payload: dict) -> list[PrerequisiteDraftEdge]:
    edges: list[PrerequisiteDraftEdge] = []
    for edge in payload.get("final_edges", []):
        if not isinstance(edge, dict):
            continue
        edges.append(
            PrerequisiteDraftEdge(
                prerequisite_name=edge["prerequisite_skill"],
                dependent_name=edge["dependent_skill"],
                confidence=edge["confidence"],
                reasoning=edge["reasoning"],
                source="ai",
            )
        )
    return edges


def _save_generated_review_draft(
    course_id: int,
    generated_edges: list[PrerequisiteDraftEdge],
) -> None:
    driver = create_neo4j_driver()
    if driver is None:
        return

    db = SessionLocal()
    try:
        review_service = PrerequisiteReviewService(
            CourseRepository(db),
            PrerequisiteReviewRepository(db),
            Neo4jPrerequisiteReviewRepository(driver),
        )
        review_service.save_generated_draft(course_id, generated_edges)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to save generated prerequisite review draft for course %d",
            course_id,
        )
        raise
    finally:
        db.close()
        driver.close()


def _mark_review_rebuild_failed(course_id: int) -> None:
    db = SessionLocal()
    try:
        PrerequisiteReviewRepository(db).mark_rebuild_failed(course_id)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to mark prerequisite rebuild failed for course %d",
            course_id,
        )
        raise
    finally:
        db.close()
