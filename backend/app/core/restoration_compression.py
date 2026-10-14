import re

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, IdentityResponder
from starlette.types import ASGIApp, Receive, Scope, Send

_RESTORATION_PATH = re.compile(
    r"/courses/[^/]+/market-demand/(?:history|state|skill-review)"
)
_GZIP_OFFERED = re.compile(r"(?:^|,)\s*gzip\s*(?:;|,|$)", re.I)
_GZIP_REFUSED = re.compile(r"(?:^|,)\s*gzip\s*;\s*q=0(?:\.0*)?\s*(?:,|$)", re.I)


class MarketRestorationCompressionMiddleware:
    """Compress large restoration reads without touching other endpoint traffic."""

    def __init__(
        self, app: ASGIApp, *, minimum_size: int = 1024, compresslevel: int = 5
    ) -> None:
        self.app = app
        self._gzip = GZipMiddleware(
            app, minimum_size=minimum_size, compresslevel=compresslevel
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "GET"
            or not _RESTORATION_PATH.fullmatch(scope["path"])
        ):
            await self.app(scope, receive, send)
            return

        # Starlette matches a substring; require a complete offer and honor q=0.
        accept_encoding = Headers(scope=scope).get("accept-encoding", "")
        if not _GZIP_OFFERED.search(accept_encoding) or _GZIP_REFUSED.search(
            accept_encoding
        ):
            await IdentityResponder(self.app, self._gzip.minimum_size)(
                scope, receive, send
            )
            return

        await self._gzip(scope, receive, send)
