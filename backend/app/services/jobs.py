"""JSearch multi-query fetch, normalize, filter, dedupe."""
from __future__ import annotations

import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.db.models import JobCache
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.schemas.jobs import DroppedCounts, Job, SearchParams
from app.schemas.library import IntentProfile
from app.schemas.resume import ResumeProfile
from app.services.job_dedup import dedupe_jobs, exact_dedupe_key
from app.services.job_filters import annotate_job, apply_hard_filters, jsearch_params_from_search

logger = get_logger(__name__)

_JSEARCH_CONCURRENCY = 3
@dataclass
class JobFetchResult:
    jobs: list[Job]
    dropped_counts: DroppedCounts = field(default_factory=DroppedCounts)
    queries: list[str] = field(default_factory=list)
def _require_jobs_config() -> None:
    if not is_set(settings.JOBS_API_KEY):
        raise ServiceNotConfiguredError("Jobs API", "JOBS_API_KEY")
    if not is_set(settings.JOBS_API_BASE):
        raise ServiceNotConfiguredError("Jobs API", "JOBS_API_BASE")
def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        posted = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    return posted.astimezone(UTC)
def _location_from_item(item: dict) -> str:
    parts = [item.get("job_city"), item.get("job_state"), item.get("job_country")]
    return ", ".join(str(part).strip() for part in parts if part)
def extract_skills_from_description(description: str, profile_skills: list[str]) -> list[str]:
    if not description:
        return []
    from app.services.ranking_math_align import phrase_in_text

    found: list[str] = []
    for skill in profile_skills:
        token = skill.strip()
        if token and phrase_in_text(token, description) and token not in found:
            found.append(token)
    return found
def _cached_job_id(db: Session, source: str, source_job_id: str) -> str | None:
    existing = (
        db.query(JobCache)
        .filter(JobCache.source == source, JobCache.source_job_id == source_job_id)
        .one_or_none()
    )
    if existing is None:
        return None
    if existing.job_id:
        return existing.job_id
    if existing.payload_json:
        return Job.model_validate_json(existing.payload_json).id
    return None
def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
def _normalize_job(item: dict, profile: ResumeProfile, *, job_id: str | None = None) -> Job | None:
    title = (item.get("job_title") or "").strip()
    description = (item.get("job_description") or "").strip()
    if not title or not description:
        return None

    source_job_id = str(item.get("job_id") or item.get("job_google_link") or uuid.uuid4())
    apply_url = item.get("job_apply_link") or item.get("job_google_link") or ""
    apply_url = str(apply_url).strip()
    if not apply_url:
        return None

    posted_at = _parse_posted_at(item.get("job_posted_at_datetime_utc"))
    skills = item.get("job_required_skills") or item.get("job_highlights", {}).get("Qualifications", [])
    if not isinstance(skills, list):
        skills = []
    skills = [str(skill).strip() for skill in skills if str(skill).strip()]
    if not skills:
        skills = extract_skills_from_description(description, profile.skills)

    is_remote = item.get("job_is_remote")
    if isinstance(is_remote, str):
        is_remote = is_remote.strip().lower() in {"1", "true", "yes"}
    elif not isinstance(is_remote, bool):
        is_remote = None

    job = Job(
        id=job_id or str(uuid.uuid4()),
        source="jsearch",
        source_job_id=source_job_id,
        title=title,
        company=str(item.get("employer_name") or "Unknown").strip(),
        location=_location_from_item(item),
        description=description,
        apply_url=apply_url,
        posted_at=posted_at,
        skills=skills,
    )
    return annotate_job(
        job,
        is_remote_flag=is_remote,
        structured_employment=item.get("job_employment_type"),
        structured_salary_min=_float_or_none(item.get("job_min_salary")),
        structured_salary_max=_float_or_none(item.get("job_max_salary")),
    )
def _within_recency(posted_at: datetime | None, cutoff: datetime) -> bool:
    if posted_at is None:
        return True
    return posted_at >= cutoff
def _content_dedupe_key(job: Job) -> str:
    return exact_dedupe_key(job)
