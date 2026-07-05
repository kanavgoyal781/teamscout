import json

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

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
    RecommendResumesResponse,
)
from app.services import drive, jobs, library_store, ranking, resume_ranking
from app.services.jobs_store import resolve_job

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/resumes", response_model=LibraryResumeListResponse)
def list_resumes(db: Session = Depends(get_db)) -> LibraryResumeListResponse:
    resumes = library_store.list_library_resumes(db)
    return LibraryResumeListResponse(resumes=resumes, total=len(resumes))


@router.post("/upload", response_model=LibraryUploadResponse)
async def upload_library(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> LibraryUploadResponse:
    result = await library_store.ingest_upload_files(files, db)
    return LibraryUploadResponse(**result)


@router.post("/drive/sync", response_model=DriveSyncResponse)
def sync_drive(
    payload: DriveSyncRequest,
    db: Session = Depends(get_db),
) -> DriveSyncResponse:
    folder_id = drive.parse_folder_id(payload.folder_url)
    result = library_store.sync_drive_folder(folder_id, payload.folder_url, db)
    return DriveSyncResponse(**result)


@router.post("/intent/search", response_model=IntentSearchResponse)
def intent_search(
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


@router.post("/jobs/{job_id}/recommend-resumes", response_model=RecommendResumesResponse)
def recommend_resumes(job_id: str, db: Session = Depends(get_db)) -> RecommendResumesResponse:
    job = resolve_job(job_id, db)
    candidates = library_store.load_candidates(db)
    if not candidates:
        raise ValidationError("Resume library is empty — upload resumes or sync Drive first")

    recommendations = resume_ranking.rank_resumes_for_job(job, candidates)
    return RecommendResumesResponse(job_id=job_id, recommendations=recommendations)