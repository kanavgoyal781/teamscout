from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.logging import get_logger
from app.core.workspace import workspace_or_system
from app.db.models import JobCache
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.schemas.jobs import DroppedCounts, Job, SearchParams, SourceCounts
from app.schemas.library import IntentProfile
from app.schemas.resume import ResumeProfile
from app.services.jobs_svc.dedup import dedupe_jobs, exact_dedupe_key
from app.services.jobs_svc.filters import annotate_job, apply_hard_filters
from app.services.jobs_svc.jsearch import build_jsearch_queries
logger = get_logger(__name__)
@dataclass
class JobFetchResult:
    jobs: list[Job]
    dropped_counts: DroppedCounts = field(default_factory=DroppedCounts)
    queries: list[str] = field(default_factory=list)
    per_source_counts: dict[str, SourceCounts] = field(default_factory=dict)
    source_errors: list[str] = field(default_factory=list)
    pool_notices: list[str] = field(default_factory=list)
    pool_empty_reason: str | None = None  # filters | partial_sources when empty
def _require_jobs_config() -> None:
    if not is_set(settings.JOBS_API_KEY):
        raise ServiceNotConfiguredError("Jobs API", "JOBS_API_KEY")
    if not is_set(settings.JOBS_API_BASE):
        raise ServiceNotConfiguredError("Jobs API", "JOBS_API_BASE")
def extract_skills_from_description(description: str, profile_skills: list[str]) -> list[str]:
    if not description:
        return []
    from app.services.ranking.math_align import phrase_in_text
    found: list[str] = []
    for skill in profile_skills:
        token = skill.strip()
        if token and phrase_in_text(token, description) and token not in found:
            found.append(token)
    return found
def _cached_job_id(db: Session, source: str, source_job_id: str) -> str | None:
    wid = workspace_or_system()
    existing = (
        db.query(JobCache)
        .filter(JobCache.workspace_id == wid, JobCache.source == source, JobCache.source_job_id == source_job_id)
        .one_or_none()
    )
    if existing is None:
        return None
    if existing.job_id:
        return existing.job_id
    if existing.payload_json:
        return Job.model_validate_json(existing.payload_json).id
    return None
def _cache_jobs(db: Session, jobs: list[Job]) -> list[Job]:
    out: list[Job] = []
    wid = workspace_or_system()
    for job in jobs:
        existing = (
            db.query(JobCache)
            .filter(JobCache.workspace_id == wid, JobCache.source == job.source, JobCache.source_job_id == job.source_job_id)
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
                workspace_id=wid, job_id=job.id, source=job.source, source_job_id=job.source_job_id,
                title=job.title, payload_json=job.model_dump_json(),
            )
        )
        out.append(job)
    db.commit()
    return out
def _assign_stable_ids(db: Session, jobs: list[Job]) -> list[Job]:
    assigned: list[Job] = []
    for job in jobs:
        cached = _cached_job_id(db, job.source, job.source_job_id)
        job_id = cached or job.id or str(uuid.uuid4())
        assigned.append(job.model_copy(update={"id": job_id}))
    return assigned
def _within_recency(posted_at: datetime | None, cutoff: datetime) -> bool:
    if posted_at is None:
        return True
    return posted_at >= cutoff
def _content_dedupe_key(job: Job) -> str:
    return exact_dedupe_key(job)
def resolve_search_queries(
    profile: ResumeProfile, db: Session, *, params: SearchParams | None = None,
) -> list[str]:
    params = params or SearchParams()
    if params.use_expand:
        from app.services.ranking.query_expand import expand_queries
        return expand_queries(profile, db, params=params)
    return build_jsearch_queries(profile.title, profile.location, profile.skills)
def _mark_deduped(per_source: dict[str, SourceCounts], before: list[Job], after: list[Job]) -> None:
    kept_ids = {j.id for j in after}
    for job in before:
        if job.id not in kept_ids:
            sc = per_source.setdefault(job.source, SourceCounts())
            sc.deduped_away += 1
def _source_name(err: str) -> str:
    return err.split(":", 1)[0].strip() if ":" in err else err.strip()
def all_enabled_sources_errored(per_source: dict[str, SourceCounts], source_errors: list[str]) -> bool:
    if not per_source: return bool(source_errors)
    if not source_errors or any(sc.fetched > 0 for sc in per_source.values()): return False
    return all(sc.errors > 0 for sc in per_source.values())
def format_all_sources_failed_message(source_errors: list[str]) -> str:
    names = sorted({_source_name(e) for e in source_errors if e})
    return f"All job sources failed ({', '.join(names) if names else 'unknown'})."
