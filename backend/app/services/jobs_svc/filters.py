from __future__ import annotations
import re
from datetime import UTC, datetime, timedelta
from app.schemas.jobs import DroppedCounts, Job, SearchParams
from app.services.jobs_svc.geo import job_geo_match
from app.services.ranking.math import infer_seniority
_REMOTE_RE = re.compile(r"\b(remote|work\s+from\s+home|wfh|distributed)\b", re.I)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.I)
_ONSITE_RE = re.compile(r"\b(on[-\s]?site|in[-\s]?office|office[-\s]?based)\b", re.I)
_SALARY_PATTERNS = (
    re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?(?:\s*[-–—to]+\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?)?",
    ),
    re.compile(
        r"([\d,]+(?:\.\d+)?)\s*([kK])\s*(?:[-–—to]+|/|to)\s*([\d,]+(?:\.\d+)?)\s*([kK])?\s*"
        r"(?:usd|dollars|salary|base|compensation)?",
        re.I,
    ),
    re.compile(
        r"(?:salary|base|compensation|pay)\s*(?:of|is|:)?\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?",
        re.I,
    ),
)
_EMPLOYMENT_MAP = {
    "FULLTIME": "fulltime",
    "FULL_TIME": "fulltime",
    "FULL-TIME": "fulltime",
    "CONTRACTOR": "contractor",
    "CONTRACT": "contractor",
    "PARTTIME": "parttime",
    "PART_TIME": "parttime",
    "PART-TIME": "parttime",
    "INTERN": "intern",
}
DATE_WINDOW_TO_JSEARCH = {
    "day": "today",
    "3days": "3days",
    "week": "week",
    "month": "month",
}
DATE_WINDOW_DAYS = {
    "day": 1,
    "3days": 3,
    "week": 7,
    "month": 30,
}
SOFT_BOOST_POINTS = 5.0
_SENIORITY_MATCH: dict[str, set[str]] = {
    "intern": {"intern"},
    "junior": {"junior"},
    "mid": {"mid"},
    "senior": {"senior"},
    "lead": {"lead", "staff", "principal", "director"},
}
def _parse_money_token(num: str, k_suffix: str | None) -> float | None:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    if k_suffix and k_suffix.lower() == "k":
        value *= 1000.0
    if value < 1000 and not k_suffix:
        if value < 15: return None
        if value <= 500:
            value *= 1000.0  # "120-150" style without k
    return value
def parse_salary_min(
    *,
    structured_min: float | None = None,
    structured_max: float | None = None,
    description: str = "",
) -> tuple[float | None, bool]:
    if structured_min is not None and structured_min > 0: return float(structured_min), False
    if structured_max is not None and structured_max > 0:
        return float(structured_max), False
    text = description or ""
    best: float | None = None
    for pattern in _SALARY_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if not groups:
                continue
            lo = _parse_money_token(groups[0], groups[1] if len(groups) > 1 else None)
            if lo is None:
                continue
            if best is None or lo < best:
                best = lo
    if best is not None and best >= 1000: return best, False
    return None, True
def infer_remote_mode(
    *,
    location: str,
    description: str,
    is_remote_flag: bool | None = None,
) -> str:
    blob = f"{location}\n{description[:600]}"
    if is_remote_flag is True: return "remote"
    if _HYBRID_RE.search(blob):
        return "hybrid"
    if _REMOTE_RE.search(blob) or (location or "").strip().lower() == "remote": return "remote"
    if _ONSITE_RE.search(blob):
        return "onsite"
    if location and location.strip().lower() not in {"", "remote", "worldwide", "anywhere"}:
        if not _REMOTE_RE.search(location): return "onsite"
    return "unknown"
def normalize_employment_type(raw: str | None) -> str | None:
    if not raw: return None
    key = str(raw).strip().upper().replace(" ", "_")
    if key in _EMPLOYMENT_MAP: return _EMPLOYMENT_MAP[key]
    lowered = str(raw).strip().lower()
    if "contract" in lowered: return "contractor"
    if "full" in lowered:
        return "fulltime"
    if "part" in lowered: return "parttime"
    return "unknown"
def annotate_job(
    job: Job,
    *,
    is_remote_flag: bool | None = None,
    structured_employment: str | None = None,
    structured_salary_min: float | None = None,
    structured_salary_max: float | None = None,
) -> Job:
    seniority = infer_seniority(job.title, job.description)
    remote = infer_remote_mode(
        location=job.location,
        description=job.description,
        is_remote_flag=is_remote_flag,
    )
    employment = normalize_employment_type(structured_employment) or job.employment_type
    if employment is None:
        desc = job.description[:400].lower()
        if "contract" in desc:
            employment = "contractor"
        elif "part-time" in desc or "part time" in desc:
            employment = "parttime"
        elif "full-time" in desc or "full time" in desc or "fulltime" in desc:
            employment = "fulltime"
        else:
            employment = "unknown"
    salary_min, salary_unknown = parse_salary_min(
        structured_min=structured_salary_min if structured_salary_min is not None else job.salary_min,
        structured_max=structured_salary_max,
        description=job.description,
    )
    return job.model_copy(
        update={
            "seniority": seniority or job.seniority,
            "remote_mode": remote,
            "employment_type": employment,
            "salary_min": salary_min,
            "salary_unknown": salary_unknown,
        }
    )
