import math
import re
from datetime import UTC, datetime
from app.core.config import settings
from app.errors import ValidationError
from app.services.ranking_config import DEFAULT_MMR_LAMBDA
_TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")
_YOE_PATTERNS = (
    re.compile(
        r"(?:minimum\s+(?:of\s+)?)?(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–|—)\s*(\d{1,2})\s*\+?\s*"
        r"(?:years?|yrs?)(?:\s+of)?(?:\s+(?:experience|exp))?",
        re.I,
    ),
    re.compile(
        r"(?:minimum\s+(?:of\s+)?)?(\d{1,2})\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+(?:experience|exp))?",
        re.I,
    ),
    re.compile(
        r"(?:at\s+least|min(?:imum)?\.?)\s+(\d{1,2})\s*(?:years?|yrs?)",
        re.I,
    ),
)
_SENIORITY_RULES: list[tuple[str, re.Pattern[str], tuple[float, float]]] = [
    ("intern", re.compile(r"\b(intern|internship|apprentice)\b", re.I), (0.0, 1.5)),
    ("junior", re.compile(r"\b(junior|entry[-\s]?level|new\s*grad|associate)\b", re.I), (0.0, 3.0)),
    ("principal", re.compile(r"\b(principal|distinguished|fellow)\b", re.I), (10.0, 30.0)),
    ("staff", re.compile(r"\b(staff|architect)\b", re.I), (8.0, 25.0)),
    ("director", re.compile(r"\b(director|head\s+of|vp\b|vice\s+president)\b", re.I), (10.0, 30.0)),
    ("lead", re.compile(r"\b(tech\s+lead|team\s+lead|engineering\s+lead)\b", re.I), (6.0, 15.0)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b", re.I), (5.0, 12.0)),
    ("mid", re.compile(r"\b(mid[-\s]?level|intermediate)\b", re.I), (2.0, 6.0)),
]
_REQ_SECTION = re.compile(
    r"(?:requirements?|qualifications?|must\s+have|what\s+you.?ll\s+need|"
    r"minimum\s+qualifications?)\s*[:\-]?\s*(.+?)(?=\n\s*\n|preferred|nice\s+to\s+have|responsibilities|$)",
    re.I | re.S,
)
_BULLET_SPLIT = re.compile(r"[\n•\-\*]+\s*")
def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())
def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b): raise ValueError("vector dimension mismatch")
    return sum(x * y for x, y in zip(a, b, strict=True))
def reciprocal_rank_fusion(rankings: list[list[str]], k: int | None = None) -> dict[str, float]:
    rrf_k = k if k is not None else settings.RRF_K
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, job_id in enumerate(ranking):
            scores[job_id] = scores.get(job_id, 0.0) + 1.0 / (rrf_k + rank + 1)
    return scores
def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores: return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    if math.isclose(maximum, minimum): return {key: 1.0 for key in scores}
    span = maximum - minimum
    return {key: (value - minimum) / span for key, value in scores.items()}
def skill_jaccard(resume_skills: list[str], job_skills: list[str]) -> float:
    from app.services.ranking_math_align import skill_equals
    resume = [s.strip() for s in resume_skills if s and s.strip()]
    job = [s.strip() for s in job_skills if s and s.strip()]
    if not resume or not job: return 0.0
    matched, used = 0, set()
    for rs in resume:
        for ji, js in enumerate(job):
            if ji not in used and skill_equals(rs, js):
                matched += 1
                used.add(ji)
                break
    union = len(resume) + len(job) - matched
    return matched / union if union else 0.0
def recency_score(posted_at: datetime | None, *, half_life_days: int | None = None) -> float:
    if posted_at is None: return 0.5
    half_life = half_life_days if half_life_days is not None else settings.RECENCY_HALF_LIFE_DAYS
    now = datetime.now(UTC)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=UTC)
    age_days = max((now - posted.astimezone(UTC)).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / half_life)
def parse_required_years(text: str) -> float | None:
    if not text: return None
    for pattern in _YOE_PATTERNS:
        match = pattern.search(text)
        if not match: continue
        groups = match.groups()
        try:
            if len(groups) >= 2 and groups[1] is not None:
                lo = float(groups[0])
                hi = float(groups[1])
                if 0 <= lo <= hi <= 40:
                    return lo
            years = float(groups[0])
            if 0 <= years <= 40:
                return years
        except (TypeError, ValueError):
            continue
    return None
