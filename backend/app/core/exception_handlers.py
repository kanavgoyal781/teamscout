"""Global exception handlers — never leak stack traces or secrets to clients."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.errors import TeamScoutError

logger = get_logger(__name__)


def _request_id(request: Request) -> str | None:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return str(rid)
    return None


async def teamscout_error_handler(_request: Request, exc: TeamScoutError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception(
        "unhandled_error",
        request_id=request_id,
        path=str(request.url.path),
        method=request.method,
        error_type=type(exc).__name__,
    )
    # Exception handlers for Exception are invoked by ServerErrorMiddleware, which sits
    # outside RequestIdMiddleware — so we must set X-Request-ID here (429 uses
    # ExceptionMiddleware inside the request-id wrapper and must not set the header).
    content = {
        "error": "internal_error",
        "message": "Internal server error",
        "details": {"request_id": request_id} if request_id else {},
    }
    response = JSONResponse(status_code=500, content=content)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response
