"""Facet bucket labels — single source for FE/BE."""

from datetime import UTC, datetime, timedelta

from app.schemas.jobs import Job
from app.services import job_facets


def _job(**kw) -> Job:
    base = dict(
        id="1",
        source="t",
        source_job_id="1",
        title="Eng",
        company="Co",
        location="Remote",
        description="Python",
        apply_url="https://example.com",
        skills=[],
    )
    base.update(kw)
    return Job(**base)


def test_annotate_facet_buckets_matches_compute() -> None:
    now = datetime.now(UTC)
    jobs = [
        _job(id="a", salary_min=100_000, salary_unknown=False, posted_at=now - timedelta(hours=12)),
        _job(id="b", salary_unknown=True, posted_at=None),
    ]
    annotated = job_facets.annotate_facet_buckets(jobs, now=now)
    assert annotated[0].salary_bucket == "80k-120k"
    assert annotated[0].posted_age_bucket == "24h"
    assert annotated[1].salary_bucket == "unknown"
    assert annotated[1].posted_age_bucket == "unknown"
    facets = job_facets.compute_facets(annotated, now=now)
    assert any(b.value == "80k-120k" for b in facets.salary_bucket)
