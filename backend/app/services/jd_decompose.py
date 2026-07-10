"""JD → atomic requirements via LLM (cached by content hash)."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import JdRequirementsCache
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.services import llm
from app.services.ranking_math import extract_requirement_terms

logger = get_logger(__name__)

DEFAULT_MUST_WEIGHT = 2.0
DEFAULT_NICE_WEIGHT = 1.0

RequirementKind = Literal["must", "nice"]
RequirementCategory = Literal["skill", "experience", "domain", "education"]

class JdRequirement(BaseModel):
    text: str
    kind: RequirementKind = "must"
    category: RequirementCategory = "skill"
    weight: float = DEFAULT_MUST_WEIGHT

class _DecomposeResponse(BaseModel):
    requirements: list[JdRequirement] = Field(default_factory=list)

def jd_content_hash(job: Job) -> str:
    blob = json.dumps(
        {
            "title": job.title,
            "company": job.company,
            "skills": job.skills,
            "description": job.description,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    tmpl = load_prompt("jd_decompose")
    raw = f"{tmpl.name}:{tmpl.version}\n{blob}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _normalize_requirements(items: list[JdRequirement]) -> list[JdRequirement]:
    out: list[JdRequirement] = []
    seen: set[str] = set()
    for item in items:
        text = (item.text or "").strip()
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        kind: RequirementKind = item.kind if item.kind in ("must", "nice") else "must"
        category: RequirementCategory = (
            item.category if item.category in ("skill", "experience", "domain", "education") else "skill"
        )
        weight = (
            float(item.weight)
            if item.weight and item.weight > 0
            else (DEFAULT_MUST_WEIGHT if kind == "must" else DEFAULT_NICE_WEIGHT)
        )
        weight = max(0.5, min(3.0, weight))
        out.append(JdRequirement(text=text, kind=kind, category=category, weight=weight))
    return out

def deterministic_requirements(job: Job) -> list[JdRequirement]:
    """Explicit offline path when use_llm=False — not a silent fallback."""
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str, *, must: bool = True) -> None:
        cleaned = term.strip()
        if len(cleaned) < 2:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        terms.append(cleaned)

    for skill in job.skills:
        add(skill)
    for term in extract_requirement_terms([], job.description):
        if " " in term or len(term) >= 5:
            if term.lower() in {"experience", "years", "required", "preferred", "minimum"}:
                continue
            add(term)
    if not terms:
        title = (job.title or "").strip()
        if title:
            add(title)
    reqs = [JdRequirement(text=term, kind="must", category="skill", weight=DEFAULT_MUST_WEIGHT) for term in terms[:12]]
    return _normalize_requirements(reqs)

def _cache_get(db: Session, content_hash: str, prompt_version: str) -> list[JdRequirement] | None:
    row = (
        db.query(JdRequirementsCache)
        .filter(
            JdRequirementsCache.content_hash == content_hash,
            JdRequirementsCache.prompt_version == prompt_version,
        )
        .one_or_none()
    )
    if row is None:
        return None
    try:
        data = json.loads(row.requirements_json)
        if not isinstance(data, list):
            return None
        items = [JdRequirement.model_validate(x) for x in data]
        return _normalize_requirements(items) or None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

def _cache_put(db: Session, content_hash: str, prompt_version: str, reqs: list[JdRequirement]) -> None:
    payload = json.dumps([r.model_dump() for r in reqs], ensure_ascii=False)
    existing = db.query(JdRequirementsCache).filter(JdRequirementsCache.content_hash == content_hash).one_or_none()
    try:
        if existing is not None:
            existing.prompt_version = prompt_version
            existing.requirements_json = payload
            db.add(existing)
        else:
            db.add(
                JdRequirementsCache(
                    content_hash=content_hash,
                    prompt_version=prompt_version,
                    requirements_json=payload,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("jd_decompose.cache_put_failed", error=str(exc))

def decompose_jd(
    job: Job,
    *,
    use_llm: bool = True,
    db: Session | None = None,
) -> list[JdRequirement]:
    if not use_llm:
        return deterministic_requirements(job)

    tmpl = load_prompt("jd_decompose")
    content_hash = jd_content_hash(job)
    if db is not None:
        cached = _cache_get(db, content_hash, tmpl.version)
        if cached is not None:
            return cached

    prompt = "\n".join(
        [
            tmpl.body.strip(),
            "",
            f"Job title: {job.title}",
            f"Company: {job.company}",
            f"Location: {job.location}",
            f"Listed skills: {', '.join(job.skills)}",
            f"Description:\n{job.description[:4000]}",
        ]
    )
    response = llm.complete_json(
        prompt,
        _DecomposeResponse,
        system=tmpl.system or "Return JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("jd_decompose")),
        operation="jd_decompose",
        prompt_meta=tmpl,
    )
    reqs = _normalize_requirements(response.requirements)
    if not reqs:
        from app.errors import ServiceFailingError

        raise ServiceFailingError("LLM", "jd_decompose returned no requirements")

    if db is not None:
        _cache_put(db, content_hash, tmpl.version, reqs)
    return reqs
