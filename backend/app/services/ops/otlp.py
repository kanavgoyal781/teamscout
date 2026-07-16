"""Best-effort OTLP/HTTP export for traces (never breaks request path)."""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger

logger = get_logger(__name__)


def maybe_export_otlp(*, operation: str, status: str, request_id: str) -> None:
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if not is_set(endpoint):
        return
    url = (endpoint or "").rstrip("/")
    if not url.endswith("/v1/traces"):
        url = f"{url}/v1/traces"
    body = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": operation,
                                "attributes": [
                                    {
                                        "key": "teamscout.operation",
                                        "value": {"stringValue": operation},
                                    },
                                    {
                                        "key": "teamscout.status",
                                        "value": {"stringValue": status},
                                    },
                                    {
                                        "key": "teamscout.request_id",
                                        "value": {"stringValue": request_id},
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            client.post(url, json=body, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        logger.warning("otlp.export_failed", error=str(exc), host=urlparse(url).netloc)
