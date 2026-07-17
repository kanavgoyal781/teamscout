"""Extract JobMetadata from arbitrary JD text — honesty-first, hash-cached."""
from __future__ import annotations
import hashlib
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import JdMetadataCache
from app.errors import ValidationError
from app.prompts import load_prompt
from app.schemas.job_metadata import JobMetadata
from app.services import llm
logger = get_logger(__name__)
def jd_text_hash(description: str) -> str:
    tmpl = load_prompt("jd_metadata")
    raw = f"{tmpl.name}:{tmpl.version}\n{description.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def _cache_get(db: Session, content_hash: str, prompt_version: str) -> JobMetadata | None:
    row = db.query(JdMetadataCache).filter(JdMetadataCache.content_hash == content_hash).one_or_none()
    if row is None or row.prompt_version != prompt_version:
        return None
    try:
        return JobMetadata.model_validate_json(row.metadata_json)
    except (ValueError, TypeError, KeyError):
        return None
def _cache_put(db: Session, content_hash: str, prompt_version: str, meta: JobMetadata) -> None:
    payload = meta.model_dump_json()
    existing = db.query(JdMetadataCache).filter(JdMetadataCache.content_hash == content_hash).one_or_none()
    try:
        if existing is not None:
            existing.prompt_version = prompt_version
            existing.metadata_json = payload
            db.add(existing)
        else:
            db.add(
                JdMetadataCache(
                    content_hash=content_hash,
                    prompt_version=prompt_version,
                    metadata_json=payload,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("jd_metadata.cache_put_failed", error=str(exc))
def extract_job_metadata(
    description: str,
    *,
    db: Session | None = None,
) -> tuple[JobMetadata, bool, str]:
    """Return (metadata, cache_hit, content_hash). One LLM call on miss."""
    text = (description or "").strip()
    if len(text) < 20:
        raise ValidationError("Job description too short for metadata extraction")
    from app.services.resume.jd_decompose import assert_pasted_jd_looks_valid
    assert_pasted_jd_looks_valid(text)  # 422 chrome pastes before any LLM spend
    tmpl = load_prompt("jd_metadata")
    content_hash = jd_text_hash(text)
    if db is not None:
        cached = _cache_get(db, content_hash, tmpl.version)
        if cached is not None:
            return cached, True, content_hash
    prompt = f"{tmpl.body.strip()}\n\n{text[:12000]}"
    meta = llm.complete_json(
        prompt,
        JobMetadata,
        system=tmpl.system,
        max_retries=1,
        operation="jd_metadata",
        prompt_meta=tmpl,
        max_tokens=int(
            tmpl.model_params.get("max_tokens")
            or settings.max_tokens_for_operation("jd_metadata")
        ),
    )
    if db is not None:
        _cache_put(db, content_hash, tmpl.version, meta)
    return meta, False, content_hash
