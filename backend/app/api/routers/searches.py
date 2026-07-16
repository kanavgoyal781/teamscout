import json
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter, search_limit
from app.core.workspace import require_workspace_id
from app.db.models import Resume, Search
from app.db.session import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.jobs import DroppedCounts, JobFacets, RankedJob, SearchParams
from app.schemas.resume import ResumeProfile
from app.services import jobs, ranking
from app.services.jobs_svc.facets import compute_facets
router = APIRouter(prefix="/searches", tags=["searches"])
class SearchRequest(BaseModel):
    resume_id: str
    params: SearchParams | None = None
class SearchResponse(BaseModel):
    search_id: str
    resume_id: str
    results: list[RankedJob] = Field(default_factory=list)
    dropped_counts: dict[str, int] = Field(default_factory=dict)
    facets: JobFacets | None = None
    per_source_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    source_errors: list[str] = Field(default_factory=list)
@router.post("", response_model=SearchResponse)
@limiter.limit(search_limit)
def create_search(request: Request, payload: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    wid = require_workspace_id()
    row = db.query(Resume).filter(Resume.id == payload.resume_id, Resume.workspace_id == wid).one_or_none()
    if row is None:
        raise NotFoundError("resume", payload.resume_id)
    if not row.confirmed:
        raise ValidationError("Resume must be confirmed before search — call PUT /resumes/{id}/confirm")
    profile = ResumeProfile.model_validate_json(row.parsed_json or "{}")
    if not profile.title.strip():
        raise ValidationError("Resume title is required before search")
    if not profile.skills:
        raise ValidationError("At least one skill is required before search")
    params = payload.params or SearchParams()
    detailed = jobs.fetch_jobs_detailed(profile, db, params=params)
    fetched_jobs = detailed.jobs if hasattr(detailed, 'jobs') else detailed
    dropped = getattr(detailed, 'dropped_counts', None) or DroppedCounts()
    ranked = ranking.rank_jobs(profile, fetched_jobs, params=params)
    facets = compute_facets(fetched_jobs)
    search_row = Search(workspace_id=wid, resume_id=row.id, label=f"{profile.title} @ {profile.location}".strip(), query_json=profile.model_dump_json(), results_json=json.dumps([item.model_dump(mode="json") for item in ranked]))
    db.add(search_row)
    db.commit()
    db.refresh(search_row)
    per_source = getattr(detailed, "per_source_counts", {}) or {}
    per_source_out = {k: (v.model_dump() if hasattr(v, "model_dump") else dict(v)) for k, v in per_source.items()}
    return SearchResponse(search_id=search_row.id, resume_id=row.id, results=ranked, dropped_counts=dropped.as_dict() if hasattr(dropped, "as_dict") else dict(dropped or {}), facets=facets, per_source_counts=per_source_out, source_errors=list(getattr(detailed, "source_errors", None) or []))
