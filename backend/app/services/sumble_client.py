from __future__ import annotations
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse
import httpx
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.errors import ServiceFailingError, ServiceNotConfiguredError
logger = get_logger(__name__)
EMAIL_REVEAL_COST = 10
DEFAULT_LIMIT = 10
@dataclass(frozen=True)
class SumbleOrganization:
    organization_id: int
    name: str | None
@dataclass(frozen=True)
class SumblePerson:
    person_id: int
    name: str | None
    title: str | None
    team: str | None
    seniority: str | None
    job_function: str | None
def require_sumble_config() -> None:
    if not is_set(settings.SUMBLE_API_KEY):
        raise ServiceNotConfiguredError("Hiring team lookup", "SUMBLE_API_KEY")
def redact_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
def auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.SUMBLE_API_KEY}",
        "Content-Type": "application/json",
    }
def post(
    path: str,
    payload: dict[str, Any],
    *,
    credit_costing: bool = False,
    operation: str | None = None,
) -> dict[str, Any]:
    from app.services import observability
    require_sumble_config()
    url = f"{settings.SUMBLE_BASE_URL.rstrip('/')}{path}"
    op = operation or observability.sumble_operation_from_path(path)
    if credit_costing:
        logger.info("sumble.credit_call", method="POST", url=redact_url(url))
    with observability.traced_call(
        op,
        check_sumble_ceiling=True,
        estimated_credits=EMAIL_REVEAL_COST if credit_costing else 1,
    ) as trace:
        try:
            with httpx.Client(timeout=default_timeout()) as client:
                response = client.post(url, headers=auth_headers(), json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            raise ServiceFailingError(
                "Hiring team lookup", f"HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceFailingError("Hiring team lookup", str(exc)) from exc
        if not isinstance(data, dict):
            raise ServiceFailingError("Hiring team lookup", "unexpected response format")
        credits = data.get("credits_used")
        if credits is not None:
            try:
                trace.credits_used = int(credits)
            except (TypeError, ValueError):
                trace.credits_used = 0
        elif credit_costing:
            trace.credits_used = EMAIL_REVEAL_COST
        else:
            trace.credits_used = 0
        if credit_costing:
            logger.info(
                "sumble.credit_result",
                credits_used=data.get("credits_used"),
                credits_remaining=data.get("credits_remaining"),
            )
        return data
def escape_query_value(value: str) -> str:
    return value.replace("'", "\\'")
def title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