def _seniority_matches(wanted: str, actual: str | None) -> bool:
    if wanted == "any": return True
    if not actual:
        return False
    allowed = _SENIORITY_MATCH.get(wanted, {wanted})
    return actual.lower() in allowed
def _employment_matches(wanted: str, actual: str | None) -> bool:
    if wanted == "any": return True
    if not actual:
        return False
    return actual == wanted
def apply_hard_filters(
    jobs: list[Job],
    params: SearchParams,
    *,
    now: datetime | None = None,
) -> tuple[list[Job], DroppedCounts]:
    dropped = DroppedCounts()
    window_days = DATE_WINDOW_DAYS.get(params.date_window, 30)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=window_days)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    kept: list[Job] = []
    for job in jobs:
        if job.posted_at is not None:
            posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
            if posted.astimezone(UTC) < cutoff:
                dropped.recency += 1
                continue
        if params.seniority != "any" and params.seniority_pref == "hard":
            actual_sen = (job.seniority or "").strip().lower()
            if actual_sen and actual_sen != "unknown":
                if not _seniority_matches(params.seniority, job.seniority):
                    dropped.hard_seniority += 1
                    continue
        if params.remote_mode != "any" and params.remote_mode_pref == "hard":
            actual = (job.remote_mode or "unknown").lower()
            if actual != "unknown" and actual != params.remote_mode:
                dropped.hard_remote += 1
                continue
        if params.employment_type != "any" and params.employment_type_pref == "hard":
            if not _employment_matches(params.employment_type, job.employment_type):
                if job.employment_type and job.employment_type != "unknown":
                    dropped.hard_employment += 1
                    continue
        if params.min_salary is not None and params.min_salary_pref == "hard":
            if not job.salary_unknown and job.salary_min is not None:
                if job.salary_min < float(params.min_salary):
                    dropped.hard_salary += 1
                    continue
        uc = (params.location_country or "").strip().upper() or None
        if uc and params.location_country_pref == "hard":
            geo = job_geo_match(
                user_country=uc, job_location=job.location, job_description=job.description,
                remote_mode=job.remote_mode, include_worldwide=bool(params.include_worldwide_remote),
            )
            if geo == "hq_mismatch":
                dropped.hard_location += 1
                continue
        kept.append(job)
    return kept, dropped
def soft_boost_score(job: Job, params: SearchParams, base_score: float) -> float:
    from app.core.config import settings
    score = float(base_score)
    if params.remote_mode != "any" and params.remote_mode_pref == "soft":
        if (job.remote_mode or "").lower() == params.remote_mode:
            score += SOFT_BOOST_POINTS
    if params.employment_type != "any" and params.employment_type_pref == "soft":
        if job.employment_type == params.employment_type:
            score += SOFT_BOOST_POINTS
    if params.seniority != "any" and params.seniority_pref == "soft":
        if _seniority_matches(params.seniority, job.seniority):
            score += SOFT_BOOST_POINTS
    if params.min_salary is not None and params.min_salary_pref == "soft":
        if not job.salary_unknown and job.salary_min is not None and job.salary_min >= float(params.min_salary):
            score += SOFT_BOOST_POINTS
    uc = (params.location_country or "").strip().upper() or None
    if uc and params.location_country_pref == "soft":
        geo = job_geo_match(
            user_country=uc, job_location=job.location, job_description=job.description,
            remote_mode=job.remote_mode, include_worldwide=bool(params.include_worldwide_remote),
        )
        if geo in {"match", "worldwide"}: score += SOFT_BOOST_POINTS
        elif geo == "hq_mismatch":
            score -= float(getattr(settings, "LOCATION_MISMATCH_PENALTY", 18.0) or 18.0)
    boost = float(getattr(settings, "RANKING_DIRECT_ATS_BOOST", 0.0) or 0.0)
    if boost > 0 and getattr(job, "source_quality", None) == "direct_ats":
        score += boost
    return max(0.0, min(100.0, round(score, 1)))
def jsearch_params_from_search(params: SearchParams) -> dict[str, str]:
    employment = "FULLTIME,CONTRACTOR,PARTTIME"
    if params.employment_type_pref == "hard" and params.employment_type == "fulltime": employment = "FULLTIME"
    elif params.employment_type_pref == "hard" and params.employment_type == "contractor": employment = "CONTRACTOR"
    out = {"page": "1", "num_pages": "3", "date_posted": DATE_WINDOW_TO_JSEARCH.get(params.date_window, "month"), "employment_types": employment}
    if params.remote_mode == "remote" and params.remote_mode_pref == "hard": out["remote_jobs_only"] = "true"
    return out
