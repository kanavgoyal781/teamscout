import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
def _uuid() -> str:
    return str(uuid.uuid4())
class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    prefs_json: Mapped[str | None] = mapped_column(Text)
class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (UniqueConstraint("workspace_id", "content_hash", name="uq_resume_ws_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    parsed_json: Mapped[str | None] = mapped_column(Text)
    confirmed: Mapped[bool] = mapped_column(default=False)
    in_library: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="upload")
    cluster_id: Mapped[str | None] = mapped_column(String(64), index=True)
    units_content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class JobCache(Base):
    __tablename__ = "jobs_cache"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source", "source_job_id", name="uq_jobs_cache_ws_source_job"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class Search(Base):
    __tablename__ = "searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    resume_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    query_json: Mapped[str | None] = mapped_column(Text)
    results_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class IntentSearch(Base):
    __tablename__ = "intent_searches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    role: Mapped[str] = mapped_column(String(256), nullable=False)
    years_of_experience: Mapped[float] = mapped_column(default=0.0)
    location: Mapped[str] = mapped_column(String(256), default="")
    remote_preference: Mapped[str] = mapped_column(String(32), default="any")
    query_json: Mapped[str | None] = mapped_column(Text)
    results_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class DriveSyncState(Base):
    __tablename__ = "drive_sync_state"
    __table_args__ = (UniqueConstraint("workspace_id", "folder_id", name="uq_drive_ws_folder"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    folder_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    folder_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class DriveSyncedFile(Base):
    __tablename__ = "drive_synced_files"
    __table_args__ = (UniqueConstraint("workspace_id", "folder_id", "file_id", name="uq_drive_ws_folder_file"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    folder_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    modified_time: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class TeamExtractionRecord(Base):
    __tablename__ = "team_extractions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    extraction_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class JobTeamSearch(Base):
    __tablename__ = "job_team_searches"
    __table_args__ = (UniqueConstraint("workspace_id", "job_id", name="uq_job_team_ws_job"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    extraction_id: Mapped[str] = mapped_column(String(36), nullable=False)
    search_id: Mapped[str | None] = mapped_column(String(36), index=True)
    team_searched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    credits_used: Mapped[int] = mapped_column(Integer, default=0)
    search_path: Mapped[str | None] = mapped_column(String(64))
class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "sumble_person_id", "job_id", name="uq_contact_ws_person_job"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
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
class Trace(Base):
    __tablename__ = "traces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(64), index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    credits_used: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    error_type: Mapped[str | None] = mapped_column(String(128))
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_embedding_content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class QueryExpansionCache(Base):
    __tablename__ = "query_expansion_cache"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_query_expand_content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    expansions_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class ResumeUnit(Base):
    __tablename__ = "resume_units"
    __table_args__ = (UniqueConstraint("resume_id", "unit_hash", name="uq_resume_unit_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    resume_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_text: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String(64), nullable=False, default="experience")
    unit_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class JdRequirementsCache(Base):
    __tablename__ = "jd_requirements_cache"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_jd_req_content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    requirements_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class PairwiseJudgeCache(Base):
    __tablename__ = "pairwise_judge_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_pairwise_cache_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hash_a: Mapped[str] = mapped_column(String(64), nullable=False)
    hash_b: Mapped[str] = mapped_column(String(64), nullable=False)
    winner_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    secondary_id: Mapped[str | None] = mapped_column(String(128), index=True)
    profile_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    jd_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    score_shown: Mapped[float | None] = mapped_column(Float)
    shown_rank: Mapped[int | None] = mapped_column(Integer)
    score_components_json: Mapped[str | None] = mapped_column(Text)
    prompt_versions_json: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128))
    embeddings_model: Mapped[str | None] = mapped_column(String(128))
    git_sha: Mapped[str | None] = mapped_column(String(64))
    ranking_config_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
class ScoreCalibration(Base):
    __tablename__ = "score_calibration"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    a: Mapped[float] = mapped_column(Float, nullable=False)
    b: Mapped[float] = mapped_column(Float, nullable=False)
    n_labels: Mapped[int] = mapped_column(Integer, default=0)
    holdout_auc: Mapped[float | None] = mapped_column(Float)
    fit_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
class JdMetadataCache(Base):
    __tablename__ = "jd_metadata_cache"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_jd_metadata_content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

