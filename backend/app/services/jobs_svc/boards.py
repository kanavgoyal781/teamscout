"""Optional free job boards (no API key). Best-effort enrichment only.
Failures are logged and swallowed so the required JSearch path remains the
source of truth for configured/failing honesty semantics.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile

logger = get_logger(__name__)
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "or",
        "the",
        "of",
        "in",
        "on",
        "at",
        "for",
        "to",
        "with",
        "jr",
        "sr",
        "senior",
        "junior",
        "lead",
        "staff",
        "principal",
        "i",
        "ii",
        "iii",
        "remote",
        "hybrid",
        "onsite",
        "full",
        "time",
        "part",
        "contract",
    }
)


def _tokens_from_profile(profile: ResumeProfile) -> list[str]:
    raw: list[str] = []
    if profile.title:
        raw.extend(re.findall(r"[a-zA-Z0-9+#.]{2,}", profile.title.lower()))
    for skill in profile.skills[:8]:
        token = skill.strip().lower()
        if token:
            raw.append(token)
    out: list[str] = []
    seen: set[str] = set()
    for token in raw:
        if token in _STOP or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _matches_profile(title: str, description: str, profile: ResumeProfile) -> bool:
    """Require at least one meaningful profile token in title or description."""
    tokens = _tokens_from_profile(profile)
    if not tokens:
        return True
    hay = f"{title}\n{description}".lower()
    # Prefer title hits; fall back to description skill hits.
    title_l = title.lower()
    for token in tokens:
        if len(token) >= 3 and token in title_l:
            return True
    for token in tokens[:6]:
        if len(token) >= 3 and token in hay:
            return True
    return False


def _parse_iso(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Remotive uses "2024-01-15T12:00:00"; Arbeitnow unix seconds sometimes.
    if text.isdigit():
        try:
            return datetime.fromtimestamp(int(text), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    normalized = text.replace("Z", "+00:00")
    try:
        posted = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    return posted.astimezone(UTC)


def _extract_skills(description: str, profile_skills: list[str]) -> list[str]:
    if not description:
        return []
    lowered = description.lower()
    found: list[str] = []
    for skill in profile_skills:
        token = skill.strip()
        if token and token.lower() in lowered and token not in found:
            found.append(token)
    return found


def _search_query(profile: ResumeProfile) -> str:
    title = profile.title.strip() or "software engineer"
    skill = next((s.strip() for s in profile.skills if s.strip()), "")
    return f"{title} {skill}".strip()


def fetch_remotive(profile: ResumeProfile, *, limit: int = 50) -> list[Job]:
    params = {"search": _search_query(profile), "limit": str(limit)}
    with httpx.Client(timeout=default_timeout()) as client:
        response = client.get(REMOTIVE_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    jobs_raw = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs_raw, list):
        return []
    out: list[Job] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            continue
        if not _matches_profile(title, description, profile):
            continue
        apply_url = str(item.get("url") or "").strip()
        if not apply_url:
            continue
        source_job_id = str(item.get("id") or apply_url)
        location = str(item.get("candidate_required_location") or "Remote").strip() or "Remote"
        skills = _extract_skills(description, profile.skills)
        tags = item.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                t = str(tag).strip()
                if t and t not in skills:
                    skills.append(t)
        out.append(
            Job(
                id="",  # filled by caller via uuid if empty cache
                source="remotive",
                source_job_id=source_job_id,
                title=title,
                company=str(item.get("company_name") or "Unknown").strip(),
                location=location,
                description=description,
                apply_url=apply_url,
                posted_at=_parse_iso(item.get("publication_date")),
                skills=skills,
            )
        )
    return out


def fetch_arbeitnow(profile: ResumeProfile, *, pages: int = 2) -> list[Job]:
    out: list[Job] = []
    with httpx.Client(timeout=default_timeout()) as client:
        for page in range(1, pages + 1):
            response = client.get(ARBEITNOW_URL, params={"page": str(page)})
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                break
            for item in data:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                description = str(item.get("description") or "").strip()
                if not title or not description:
                    continue
                if not _matches_profile(title, description, profile):
                    continue
                apply_url = str(item.get("url") or "").strip()
                if not apply_url:
                    continue
                source_job_id = str(item.get("slug") or apply_url)
                location = str(item.get("location") or "").strip()
                if item.get("remote") and "remote" not in location.lower():
                    location = f"{location}, Remote".strip(", ") if location else "Remote"
                tags_raw = item.get("tags")
                tags: list = tags_raw if isinstance(tags_raw, list) else []
                skills = [str(t).strip() for t in tags if str(t).strip()]
                if not skills:
                    skills = _extract_skills(description, profile.skills)
                out.append(
                    Job(
                        id="",
                        source="arbeitnow",
                        source_job_id=source_job_id,
                        title=title,
                        company=str(item.get("company_name") or "Unknown").strip(),
                        location=location or "Europe",
                        description=description,
                        apply_url=apply_url,
                        posted_at=_parse_iso(item.get("created_at")),
                        skills=skills,
                    )
                )
    return out


def fetch_optional_boards(profile: ResumeProfile) -> list[Job]:
    """Fetch free boards; never raise — optional enrichment only."""
    sources: list[tuple[str, Callable[[ResumeProfile], list[Job]]]] = [
        ("remotive", fetch_remotive),
        ("arbeitnow", fetch_arbeitnow),
    ]
    merged: list[Job] = []
    for name, fetcher in sources:
        try:
            batch = fetcher(profile)
            logger.info("jobs.optional_source", source=name, count=len(batch))
            merged.extend(batch)
        except httpx.HTTPError as exc:
            from app.core.redact import format_httpx_error

            logger.warning("jobs.optional_source_failed", source=name, error=format_httpx_error(exc))
        except (ValueError, TypeError, KeyError) as exc:
            from app.core.redact import redact_error

            logger.warning("jobs.optional_source_failed", source=name, error=redact_error(exc))
    return merged