def infer_seniority(title: str, description: str = "") -> str | None:
    blob = f"{title}\n{description[:800]}"
    for name, pattern, _band in _SENIORITY_RULES:
        if pattern.search(blob): return name
    return None
def seniority_yoe_band(level: str | None) -> tuple[float, float] | None:
    if not level: return None
    for name, _pat, band in _SENIORITY_RULES:
        if name == level: return band
    return None
def experience_fit_score(
    candidate_yoe: float,
    *,
    title: str,
    description: str = "",
) -> float:
    yoe = max(float(candidate_yoe or 0.0), 0.0)
    required = parse_required_years(f"{title}\n{description}")
    level = infer_seniority(title, description)
    band = seniority_yoe_band(level)
    if required is not None:
        if yoe >= required:
            overshoot = yoe - required
            if overshoot <= 2.5:
                base = 1.0
            elif overshoot <= 5:
                base = 0.82
            elif overshoot <= 8:
                base = 0.55
            else:
                base = 0.28  # massively overqualified
        else:
            gap = required - yoe
            if gap <= 0.5:
                base = 0.85
            elif gap <= 1.5:
                base = 0.55
            elif gap <= 3:
                base = 0.28
            else:
                base = 0.08
        if band is not None:
            lo, hi = band
            if yoe < lo - 1:
                base = min(base, 0.35)
            elif yoe > hi + 3:
                base = min(base, 0.45)
        return round(max(0.0, min(1.0, base)), 4)
    if band is not None:
        lo, hi = band
        if lo <= yoe <= hi: return 1.0
        if yoe < lo:
            gap = lo - yoe
            return round(max(0.05, 1.0 - gap * 0.22), 4)
        gap = yoe - hi
        return round(max(0.15, 1.0 - gap * 0.14), 4)
    if yoe <= 0: return 0.45
    return 0.6
