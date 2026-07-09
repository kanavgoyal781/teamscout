import math
import re
from datetime import UTC, datetime

from app.core.config import settings
from app.errors import ValidationError

_TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("vector dimension mismatch")
    return sum(x * y for x, y in zip(a, b, strict=True))


def reciprocal_rank_fusion(rankings: list[list[str]], k: int | None = None) -> dict[str, float]:
    rrf_k = k if k is not None else settings.RRF_K
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, job_id in enumerate(ranking):
            scores[job_id] = scores.get(job_id, 0.0) + 1.0 / (rrf_k + rank + 1)
    return scores


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    minimum = min(values)
    maximum = max(values)
    if math.isclose(maximum, minimum):
        return {key: 1.0 for key in scores}
    span = maximum - minimum
    return {key: (value - minimum) / span for key, value in scores.items()}


def skill_jaccard(resume_skills: list[str], job_skills: list[str]) -> float:
    resume = {skill.strip().lower() for skill in resume_skills if skill.strip()}
    job = {skill.strip().lower() for skill in job_skills if skill.strip()}
    if not resume and not job:
        return 0.0
    union = resume | job
    if not union:
        return 0.0
    return len(resume & job) / len(union)


def recency_score(posted_at: datetime | None, *, half_life_days: int | None = None) -> float:
    if posted_at is None:
        return 0.5
    half_life = half_life_days if half_life_days is not None else settings.RECENCY_HALF_LIFE_DAYS
    now = datetime.now(UTC)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=UTC)
    age_days = max((now - posted.astimezone(UTC)).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / half_life)


def validate_ranking_weights() -> None:
    total = (
        settings.RANKING_WEIGHT_LLM
        + settings.RANKING_WEIGHT_RRF
        + settings.RANKING_WEIGHT_SKILLS
        + settings.RANKING_WEIGHT_RECENCY
    )
    if not math.isclose(total, 1.0, abs_tol=0.01):
        raise ValidationError(
            f"Ranking weights must sum to 1.0, got {total}",
            details={
                "llm": settings.RANKING_WEIGHT_LLM,
                "rrf": settings.RANKING_WEIGHT_RRF,
                "skills": settings.RANKING_WEIGHT_SKILLS,
                "recency": settings.RANKING_WEIGHT_RECENCY,
            },
        )


def fuse_final_score(
    *,
    llm_fit: float,
    rrf_normalized: float,
    skill_overlap: float,
    recency: float,
) -> float:
    validate_ranking_weights()
    return (
        settings.RANKING_WEIGHT_LLM * (llm_fit / 100.0)
        + settings.RANKING_WEIGHT_RRF * rrf_normalized
        + settings.RANKING_WEIGHT_SKILLS * skill_overlap
        + settings.RANKING_WEIGHT_RECENCY * recency
    ) * 100.0
