from __future__ import annotations

import logging
import os
from typing import Iterable

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


def configure_langsmith_env(*, api_key: str | None, project: str) -> None:
    """Configure process env vars for LangSmith/LangChain libraries.

    We intentionally DO NOT enable global LangChain tracing here. Tracing is activated
    only for selected requests (e.g. `/normalization/*`) via middleware + `@traceable`
    spans, so other endpoints remain untraced.
    """

    if not api_key:
        return

    # Prefer explicit LangSmith vars.
    os.environ.setdefault("LANGSMITH_API_KEY", api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", project)
    # Required for `langsmith.traceable` to emit runs.
    os.environ.setdefault("LANGSMITH_TRACING_V2", "true")

    # Compatibility (some libraries still read LANGCHAIN_* for auth/project context).
    os.environ.setdefault("LANGCHAIN_API_KEY", api_key)
    os.environ.setdefault("LANGCHAIN_PROJECT", project)


class ConditionalLangSmithTracingMiddleware:
    """Apply LangSmith TracingMiddleware only for selected path prefixes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        path_prefixes: Iterable[str] = ("/normalization",),
    ) -> None:
        self.app = app
        self.path_prefixes = tuple(path_prefixes)
        self._inner = None

    def _should_trace(self, scope: Scope) -> bool:
        if scope.get("type") != "http":
            return False
        path = scope.get("path") or ""
        return any(path.startswith(p) for p in self.path_prefixes)

    def _get_inner(self) -> ASGIApp:
        if self._inner is not None:
            return self._inner

        try:
            from langsmith.middleware import TracingMiddleware
        except Exception:
            logger.exception("LangSmith TracingMiddleware import failed; tracing disabled")
            self._inner = self.app
            return self._inner

        # Rely on env vars for configuration.
        self._inner = TracingMiddleware(self.app)
        return self._inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._should_trace(scope):
            await self.app(scope, receive, send)
            return

        inner = self._get_inner()
        await inner(scope, receive, send)


