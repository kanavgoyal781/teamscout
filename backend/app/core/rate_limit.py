"""slowapi rate limiting for expensive endpoints."""
from __future__ import annotations
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from app.core.config import settings
def _key_func(request: Request) -> str:
    return get_remote_address(request)
limiter = Limiter(
    key_func=_key_func,
    enabled=settings.RATE_LIMIT_ENABLED,
    headers_enabled=False,
    default_limits=[],
)
def upload_limit() -> str:
    return settings.RATE_LIMIT_UPLOAD
def search_limit() -> str:
    return settings.RATE_LIMIT_SEARCH
def find_team_limit() -> str:
    return settings.RATE_LIMIT_FIND_TEAM
def reveal_email_limit() -> str:
    return settings.RATE_LIMIT_REVEAL_EMAIL
def llm_limit() -> str:
    return settings.RATE_LIMIT_LLM
def feedback_limit() -> str:
    return settings.RATE_LIMIT_FEEDBACK
def stats_limit() -> str:
    return "60/minute"
def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Return 429 JSON. X-Request-ID is set solely by RequestIdMiddleware."""
    message = "Rate limit exceeded — try again later"
    if isinstance(exc, RateLimitExceeded):
        message = str(exc.detail) if exc.detail else message
    request_id = getattr(request.state, "request_id", None)
    details = {"request_id": request_id} if request_id else {}
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "message": message, "details": details},
    )
