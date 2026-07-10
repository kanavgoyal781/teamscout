import json
from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session
from app.core.rate_limit import limiter, llm_limit, search_limit, upload_limit
from app.db.models import IntentSearch
from app.db.session import get_db
from app.errors import ValidationError
from app.schemas.library import (
    DriveSyncRequest,
    DriveSyncResponse,
    IntentProfile,
    IntentSearchRequest,
    IntentSearchResponse,
    LibraryResumeListResponse,
    LibraryUploadResponse,
    RecommendFromJdRequest,
    RecommendFromJdResponse,
    RecommendResumesResponse,
)
from app.services import drive, jobs, library_store, ranking, resume_ranking
from app.services.jobs_store import cache_pasted_job, resolve_job
router = APIRouter(prefix="/library", tags=["library"])
@router.get("/resumes", response_model=LibraryResumeListResponse)
def list_resumes(db: Session = Depends(get_db)) -> LibraryResumeListResponse:
    resumes = library_store.list_library_resumes(db)
    return LibraryResumeListResponse(
        resumes=resumes,
        total=len(resumes),
        distinct_versions=library_store.distinct_version_count(db),
    )
@router.post("/upload", response_model=LibraryUploadResponse)
@limiter.limit(upload_limit)
async def upload_library(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> LibraryUploadResponse:
    result = await library_store.ingest_upload_files(files, db)
    units_indexed = result.get("units_indexed")
    return LibraryUploadResponse(
        files_received=int(result["files_received"]),
        files_parsed=int(result["files_parsed"]),
        files_skipped=int(result["files_skipped"]),
        files_ignored=int(result["files_ignored"]),
        resumes=result["resumes"],  # type: ignore[arg-type]
        distinct_versions=int(result.get("distinct_versions") or 0),
        units_indexed=units_indexed if isinstance(units_indexed, bool) or units_indexed is None else None,
        units_index_warning=(
            str(result["units_index_warning"]) if result.get("units_index_warning") else None
        ),
    )
@router.post("/drive/sync", response_model=DriveSyncResponse)
def sync_drive(
    payload: DriveSyncRequest,
    db: Session = Depends(get_db),
) -> DriveSyncResponse:
    folder_id = drive.parse_folder_id(payload.folder_url)
    result = library_store.sync_drive_folder(folder_id, payload.folder_url, db)
    return DriveSyncResponse(**result)
@router.post("/intent/search", response_model=IntentSearchResponse)
@limiter.limit(search_limit)
def intent_search(
    request: Request,
    payload: IntentSearchRequest,
    db: Session = Depends(get_db),
) -> IntentSearchResponse:
    role = payload.role.strip()
    if not role:
        raise ValidationError("Desired role is required")
    intent = IntentProfile(
        role=role,
        years_of_experience=payload.years_of_experience,
        location=payload.location.strip(),
        remote_preference=payload.remote_preference,
    )
    fetched_jobs = jobs.fetch_jobs_for_intent(intent, db)
    ranked = ranking.rank_jobs(intent.as_query_profile(), fetched_jobs)
    row = IntentSearch(
        role=intent.role,
        years_of_experience=intent.years_of_experience,
        location=intent.location,
        remote_preference=intent.remote_preference,
        query_json=intent.model_dump_json(),
        results_json=json.dumps([item.model_dump(mode="json") for item in ranked]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return IntentSearchResponse(search_id=row.id, results=ranked)
@router.post("/recommend-from-jd", response_model=RecommendFromJdResponse)
@limiter.limit(llm_limit)
def recommend_from_jd(
    request: Request,
    payload: RecommendFromJdRequest,
    db: Session = Depends(get_db),
) -> RecommendFromJdResponse:
    """Primary Feature 2 path: paste a JD → rank all library resumes → top 3."""
    candidates = library_store.load_candidates(db)
    if not candidates:
        raise ValidationError("Resume library is empty — upload resumes or sync Drive first")
    job = cache_pasted_job(
        description=payload.job_description,
        title=payload.title,
        company=payload.company,
        location=payload.location,
        apply_url=payload.apply_url,
        db=db,
    )
    recommendations = resume_ranking.rank_resumes_for_job(job, candidates, db=db)
    tournament_ran = any(r.tournament and r.tournament.ran for r in recommendations)
    comparisons = max((r.tournament.comparisons for r in recommendations if r.tournament), default=0)
    return RecommendFromJdResponse(
        job_id=job.id,
        job_title=job.title,
        job_company=job.company,
        recommendations=recommendations,
        tournament_ran=tournament_ran,
        tournament_comparisons=comparisons,
    )
@router.post("/jobs/{job_id}/recommend-resumes", response_model=RecommendResumesResponse)
@limiter.limit(llm_limit)
def recommend_resumes(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
) -> RecommendResumesResponse:
    job = resolve_job(job_id, db)
    candidates = library_store.load_candidates(db)
    if not candidates:
        raise ValidationError("Resume library is empty — upload resumes or sync Drive first")
    recommendations = resume_ranking.rank_resumes_for_job(job, candidates, db=db)
    tournament_ran = any(r.tournament and r.tournament.ran for r in recommendations)
    comparisons = max((r.tournament.comparisons for r in recommendations if r.tournament), default=0)
    return RecommendResumesResponse(
        job_id=job_id,
        recommendations=recommendations,
        tournament_ran=tournament_ran,
        tournament_comparisons=comparisons,
    )
