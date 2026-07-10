"""JSearch HTTP client: query build + multi-query fetch."""
from __future__ import annotations
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from app.core.config import settings
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.errors import ServiceFailingError
logger = get_logger(__name__)
_JSEARCH_CONCURRENCY = 3
def jsearch_source_job_id(item: dict) -> str:
    """Stable vendor id: job_id → google_link → apply_link (never random UUID)."""
    for key in ("job_id", "job_google_link", "job_apply_link"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return ""
def _jsearch_headers() -> dict[str, str]:
    return {
        "X-RapidAPI-Key": settings.JOBS_API_KEY or "",
        "X-RapidAPI-Host": settings.JOBS_API_HOST or "jsearch.p.rapidapi.com",
    }
def _jsearch_search_url() -> str:
    return f"{(settings.JOBS_API_BASE or 'https://jsearch.p.rapidapi.com').rstrip('/')}/search-v2"
def _extract_jsearch_items(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise ServiceFailingError("Jobs API", "unexpected response format")
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        jobs = data.get("jobs")
        if isinstance(jobs, list):
            return [item for item in jobs if isinstance(item, dict)]
        for key in ("results", "job_results", "items"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    raise ServiceFailingError("Jobs API", "missing data.jobs array in search response")
def jsearch_get(params: dict[str, str]) -> list[dict]:
    import json as _json
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            response = client.get(_jsearch_search_url(), headers=_jsearch_headers(), params=params)
            response.raise_for_status()
            try:
                payload = response.json()
            except (_json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("jobs.jsearch_invalid_json", error=type(exc).__name__)
                raise ServiceFailingError("Jobs API", "upstream invalid JSON") from exc
    except ServiceFailingError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, OSError) as exc:
        logger.warning("jobs.jsearch_http_error", error=type(exc).__name__)
        raise ServiceFailingError("Jobs API", "upstream request failed") from exc
    return _extract_jsearch_items(payload)
def build_jsearch_queries(title: str, location: str, skills: list[str] | None = None) -> list[str]:
    role = (title or "").strip() or "software engineer"
    loc = (location or "").strip() or "United States"
    skill_bits = [s.strip() for s in (skills or []) if s and s.strip()][:2]
    queries: list[str] = []
    seen: set[str] = set()
    def add(q: str) -> None:
        cleaned = re.sub(r"\s+", " ", q).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            queries.append(cleaned)
    add(f"{role} in {loc}")
    if skill_bits:
        add(f"{role} {' '.join(skill_bits)}")
    loc_l = loc.lower()
    if "remote" not in loc_l and "remote" not in role.lower():
        add(f"{role} remote")
    if skill_bits:
        add(f"{' '.join(skill_bits)} {role} jobs")
    return queries[:4]
def fetch_jsearch_raw(queries: list[str], *, base_params: dict[str, str]) -> tuple[list[dict], int]:
    """Return (merged items, failed_query_count). Partial failures soft-fail."""
    merged: list[dict] = []
    seen_ids: set[str] = set()
    first_error: ServiceFailingError | None = None
    failed = 0
    def one(query: str) -> tuple[str, list[dict]]:
        return query, jsearch_get({**base_params, "query": query})
    with ThreadPoolExecutor(max_workers=_JSEARCH_CONCURRENCY) as pool:
        futures = [pool.submit(one, q) for q in queries]
        for fut in as_completed(futures):
            try:
                query, items = fut.result()
            except ServiceFailingError as exc:
                failed += 1
                if first_error is None:
                    first_error = exc
                logger.warning("jobs.jsearch_query_failed", error=str(exc))
                continue
            except (RuntimeError, OSError, TypeError, ValueError) as exc:
                failed += 1
                if first_error is None:
                    first_error = ServiceFailingError("Jobs API", "upstream request failed")
                logger.warning("jobs.jsearch_query_failed", error=type(exc).__name__)
                continue
            logger.info("jobs.jsearch_query", query=query, count=len(items))
            for item in items:
                sid = jsearch_source_job_id(item)
                if sid and sid in seen_ids:
                    continue
                if sid:
                    seen_ids.add(sid)
                merged.append(item)
    if not merged and first_error is not None:
        raise first_error
    return merged, failed
