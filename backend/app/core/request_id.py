"""Request-ID middleware: UUID per request, response header, structlog binding."""

from __future__ import annotations

import re
import uuid
from typing import Any

import structlog

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_HEADER_LOWER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def sanitize_request_id(raw: str | None) -> str:
    """Return client id if token-safe; otherwise a new UUID."""
    if raw is None:
        return str(uuid.uuid4())
    candidate = raw.strip()
    if _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        request_id = sanitize_request_id(headers.get(REQUEST_ID_HEADER_LOWER))
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["request_id"] = request_id
        extensions = scope.setdefault("extensions", {})
        if isinstance(extensions, dict):
            extensions["teamscout_request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_with_request_id(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers") or [])
                filtered = [
                    (name, value)
                    for name, value in raw_headers
                    if name.decode("latin-1").lower() != REQUEST_ID_HEADER_LOWER
                ]
                filtered.append((REQUEST_ID_HEADER.lower().encode("latin-1"), request_id.encode("latin-1")))
                message = {**message, "headers": filtered}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            structlog.contextvars.clear_contextvars()
