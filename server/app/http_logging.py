"""HTTP request correlation and canonical access logging."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import JSONResponse, Response

from .logging_config import log_context, log_event, safe_exception_info


logger = logging.getLogger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    value = getattr(route, "path", None)
    return value if isinstance(value, str) and value else "<unmatched>"


async def http_request_logging(
    request: Request,
    call_next: RequestHandler,
) -> Response:
    """Bind a request ID and emit exactly one safe request summary."""

    request_id = uuid.uuid4().hex
    started = time.monotonic()
    with log_context(request_id=request_id):
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.monotonic() - started) * 1000, 2)
            logger.error(
                "event=http.request.failed method=%s route=%s status=500 "
                "duration_ms=%.2f error_type=%s",
                request.method,
                _route_template(request),
                duration_ms,
                type(exc).__name__,
                exc_info=safe_exception_info(exc),
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "request_id": request_id},
                headers={"X-Request-ID": request_id},
            )

        duration_ms = round((time.monotonic() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log_event(
            logger,
            logging.INFO,
            "http.request.completed",
            method=request.method,
            route=_route_template(request),
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
