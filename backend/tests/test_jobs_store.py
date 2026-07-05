from datetime import datetime, timezone

from app.db.models import JobCache
from app.db.session import SessionLocal, init_db
from app.schemas.jobs import Job
from app.services.jobs_store import resolve_job


def test_resolve_job_uses_indexed_job_id() -> None:
    init_db()
    db = SessionLocal()
    try:
        job = Job(
            id="indexed-job-1",
            source="fixture",
            source_job_id="fixture-indexed-1",
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Python",
            apply_url="https://example.com/apply",
            posted_at=datetime.now(timezone.utc),
            skills=["Python"],
        )
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

        resolved = resolve_job("indexed-job-1", db)
        assert resolved.id == "indexed-job-1"
        assert resolved.title == "Backend Engineer"
    finally:
        db.close()