def _cache_jobs(db: Session, jobs: list[Job]) -> list[Job]:
    out: list[Job] = []
    for job in jobs:
        existing = (
            db.query(JobCache)
            .filter(JobCache.source == job.source, JobCache.source_job_id == job.source_job_id)
            .first()
        )
        if existing is not None:
            stable_id = existing.job_id if isinstance(getattr(existing, "job_id", None), str) else None
            if not stable_id and existing.payload_json:
                try:
                    stable_id = Job.model_validate_json(existing.payload_json).id
                except (TypeError, ValueError):
                    stable_id = None
            if isinstance(stable_id, str) and stable_id:
                job = job.model_copy(update={"id": stable_id})
            existing.job_id = job.id
            existing.title = job.title
            existing.payload_json = job.model_dump_json()
            db.add(existing)
            out.append(job)
            continue
        db.add(
            JobCache(
                job_id=job.id,
                source=job.source,
                source_job_id=job.source_job_id,
                title=job.title,
                payload_json=job.model_dump_json(),
            )
        )
        out.append(job)
    db.commit()
    return out
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
def _jsearch_get(params: dict[str, str]) -> list[dict]:
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            response = client.get(
                _jsearch_search_url(),
                headers=_jsearch_headers(),
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Jobs API", str(exc)) from exc
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
def fetch_jsearch_raw(queries: list[str], *, base_params: dict[str, str]) -> list[dict]:
    merged: list[dict] = []
    seen_ids: set[str] = set()
    first_error: ServiceFailingError | None = None

    def one(query: str) -> tuple[str, list[dict]]:
        return query, _jsearch_get({**base_params, "query": query})

    with ThreadPoolExecutor(max_workers=_JSEARCH_CONCURRENCY) as pool:
        futures = [pool.submit(one, q) for q in queries]
        for fut in as_completed(futures):
            try:
                query, items = fut.result()
            except ServiceFailingError as exc:
                if first_error is None:
                    first_error = exc
                logger.warning("jobs.jsearch_query_failed", error=str(exc))
                continue
            logger.info("jobs.jsearch_query", query=query, count=len(items))
            for item in items:
                sid = str(item.get("job_id") or item.get("job_google_link") or "")
                if sid and sid in seen_ids:
                    continue
                if sid:
                    seen_ids.add(sid)
                merged.append(item)

    if not merged and first_error is not None:
        raise first_error
    return merged
def _assign_stable_ids(db: Session, jobs: list[Job]) -> list[Job]:
    assigned: list[Job] = []
    for job in jobs:
        cached = _cached_job_id(db, job.source, job.source_job_id)
        job_id = cached or (job.id if job.id else str(uuid.uuid4()))
        if not job_id:
            job_id = str(uuid.uuid4())
        assigned.append(job.model_copy(update={"id": job_id}))
    return assigned
def _filter_and_cap(jobs: list[Job], *, cutoff: datetime, limit: int) -> list[Job]:
    out: list[Job] = []
    seen_source: set[tuple[str, str]] = set()
    seen_content: set[str] = set()
    for job in jobs:
        key = (job.source, job.source_job_id)
        if key in seen_source:
            continue
        content = _content_dedupe_key(job)
        if content in seen_content:
            continue
        if not _within_recency(job.posted_at, cutoff):
            continue
        seen_source.add(key)
        seen_content.add(content)
        out.append(job)
        if len(out) >= limit:
            break
    return out
def _normalize_raw_items(
    raw_items: list[dict],
    profile: ResumeProfile,
    db: Session,
) -> tuple[list[Job], DroppedCounts]:
    dropped = DroppedCounts()
    jobs: list[Job] = []
    for item in raw_items:
        title = (item.get("job_title") or "").strip()
        description = (item.get("job_description") or "").strip()
        if not title or not description:
            dropped.missing_title_or_description += 1
            continue
        apply_url = str(item.get("job_apply_link") or item.get("job_google_link") or "").strip()
        if not apply_url:
            dropped.missing_apply_url += 1
            continue
        source_job_id = str(item.get("job_id") or item.get("job_google_link") or "")
        cached_id = _cached_job_id(db, "jsearch", source_job_id) if source_job_id else None
        job = _normalize_job(item, profile, job_id=cached_id)
        if job is None:
            dropped.missing_title_or_description += 1
            continue
        jobs.append(job)
    return jobs, dropped
def _merge_fetch(
    profile: ResumeProfile,
    db: Session,
    *,
    queries: list[str],
    params: SearchParams | None = None,
    remote_only: bool = False,
) -> JobFetchResult:
    _require_jobs_config()
    from app.services import observability
    from app.services.job_boards import fetch_optional_boards

    params = params or SearchParams()
    base = jsearch_params_from_search(params)
    if remote_only:
        base = {**base, "remote_jobs_only": "true"}

    dropped = DroppedCounts()

    with observability.traced_call("jsearch.search", model="jsearch") as trace:
        raw_items = fetch_jsearch_raw(queries, base_params=base)
        if isinstance(raw_items, tuple):
            raw_items = raw_items[0]
        jsearch_jobs, norm_dropped = _normalize_raw_items(raw_items, profile, db)
        dropped = dropped.merge(norm_dropped)

        board_jobs: list[Job] = []
        if settings.JOBS_EXTRA_SOURCES_ENABLED:
            board_jobs = fetch_optional_boards(profile)
            board_jobs = _assign_stable_ids(db, board_jobs)
            board_jobs = [annotate_job(j) for j in board_jobs]

        combined = jsearch_jobs + board_jobs
        filtered, hard_dropped = apply_hard_filters(combined, params)
        dropped = dropped.merge(hard_dropped)

        from app.core.env_utils import is_set as _is_set
        from app.services.embeddings import embeddings_endpoint

        use_emb = _is_set(settings.EMBEDDINGS_API_KEY) and bool(embeddings_endpoint())
        deduped, dedup_dropped = dedupe_jobs(filtered, use_embeddings=use_emb)
        dropped = dropped.merge(dedup_dropped)

        def sort_key(j: Job) -> tuple:
            ts = j.posted_at.timestamp() if j.posted_at else 0.0
            return (-ts, j.title)

        deduped = sorted(deduped, key=sort_key)[: settings.JOBS_FETCH_TARGET]

        by_source: dict[str, int] = {}
        for job in deduped:
            by_source[job.source] = by_source.get(job.source, 0) + 1
        logger.info(
            "jobs.fetch_merged",
            jsearch_raw=len(raw_items),
            jsearch_kept=len(jsearch_jobs),
            boards=len(board_jobs),
            final=len(deduped),
            by_source=by_source,
            dropped=dropped.as_dict(),
            queries=queries,
        )

        if not deduped:
            raise ServiceFailingError(
                "Jobs API",
                f"no jobs matched filters (date_window={params.date_window})",
            )

        trace.input_tokens = len(raw_items) + len(board_jobs)
        trace.output_tokens = len(deduped)
        _cache_jobs(db, deduped)
        return JobFetchResult(jobs=deduped, dropped_counts=dropped, queries=list(queries))
def resolve_search_queries(
    profile: ResumeProfile,
    db: Session,
    *,
    params: SearchParams | None = None,
) -> list[str]:
    params = params or SearchParams()
    if params.use_expand:
        from app.services.query_expand import expand_queries

        return expand_queries(profile, db, params=params)
    return build_jsearch_queries(profile.title, profile.location, profile.skills)
def fetch_jobs(
    profile: ResumeProfile,
    db: Session,
    *,
    params: SearchParams | None = None,
) -> list[Job]:
    return fetch_jobs_detailed(profile, db, params=params).jobs
def fetch_jobs_detailed(
    profile: ResumeProfile,
    db: Session,
    *,
    params: SearchParams | None = None,
) -> JobFetchResult:
    params = params or SearchParams()
    _require_jobs_config()  # fail-loud before spending LLM expand credits
    queries = resolve_search_queries(profile, db, params=params)
    return _merge_fetch(profile, db, queries=queries, params=params)
def fetch_jobs_for_intent(intent: IntentProfile, db: Session) -> list[Job]:
    role = intent.role.strip() or "software engineer"
    loc = intent.location.strip() or "United States"
    queries = build_jsearch_queries(role, loc, skills=None)
    remote_only = intent.remote_preference == "remote"
    pref = intent.remote_preference
    rmode = pref if pref in {"remote", "hybrid", "onsite", "any"} else "any"
    params = SearchParams(remote_mode=rmode, use_expand=False)  # type: ignore[arg-type]
    return _merge_fetch(
        intent.as_query_profile(),
        db,
        queries=queries,
        params=params,
        remote_only=remote_only,
    ).jobs
