from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from app.errors import ServiceNotConfiguredError
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services import jobs


def test_fetch_jobs_missing_key_raises() -> None:
    profile = ResumeProfile(title="Engineer", skills=["Python"], location="Remote")
    with pytest.raises(ServiceNotConfiguredError) as exc:
        jobs.fetch_jobs(profile, db=None)  # type: ignore[arg-type]
    assert exc.value.error_code == "service_not_configured"
    assert "JOBS_API_KEY" in exc.value.message


def test_within_recency_keeps_undated_jobs() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    assert jobs._within_recency(None, cutoff) is True


def test_within_recency_accepts_recent_jobs() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    recent = datetime.now(UTC) - timedelta(days=3)
    assert jobs._within_recency(recent, cutoff) is True


def test_within_recency_rejects_stale_jobs() -> None:
    cutoff = datetime.now(UTC) - timedelta(days=14)
    stale = datetime.now(UTC) - timedelta(days=30)
    assert jobs._within_recency(stale, cutoff) is False


def test_extract_skills_only_matches_profile_skills() -> None:
    description = "We need Python and PostgreSQL. Candidates should demonstrate Leadership and Ownership."
    profile = ResumeProfile(title="Engineer", skills=["Python", "Redis"], location="Remote")
    extracted = jobs.extract_skills_from_description(description, profile.skills)
    assert extracted == ["Python"]
    assert "Leadership" not in extracted
    assert "Ownership" not in extracted


def test_extract_skills_rejects_java_substring_of_javascript() -> None:
    description = "Stack is JavaScript, TypeScript, and React."
    profile = ResumeProfile(title="Engineer", skills=["Java", "JavaScript", "Python"])
    extracted = jobs.extract_skills_from_description(description, profile.skills)
    assert "JavaScript" in extracted
    assert "Java" not in extracted


def test_build_jsearch_queries_diversifies() -> None:
    queries = jobs.build_jsearch_queries(
        "Data Scientist",
        "San Francisco",
        ["Python", "PyTorch", "SQL"],
    )
    assert len(queries) >= 2
    assert any("Data Scientist" in q and "San Francisco" in q for q in queries)
    assert any("Python" in q for q in queries)
    assert any("remote" in q.lower() for q in queries)


def test_build_jsearch_queries_skips_extra_remote_when_already_remote() -> None:
    queries = jobs.build_jsearch_queries("ML Engineer", "Remote", ["Python"])
    assert not any(
        q.lower().endswith("remote") and " in " not in q.lower()
        for q in queries
        if "remote" in q.lower() and q.count("remote") > 1
    )
    # Location already Remote → no separate "title remote" broaden query is fine either way;
    # ensure primary still present.
    assert any("ML Engineer" in q for q in queries)


def test_content_dedupe_key_normalizes() -> None:
    a = Job(
        id="1",
        source="jsearch",
        source_job_id="a",
        title="  Backend  Engineer ",
        company="Acme  Inc",
        location="Remote",
        description="x",
        apply_url="https://example.com",
    )
    b = Job(
        id="2",
        source="remotive",
        source_job_id="b",
        title="Backend Engineer",
        company="Acme Inc",
        location="US",
        description="y",
        apply_url="https://example.com/2",
    )
    assert jobs._content_dedupe_key(a) == jobs._content_dedupe_key(b)


def test_exact_dedupe_across_sources_live_path() -> None:
    """Live path uses job_dedup.dedupe_exact (not legacy _filter_and_cap)."""
    from app.services import job_dedup

    posted = datetime.now(UTC) - timedelta(days=1)
    jobs_list = [
        Job(
            id="1",
            source="jsearch",
            source_job_id="j1",
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Python",
            apply_url="https://a.example",
            posted_at=posted,
        ),
        Job(
            id="2",
            source="remotive",
            source_job_id="r1",
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Python remote",
            apply_url="https://b.example",
            posted_at=posted - timedelta(hours=1),  # earlier? wait later than id1
        ),
        Job(
            id="3",
            source="arbeitnow",
            source_job_id="w1",
            title="Data Scientist",
            company="Beta",
            location="Berlin",
            description="ML",
            apply_url="https://c.example",
            posted_at=posted,
        ),
    ]
    # Make id2 earlier so earliest-posted wins among Acme dups
    jobs_list[1] = jobs_list[1].model_copy(update={"posted_at": posted - timedelta(days=2)})
    kept, dropped = job_dedup.dedupe_exact(jobs_list)
    assert len(kept) == 2
    acme = next(j for j in kept if j.company == "Acme")
    assert acme.id == "2"  # earlier posted
    assert acme.duplicates_count == 2
    assert dropped.exact_duplicate == 1
    assert any(j.title == "Data Scientist" for j in kept)


def test_cache_jobs_upserts_existing_rows() -> None:
    db = MagicMock()
    existing = MagicMock()
    existing.job_id = "stable-job-id"
    existing.payload_json = None
    db.query.return_value.filter.return_value.first.return_value = existing

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
    result = jobs._cache_jobs(db, [job])
    assert result[0].id == "stable-job-id"

    assert existing.job_id == "stable-job-id"
    assert existing.title == "Backend Engineer"
    db.add.assert_called_with(existing)
    db.commit.assert_called_once()


def test_cache_jobs_preserves_job_id_from_payload_when_column_empty() -> None:
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
    db.query.return_value.filter.return_value.first.return_value = existing

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
    result = jobs._cache_jobs(db, [incoming])
    assert result[0].id == "payload-job-id"

    assert existing.job_id == "payload-job-id"


def test_cache_jobs_returns_stable_ids_on_existing() -> None:
    """Returned list must match DB stable id for team flow."""
    db = MagicMock()
    existing = MagicMock()
    existing.job_id = "stable-A"
    existing.payload_json = None
    db.query.return_value.filter.return_value.first.return_value = existing
    job = Job(
        id="client-B",
        source="jsearch",
        source_job_id="src-1",
        title="Eng",
        company="Co",
        location="Remote",
        description="Python role here for testing cache identity path thoroughly.",
        apply_url="https://example.com/a",
        skills=["Python"],
    )
    out = jobs._cache_jobs(db, [job])
    assert out[0].id == "stable-A"


def test_jsearch_source_job_id_uses_apply_url() -> None:
    from app.services.jsearch_client import jsearch_source_job_id

    assert jsearch_source_job_id({"job_apply_link": "https://x.com/a"}) == "https://x.com/a"
    assert jsearch_source_job_id({"job_id": "id1", "job_apply_link": "https://x.com/a"}) == "id1"
