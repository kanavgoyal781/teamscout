import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Resume, Search
from app.db.session import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.jobs import RankedJob
from app.schemas.resume import ResumeProfile
from app.services import jobs, ranking

router = APIRouter(prefix="/searches", tags=["searches"])


class SearchRequest(BaseModel):
    resume_id: str


class SearchResponse(BaseModel):
    search_id: str
    resume_id: str
    results: list[RankedJob] = Field(default_factory=list)


@router.post("", response_model=SearchResponse)
def create_search(payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    row = db.query(Resume).filter(Resume.id == payload.resume_id).one_or_none()
    if row is None:
        raise NotFoundError("resume", payload.resume_id)

    if not row.confirmed:
        raise ValidationError("Resume must be confirmed before search — call PUT /resumes/{id}/confirm")

    profile = ResumeProfile.model_validate_json(row.parsed_json or "{}")
    if not profile.title.strip():
        raise ValidationError("Resume title is required before search")
    if not profile.skills:
        raise ValidationError("At least one skill is required before search")

    fetched_jobs = jobs.fetch_jobs(profile, db)
    ranked = ranking.rank_jobs(profile, fetched_jobs)

    search_row = Search(
        resume_id=row.id,
        label=f"{profile.title} @ {profile.location}".strip(),
        query_json=profile.model_dump_json(),
        results_json=json.dumps([item.model_dump(mode="json") for item in ranked]),
    )
    db.add(search_row)
    db.commit()
    db.refresh(search_row)

    return SearchResponse(search_id=search_row.id, resume_id=row.id, results=ranked)