from sqlalchemy.orm import Session

from app.db.models import JobCache
from app.errors import NotFoundError
from app.schemas.jobs import Job


def resolve_job(job_id: str, db: Session) -> Job:
    row = db.query(JobCache).filter(JobCache.job_id == job_id).one_or_none()
    if row is None or not row.payload_json:
        raise NotFoundError("job", job_id)
    return Job.model_validate_json(row.payload_json)