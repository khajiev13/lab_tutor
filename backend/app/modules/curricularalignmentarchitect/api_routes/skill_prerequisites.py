"""SSE endpoint for skill prerequisite pipeline.

POST /courses/{course_id}/skill-prerequisites/build
GET  /courses/{course_id}/skill-prerequisites
"""

from __future__ import annotations

import asyncio
import json

from fastapi import Depends
from fastapi.responses import StreamingResponse

from app.core.neo4j import create_neo4j_driver
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..skill_prerequisites.repository import get_skill_prerequisites
from ..skill_prerequisites.service import run_skill_prerequisites


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
    async def emit_event(event_type: str, payload: dict) -> None:
        await queue.put(_sse(event_type, payload))

    await run_skill_prerequisites(course_id, emit_event=emit_event)
    await queue.put(None)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"
