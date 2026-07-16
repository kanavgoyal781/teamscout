"""Central secret redaction for user-facing errors and logs.

Strip query strings, API keys, Bearer tokens, and Authorization material before
messages reach API responses or log sinks.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

# Full URLs (capture until whitespace / quotes / angle brackets)
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
# Query or form key material that often carries secrets
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&])(key|api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|"
    r"password|authorization|auth|client_secret|private_key)=([^&\s'\"<>]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]+")
# Google API key prefix
_AIZA_RE = re.compile(r"\bAIza[0-9A-Za-z_\-]{10,}\b")
_AUTH_HEADER_RE = re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+")
# Long hex/base64-looking tokens after common secret labels
_LABELED_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client_secret|"
    r"private_key|password)\s*[:=]\s*([^\s'\"<>]+)"
)


def _scrub_url(match: re.Match[str]) -> str:
    raw = match.group(0).rstrip(").,;]")
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    # Host + path only — never query (where key= lives)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def redact_error(message: str | BaseException | None) -> str:
    """Redact secrets from an error message or exception string.

    Returns a safe string suitable for API responses and logs. Prefer host +
    status + short reason when the input is an httpx error (see format_httpx_error).
    """
    if message is None:
        return ""
    text = str(message)
    if not text:
        return ""
    text = _URL_RE.sub(_scrub_url, text)
    text = _QUERY_SECRET_RE.sub(r"\1\2=[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _AIZA_RE.sub("[REDACTED_API_KEY]", text)
    text = _AUTH_HEADER_RE.sub("Authorization: [REDACTED]", text)
    text = _LABELED_SECRET_RE.sub(r"\1=[REDACTED]", text)
    return text


def redact_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively redact string values in an error details dict."""
    if not details:
        return {}
    out: dict[str, Any] = {}
    for key, value in details.items():
        if isinstance(value, str):
            out[key] = redact_error(value)
        elif isinstance(value, dict):
            out[key] = redact_details(value)
        elif isinstance(value, list):
            out[key] = [
                redact_error(v) if isinstance(v, str) else (redact_details(v) if isinstance(v, dict) else v)
                for v in value
            ]
        else:
            out[key] = value
    return out


def format_httpx_error(exc: BaseException, *, service: str | None = None) -> str:
    """Host + status + short reason only — never the request URL with query."""
    try:
        import httpx
    except ImportError:  # pragma: no cover
        return redact_error(exc)

    if isinstance(exc, httpx.HTTPStatusError):
        host = ""
        if exc.request is not None:
            host = urlparse(str(exc.request.url)).netloc or ""
        status = exc.response.status_code if exc.response is not None else "?"
        phrase = ""
        if exc.response is not None:
            phrase = (exc.response.reason_phrase or "").strip()
        bits = [b for b in (host, f"HTTP {status}", phrase) if b]
        msg = " ".join(bits) if bits else f"HTTP {status}"
        return redact_error(msg)
    if isinstance(exc, httpx.RequestError):
        host = ""
        if exc.request is not None:
            host = urlparse(str(exc.request.url)).netloc or ""
        kind = type(exc).__name__
        return redact_error(f"{host} {kind}".strip() if host else kind)
    return redact_error(exc)


def drive_user_reason(exc: BaseException | str | None, *, status_code: int | None = None) -> str:
    """Plain-language per-file Drive failure reason for the library UI."""
    code = status_code
    if code is None and exc is not None:
        try:
            import httpx

            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                code = exc.response.status_code
        except ImportError:  # pragma: no cover
            pass
    text = redact_error(exc) if exc is not None else ""
    if code == 403 or "403" in text or "Forbidden" in text:
        return "Not shared publicly — set 'Anyone with the link' in Drive"
    if code == 404 or "404" in text:
        return "File not found or removed from the folder"
    if code == 401 or "401" in text:
        return "Drive authentication failed — check API key or OAuth credentials"
    if code is not None and code >= 500:
        return f"Google Drive temporary error (HTTP {code}) — try again shortly"
    if code is not None:
        return f"Could not download file (HTTP {code})"
    return "Could not download file — check sharing settings and try again"
