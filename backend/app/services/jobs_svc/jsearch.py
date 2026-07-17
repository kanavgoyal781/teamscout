from __future__ import annotations
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import httpx
from app.core.config import settings
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.errors import ServiceFailingError
logger = get_logger(__name__)
_JSEARCH_CONCURRENCY = 3
JSEARCH_QUOTA_NOTICE = "JSearch monthly quota reached — continuing with free board sources"
class JSearchQuotaError(Exception):
    def __init__(self, notice: str = JSEARCH_QUOTA_NOTICE) -> None:
        self.notice = notice; super().__init__(notice)
def jsearch_source_job_id(item: dict) -> str:
    for key in ("job_id", "job_google_link", "job_apply_link"):
        text = str(item.get(key) or "").strip()
        if text: return text
    return ""
def _jsearch_headers() -> dict[str, str]:
    return {"X-RapidAPI-Key": settings.JOBS_API_KEY or "", "X-RapidAPI-Host": settings.JOBS_API_HOST or "jsearch.p.rapidapi.com"}
def _jsearch_search_url() -> str:
    return f"{(settings.JOBS_API_BASE or 'https://jsearch.p.rapidapi.com').rstrip('/')}/search-v2"
def _norm_query(q: str) -> str:
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", (q or "").lower())).strip()
def _near_dup(a: str, b: str) -> bool:
    if not a or not b or a == b: return a == b
    if a in b or b in a: return abs(len(a) - len(b)) <= max(6, int(0.25 * max(len(a), len(b))))
    wa, wb = set(a.split()), set(b.split())
    return bool(wa and wb) and len(wa & wb) / max(len(wa), len(wb)) >= 0.85
def dedupe_jsearch_queries(queries: list[str], *, max_n: int | None = None) -> list[str]:
    cap = max(1, int(settings.JSEARCH_MAX_REQUESTS_PER_SEARCH if max_n is None else max_n))
    out: list[str] = []; norms: list[str] = []
    for q in queries:
        cleaned = re.sub(r"\s+", " ", (q or "").strip())
        if not cleaned: continue
        key = _norm_query(cleaned)
        if not key or any(_near_dup(key, n) for n in norms): continue
        norms.append(key); out.append(cleaned)
        if len(out) >= cap: break
    return out
def _extract_jsearch_items(payload: object) -> list[dict]:
    if not isinstance(payload, dict): raise ServiceFailingError("Jobs API", "unexpected response format")
    data = payload.get("data")
    if isinstance(data, list): return [i for i in data if isinstance(i, dict)]
    if isinstance(data, dict):
        for key in ("jobs", "results", "job_results", "items"):
            nested = data.get(key) if key != "jobs" else data.get("jobs")
            if key == "jobs" and isinstance(nested, list): return [i for i in nested if isinstance(i, dict)]
            if key != "jobs" and isinstance(nested, list): return [i for i in nested if isinstance(i, dict)]
    raise ServiceFailingError("Jobs API", "missing data.jobs array in search response")
def _is_quota_response(status: int, body_text: str) -> bool:
    if status == 429: return True
    low = (body_text or "").lower()
    return status in {403, 402} and any(t in low for t in ("quota", "rate limit", "exceeded your monthly", "too many requests"))
def _with_cache_session(fn):
    from sqlalchemy.exc import SQLAlchemyError
    from app.db.session import SessionLocal
    session = SessionLocal()
    try:
        return fn(session)
    except (SQLAlchemyError, OSError, TypeError, ValueError, RuntimeError) as exc:
        logger.warning("jobs.jsearch_cache_failed", error=type(exc).__name__); return None
    finally:
        session.close()
