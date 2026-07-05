from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.errors import ServiceNotConfiguredError
from app.schemas.resume import ResumeProfile
from app.services import jobs


def test_fetch_jobs_missing_key_raises() -> None:
    profile = ResumeProfile(title="Engineer", skills=["Python"], location="Remote")
    with pytest.raises(ServiceNotConfiguredError) as exc:
        jobs.fetch_jobs(profile, db=None)  # type: ignore[arg-type]
    assert exc.value.error_code == "service_not_configured"
    assert "JOBS_API_KEY" in exc.value.message


def test_within_recency_excludes_undated_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    assert jobs._within_recency(None, cutoff) is False


def test_within_recency_accepts_recent_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    recent = datetime.now(timezone.utc) - timedelta(days=3)
    assert jobs._within_recency(recent, cutoff) is True


def test_within_recency_rejects_stale_jobs() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    stale = datetime.now(timezone.utc) - timedelta(days=30)
    assert jobs._within_recency(stale, cutoff) is False


def test_extract_skills_only_matches_profile_skills() -> None:
    description = "We need Python and PostgreSQL. Candidates should demonstrate Leadership and Ownership."
    profile = ResumeProfile(title="Engineer", skills=["Python", "Redis"], location="Remote")
    extracted = jobs._extract_skills(description, profile.skills)
    assert extracted == ["Python"]
    assert "Leadership" not in extracted
    assert "Ownership" not in extracted


def test_cache_jobs_upserts_existing_rows() -> None:
    db = MagicMock()
    existing = MagicMock()
    existing.job_id = "stable-job-id"
    existing.payload_json = None
    db.query.return_value.filter.return_value.one_or_none.return_value = existing

    from app.schemas.jobs import Job

    job = Job(
        id="new-uuid-should-not-win",
        source="jsearch",
        source_job_id="abc-123",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Python",
        apply_url="https://example.com/apply",
        skills=["Python"],
    )
    jobs._cache_jobs(db, [job])

    assert existing.job_id == "stable-job-id"
    assert existing.title == "Backend Engineer"
    db.add.assert_called_with(existing)
    db.commit.assert_called_once()


def test_cache_jobs_preserves_job_id_from_payload_when_column_empty() -> None:
    from app.schemas.jobs import Job

    db = MagicMock()
    existing = MagicMock()
    existing.job_id = None
    existing.payload_json = Job(
        id="payload-job-id",
        source="jsearch",
        source_job_id="abc-123",
        title="Old Title",
        company="Acme",
        location="Remote",
        description="Python",
        apply_url="https://example.com/apply",
        skills=["Python"],
    ).model_dump_json()
    db.query.return_value.filter.return_value.one_or_none.return_value = existing

    incoming = Job(
        id="incoming-new-id",
        source="jsearch",
        source_job_id="abc-123",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Python",
        apply_url="https://example.com/apply",
        skills=["Python"],
    )
    jobs._cache_jobs(db, [incoming])

    assert existing.job_id == "payload-job-id"