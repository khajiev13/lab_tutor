import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# NOTE: Do NOT log to `uvicorn.access` here.
# Uvicorn's AccessFormatter expects access logs to use a specific 5-arg tuple shape.
# Custom log lines (like timing) can break formatting and crash logging.
timing_logger = logging.getLogger("uvicorn.error")


class RequestTimingMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        add_timing_header: bool = True,
        log_timings: bool = False,
        slow_request_ms: int = 500,
    ) -> None:
        super().__init__(app)
        self._add_timing_header = add_timing_header
        self._log_timings = log_timings
        self._slow_request_ms = slow_request_ms

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            if self._log_timings:
                self._log_line(
                    request=request,
                    status_code=500,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    error_tag=" ERROR",
                    is_exception=True,
                )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)

        if self._add_timing_header:
            response.headers.setdefault("X-Request-Id", request_id)
            response.headers["X-Request-Duration-Ms"] = str(duration_ms)

        if self._log_timings:
            self._log_line(
                request=request,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                error_tag="",
                is_exception=False,
            )

        return response

    def _log_line(
        self,
        *,
        request: Request,
        status_code: int,
        duration_ms: int,
        request_id: str,
        error_tag: str,
        is_exception: bool,
    ) -> None:
        client = request.client
        client_str = f"{client.host}:{client.port}" if client is not None else "-"
        http_version = request.scope.get("http_version") or "1.1"
        path_qs = request.url.path
        if request.url.query:
            path_qs = f"{path_qs}?{request.url.query}"

        slow_tag = " SLOW" if duration_ms >= self._slow_request_ms else ""
        msg = (
            f'{client_str} - "{request.method} {path_qs} HTTP/{http_version}" '
            f"{status_code}{error_tag}{slow_tag} {duration_ms}ms id={request_id}"
        )

        if is_exception:
            timing_logger.exception(msg)
        else:
            timing_logger.info(msg)
