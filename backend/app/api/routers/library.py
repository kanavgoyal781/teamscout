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
from app.services.jobs_svc.jd_metadata import extract_job_metadata
from app.services.jobs_svc.store import cache_pasted_job, resolve_job
router = APIRouter(prefix="/library", tags=["library"])

def _tournament_response_fields(recommendations, tmeta=None):
    from app.schemas.library import AdversarialCritiqueOut
    tournament_ran = any(r.tournament and r.tournament.ran for r in recommendations)
    comparisons = max((r.tournament.comparisons for r in recommendations if r.tournament), default=0)
    agree = next((r.tournament.judge_agreement for r in recommendations if r.tournament and r.tournament.judge_agreement is not None), None)
    agree_lbl = next((r.tournament.judge_agreement_label for r in recommendations if r.tournament and r.tournament.judge_agreement_label), None)
    crit = None
    adv = getattr(tmeta, "adversarial", None) if tmeta is not None else None
    if adv is not None and isinstance(getattr(adv, "side_a_resume_id", None), str):
        crit = AdversarialCritiqueOut(side_a_resume_id=adv.side_a_resume_id, side_a_filename=adv.side_a_filename, side_a_model=adv.side_a_model, side_a_argument=adv.side_a_argument, side_b_resume_id=adv.side_b_resume_id, side_b_filename=adv.side_b_filename, side_b_model=adv.side_b_model, side_b_argument=adv.side_b_argument, verdict_winner_resume_id=adv.verdict_winner_resume_id, verdict_winner_filename=adv.verdict_winner_filename, verdict_model=adv.verdict_model, verdict_reason=adv.verdict_reason, verdict_margin=adv.verdict_margin)
    return dict(tournament_ran=tournament_ran, tournament_comparisons=comparisons, tournament_judge_agreement=agree, tournament_judge_agreement_label=agree_lbl, adversarial_critique=crit)

@router.get("/resumes", response_model=LibraryResumeListResponse)
def list_resumes(db: Session = Depends(get_db)) -> LibraryResumeListResponse:
    resumes = library_store.list_library_resumes(db)
    return LibraryResumeListResponse(resumes=resumes, total=len(resumes))
@router.post("/upload", response_model=LibraryUploadResponse)
@limiter.limit(upload_limit)
async def upload_library(
    request: Request,
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
    """Primary Feature 2 path: paste JD → cache synthetic job → rank library resumes."""
    candidates = library_store.load_candidates(db)
    if not candidates:
        raise ValidationError("Resume library is empty — upload resumes or sync Drive first")
    from app.errors import ServiceFailingError, ServiceNotConfiguredError

    meta = None
    try:
        meta, _, _ = extract_job_metadata(payload.job_description, db=db)
    except (ValidationError, ServiceNotConfiguredError, ServiceFailingError):
        meta = None
    job = cache_pasted_job(
        description=payload.job_description,
        title=payload.title or (meta.title if meta else None),
        company=payload.company or (meta.company if meta else None),
        location=payload.location or (meta.location if meta else None),
        apply_url=payload.apply_url,
        db=db,
    )
    tbucket: list = []
    recommendations = resume_ranking.rank_resumes_for_job(
        job, candidates, db=db, metadata_hints=meta, out_tournament=tbucket
    )
    return RecommendFromJdResponse(
        job_id=job.id, job_title=job.title, job_company=job.company,
        recommendations=recommendations, **_tournament_response_fields(recommendations, tbucket[0] if tbucket else None),
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
    tbucket: list = []
    recommendations = resume_ranking.rank_resumes_for_job(job, candidates, out_tournament=tbucket)
    return RecommendResumesResponse(job_id=job_id, recommendations=recommendations, **_tournament_response_fields(recommendations, tbucket[0] if tbucket else None))
