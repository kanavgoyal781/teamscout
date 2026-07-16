from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import JdRequirementsCache
from app.prompts import load_prompt
from app.schemas.job_metadata import JobMetadata
from app.schemas.jobs import Job
from app.services import llm
from app.services.ranking.math import extract_requirement_terms

logger = get_logger(__name__)
DEFAULT_MUST_WEIGHT = 2.0
DEFAULT_NICE_WEIGHT = 1.0
RequirementKind = Literal["must", "nice"]
RequirementCategory = Literal["skill", "experience", "domain", "education"]
# Tool/library tokens that force category=skill when present in requirement text
_TOOLISH = re.compile(
    r"(?i)\b(?:python|java(?:script)?|typescript|golang|rust|scala|kotlin|swift|"
    r"sql|nosql|postgres(?:ql)?|mysql|mongodb|redis|spark|hadoop|"
    r"pandas|numpy|scipy|pytorch|tensorflow|scikit[- ]?learn|xgboost|"
    r"plotly|dash|streamlit|matplotlib|seaborn|fastapi|django|flask|react|"
    r"vue|angular|node\.?js|aws|gcp|azure|docker|"
    r"airflow|dbt|snowflake|mlflow|langchain)\b"
)
_SPLIT_TOOLS = re.compile(r"\s*(?:,|/|\bor\b|\band\b)\s*", re.IGNORECASE)
_STUB_HEAD = re.compile(
    r"(?i)^\s*(?:recommended(?:\s+for\s+you)?|people\s+also\s+viewed|similar\s+jobs|"
    r"other\s+openings|jobs\s+you\s+may\s+like|sponsored|promoted)\b"
)


class JdRequirement(BaseModel):
    text: str
    kind: RequirementKind = "must"
    category: RequirementCategory = "skill"
    weight: float = DEFAULT_MUST_WEIGHT


class _DecomposeResponse(BaseModel):
    requirements: list[JdRequirement] = Field(default_factory=list)


def extract_primary_posting(description: str) -> str:
    """Heuristic primary block for multi-job pastes (deterministic path / stub resistance).

    Cuts at recommendation/ad section headers, then prefers the longest remaining block.
    """
    text = (description or "").strip()
    if not text:
        return ""
    # Drop recommendation / similar-jobs tails common on aggregator pages
    cut = re.split(
        r"(?im)^(?:recommended(?:\s+for\s+you)?|people\s+also\s+viewed|similar\s+jobs|"
        r"other\s+openings|jobs\s+you\s+may\s+like|sponsored|promoted)\b.*$",
        text,
        maxsplit=1,
    )
    head = (cut[0] if cut else text).strip()
    if len(head) >= 120:
        return head
    parts = [p.strip() for p in re.split(r"\n{2,}|={3,}|-{4,}", text) if p and p.strip()]
    if len(parts) <= 1:
        return text
    substantive = [p for p in parts if len(p) >= 200 and not _STUB_HEAD.match(p)]
    if substantive:
        return max(substantive, key=len)
    non_stub = [p for p in parts if not _STUB_HEAD.match(p)]
    return max(non_stub or parts, key=len)


def _looks_like_skill_tools(text: str) -> bool:
    return bool(_TOOLISH.search(text or ""))


def _split_compound_skill_atoms(text: str) -> list[str]:
    """Split 'Plotly, Dash, Streamlit, or similar' into atomic skill names when possible."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    # Parenthetical tool lists: "Data visualization skills (Plotly, Dash, Streamlit, or similar)"
    paren = re.search(r"\(([^)]+)\)", cleaned)
    source = paren.group(1) if paren else cleaned
    # Drop soft trailing phrases
    source = re.sub(r"(?i)\b(?:or\s+similar|etc\.?|and\s+similar)\b", "", source)
    parts = [p.strip(" .;") for p in _SPLIT_TOOLS.split(source) if p and p.strip(" .;")]
    atoms = [p for p in parts if _looks_like_skill_tools(p) or (len(p) <= 24 and p[:1].isupper())]
    # Only split when we got multiple tool-like atoms
    if len(atoms) >= 2:
        return atoms
    return [cleaned]


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
        # Force skill category for tool/library names; split compound skill lists into atoms
        texts = [text]
        if category == "skill" or _looks_like_skill_tools(text):
            category = "skill"
            split = _split_compound_skill_atoms(text)
            if len(split) > 1:
                texts = split
        for t in texts:
            key = t.lower()
            if key in seen or len(t) < 2:
                continue
            seen.add(key)
            out.append(JdRequirement(text=t, kind=kind, category=category, weight=weight))
    return out


def deterministic_requirements(job: Job) -> list[JdRequirement]:
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
    # Only scan primary posting — resists stub-card leakage on multi-job pastes
    primary = extract_primary_posting(job.description)
    for term in extract_requirement_terms([], primary):
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
    metadata_hints: JobMetadata | None = None,
) -> list[JdRequirement]:
    if not use_llm:
        return deterministic_requirements(job)
    tmpl = load_prompt("jd_decompose")
    content_hash = jd_content_hash(job)
    if db is not None:
        cached = _cache_get(db, content_hash, tmpl.version)
        if cached is not None:
            return cached
    title = (metadata_hints.title if metadata_hints and metadata_hints.title else job.title) or ""
    company = (metadata_hints.company if metadata_hints and metadata_hints.company else job.company) or ""
    location = (metadata_hints.location if metadata_hints and metadata_hints.location else job.location) or ""
    extra = []
    if metadata_hints and metadata_hints.seniority:
        extra.append(f"Seniority: {metadata_hints.seniority}")
    if metadata_hints and metadata_hints.department:
        extra.append(f"Department: {metadata_hints.department}")
    if metadata_hints and metadata_hints.remote_mode:
        extra.append(f"Remote mode: {metadata_hints.remote_mode}")
    if metadata_hints and (metadata_hints.salary_min or metadata_hints.salary_max):
        extra.append(
            f"Salary: {metadata_hints.salary_min}-{metadata_hints.salary_max} {metadata_hints.salary_currency or ''}".strip()
        )
    prompt = "\n".join(
        [
            tmpl.body.strip(),
            "",
            f"Job title: {title}",
            f"Company: {company}",
            f"Location: {location}",
            *extra,
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
