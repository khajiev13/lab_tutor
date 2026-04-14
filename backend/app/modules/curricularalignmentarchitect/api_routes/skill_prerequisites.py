"""SSE endpoint for skill prerequisite pipeline.

POST /courses/{course_id}/skill-prerequisites/build
GET  /courses/{course_id}/skill-prerequisites
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import Depends
from fastapi.responses import StreamingResponse

from app.core.neo4j import create_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..skill_prerequisites.graph import build_skill_prerequisite_graph
from ..skill_prerequisites.repository import get_skill_prerequisites

logger = logging.getLogger(__name__)

MAX_CONCURRENCY = 10


def register_routes(router):
    @router.post("/courses/{course_id}/skill-prerequisites/build")
    async def build_skill_prerequisites(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        q: asyncio.Queue[str | None] = asyncio.Queue()
        asyncio.create_task(_run_background(course_id, q))

        async def stream():
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    yield item
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/courses/{course_id}/skill-prerequisites")
    def get_prerequisites(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        driver = create_neo4j_driver()
        if driver is None:
            return {"edges": []}
        edges = get_skill_prerequisites(driver, course_id)
        driver.close()
        return {"edges": edges}


async def _run_background(course_id: int, queue: asyncio.Queue[str | None]):
    await queue.put(_sse("prerequisite_started", {"course_id": course_id}))
    try:
        graph = build_skill_prerequisite_graph()
        async for mode, chunk in graph.astream(
            {
                "course_id": course_id,
                "merged_skill_names": [],
                "prereq_edges": [],
                "final_edges": [],
                "_clusterable_skills": [],
            },
            stream_mode=["custom", "updates"],
            config={"max_concurrency": MAX_CONCURRENCY},
        ):
            if mode == "custom":
                event_type = chunk.get("type", "prerequisite_progress")
                await queue.put(_sse(event_type, chunk))
    except Exception as e:
        logger.exception("Skill prerequisite pipeline failed for course %d", course_id)
        await queue.put(_sse("error", {"message": str(e)[:500]}))
    finally:
        await queue.put(None)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"
