from datetime import UTC, datetime

from app.core import workspace as ws_mod
from app.db.models import JobCache
from app.db.session import SessionLocal, init_db
from app.schemas.jobs import Job
from app.services.jobs_svc.store import resolve_job


def test_resolve_job_uses_indexed_job_id() -> None:
    init_db()
    db = SessionLocal()
    token = ws_mod._workspace_cv.set("ws-unit-resolve")
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
            posted_at=datetime.now(UTC),
            skills=["Python"],
        )
        db.add(
            JobCache(
                workspace_id="ws-unit-resolve",
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
        ws_mod._workspace_cv.reset(token)
        db.close()


def test_cache_pasted_job_persists_skills_and_dedupes() -> None:
    from app.services.jobs_svc.store import cache_pasted_job, resolve_job

    init_db()
    db = SessionLocal()
    token = ws_mod._workspace_cv.set("ws-unit-paste")
    try:
        desc = (
            "Requirements: Must have strong Python and Django experience. "
            "Preferred: PostgreSQL, Redis. Ability to work in a team environment."
        )
        first = cache_pasted_job(
            description=desc,
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            db=db,
        )
        assert first.source == "paste"
        assert first.id
        lowered = {s.lower() for s in first.skills}
        assert "python" in lowered
        resolved = resolve_job(first.id, db)
        assert resolved.id == first.id
        assert resolved.source == "paste"

        second = cache_pasted_job(
            description=desc,
            title="Backend Engineer II",
            company="Acme",
            location="Remote",
            db=db,
        )
        assert second.id == first.id
        assert second.title == "Backend Engineer II"
    finally:
        ws_mod._workspace_cv.reset(token)
        db.close()


def test_ingest_job_from_text_api(client) -> None:
    short = client.post("/jobs/from-text", json={"description": "too short"})
    assert short.status_code == 400

    desc = (
        "Requirements: Must have strong Python and Django experience. "
        "Preferred: PostgreSQL, Redis. Full posting for paste-team flow."
    )
    ok = client.post(
        "/jobs/from-text",
        json={
            "description": desc,
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Remote",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["job_id"]
    assert body["title"] == "Backend Engineer"
    assert body["company"] == "Acme"
    assert "Python" in body["description_preview"] or "python" in body["description_preview"].lower()

    again = client.post(
        "/jobs/from-text",
        json={"description": desc, "title": "Backend Engineer", "company": "Acme"},
    )
    assert again.status_code == 200
    assert again.json()["job_id"] == body["job_id"]
