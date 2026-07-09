import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.db.models import JobCache
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.schemas.jobs import Job
from app.schemas.library import IntentProfile
from app.schemas.resume import ResumeProfile

logger = get_logger(__name__)


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
    parts = [
        item.get("job_city"),
        item.get("job_state"),
        item.get("job_country"),
    ]
    return ", ".join(str(part).strip() for part in parts if part)


def extract_skills_from_description(description: str, profile_skills: list[str]) -> list[str]:
    """Return profile skills that appear as substrings in the job description."""
    if not description:
        return []
    lowered = description.lower()
    found: list[str] = []
    for skill in profile_skills:
        token = skill.strip()
        if token and token.lower() in lowered and token not in found:
            found.append(token)
    return found


def _cached_job_id(db: Session, source: str, source_job_id: str) -> str | None:
    existing = (
        db.query(JobCache)
        .filter(
            JobCache.source == source,
            JobCache.source_job_id == source_job_id,
        )
        .one_or_none()
    )
    if existing is None:
        return None
    if existing.job_id:
        return existing.job_id
    if existing.payload_json:
        return Job.model_validate_json(existing.payload_json).id
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

    return Job(
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


def _within_recency(posted_at: datetime | None, cutoff: datetime) -> bool:
    """Keep undated jobs (many free-board/JSearch rows lack dates); ranker penalizes them."""
    if posted_at is None:
        return True
    return posted_at >= cutoff


def _content_dedupe_key(job: Job) -> str:
    title = re.sub(r"\s+", " ", job.title.lower()).strip()
    company = re.sub(r"\s+", " ", job.company.lower()).strip()
    return f"{title}|{company}"


def _cache_jobs(db: Session, jobs: list[Job]) -> None:
    for job in jobs:
        existing = (
            db.query(JobCache)
            .filter(
                JobCache.source == job.source,
                JobCache.source_job_id == job.source_job_id,
            )
            .one_or_none()
        )
        if existing is not None:
            stable_id = existing.job_id
            if not stable_id and existing.payload_json:
                stable_id = Job.model_validate_json(existing.payload_json).id
            if stable_id:
                job = job.model_copy(update={"id": stable_id})
            existing.job_id = job.id
            existing.title = job.title
            existing.payload_json = job.model_dump_json()
            db.add(existing)
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
    db.commit()


def _jsearch_headers() -> dict[str, str]:
    return {
        "X-RapidAPI-Key": settings.JOBS_API_KEY or "",
        "X-RapidAPI-Host": settings.JOBS_API_HOST or "jsearch.p.rapidapi.com",
    }


def _jsearch_search_url() -> str:
    """RapidAPI JSearch deprecated /search; current path is /search-v2."""
    return f"{(settings.JOBS_API_BASE or 'https://jsearch.p.rapidapi.com').rstrip('/')}/search-v2"


def _extract_jsearch_items(payload: object) -> list[dict]:
    """Normalize search-v2 (and legacy) payloads to a list of job dicts.

    search-v2: { "data": { "jobs": [ ... ], "cursor": "..." }, ... }
    legacy:    { "data": [ ... ], ... }
    """
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
    """Diverse query set so one narrow string does not starve the candidate pool."""
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


def _jsearch_base_params() -> dict[str, str]:
    date_posted = "month" if settings.JOBS_RECENCY_DAYS > 7 else "week"
    # Broader than FULLTIME-only: contract/part-time often match tech seekers.
    return {
        "page": "1",
        "num_pages": "3",
        "date_posted": date_posted,
        "employment_types": "FULLTIME,CONTRACTOR,PARTTIME",
    }


def _fetch_jsearch_raw(queries: list[str], *, remote_only: bool = False) -> list[dict]:
    """Run multi-query JSearch and union by job_id."""
    merged: list[dict] = []
    seen_ids: set[str] = set()
    base = _jsearch_base_params()
    if remote_only:
        base = {**base, "remote_jobs_only": "true"}

    for query in queries:
        params = {**base, "query": query}
        try:
            items = _jsearch_get(params)
        except ServiceFailingError:
            # First query failure is fatal; subsequent are best-effort broadeners.
            if not merged:
                raise
            logger.warning("jobs.jsearch_query_failed", query=query)
            continue
        logger.info("jobs.jsearch_query", query=query, count=len(items))
        for item in items:
            sid = str(item.get("job_id") or item.get("job_google_link") or "")
            if sid and sid in seen_ids:
                continue
            if sid:
                seen_ids.add(sid)
            merged.append(item)
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


def _merge_fetch(
    profile: ResumeProfile,
    db: Session,
    *,
    queries: list[str],
    remote_only: bool = False,
) -> list[Job]:
    _require_jobs_config()
    from app.services import observability
    from app.services.job_boards import fetch_optional_boards

    with observability.traced_call("jsearch.search", model="jsearch") as trace:
        raw_items = _fetch_jsearch_raw(queries, remote_only=remote_only)

        jsearch_jobs: list[Job] = []
        for item in raw_items:
            source_job_id = str(item.get("job_id") or item.get("job_google_link") or "")
            cached_id = _cached_job_id(db, "jsearch", source_job_id) if source_job_id else None
            job = _normalize_job(item, profile, job_id=cached_id)
            if job is not None:
                jsearch_jobs.append(job)

        board_jobs: list[Job] = []
        if settings.JOBS_EXTRA_SOURCES_ENABLED:
            board_jobs = fetch_optional_boards(profile)
            board_jobs = _assign_stable_ids(db, board_jobs)

        # Prefer JSearch first (richer US coverage), then free boards.
        combined = jsearch_jobs + board_jobs
        cutoff = datetime.now(UTC) - timedelta(days=settings.JOBS_RECENCY_DAYS)
        jobs = _filter_and_cap(combined, cutoff=cutoff, limit=settings.JOBS_FETCH_TARGET)

        by_source: dict[str, int] = {}
        for job in jobs:
            by_source[job.source] = by_source.get(job.source, 0) + 1
        logger.info(
            "jobs.fetch_merged",
            jsearch_raw=len(raw_items),
            jsearch_kept=len(jsearch_jobs),
            boards=len(board_jobs),
            final=len(jobs),
            by_source=by_source,
        )

        if not jobs:
            raise ServiceFailingError(
                "Jobs API",
                f"no jobs matched filters in the last {settings.JOBS_RECENCY_DAYS} days",
            )

        trace.input_tokens = len(raw_items) + len(board_jobs)
        trace.output_tokens = len(jobs)
        _cache_jobs(db, jobs)
        return jobs


def fetch_jobs(profile: ResumeProfile, db: Session) -> list[Job]:
    title = profile.title.strip() or "software engineer"
    location = profile.location.strip() or "United States"
    queries = build_jsearch_queries(title, location, profile.skills)
    return _merge_fetch(profile, db, queries=queries)


def fetch_jobs_for_intent(intent: IntentProfile, db: Session) -> list[Job]:
    role = intent.role.strip() or "software engineer"
    loc = intent.location.strip() or "United States"
    queries = build_jsearch_queries(role, loc, skills=None)
    remote_only = intent.remote_preference == "remote"
    return _merge_fetch(
        intent.as_query_profile(),
        db,
        queries=queries,
        remote_only=remote_only,
    )
