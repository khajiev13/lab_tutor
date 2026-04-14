"""On-demand book skill → course chapter mapping endpoint.

POST /courses/{course_id}/book-skill-mapping

Triggers the LangGraph book_skill_mapping workflow and streams SSE progress events.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import Depends
from fastapi.responses import StreamingResponse

from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User, UserRole

from ..book_skill_mapping.graph import build_book_skill_mapping_graph

logger = logging.getLogger(__name__)

BOOK_SKILL_MAPPING_MAX_CONCURRENCY = 5


def register_routes(router):
    @router.post("/courses/{course_id}/book-skill-mapping")
    async def start_book_skill_mapping(
        course_id: int,
        _teacher: User = Depends(require_role(UserRole.TEACHER)),
    ):
        """Map BOOK_SKILLs to COURSE_CHAPTERs and stream SSE progress.

        SSE event types:
          - ``skill_mapping_started``    — pipeline beginning
          - ``skill_mapping_progress``   — progress update from persist_all node
          - ``skill_mapping_completed``  — pipeline finished with stats
          - ``error``                    — fatal error
        """
        q: asyncio.Queue[str | None] = asyncio.Queue()
        asyncio.create_task(_run_mapping_background(course_id, q))

        async def stream_from_queue():
            try:
                while True:
                    item = await q.get()
                    if item is None:
                        break
                    yield item
            except asyncio.CancelledError:
                logger.info("Client disconnected from book skill mapping SSE.")

        return StreamingResponse(
            stream_from_queue(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


async def _run_mapping_background(course_id: int, queue: asyncio.Queue[str | None]):
    """Background task: run book skill mapping graph and forward SSE events."""
    await queue.put(_sse("skill_mapping_started", {"course_id": course_id}))

    try:
        graph = build_book_skill_mapping_graph()

        async for mode, chunk in graph.astream(
            {"course_id": course_id, "mappings": [], "errors": []},
            stream_mode=["custom", "updates"],
            config={"max_concurrency": BOOK_SKILL_MAPPING_MAX_CONCURRENCY},
        ):
            if mode == "custom":
                event_type = chunk.get("type", "skill_mapping_progress")
                await queue.put(_sse(event_type, chunk))

    except Exception as e:
        logger.exception("Book skill mapping failed for course %d", course_id)
        await queue.put(_sse("error", {"message": str(e)[:500]}))
    finally:
        await queue.put(None)


def _sse(event: str, data: dict) -> str:
    payload = {"type": event, **data}
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"
