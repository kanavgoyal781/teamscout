from collections.abc import Generator
from pathlib import Path
from threading import Lock
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.logging import get_logger
from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.schemas.jobs import Job
_BACKEND_DIR = Path(__file__).resolve().parents[2]
def resolve_database_url(url: str) -> str:
    if not url.startswith("sqlite:"):
        return url
    if ":memory:" in url:
        return url
    if url.startswith("sqlite:////"):
        return url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    rel = url[len(prefix) :]
    if not rel or rel.startswith("/"):
        return url
    abs_path = (_BACKEND_DIR / rel).resolve()
    return f"sqlite:///{abs_path}"
DATABASE_URL = resolve_database_url(settings.DATABASE_URL)
connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30}
engine_kwargs: dict = {"connect_args": connect_args}
if DATABASE_URL.startswith("sqlite") and ":memory:" in DATABASE_URL:
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_kwargs)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA busy_timeout=5000")
        if ":memory:" not in DATABASE_URL:
            cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
_init_lock = Lock()
_initialized = False
_WS_TABLES = (
    "resumes", "jobs_cache", "searches", "intent_searches", "team_extractions",
    "job_team_searches", "contacts", "feedback", "resume_units", "traces",
    "drive_synced_files", "drive_sync_state",
)
def _ensure_column(table: str, column: str, ddl: str) -> None:
    with engine.connect() as conn:
        columns = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {row[1] for row in columns}
        if column not in names:
            conn.execute(text(ddl))
            conn.commit()
def _migrate_schema() -> None:
    _ensure_column("feedback", "ranking_config_hash", "ALTER TABLE feedback ADD COLUMN ranking_config_hash VARCHAR(64)")
    _ensure_column("feedback", "shown_rank", "ALTER TABLE feedback ADD COLUMN shown_rank INTEGER")
    _ensure_column("feedback", "score_components_json", "ALTER TABLE feedback ADD COLUMN score_components_json TEXT")
    _ensure_column("resumes", "in_library", "ALTER TABLE resumes ADD COLUMN in_library BOOLEAN DEFAULT 0")
    _ensure_column("resumes", "source", "ALTER TABLE resumes ADD COLUMN source VARCHAR(32) DEFAULT 'upload'")
    _ensure_column("resumes", "cluster_id", "ALTER TABLE resumes ADD COLUMN cluster_id VARCHAR(64)")
    _ensure_column("resumes", "units_content_hash", "ALTER TABLE resumes ADD COLUMN units_content_hash VARCHAR(64)")
    for table in _WS_TABLES:
        _ensure_column(table, "workspace_id", f"ALTER TABLE {table} ADD COLUMN workspace_id VARCHAR(64) DEFAULT ''")
    _migrate_jobs_cache_job_id()
    _migrate_jobs_cache_unique()
    _migrate_workspace_uniques()
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
            conn.execute(text("UPDATE jobs_cache SET job_id = :job_id WHERE id = :id"), {"job_id": job.id, "id": row_id})
        conn.commit()
def _migrate_workspace_uniques() -> None:
    with engine.connect() as conn:
        for ddl in (
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_ws_person_job ON contacts (workspace_id, sumble_person_id, job_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_job_team_ws_job ON job_team_searches (workspace_id, job_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_drive_ws_folder_file ON drive_synced_files (workspace_id, folder_id, file_id)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_drive_ws_folder ON drive_sync_state (workspace_id, folder_id)",
        ):
            conn.execute(text(ddl))
        conn.commit()
def _migrate_jobs_cache_unique() -> None:
    with engine.connect() as conn:
        names = {str(r[1]) for r in conn.execute(text("PRAGMA index_list(jobs_cache)")).fetchall()}
        if "uq_jobs_cache_ws_source_job" not in names:
            conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_cache_ws_source_job "
                "ON jobs_cache (workspace_id, source, source_job_id)"
            ))
        conn.commit()
_REQUIRED_SQLITE_TABLES = frozenset({"traces", "embedding_cache", "workspaces"})
def _sqlite_tables() -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    return {str(row[0]) for row in rows}
def _schema_ready() -> bool:
    if not DATABASE_URL.startswith("sqlite") or ":memory:" in DATABASE_URL:
        return _initialized
    return _REQUIRED_SQLITE_TABLES.issubset(_sqlite_tables())
def init_db() -> None:
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
