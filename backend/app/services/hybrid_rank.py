from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services import embeddings
from app.services.ranking_math import (
    cosine_similarity,
    fuse_final_score,
    normalize_scores,
    reciprocal_rank_fusion,
    tokenize,
)


@dataclass(frozen=True)
class Rankable:
    id: str
    dense_text: str
    lexical_text: str


@dataclass
class RerankResult:
    fit_score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass
class ScoredCandidate:
    id: str
    llm_fit: float
    matched_skills: list[str]
    missing_skills: list[str]
    rationale: str
    rrf_normalized: float
    skill_overlap: float
    recency: float
    experience_fit: float
    requirements_met: float
    final_score: float


def dense_ranking(query_dense_text: str, candidates: list[Rankable]) -> list[str]:
    query_vec = embeddings.embed(query_dense_text)
    candidate_vecs = embeddings.embed_batch([candidate.dense_text for candidate in candidates])
    scored = [
        (candidate.id, cosine_similarity(query_vec, candidate_vec))
        for candidate, candidate_vec in zip(candidates, candidate_vecs, strict=True)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [candidate_id for candidate_id, _ in scored]


def lexical_ranking(query_lexical_text: str, candidates: list[Rankable]) -> list[str]:
    corpus = [tokenize(candidate.lexical_text) for candidate in candidates]
    if not corpus:
        return []
    query = tokenize(query_lexical_text)
    if not query:
        return [candidate.id for candidate in candidates]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query)
    ranked = sorted(range(len(candidates)), key=lambda idx: scores[idx], reverse=True)
    return [candidates[idx].id for idx in ranked]


def hybrid_rank(
    query_dense_text: str,
    query_lexical_text: str,
    candidates: list[Rankable],
    *,
    rerank_fn: Callable[[list[Rankable]], dict[str, RerankResult]] | None = None,
    skill_overlap_fn: Callable[[Rankable], float],
    recency_fn: Callable[[Rankable], float],
    experience_fn: Callable[[Rankable], float] | None = None,
    requirements_fn: Callable[[Rankable], float] | None = None,
    use_llm: bool = True,
    score_pool: Literal["rerank_top_n", "all"] = "rerank_top_n",
    top_n: int,
) -> list[ScoredCandidate]:
    if not candidates:
        return []

    by_id = {candidate.id: candidate for candidate in candidates}
    dense_ids = dense_ranking(query_dense_text, candidates)
    lexical_ids = lexical_ranking(query_lexical_text, candidates)
    rrf_scores = reciprocal_rank_fusion([dense_ids, lexical_ids])
    rrf_normalized = normalize_scores(rrf_scores)

    rrf_ranked_ids = sorted(rrf_scores, key=lambda candidate_id: rrf_scores[candidate_id], reverse=True)
    rerank_ids = rrf_ranked_ids[: settings.RERANK_TOP_N]
    rerank_candidates = [by_id[candidate_id] for candidate_id in rerank_ids if candidate_id in by_id]

    rerank_lookup: dict[str, RerankResult] = {}
    if use_llm and rerank_fn is not None and rerank_candidates:
        rerank_lookup = rerank_fn(rerank_candidates)

    pool_ids = rrf_ranked_ids if score_pool == "all" else rerank_ids

    scored: list[ScoredCandidate] = []
    for candidate_id in pool_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            continue
        if use_llm and rerank_fn is not None and candidate_id in rerank_lookup:
            rerank_item = rerank_lookup[candidate_id]
            llm_fit = rerank_item.fit_score
            matched = rerank_item.matched_skills
            missing = rerank_item.missing_skills
            rationale = rerank_item.rationale
        else:
            llm_fit = 0.0
            matched = []
            missing = []
            rationale = ""
        overlap = skill_overlap_fn(candidate)
        recency = recency_fn(candidate)
        experience = experience_fn(candidate) if experience_fn is not None else 0.5
        requirements = requirements_fn(candidate) if requirements_fn is not None else 0.5
        final = fuse_final_score(
            llm_fit=llm_fit,
            rrf_normalized=rrf_normalized.get(candidate_id, 0.0),
            skill_overlap=overlap,
            recency=recency,
            experience_fit=experience,
            requirements_met=requirements,
        )
        scored.append(
            ScoredCandidate(
                id=candidate_id,
                llm_fit=llm_fit,
                matched_skills=matched,
                missing_skills=missing,
                rationale=rationale,
                rrf_normalized=rrf_normalized.get(candidate_id, 0.0),
                skill_overlap=overlap,
                recency=recency,
                experience_fit=experience,
                requirements_met=requirements,
                final_score=round(final, 1),
            )
        )

    scored.sort(key=lambda item: item.final_score, reverse=True)
    return scored[:top_n]