def jsearch_get(params: dict[str, str], *, db=None) -> list[dict]:
    import json as _json
    from app.services.jobs_svc.sources.util import board_cache_get, board_cache_set
    _ = db
    slug = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:40]
    hit = _with_cache_session(lambda s: board_cache_get(s, "jsearch", slug))
    if isinstance(hit, list): return [x for x in hit if isinstance(x, dict)]
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            response = client.get(_jsearch_search_url(), headers=_jsearch_headers(), params=params)
            preview = (response.text or "")[:400]
            if _is_quota_response(response.status_code, preview): raise JSearchQuotaError()
            response.raise_for_status()
            try: payload = response.json()
            except (_json.JSONDecodeError, ValueError, TypeError) as exc:
                raise ServiceFailingError("Jobs API", "upstream invalid JSON") from exc
    except JSearchQuotaError: raise
    except ServiceFailingError: raise
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        preview = (exc.response.text if exc.response is not None else "")[:400]
        if _is_quota_response(status, preview): raise JSearchQuotaError() from exc
        raise ServiceFailingError("Jobs API", f"upstream HTTP {status}") from exc
    except (httpx.HTTPError, ValueError, TypeError, OSError) as exc:
        raise ServiceFailingError("Jobs API", "upstream request failed") from exc
    items = _extract_jsearch_items(payload)
    def _put_cache(s) -> None:
        board_cache_set(s, "jsearch", slug, items)
    _with_cache_session(_put_cache)
    return items
def build_jsearch_queries(title: str, location: str, skills: list[str] | None = None) -> list[str]:
    role = (title or "").strip() or "software engineer"
    loc = (location or "").strip() or "United States"
    skill_bits = [s.strip() for s in (skills or []) if s and s.strip()][:2]
    qs: list[str] = []; seen: set[str] = set()
    def add(q: str) -> None:
        c = re.sub(r"\s+", " ", q).strip(); k = c.lower()
        if c and k not in seen: seen.add(k); qs.append(c)
    add(f"{role} in {loc}")
    if skill_bits: add(f"{role} {' '.join(skill_bits)}")
    if "remote" not in loc.lower() and "remote" not in role.lower(): add(f"{role} remote")
    if skill_bits: add(f"{' '.join(skill_bits)} {role} jobs")
    return dedupe_jsearch_queries(qs)
def fetch_jsearch_raw(queries: list[str], *, base_params: dict[str, str], db=None) -> tuple[list[dict], int, int]:
    _ = db
    capped = dedupe_jsearch_queries(list(queries or ["software engineer"]))
    merged: list[dict] = []; seen_ids: set[str] = set(); first_error: Exception | None = None; failed = 0
    requests_made = len(capped)
    def one(query: str) -> tuple[str, list[dict]]:
        return query, jsearch_get({**base_params, "query": query}, db=None)
    with ThreadPoolExecutor(max_workers=min(_JSEARCH_CONCURRENCY, max(1, len(capped) or 1))) as pool:
        for fut in as_completed([pool.submit(one, q) for q in capped]):
            try: query, items = fut.result()
            except (JSearchQuotaError, ServiceFailingError) as exc:
                failed += 1; first_error = first_error or exc; continue
            except (RuntimeError, OSError, TypeError, ValueError):
                failed += 1; first_error = first_error or ServiceFailingError("Jobs API", "upstream request failed"); continue
            for item in items:
                sid = jsearch_source_job_id(item)
                if sid and sid in seen_ids: continue
                if sid: seen_ids.add(sid)
                merged.append(item)
    logger.info("jobs.jsearch_search_budget", requests=requests_made, failed=failed, items=len(merged))
    try:
        from app.services.ops.observability import record_trace
        record_trace(operation="jsearch.search", status="ok" if merged or first_error is None else "error",
            input_tokens=requests_made, output_tokens=len(merged),
            error_type=type(first_error).__name__ if first_error and not merged else None,
            prompt_name="jsearch_requests_per_search", prompt_version=str(requests_made))
    except (OSError, RuntimeError, TypeError, ValueError): pass
    if not merged and first_error is not None: raise first_error
    return merged, failed, requests_made
