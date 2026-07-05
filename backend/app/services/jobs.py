import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.models import JobCache
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.schemas.jobs import Job
from app.schemas.library import IntentProfile
from app.schemas.resume import ResumeProfile

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
        posted = posted.replace(tzinfo=timezone.utc)
    return posted.astimezone(timezone.utc)


def _location_from_item(item: dict) -> str:
    parts = [
        item.get("job_city"),
        item.get("job_state"),
        item.get("job_country"),
    ]
    return ", ".join(str(part).strip() for part in parts if part)


def _extract_skills(description: str, profile_skills: list[str]) -> list[str]:
    if not description:
        return []
    lowered = description.lower()
    found = []
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
        skills = _extract_skills(description, profile.skills)

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
    if posted_at is None:
        return False
    return posted_at >= cutoff


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


def fetch_jobs(profile: ResumeProfile, db: Session) -> list[Job]:
    _require_jobs_config()

    title = profile.title.strip() or "software engineer"
    location = profile.location.strip() or "United States"
    # Use title + location + at most top 2 distinguishing skills (no 8-skill concat)
    top_skills = " ".join(s for s in profile.skills[:2] if s.strip())
    query = f"{title} {top_skills} in {location}".strip()

    headers = {
        "X-RapidAPI-Key": settings.JOBS_API_KEY or "",
        "X-RapidAPI-Host": settings.JOBS_API_HOST,
    }
    # Align recency param with JOBS_RECENCY_DAYS (use month for 14d, week for <=7)
    date_posted = "month" if settings.JOBS_RECENCY_DAYS > 7 else "week"
    params = {
        "query": query,
        "page": "1",
        "num_pages": "5",
        "date_posted": date_posted,
        "employment_types": "FULLTIME",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                f"{settings.JOBS_API_BASE.rstrip('/')}/search",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Jobs API", str(exc)) from exc

    if not isinstance(payload, dict):
        raise ServiceFailingError("Jobs API", "unexpected response format")

    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raise ServiceFailingError("Jobs API", "missing data array")

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.JOBS_RECENCY_DAYS)
    jobs: list[Job] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        source_job_id = str(item.get("job_id") or item.get("job_google_link") or "")
        cached_id = _cached_job_id(db, "jsearch", source_job_id) if source_job_id else None
        job = _normalize_job(item, profile, job_id=cached_id)
        if job is None or job.source_job_id in seen:
            continue
        if not _within_recency(job.posted_at, cutoff):
            continue
        seen.add(job.source_job_id)
        jobs.append(job)
        if len(jobs) >= settings.JOBS_FETCH_TARGET:
            break

    if not jobs:
        raise ServiceFailingError("Jobs API", f"no jobs matched filters in the last {settings.JOBS_RECENCY_DAYS} days")

    _cache_jobs(db, jobs)
    return jobs


def fetch_jobs_for_intent(intent: IntentProfile, db: Session) -> list[Job]:
    _require_jobs_config()

    role = intent.role.strip() or "software engineer"
    loc = intent.location.strip() or "United States"
    # title + loc + <=2 skills style; keep remote handling
    query = f"{role} in {loc}".strip()
    headers = {
        "X-RapidAPI-Key": settings.JOBS_API_KEY or "",
        "X-RapidAPI-Host": settings.JOBS_API_HOST,
    }
    date_posted = "month" if settings.JOBS_RECENCY_DAYS > 7 else "week"
    params = {
        "query": query,
        "page": "1",
        "num_pages": "5",
        "date_posted": date_posted,
        "employment_types": "FULLTIME",
    }
    if intent.remote_preference == "remote":
        params["remote_jobs_only"] = "true"

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                f"{settings.JOBS_API_BASE.rstrip('/')}/search",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Jobs API", str(exc)) from exc

    if not isinstance(payload, dict):
        raise ServiceFailingError("Jobs API", "unexpected response format")

    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        raise ServiceFailingError("Jobs API", "missing data array")

    profile = intent.as_query_profile()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.JOBS_RECENCY_DAYS)
    jobs: list[Job] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        source_job_id = str(item.get("job_id") or item.get("job_google_link") or "")
        cached_id = _cached_job_id(db, "jsearch", source_job_id) if source_job_id else None
        job = _normalize_job(item, profile, job_id=cached_id)
        if job is None or job.source_job_id in seen:
            continue
        if not _within_recency(job.posted_at, cutoff):
            continue
        seen.add(job.source_job_id)
        jobs.append(job)
        if len(jobs) >= settings.JOBS_FETCH_TARGET:
            break

    if not jobs:
        raise ServiceFailingError("Jobs API", f"no jobs matched filters in the last {settings.JOBS_RECENCY_DAYS} days")

    _cache_jobs(db, jobs)
    return jobs