def extract_requirement_terms(job_skills: list[str], description: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    def add(term: str) -> None:
        cleaned = term.strip().lower()
        if len(cleaned) < 2 or cleaned in seen:
            return
        if cleaned in {"and", "or", "the", "with", "from", "experience", "years", "year", "plus"}:
            return
        seen.add(cleaned)
        terms.append(cleaned)
    for skill in job_skills:
        add(skill)
    section_match = _REQ_SECTION.search(description or "")
    section = section_match.group(1) if section_match else (description or "")[:1200]
    for chunk in _BULLET_SPLIT.split(section):
        chunk = chunk.strip()
        if not chunk: continue
        if 2 <= len(chunk) <= 40 and not chunk.endswith("."):
            chunk = re.sub(r"^\d+\+?\s*years?\s+(?:of\s+)?", "", chunk, flags=re.I)
            if chunk:
                add(chunk)
        for token in tokenize(chunk):
            if len(token) >= 3:
                add(token)
        if len(terms) >= 24:
            break
    return terms[:24]
def requirements_met_score(
    *,
    profile_skills: list[str],
    profile_text: str,
    job_skills: list[str],
    job_description: str,
) -> float:
    from app.services.ranking_math_align import phrase_in_text
    terms = extract_requirement_terms(job_skills, job_description)
    if not terms: return 0.5
    skill_blob = " ".join(s for s in profile_skills if s)
    hay = f"{profile_text or ''}\n{skill_blob}"
    hits = 0
    for term in terms:
        if phrase_in_text(term, hay):
            hits += 1
    return round(hits / len(terms), 4)
def validate_ranking_weights() -> None:
    total = (
        settings.RANKING_WEIGHT_LLM
        + settings.RANKING_WEIGHT_RRF
        + settings.RANKING_WEIGHT_SKILLS
        + settings.RANKING_WEIGHT_RECENCY
        + settings.RANKING_WEIGHT_EXPERIENCE
        + settings.RANKING_WEIGHT_REQUIREMENTS
        + settings.RANKING_WEIGHT_CROSS_ENCODER
    )
    if not math.isclose(total, 1.0, abs_tol=0.01): raise ValidationError(
            f"Ranking weights must sum to 1.0, got {total}",
            details={
                "llm": settings.RANKING_WEIGHT_LLM,
                "rrf": settings.RANKING_WEIGHT_RRF,
                "skills": settings.RANKING_WEIGHT_SKILLS,
                "recency": settings.RANKING_WEIGHT_RECENCY,
                "experience": settings.RANKING_WEIGHT_EXPERIENCE,
                "requirements": settings.RANKING_WEIGHT_REQUIREMENTS,
                "cross_encoder": settings.RANKING_WEIGHT_CROSS_ENCODER,
            },
        )
def fuse_final_score(
    *,
    llm_fit: float,
    rrf_normalized: float,
    skill_overlap: float,
    recency: float,
    experience_fit: float = 0.5,
    requirements_met: float = 0.5,
    cross_encoder: float = 0.0,
) -> float:
    validate_ranking_weights()
    return (
        settings.RANKING_WEIGHT_LLM * (llm_fit / 100.0)
        + settings.RANKING_WEIGHT_RRF * rrf_normalized
        + settings.RANKING_WEIGHT_SKILLS * skill_overlap
        + settings.RANKING_WEIGHT_RECENCY * recency
        + settings.RANKING_WEIGHT_EXPERIENCE * experience_fit
        + settings.RANKING_WEIGHT_REQUIREMENTS * requirements_met
        + settings.RANKING_WEIGHT_CROSS_ENCODER * cross_encoder
    ) * 100.0
def mmr(
    item_ids: list[str],
    relevance: dict[str, float],
    pairwise_similarity: dict[tuple[str, str], float],
    *,
    lambda_: float = DEFAULT_MMR_LAMBDA,
    k: int | None = None,
) -> list[str]:
    if not item_ids: return []
    seen: set[str] = set()
    candidates: list[str] = []
    for item_id in item_ids:
        if item_id not in seen:
            seen.add(item_id)
            candidates.append(item_id)
    limit = len(candidates) if k is None else max(0, min(k, len(candidates)))
    if limit == 0: return []
    def sim(a: str, b: str) -> float:
        if a == b: return 1.0
        if (a, b) in pairwise_similarity:
            return pairwise_similarity[(a, b)]
        if (b, a) in pairwise_similarity: return pairwise_similarity[(b, a)]
        return 0.0
    by_rel = sorted(candidates, key=lambda i: (-relevance.get(i, 0.0), i))
    selected: list[str] = []
    remaining = set(candidates)
    while remaining and len(selected) < limit:
        if not selected:
            best = by_rel[0]
            selected.append(best)
            remaining.remove(best)
            continue
        best_id: str | None = None
        best_score = float("-inf")
        for item_id in by_rel:
            if item_id not in remaining:
                continue
            rel = relevance.get(item_id, 0.0)
            max_sim = max(sim(item_id, s) for s in selected)
            score = lambda_ * rel - (1.0 - lambda_) * max_sim
            if best_id is None or score > best_score:
                best_score = score
                best_id = item_id
        if best_id is None:
            break
        selected.append(best_id)
        remaining.remove(best_id)
    return selected
def apply_company_soft_cap(
    ordered_ids: list[str],
    company_by_id: dict[str, str],
    *,
    top_k: int = 10,
    max_per_company: int = 3,
    pool_company_count: int | None = None,
) -> list[str]:
    if not ordered_ids or top_k <= 0: return list(ordered_ids)
    if pool_company_count is None:
        companies = {company_by_id.get(i, "") for i in ordered_ids}
        companies.discard("")
        pool_count = len(companies)
    else:
        pool_count = pool_company_count
    if pool_count < top_k: return list(ordered_ids)
    head: list[str] = []
    deferred: list[str] = []
    counts: dict[str, int] = {}
    for item_id in ordered_ids:
        if len(head) >= top_k:
            deferred.append(item_id)
            continue
        company = company_by_id.get(item_id, "")
        used = counts.get(company, 0)
        if company and used >= max_per_company:
            deferred.append(item_id)
            continue
        head.append(item_id)
        if company:
            counts[company] = used + 1
    rest = []
    for item_id in deferred:
        if len(head) < top_k:
            company = company_by_id.get(item_id, "")
            used = counts.get(company, 0)
            if company and used >= max_per_company:
                rest.append(item_id)
                continue
            head.append(item_id)
            if company:
                counts[company] = used + 1
        else:
            rest.append(item_id)
    return head + rest
