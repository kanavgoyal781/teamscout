"""Enumerate enabled job sources and fetch in parallel with isolation."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.schemas.jobs import Job, SourceCounts
from app.services import observability
from app.services.jobs_svc.sources.base import FetchCriteria, JobSource, SourceFetchOutcome
from app.services.jobs_svc.sources.sources import (
    AdzunaSource, AshbySource, GreenhouseSource, JSearchSource, LeverSource,
    RemoteOKSource, RemotiveSource,
)
from app.services.jobs_svc.sources.util import filter_jobs
logger = get_logger(__name__)
_N = 4
def all_sources() -> list[JobSource]:
    return [JSearchSource(), GreenhouseSource(), LeverSource(), AshbySource(),
            RemotiveSource(), RemoteOKSource(), AdzunaSource()]
def enabled_sources(criteria: FetchCriteria) -> list[JobSource]:
    return [s for s in all_sources() if s.is_enabled_for(criteria)]
def source_health_status() -> dict[str, str]:
    from app.core.config import settings
    out: dict[str, str] = {}
    for src in all_sources():
        if src.name == "adzuna":
            out[src.name] = "configured" if src.is_configured() else "disabled"; continue
        if src.name == "jsearch":
            out[src.name] = "configured" if src.is_configured() else "missing"; continue
        en = bool(settings.JOBS_EXTRA_SOURCES_ENABLED)
        if src.name in {"greenhouse", "lever", "ashby"}:
            en = en and bool(settings.JOBS_SOURCE_ATS_ENABLED)
        elif src.name == "remotive":
            en = en and bool(settings.JOBS_SOURCE_REMOTIVE_ENABLED)
        elif src.name == "remoteok":
            en = en and bool(settings.JOBS_SOURCE_REMOTEOK_ENABLED)
        out[src.name] = "configured" if en and src.is_configured() else "disabled"
    return out
def _run_one(src: JobSource, criteria: FetchCriteria, db: Session | None) -> SourceFetchOutcome:
    counts = SourceCounts()
    with observability.traced_call(f"source.{src.name}", model=src.name) as trace:
        try:
            raw = src.fetch(criteria, db)
            counts.fetched = len(raw)
            jobs = filter_jobs(raw, criteria)
            counts.kept_after_filters = len(jobs)
            trace.input_tokens, trace.output_tokens = counts.fetched, counts.kept_after_filters
            return SourceFetchOutcome(name=src.name, jobs=jobs, counts=counts)
        except Exception as exc:  # isolate sources — never abort siblings
            from app.services.jobs_svc.jsearch import JSearchQuotaError, JSEARCH_QUOTA_NOTICE
            counts.errors = 1
            trace.status, trace.error_type = "error", type(exc).__name__
            if isinstance(exc, JSearchQuotaError) or JSEARCH_QUOTA_NOTICE in str(exc):
                msg = JSEARCH_QUOTA_NOTICE
            else:
                from app.core.redact import redact_error
                msg = redact_error(f"{type(exc).__name__}: {str(exc)[:140]}")
            logger.warning("jobs.source_failed", source=src.name, error=msg)
            return SourceFetchOutcome(name=src.name, counts=counts, error=msg)
def fetch_from_registry(criteria: FetchCriteria, db: Session | None = None
) -> tuple[list[Job], dict[str, SourceCounts], list[str]]:
    sources = enabled_sources(criteria)
    if not sources:
        return [], {}, ["no_enabled_sources"]
    outcomes: list[SourceFetchOutcome] = []
    with ThreadPoolExecutor(max_workers=_N) as pool:
        futs = [pool.submit(_run_one, s, criteria, db) for s in sources]
        for fut in as_completed(futs):
            try:
                outcomes.append(fut.result())
            except Exception as exc:  # defensive
                logger.warning("jobs.registry_future_failed", error=type(exc).__name__)
                outcomes.append(SourceFetchOutcome(
                    name="unknown", counts=SourceCounts(errors=1), error=type(exc).__name__))
    merged, per_source, errors = [], {}, []
    for oc in outcomes:
        per_source[oc.name] = oc.counts
        merged.extend(oc.jobs)
        if oc.error:
            errors.append(f"{oc.name}:{oc.error[:80]}")
    logger.info("jobs.registry_fetch", sources=[s.name for s in sources], total=len(merged),
                errors=len(errors), per_source={k: v.model_dump() for k, v in per_source.items()})
    return merged, per_source, errors
