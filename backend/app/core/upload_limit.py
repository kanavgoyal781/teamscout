"""Enforce maximum request body size for uploads (default 10 MiB)."""
from __future__ import annotations
import json
from typing import Any
from app.core.config import settings
class UploadSizeLimitMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app
    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        max_bytes = settings.MAX_UPLOAD_BYTES
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                length = -1
            if length > max_bytes:
                body = json.dumps(
                    {
                        "error": "payload_too_large",
                        "message": f"Request body exceeds {max_bytes} bytes",
                        "details": {"max_bytes": max_bytes, "content_length": length},
                    }
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("latin-1")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
def enforce_upload_size(data: bytes) -> None:
    """Raise ValidationError if in-memory body exceeds the configured limit."""
    from app.errors import ValidationError
    max_bytes = settings.MAX_UPLOAD_BYTES
    if len(data) > max_bytes:
        raise ValidationError(
            f"Uploaded file exceeds {max_bytes} bytes",
            details={"max_bytes": max_bytes, "size": len(data)},
        )
