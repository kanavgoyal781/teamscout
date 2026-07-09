import hashlib
import uuid

from sqlalchemy.orm import Session

from app.db.models import JobCache
from app.errors import NotFoundError, ValidationError
from app.schemas.jobs import Job


def resolve_job(job_id: str, db: Session) -> Job:
    row = db.query(JobCache).filter(JobCache.job_id == job_id).one_or_none()
    if row is None or not row.payload_json:
        raise NotFoundError("job", job_id)
    return Job.model_validate_json(row.payload_json)


def cache_pasted_job(
    *,
    description: str,
    title: str = "",
    company: str = "",
    location: str = "",
    apply_url: str = "",
    db: Session,
) -> Job:
    """Persist a user-pasted JD as a JobCache row and return the Job.

    Used by library recommend-from-jd and jobs/from-text (team path) without JSearch.
    """
    desc = (description or "").strip()
    if len(desc) < 40:
        raise ValidationError(
            "Job description is too short — paste the full posting (at least ~40 characters)"
        )

    title_clean = (title or "").strip() or "Pasted job"
    company_clean = (company or "").strip() or "Unknown company"
    location_clean = (location or "").strip() or ""
    apply_clean = (apply_url or "").strip() or "https://www.linkedin.com/jobs/view/pasted"

    content_hash = hashlib.sha256(desc.encode("utf-8")).hexdigest()[:32]
    source_job_id = f"paste-{content_hash}"

    existing = (
        db.query(JobCache)
        .filter(JobCache.source == "paste", JobCache.source_job_id == source_job_id)
        .one_or_none()
    )
    if existing is not None and existing.payload_json:
        job = Job.model_validate_json(existing.payload_json)
        # Refresh title/company if user provided better metadata
        updated = job.model_copy(
            update={
                "title": title_clean,
                "company": company_clean,
                "location": location_clean,
                "description": desc,
                "apply_url": apply_clean if apply_url.strip() else job.apply_url,
            }
        )
        existing.title = updated.title
        existing.payload_json = updated.model_dump_json()
        if not existing.job_id:
            existing.job_id = updated.id
        db.add(existing)
        db.commit()
        return updated

    job = Job(
        id=str(uuid.uuid4()),
        source="paste",
        source_job_id=source_job_id,
        title=title_clean,
        company=company_clean,
        location=location_clean,
        description=desc,
        apply_url=apply_clean,
        posted_at=None,
        skills=[],
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
    return job
