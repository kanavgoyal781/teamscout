"""LLM query expansion: profile/intent → 3–5 JSearch query variants (cached)."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import QueryExpansionCache
from app.prompts import load_prompt
from app.schemas.jobs import SearchParams
from app.schemas.resume import ResumeProfile
from app.services import llm

logger = get_logger(__name__)

class _ExpandVariant(BaseModel):
    title: str = ""
    skills: list[str] = Field(default_factory=list)
    query: str = ""

class _ExpandResponse(BaseModel):
    variants: list[_ExpandVariant] = Field(default_factory=list)

def expansion_cache_key(profile: ResumeProfile, params: SearchParams | None = None) -> str:
    """Stable content hash of profile search text + structured intent."""
    params = params or SearchParams()
    blob = json.dumps(
        {
            "search_text": profile.search_text(),
            "title": profile.title,
            "skills": profile.skills[:12],
            "location": profile.location,
            "remote_mode": params.remote_mode,
            "employment_type": params.employment_type,
            "seniority": params.seniority,
            "date_window": params.date_window,
            "min_salary": params.min_salary,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    tmpl = load_prompt("query_expand")
    raw = f"{tmpl.name}:{tmpl.version}\n{blob}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _cache_get(db: Session, content_hash: str, prompt_version: str) -> list[str] | None:
    row = (
        db.query(QueryExpansionCache)
        .filter(
            QueryExpansionCache.content_hash == content_hash,
            QueryExpansionCache.prompt_version == prompt_version,
        )
        .one_or_none()
    )
    if row is None:
        return None
    try:
        data = json.loads(row.expansions_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, list):
        return None
    queries = [str(q).strip() for q in data if str(q).strip()]
    return queries or None

def _cache_put(db: Session, content_hash: str, prompt_version: str, queries: list[str]) -> None:
    payload = json.dumps(queries, ensure_ascii=False)
    existing = db.query(QueryExpansionCache).filter(QueryExpansionCache.content_hash == content_hash).one_or_none()
    try:
        if existing is not None:
            existing.prompt_version = prompt_version
            existing.expansions_json = payload
            db.add(existing)
        else:
            db.add(
                QueryExpansionCache(
                    content_hash=content_hash,
                    prompt_version=prompt_version,
                    expansions_json=payload,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("query_expand.cache_put_failed", error=str(exc))

def _build_prompt(profile: ResumeProfile, params: SearchParams) -> str:
    tmpl = load_prompt("query_expand")
    lines = [
        tmpl.body.strip(),
        "",
        f"Title: {profile.title}",
        f"Years of experience: {profile.years_of_experience}",
        f"Location: {profile.location}",
        f"Skills: {', '.join(profile.skills[:15])}",
        f"Summary: {(profile.summary or '')[:300]}",
        f"Intent remote_mode: {params.remote_mode}",
        f"Intent employment_type: {params.employment_type}",
        f"Intent seniority: {params.seniority}",
    ]
    return "\n".join(lines)

def _variants_to_queries(variants: list[_ExpandVariant], profile: ResumeProfile) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    loc = (profile.location or "").strip()

    def add(q: str) -> None:
        cleaned = " ".join(q.split()).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)

    for var in variants:
        if var.query.strip():
            add(var.query)
            continue
        title = (var.title or profile.title or "software engineer").strip()
        skills = [s.strip() for s in var.skills if s and s.strip()][:2]
        if skills:
            add(f"{title} {' '.join(skills)}")
        else:
            add(title if not loc else f"{title} in {loc}")
    return out[:5]

def expand_queries(
    profile: ResumeProfile,
    db: Session,
    *,
    params: SearchParams | None = None,
) -> list[str]:
    """Return 3–5 search query strings. Requires LLM when called (use_expand path)."""
    params = params or SearchParams()
    tmpl = load_prompt("query_expand")
    content_hash = expansion_cache_key(profile, params)

    cached = _cache_get(db, content_hash, tmpl.version)
    if cached is not None:
        logger.info("query_expand.cache_hit", count=len(cached))
        return cached[:5]

    response = llm.complete_json(
        _build_prompt(profile, params),
        _ExpandResponse,
        system=tmpl.system or "Return valid JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or 800),
        max_retries=1,
        operation="query_expand",
        prompt_meta=tmpl,
    )
    queries = _variants_to_queries(response.variants, profile)
    llm_count = len(queries)
    if len(queries) < 3:
        title = (profile.title or "software engineer").strip()
        loc = (profile.location or "United States").strip()
        skills = [s.strip() for s in profile.skills if s.strip()][:2]
        fallback = [f"{title} in {loc}"]
        if skills:
            fallback.append(f"{title} {' '.join(skills)}")
        if "remote" not in loc.lower():
            fallback.append(f"{title} remote")
        for q in fallback:
            key = q.lower()
            if key not in {x.lower() for x in queries}:
                queries.append(q)
        queries = queries[:5]
        logger.info(
            "query_expand.padded",
            llm_variants=llm_count,
            final_count=len(queries),
        )

    if not queries:
        from app.errors import ServiceFailingError

        raise ServiceFailingError("LLM", "query expansion returned no variants")

    _cache_put(db, content_hash, tmpl.version, queries)
    logger.info("query_expand.ok", count=len(queries))
    return queries
