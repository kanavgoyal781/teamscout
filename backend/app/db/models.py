import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    parsed_json: Mapped[str | None] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(default=False)
    in_library: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="upload")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobCache(Base):
    __tablename__ = "jobs_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resume_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    query_json: Mapped[str | None] = mapped_column(Text)
    results_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IntentSearch(Base):
    __tablename__ = "intent_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role: Mapped[str] = mapped_column(String(256), nullable=False)
    years_of_experience: Mapped[float] = mapped_column(default=0.0)
    location: Mapped[str] = mapped_column(String(256), default="")
    remote_preference: Mapped[str] = mapped_column(String(32), default="any")
    query_json: Mapped[str | None] = mapped_column(Text)
    results_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DriveSyncState(Base):
    __tablename__ = "drive_sync_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    folder_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    folder_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DriveSyncedFile(Base):
    __tablename__ = "drive_synced_files"
    __table_args__ = (UniqueConstraint("folder_id", "file_id", name="uq_drive_folder_file"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    folder_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    modified_time: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TeamExtractionRecord(Base):
    __tablename__ = "team_extractions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    extraction_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobTeamSearch(Base):
    __tablename__ = "job_team_searches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    extraction_id: Mapped[str] = mapped_column(String(36), nullable=False)
    search_id: Mapped[str | None] = mapped_column(String(36), index=True)
    team_searched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    search_path: Mapped[str | None] = mapped_column(String(64))


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("sumble_person_id", "job_id", name="uq_contact_person_job"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256))
    company: Mapped[str | None] = mapped_column(String(256))
    team: Mapped[str | None] = mapped_column(String(256))
    seniority: Mapped[str | None] = mapped_column(String(128))
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    search_id: Mapped[str | None] = mapped_column(String(36), index=True)
    extraction_id: Mapped[str | None] = mapped_column(String(36), index=True)
    sumble_person_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmailReveal(Base):
    __tablename__ = "email_reveals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    contact_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    sumble_person_id: Mapped[str | None] = mapped_column(String(128), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    cost_credits: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())