def build_pool_notices(*, params: SearchParams, per_source: dict[str, SourceCounts], source_errors: list[str], empty: bool) -> tuple[list[str], str | None]:
    from app.services.jobs_svc.jsearch import JSEARCH_QUOTA_NOTICE
    notices: list[str] = []
    empty_reason: str | None = None
    for err in source_errors:
        if JSEARCH_QUOTA_NOTICE in err or "quota" in err.lower():
            if JSEARCH_QUOTA_NOTICE not in notices: notices.append(JSEARCH_QUOTA_NOTICE)
        else:
            src = _source_name(err)
            line = f"{src} failed — results may be partial."
            if src and line not in notices: notices.append(line)
    if empty:
        short = params.date_window in {"day", "3days"}
        if source_errors and not all_enabled_sources_errored(per_source, source_errors):
            empty_reason = "partial_sources"
            notices.append("No postings kept for this window — try widening Posted within (week or month)." if short else "Sources ran but no jobs were kept after filters — try loosening hard filters.")
        else:
            empty_reason = "filters"
            notices.append("No jobs matched this date window — try widening Posted within (week or month)." if short else "No jobs matched your filters — try refining title, skills, or location.")
        for name, sc in sorted(per_source.items()):
            notices.append(f"{name}: fetched={sc.fetched} kept={sc.kept_after_filters} errors={sc.errors}")
    return notices, empty_reason
def _merge_fetch(
    profile: ResumeProfile, db: Session, *, queries: list[str],
    params: SearchParams | None = None, remote_only: bool = False,
) -> JobFetchResult:
    from app.services.jobs_svc.sources import FetchCriteria, fetch_from_registry
    params = params or SearchParams()
    if remote_only and params.remote_mode == "any":
        params = params.model_copy(update={"remote_mode": "remote", "remote_mode_pref": "hard"})
    criteria = FetchCriteria(profile=profile, params=params, queries=list(queries))
    raw_jobs, per_source, source_errors = fetch_from_registry(criteria, db)
    dropped = DroppedCounts()
    complete: list[Job] = []
    for job in raw_jobs:
        if not job.title or not job.description:
            dropped.missing_title_or_description += 1
            continue
        if not job.apply_url:
            dropped.missing_apply_url += 1
            continue
        complete.append(annotate_job(job) if not job.remote_mode else job)
    complete = _assign_stable_ids(db, complete)
    filtered, hard_dropped = apply_hard_filters(complete, params)
    dropped = dropped.merge(hard_dropped)
    for src, sc in per_source.items():
        kept_n = sum(1 for j in filtered if j.source == src)
        sc.kept_after_filters = kept_n
    from app.services.inference.embeddings import embeddings_endpoint
    use_emb = is_set(settings.EMBEDDINGS_API_KEY) and bool(embeddings_endpoint())
    pre_dedup = list(filtered)
    deduped, dedup_dropped = dedupe_jobs(filtered, use_embeddings=use_emb)
    dropped = dropped.merge(dedup_dropped)
    _mark_deduped(per_source, pre_dedup, deduped)
    def sort_key(j: Job) -> tuple:
        ts = j.posted_at.timestamp() if j.posted_at else 0.0
        return (-ts, j.title)
    capped = sorted(deduped, key=sort_key)[: settings.JOBS_FETCH_TARGET]
    if len(deduped) > len(capped):
        dropped.fetch_cap += len(deduped) - len(capped)
    logger.info("jobs.fetch_merged", final=len(capped), sources=list(per_source.keys()), dropped=dropped.as_dict(), errors=len(source_errors))
    if not capped and all_enabled_sources_errored(per_source, source_errors):
        raise ServiceFailingError("Jobs API", format_all_sources_failed_message(source_errors))
    notices, empty_reason = build_pool_notices(
        params=params, per_source=per_source, source_errors=source_errors, empty=not capped,
    )
    if capped:
        _cache_jobs(db, capped)
        notices = [
            n for n in notices
            if "quota" in n.lower() or "failed" in n.lower() or "partial" in n.lower()
        ]
        empty_reason = None
    return JobFetchResult(
        jobs=capped, dropped_counts=dropped, queries=list(queries),
        per_source_counts=per_source, source_errors=source_errors,
        pool_notices=notices, pool_empty_reason=empty_reason,
    )
def fetch_jobs(
    profile: ResumeProfile, db: Session, *, params: SearchParams | None = None,
) -> list[Job]:
    return fetch_jobs_detailed(profile, db, params=params).jobs
def fetch_jobs_detailed(
    profile: ResumeProfile, db: Session, *, params: SearchParams | None = None,
) -> JobFetchResult:
    params = params or SearchParams()
    _require_jobs_config()
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
        intent.as_query_profile(), db, queries=queries, params=params, remote_only=remote_only,
    ).jobs

