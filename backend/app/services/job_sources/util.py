"""Board cache (6h), post-fetch filter, ATS slugs."""
from __future__ import annotations
import html as html_lib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.logging import get_logger
from app.db.models import JobCache
from app.schemas.jobs import Job
from app.services.job_filters import DATE_WINDOW_DAYS, infer_remote_mode
from app.services.job_sources.base import FetchCriteria
logger = get_logger(__name__)
BOARD_TTL = timedelta(hours=6)
_ATS_CONFIG = Path(__file__).resolve().parents[4] / "configs" / "ats_companies.json"
_HTML_TAG, _WS, _TOKEN = re.compile(r"<[^>]+>"), re.compile(r"\s+"), re.compile(r"[a-z0-9+#.]{2,}", re.I)
_REMOTE = frozenset({"", "remote", "anywhere", "worldwide", "global", "unknown"})
_US_PROF = frozenset({"united states", "usa", "us", "u.s.", "u.s.a."})
_US = frozenset({"us", "usa", "united", "states", "america", "american"})
_NON_US = frozenset("japan tokyo china india bangalore uk london germany berlin france paris canada toronto sydney australia singapore korea seoul ireland dublin netherlands amsterdam brazil mexico israel emea apac".split())
def strip_html(text: str) -> str:
    return _WS.sub(" ", _HTML_TAG.sub(" ", html_lib.unescape(text or ""))).strip()
def parse_iso(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / (1000 if value > 1e12 else 1), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            n = int(text)
            return datetime.fromtimestamp(n / (1000 if n > 1e12 else 1), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        posted = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=UTC)
    return posted.astimezone(UTC)
def load_ats_slugs() -> dict[str, list[str]]:
    if not _ATS_CONFIG.is_file():
        logger.warning("jobs.ats_config_missing", path=str(_ATS_CONFIG))
        return {"greenhouse": [], "lever": [], "ashby": []}
    raw = json.loads(_ATS_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("ats_companies.json must be an object of source→slug lists")
    out: dict[str, list[str]] = {}
    for key in ("greenhouse", "lever", "ashby"):
        vals = raw.get(key) or []
        if not isinstance(vals, list):
            raise ValueError(f"ats_companies.json[{key}] must be a list")
        out[key] = [str(s).strip() for s in vals if str(s).strip()]
    return out
def _board_row(db: Session, source: str, slug: str):
    return db.query(JobCache).filter(JobCache.source == f"{source}_board", JobCache.source_job_id == slug).one_or_none()
def board_cache_get(db: Session | None, source: str, slug: str) -> object | None:
    if db is None:
        return None
    row = _board_row(db, source, slug)
    if row is None or not row.payload_json:
        return None
    fetched = row.fetched_at
    if fetched is not None:
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if datetime.now(UTC) - fetched.astimezone(UTC) > BOARD_TTL:
            return None
    try:
        return json.loads(row.payload_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
def board_cache_set(db: Session | None, source: str, slug: str, payload: object) -> None:
    if db is None:
        return
    body, now = json.dumps(payload), datetime.now(UTC).replace(tzinfo=None)
    existing = _board_row(db, source, slug)
    if existing is not None:
        existing.payload_json, existing.title, existing.fetched_at = body, f"board:{slug}", now
        db.add(existing)
    else:
        db.add(JobCache(source=f"{source}_board", source_job_id=slug, title=f"board:{slug}", payload_json=body, fetched_at=now))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback(); raise
def board_cache_delete(db: Session | None, source: str, slug: str) -> None:
    if db is None:
        return
    row = _board_row(db, source, slug)
    if row is None:
        return
    db.delete(row)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback(); raise
def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN.finditer(text or "")}
def _token_hit(term: str, tokens: set[str]) -> bool:
    t = (term or "").strip().lower()
    if len(t) < 2:
        return False
    if " " in t or "/" in t:
        parts = [p for p in re.split(r"[\s/]+", t) if len(p) >= 2]
        return bool(parts) and all(p in tokens for p in parts)
    return t in tokens
_GENERIC_ROLE = frozenset("engineer engineering developer development programmer".split())
_TECH_TITLE = frozenset(
    "software swe sde backend frontend front fullstack full stack platform infra infrastructure "
    "devops sre ml ai data machine learning systems security cloud mobile ios android web python "
    "java golang rust typescript javascript react distributed reliability".split()
)
def _role_or_skill_match(job: Job, criteria: FetchCriteria) -> bool:
    role, skills = criteria.role_tokens(), criteria.skill_terms()
    if not role and not skills:
        return True
    title_toks = _tokens(job.title or "")
    if any(t not in _GENERIC_ROLE and _token_hit(t, title_toks) for t in role):
        return True
    if (title_toks & _GENERIC_ROLE) and (title_toks & _TECH_TITLE):
        return True
    from app.services.ranking_math_align import phrase_in_text
    title, desc = job.title or "", (job.description or "")[:800]
    return any(phrase_in_text(s, title) or phrase_in_text(s, desc) for s in skills)
def _location_ok(job: Job, criteria: FetchCriteria) -> bool:
    prof = (criteria.profile.location or "").strip().lower()
    job_loc = (job.location or "").strip().lower()
    if (job.remote_mode or "") == "remote" or "remote" in job_loc or job_loc in _REMOTE or not prof or prof in _REMOTE:
        return True
    jtoks = _tokens(job_loc)
    if prof in _US_PROF or (_tokens(prof) & _US):
        return bool(jtoks & _US) or not bool(jtoks & _NON_US)
    return bool(_tokens(prof) & jtoks) if jtoks else True
def job_matches_criteria(job: Job, criteria: FetchCriteria) -> bool:
    params = criteria.params
    if not _role_or_skill_match(job, criteria):
        return False
    days = DATE_WINDOW_DAYS.get(params.date_window, 30)
    if job.posted_at is not None:
        posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
        if posted.astimezone(UTC) < datetime.now(UTC) - timedelta(days=days):
            return False
    if params.remote_mode != "any" and params.remote_mode_pref == "hard":
        mode = (job.remote_mode or infer_remote_mode(location=job.location, description=job.description[:600])).lower()
        if mode not in {"unknown", params.remote_mode}:
            return False
    return _location_ok(job, criteria)
def filter_jobs(jobs: list[Job], criteria: FetchCriteria) -> list[Job]:
    return [j for j in jobs if job_matches_criteria(j, criteria)]
