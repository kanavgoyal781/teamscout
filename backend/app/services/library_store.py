import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.upload_limit import enforce_upload_size
from app.db.models import DriveSyncedFile, DriveSyncState, Resume
from app.errors import NotFoundError, ValidationError
from app.schemas.library import LibraryResumeOut, ResumeCandidate
from app.schemas.resume import ResumeProfile
from app.services import drive, parser

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


def _resume_to_out(row: Resume) -> LibraryResumeOut:
    profile = ResumeProfile.model_validate_json(row.parsed_json or "{}")
    created = row.created_at.isoformat() if row.created_at else None
    return LibraryResumeOut(
        id=row.id,
        filename=row.filename,
        content_hash=row.content_hash,
        source=row.source,
        profile=profile,
        created_at=created,
    )


def _resume_out_by_hash(content_hash: str, db: Session) -> LibraryResumeOut:
    row = db.query(Resume).filter(Resume.content_hash == content_hash).one_or_none()
    if row is None:
        raise NotFoundError("resume", content_hash)
    return _resume_to_out(row)


def load_candidates(db: Session) -> list[ResumeCandidate]:
    rows = db.query(Resume).filter(Resume.in_library.is_(True)).order_by(Resume.created_at.desc()).all()
    return [
        ResumeCandidate(
            resume_id=row.id,
            filename=row.filename,
            profile=ResumeProfile.model_validate_json(row.parsed_json or "{}"),
        )
        for row in rows
    ]


def list_library_resumes(db: Session) -> list[LibraryResumeOut]:
    rows = db.query(Resume).filter(Resume.in_library.is_(True)).order_by(Resume.created_at.desc()).all()
    return [_resume_to_out(row) for row in rows]


def ingest_resume_bytes(
    filename: str,
    data: bytes,
    db: Session,
    *,
    source: str = "upload",
) -> tuple[LibraryResumeOut, bool]:
    if not data:
        raise ValidationError(f"File is empty: {filename}")
    enforce_upload_size(data)

    file_hash, profile = parser.parse_resume_file(filename, data)
    existing = db.query(Resume).filter(Resume.content_hash == file_hash).one_or_none()
    if existing is not None:
        if not existing.in_library:
            existing.in_library = True
            existing.source = source
            db.add(existing)
            db.commit()
            db.refresh(existing)
        return _resume_to_out(existing), False

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{file_hash}_{Path(filename).name}"
    destination.write_bytes(data)

    row = Resume(
        filename=filename,
        content_hash=file_hash,
        file_path=str(destination),
        parsed_json=profile.model_dump_json(),
        confirmed=False,
        in_library=True,
        source=source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _resume_to_out(row), True


def sync_drive_folder(folder_id: str, folder_url: str, db: Session) -> dict[str, object]:
    listing = drive.list_folder_files(folder_id)
    parsed = 0
    skipped = 0
    resumes: list[LibraryResumeOut] = []

    for item in listing.supported_files:
        synced = (
            db.query(DriveSyncedFile)
            .filter(
                DriveSyncedFile.folder_id == folder_id,
                DriveSyncedFile.file_id == item.file_id,
            )
            .one_or_none()
        )
        if synced is not None and synced.modified_time == item.modified_time:
            resumes.append(_resume_out_by_hash(synced.content_hash, db))
            skipped += 1
            continue

        data = drive.download_file(item.file_id)
        content_hash = parser.content_hash(data)
        out, created = ingest_resume_bytes(item.name, data, db, source="drive")
        resumes.append(out)
        if created:
            parsed += 1
        else:
            skipped += 1

        now = datetime.now(UTC)
        if synced is None:
            db.add(
                DriveSyncedFile(
                    folder_id=folder_id,
                    file_id=item.file_id,
                    filename=item.name,
                    modified_time=item.modified_time,
                    content_hash=content_hash,
                    synced_at=now,
                )
            )
        else:
            synced.filename = item.name
            synced.modified_time = item.modified_time
            synced.content_hash = content_hash
            synced.synced_at = now
            db.add(synced)

    state = db.query(DriveSyncState).filter(DriveSyncState.folder_id == folder_id).one_or_none()
    now = datetime.now(UTC)
    if state is None:
        state = DriveSyncState(folder_id=folder_id, folder_url=folder_url, last_synced_at=now)
        db.add(state)
    else:
        state.folder_url = folder_url
        state.last_synced_at = now
        db.add(state)
    db.commit()

    return {
        "folder_id": folder_id,
        "files_seen": len(listing.supported_files),
        "files_parsed": parsed,
        "files_skipped": skipped,
        "files_ignored": listing.files_ignored,
        "resumes": resumes,
    }


async def ingest_upload_files(files: list[UploadFile], db: Session) -> dict[str, object]:
    parsed = 0
    skipped = 0
    ignored = 0
    received = 0
    resumes: list[LibraryResumeOut] = []

    for upload in files:
        if not upload.filename:
            continue
        data = await upload.read()
        enforce_upload_size(data)
        received += 1
        suffix = Path(upload.filename).suffix.lower()
        if suffix == ".zip":
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile as exc:
                raise ValidationError(f"Invalid ZIP archive: {upload.filename}") from exc
            for info in archive.infolist():
                if info.is_dir():
                    continue
                inner_name = Path(info.filename).name
                if Path(inner_name).suffix.lower() not in parser.ALLOWED_EXTENSIONS:
                    ignored += 1
                    continue
                inner_data = archive.read(info)
                out, created = ingest_resume_bytes(inner_name, inner_data, db, source="upload")
                resumes.append(out)
                if created:
                    parsed += 1
                else:
                    skipped += 1
            continue

        if suffix not in parser.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported file type: {upload.filename}",
                details={"allowed": sorted(parser.ALLOWED_EXTENSIONS)},
            )
        out, created = ingest_resume_bytes(upload.filename, data, db, source="upload")
        resumes.append(out)
        if created:
            parsed += 1
        else:
            skipped += 1

    if received == 0:
        raise ValidationError("No files uploaded")

    return {
        "files_received": received,
        "files_parsed": parsed,
        "files_skipped": skipped,
        "files_ignored": ignored,
        "resumes": resumes,
    }
