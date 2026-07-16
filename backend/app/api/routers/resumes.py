from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, upload_limit
from app.core.upload_limit import enforce_upload_size
from app.core.workspace import require_workspace_id, workspace_upload_path
from app.db.models import Resume
from app.db.session import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.resume import ResumeProfile
from app.services import parser

router = APIRouter(prefix="/resumes", tags=["resumes"])


class ResumeUploadResponse(BaseModel):
    id: str
    filename: str
    content_hash: str
    confirmed: bool
    profile: ResumeProfile


class ResumeConfirmRequest(BaseModel):
    title: str = ""
    location: str = ""
    skills: list[str] = Field(default_factory=list)


class ResumeConfirmResponse(BaseModel):
    id: str
    confirmed: bool
    profile: ResumeProfile


@router.post("/upload", response_model=ResumeUploadResponse)
@limiter.limit(upload_limit)
async def upload_resume(
    request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ResumeUploadResponse:
    wid = require_workspace_id()
    if not file.filename:
        raise ValidationError("Missing filename")
    data = await file.read()
    if not data:
        raise ValidationError("Uploaded file is empty")
    enforce_upload_size(data)
    file_hash, profile = parser.parse_resume_file(file.filename, data)
    existing = db.query(Resume).filter(Resume.workspace_id == wid, Resume.content_hash == file_hash).one_or_none()
    if existing is not None:
        stored_profile = ResumeProfile.model_validate_json(existing.parsed_json or "{}")
        return ResumeUploadResponse(
            id=existing.id,
            filename=existing.filename,
            content_hash=existing.content_hash,
            confirmed=existing.confirmed,
            profile=stored_profile,
        )
    destination = workspace_upload_path(wid, file_hash, file.filename)
    destination.write_bytes(data)
    row = Resume(
        workspace_id=wid,
        filename=file.filename,
        content_hash=file_hash,
        file_path=str(destination),
        parsed_json=profile.model_dump_json(),
        confirmed=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ResumeUploadResponse(
        id=row.id, filename=row.filename, content_hash=row.content_hash, confirmed=row.confirmed, profile=profile
    )


@router.put("/{resume_id}/confirm", response_model=ResumeConfirmResponse)
def confirm_resume(
    resume_id: str, payload: ResumeConfirmRequest, db: Session = Depends(get_db)
) -> ResumeConfirmResponse:
    wid = require_workspace_id()
    row = db.query(Resume).filter(Resume.id == resume_id, Resume.workspace_id == wid).one_or_none()
    if row is None:
        raise NotFoundError("resume", resume_id)
    profile = ResumeProfile.model_validate_json(row.parsed_json or "{}")
    profile.title = payload.title.strip() or profile.title
    profile.location = payload.location.strip() or profile.location
    profile.skills = [skill.strip() for skill in payload.skills if skill.strip()]
    row.parsed_json = profile.model_dump_json()
    row.confirmed = True
    db.add(row)
    db.commit()
    return ResumeConfirmResponse(id=row.id, confirmed=True, profile=profile)
