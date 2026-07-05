from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db import models as _models  # noqa: F401
from app.schemas.jobs import Job

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine_kwargs: dict = {"connect_args": connect_args}
if settings.DATABASE_URL.startswith("sqlite") and ":memory:" in settings.DATABASE_URL:
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _ensure_column(table: str, column: str, ddl: str) -> None:
    with engine.connect() as conn:
        columns = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        names = {row[1] for row in columns}
        if column not in names:
            conn.execute(text(ddl))
            conn.commit()


def _migrate_schema() -> None:
    _ensure_column("resumes", "in_library", "ALTER TABLE resumes ADD COLUMN in_library BOOLEAN DEFAULT 0")
    _ensure_column("resumes", "source", "ALTER TABLE resumes ADD COLUMN source VARCHAR(32) DEFAULT 'upload'")
    _migrate_jobs_cache_job_id()


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


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.DATABASE_URL.startswith("sqlite"):
        _migrate_schema()


def ping_db() -> bool:
    logger = get_logger(__name__)
    try:
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