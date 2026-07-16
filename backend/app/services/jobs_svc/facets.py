"""Facet aggregation over a job pool (for client-side filtering)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from app.schemas.jobs import FacetBucket, Job, JobFacets


def _salary_bucket(job: Job) -> str:
    if job.salary_unknown or job.salary_min is None:
        return "unknown"
    annual = job.salary_min
    if annual < 80_000:
        return "<80k"
    if annual < 120_000:
        return "80k-120k"
    if annual < 160_000:
        return "120k-160k"
    if annual < 200_000:
        return "160k-200k"
    return "200k+"


def _posted_age_bucket(job: Job, *, now: datetime | None = None) -> str:
    if job.posted_at is None:
        return "unknown"
    now = now or datetime.now(UTC)
    posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
    age_days = max((now.astimezone(UTC) - posted.astimezone(UTC)).total_seconds() / 86400.0, 0.0)
    if age_days < 1:
        return "24h"
    if age_days < 3:
        return "3d"
    if age_days < 7:
        return "7d"
    if age_days < 14:
        return "14d"
    if age_days < 30:
        return "30d"
    return "30d+"


def _to_buckets(counter: Counter[str], *, limit: int = 30) -> list[FacetBucket]:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [FacetBucket(value=k, count=v) for k, v in items[:limit]]


def annotate_facet_buckets(jobs: list[Job], *, now: datetime | None = None) -> list[Job]:
    """Write salary_bucket / posted_age_bucket onto each job (FE filters by these)."""
    now = now or datetime.now(UTC)
    out: list[Job] = []
    for job in jobs:
        out.append(
            job.model_copy(
                update={
                    "salary_bucket": _salary_bucket(job),
                    "posted_age_bucket": _posted_age_bucket(job, now=now),
                }
            )
        )
    return out


def compute_facets(jobs: list[Job], *, now: datetime | None = None) -> JobFacets:
    companies: Counter[str] = Counter()
    seniorities: Counter[str] = Counter()
    remotes: Counter[str] = Counter()
    salaries: Counter[str] = Counter()
    ages: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    for job in jobs:
        companies[job.company or "Unknown"] += 1
        seniorities[job.seniority or "unknown"] += 1
        remotes[job.remote_mode or "unknown"] += 1
        salaries[_salary_bucket(job)] += 1
        ages[_posted_age_bucket(job, now=now)] += 1
        sources[job.source or "unknown"] += 1
    return JobFacets(
        company=_to_buckets(companies),
        seniority=_to_buckets(seniorities),
        remote_mode=_to_buckets(remotes),
        salary_bucket=_to_buckets(salaries),
        posted_age=_to_buckets(ages),
        source=_to_buckets(sources),
    )
