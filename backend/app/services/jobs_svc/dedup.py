from __future__ import annotations

import re
from datetime import UTC

from app.schemas.jobs import DroppedCounts, Job
from app.services import embeddings
from app.services.ranking.math import cosine_similarity

_WS = re.compile(r"\s+")
_QUALITY_RANK = {"direct_ats": 0, "feed": 1, "aggregator": 2}


def normalize_company(company: str) -> str:
    text = _WS.sub(" ", (company or "").lower()).strip()
    for suffix in (
        " inc.",
        " inc",
        " llc",
        " ltd",
        " ltd.",
        " corp",
        " corp.",
        " co.",
        " company",
        " technologies",
        " technology",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def normalize_title(title: str) -> str:
    return _WS.sub(" ", (title or "").lower()).strip()


def exact_dedupe_key(job: Job) -> str:
    return f"{normalize_company(job.company)}|{normalize_title(job.title)}"


def _posted_sort_key(job: Job) -> tuple[int, float]:
    if job.posted_at is None:
        return (1, 0.0)
    posted = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=UTC)
    return (0, posted.astimezone(UTC).timestamp())


def _dedupe_winner_key(job: Job) -> tuple:
    q = _QUALITY_RANK.get(getattr(job, "source_quality", None) or "aggregator", 2)
    return (q, *_posted_sort_key(job))


def dedupe_exact(jobs: list[Job]) -> tuple[list[Job], DroppedCounts]:
    dropped = DroppedCounts()
    groups: dict[str, list[Job]] = {}
    order: list[str] = []
    for job in jobs:
        key = exact_dedupe_key(job)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(job)
    kept: list[Job] = []
    for key in order:
        group = groups[key]
        winner = sorted(group, key=_dedupe_winner_key)[0].model_copy(update={"duplicates_count": len(group)})
        kept.append(winner)
        dropped.exact_duplicate += len(group) - 1
    return kept, dropped


_CROSS_COMPANY_THRESHOLD = 0.99


def _should_merge_embedding(job: Job, other: Job, sim: float, *, threshold: float) -> bool:
    if sim <= threshold:
        return False
    if normalize_company(job.company) == normalize_company(other.company):
        return True
    return sim > _CROSS_COMPANY_THRESHOLD


def dedupe_embeddings(jobs: list[Job], *, threshold: float = 0.97) -> tuple[list[Job], DroppedCounts]:
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    dropped = DroppedCounts()
    if len(jobs) <= 1:
        return jobs, dropped
    ordered = sorted(jobs, key=_dedupe_winner_key)
    texts = [job.dedup_embedding_text() for job in ordered]
    vectors = embeddings.embed_batch(texts)
    kept_indices: list[int] = []
    kept_vectors: list[list[float]] = []
    duplicates_extra: dict[int, int] = {}
    for idx, (job, vec) in enumerate(zip(ordered, vectors, strict=True)):
        merged_into: int | None = None
        for k_i, k_vec in zip(kept_indices, kept_vectors, strict=True):
            sim = cosine_similarity(vec, k_vec)
            other = ordered[k_i]
            if _should_merge_embedding(job, other, sim, threshold=threshold):
                logger.info(
                    "jobs.embedding_dedup_merge",
                    kept_company=other.company,
                    dropped_company=job.company,
                    title=job.title[:80],
                    sim=round(sim, 4),
                )
                merged_into = k_i
                break
        if merged_into is not None:
            dropped.embedding_duplicate += 1
            duplicates_extra[merged_into] = duplicates_extra.get(merged_into, 0) + 1
            continue
        kept_indices.append(idx)
        kept_vectors.append(vec)
        duplicates_extra[idx] = 0
    result: list[Job] = []
    for idx in kept_indices:
        job = ordered[idx]
        result.append(job.model_copy(update={"duplicates_count": job.duplicates_count + duplicates_extra.get(idx, 0)}))
    return result, dropped


def dedupe_jobs(jobs: list[Job], *, use_embeddings: bool = True) -> tuple[list[Job], DroppedCounts]:
    after_exact, dropped = dedupe_exact(jobs)
    if not use_embeddings or len(after_exact) <= 1:
        return after_exact, dropped
    after_emb, emb_dropped = dedupe_embeddings(after_exact)
    return after_emb, dropped.merge(emb_dropped)
