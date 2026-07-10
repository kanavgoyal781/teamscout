from collections.abc import Generator
from pathlib import Path
from threading import Lock

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.logging import get_logger
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.schemas.jobs import Job

# Resolve relative sqlite:/// paths against backend/ so scripts run from the
# repo root and `cd backend && uvicorn` share the same database file.
# session.py lives at backend/app/db/session.py → parents[2] == backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
def resolve_database_url(url: str) -> str:
    if not url.startswith("sqlite:"):
        return url
    if ":memory:" in url:
        return url
    # Absolute file URL: sqlite:////abs/path (4 slashes) or sqlite:////var/...
    if url.startswith("sqlite:////"):
        return url
    # Relative: sqlite:///./teamscout.db or sqlite:///teamscout.db
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    rel = url[len(prefix) :]
    if not rel or rel.startswith("/"):
        return url
    abs_path = (_BACKEND_DIR / rel).resolve()
    return f"sqlite:///{abs_path}"
DATABASE_URL = resolve_database_url(settings.DATABASE_URL)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs: dict = {"connect_args": connect_args}
if DATABASE_URL.startswith("sqlite") and ":memory:" in DATABASE_URL:
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_init_lock = Lock()
_initialized = False
def _ensure_column(table: str, column: str, ddl: str) -> None:
    with engine.connect() as conn:
        columns = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {row[1] for row in columns}
        if column not in names:
            conn.execute(text(ddl))
            conn.commit()
def _migrate_schema() -> None:
    _ensure_column(
        "feedback",
        "ranking_config_hash",
        "ALTER TABLE feedback ADD COLUMN ranking_config_hash VARCHAR(64)",
    )
    _ensure_column("resumes", "in_library", "ALTER TABLE resumes ADD COLUMN in_library BOOLEAN DEFAULT 0")
    _ensure_column("resumes", "source", "ALTER TABLE resumes ADD COLUMN source VARCHAR(32) DEFAULT 'upload'")
    _ensure_column("resumes", "cluster_id", "ALTER TABLE resumes ADD COLUMN cluster_id VARCHAR(64)")
    _ensure_column(
        "resumes",
        "units_content_hash",
        "ALTER TABLE resumes ADD COLUMN units_content_hash VARCHAR(64)",
    )
    _migrate_jobs_cache_job_id()
    _migrate_jobs_cache_unique()
def _migrate_jobs_cache_job_id() -> None:
    with engine.connect() as conn:
        columns = conn.execute(text("PRAGMA table_info(jobs_cache)")).fetchall()
        names = {row[1] for row in columns}
        if "job_id" not in names:
            conn.execute(text("ALTER TABLE jobs_cache ADD COLUMN job_id VARCHAR(36)"))
            conn.commit()
        rows = conn.execute(
            text("SELECT id, payload_json FROM jobs_cache WHERE job_id IS NULL AND payload_json IS NOT NULL")
        ).fetchall()
        for row_id, payload_json in rows:
            if not payload_json:
                continue
            job = Job.model_validate_json(payload_json)
            conn.execute(
                text("UPDATE jobs_cache SET job_id = :job_id WHERE id = :id"),
                {"job_id": job.id, "id": row_id},
            )
        conn.commit()
def _migrate_jobs_cache_unique() -> None:
    """Dedupe (source, source_job_id) then ensure unique index (SQLite)."""
    with engine.connect() as conn:
        conn.execute(text(
            "DELETE FROM jobs_cache WHERE id IN ("
            "SELECT j.id FROM jobs_cache j INNER JOIN ("
            "SELECT source, source_job_id, MIN(id) AS keep_id FROM jobs_cache "
            "GROUP BY source, source_job_id HAVING COUNT(*) > 1"
            ") d ON j.source = d.source AND j.source_job_id = d.source_job_id "
            "WHERE j.id != d.keep_id)"
        ))
        names = {str(r[1]) for r in conn.execute(text("PRAGMA index_list(jobs_cache)")).fetchall()}
        if "uq_jobs_cache_source_job" not in names:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_cache_source_job "
                "ON jobs_cache (source, source_job_id)"
            ))
        conn.commit()
_REQUIRED_SQLITE_TABLES = frozenset({"traces", "embedding_cache"})
def _sqlite_tables() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    return {str(row[0]) for row in rows}
def _schema_ready() -> bool:
    if not DATABASE_URL.startswith("sqlite") or ":memory:" in DATABASE_URL:
        return _initialized
    return _REQUIRED_SQLITE_TABLES.issubset(_sqlite_tables())
def init_db() -> None:
    """Create missing tables and run lightweight SQLite migrations (idempotent)."""
    global _initialized
    with _init_lock:
        Base.metadata.create_all(bind=engine)
        if DATABASE_URL.startswith("sqlite") and ":memory:" not in DATABASE_URL:
            _migrate_schema()
            missing = _REQUIRED_SQLITE_TABLES - _sqlite_tables()
            if missing:
                raise RuntimeError(
                    f"SQLite schema incomplete at {DATABASE_URL}; missing tables: "
                    f"{sorted(missing)}. Check DATABASE_URL and write permissions."
                )
        _initialized = True
def ensure_db() -> None:
    """Idempotent schema ensure for scripts / first request that bypasses lifespan."""
    if _initialized and _schema_ready():
        return
    init_db()
def ping_db() -> bool:
    logger = get_logger(__name__)
    try:
        ensure_db()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning("db.ping_failed", error=str(exc))
        return False
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
