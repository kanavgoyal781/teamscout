import hashlib

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import find_team_limit, limiter, llm_limit
from app.db.models import Contact, EmailReveal, JobTeamSearch, TeamExtractionRecord
from app.db.session import get_db
from app.errors import ValidationError
from app.schemas.team import (
    ContactOut,
    FindTeamRequest,
    FindTeamResponse,
    TeamExtraction,
    TeamExtractionResponse,
    TeamListResponse,
)
from app.services import team_extract, team_search
from app.services.jobs_store import resolve_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _extraction_hash(extraction: TeamExtraction) -> str:
    payload = extraction.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_confirmed_extraction(
    job_id: str,
    extraction_id: str,
    db: Session,
) -> TeamExtraction:
    row = (
        db.query(TeamExtractionRecord)
        .filter(
            TeamExtractionRecord.id == extraction_id,
            TeamExtractionRecord.job_id == job_id,
        )
        .one_or_none()
    )
    if row is None:
        raise ValidationError(
            "Team extraction not found for this job — call POST /jobs/{job_id}/extract-team first",
            details={"job_id": job_id, "extraction_id": extraction_id},
        )
    return TeamExtraction.model_validate_json(row.extraction_json)


def _team_searched(job_id: str, db: Session) -> bool:
    return db.query(JobTeamSearch).filter(JobTeamSearch.job_id == job_id).one_or_none() is not None


def _latest_extraction(job_id: str, db: Session) -> tuple[str | None, TeamExtraction | None]:
    row = (
        db.query(TeamExtractionRecord)
        .filter(TeamExtractionRecord.job_id == job_id)
        .order_by(TeamExtractionRecord.created_at.desc())
        .first()
    )
    if row is None:
        return None, None
    return row.id, TeamExtraction.model_validate_json(row.extraction_json)


def _contact_to_out(contact: Contact, reveal_email: str | None = None) -> ContactOut:
    return ContactOut(
        id=contact.id,
        full_name=contact.full_name,
        title=contact.title,
        company=contact.company,
        team=contact.team,
        seniority=contact.seniority,
        sumble_person_id=contact.sumble_person_id,
        email_revealed=reveal_email is not None,
        email=reveal_email,
    )


@router.post("/{job_id}/extract-team", response_model=TeamExtractionResponse)
@limiter.limit(llm_limit)
def extract_team(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
) -> TeamExtractionResponse:
    job = resolve_job(job_id, db)
    extraction = team_extract.extract_team_from_job(job)
    record = TeamExtractionRecord(
        job_id=job_id,
        extraction_json=extraction.model_dump_json(),
        content_hash=_extraction_hash(extraction),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return TeamExtractionResponse(job_id=job_id, extraction_id=record.id, extraction=extraction)


@router.post("/{job_id}/find-team", response_model=FindTeamResponse)
@limiter.limit(find_team_limit)
def find_team(
    request: Request,
    job_id: str,
    payload: FindTeamRequest,
    db: Session = Depends(get_db),
) -> FindTeamResponse:
    job = resolve_job(job_id, db)
    extraction = _load_confirmed_extraction(job_id, payload.extraction_id, db)
    return team_search.find_team_for_job(
        job=job,
        extraction=extraction,
        extraction_id=payload.extraction_id,
        search_id=payload.search_id,
        db=db,
    )


@router.get("/{job_id}/team", response_model=TeamListResponse)
def list_team(job_id: str, db: Session = Depends(get_db)) -> TeamListResponse:
    resolve_job(job_id, db)
    rows = db.query(Contact).filter(Contact.job_id == job_id).order_by(Contact.created_at.desc()).all()
    contact_ids = [row.id for row in rows]
    reveals: dict[str, str] = {}
    if contact_ids:
        reveal_rows = (
            db.query(EmailReveal)
            .filter(
                EmailReveal.contact_id.in_(contact_ids),
                EmailReveal.status == "revealed",
            )
            .all()
        )
        reveals = {row.contact_id: row.email for row in reveal_rows if row.email}

    extraction_id, extraction = _latest_extraction(job_id, db)
    ts = db.query(JobTeamSearch).filter(JobTeamSearch.job_id == job_id).one_or_none()
    return TeamListResponse(
        job_id=job_id,
        contacts=[_contact_to_out(row, reveals.get(row.id)) for row in rows],
        extraction_id=extraction_id,
        extraction=extraction,
        team_searched=_team_searched(job_id, db),
        search_path=ts.search_path if ts else None,
    )
