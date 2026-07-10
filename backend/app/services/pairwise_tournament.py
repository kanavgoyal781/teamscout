"""Close-call pairwise LLM tournament with order-normalized cache + Borda."""
from __future__ import annotations
import hashlib
import random
from dataclasses import dataclass, field
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import PairwiseJudgeCache
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.services import llm, observability
from app.services.jd_decompose import JdRequirement, jd_content_hash
from app.services.ranking_math_align import (
    TOURNAMENT_GAP,
    TOURNAMENT_TOP_K,
    borda_order,
    close_call_band,
    merge_tournament_order,
    order_normalized_pair,
)
logger = get_logger(__name__)
class _PairwiseResponse(BaseModel):
    winner: str  # "A" | "B"
    reason: str = ""
@dataclass
class AlignmentEvidence:
    resume_id: str
    content_hash: str
    coverage: float
    top_units: list[str] = field(default_factory=list)
@dataclass
class TournamentResult:
    ran: bool
    ordered_ids: list[str]
    contested_ids: list[str] = field(default_factory=list)
    comparisons: int = 0
    cache_hits: int = 0
    cost_usd: float = 0.0
    reasons: dict[tuple[str, str], str] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    pairwise_winners: dict[tuple[str, str], str] = field(default_factory=dict)
def tournament_jd_key(job: Job) -> str:
    """JD hash + pairwise_judge prompt version/hash so prompt edits invalidate cache."""
    jd = jd_content_hash(job)
    tmpl = load_prompt("pairwise_judge")
    raw = f"{jd}:pairwise_judge:{tmpl.version}:{tmpl.content_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def pairwise_cache_key(jd_hash: str, hash_a: str, hash_b: str) -> str:
    """Order-normalized symmetric key. `jd_hash` should be `tournament_jd_key` output."""
    a, b = order_normalized_pair(hash_a, hash_b)
    raw = f"{jd_hash}:{a}:{b}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def _cache_get(db: Session | None, key: str) -> tuple[str, str] | None:
    if db is None:
        return None
    row = db.query(PairwiseJudgeCache).filter(PairwiseJudgeCache.cache_key == key).one_or_none()
    if row is None:
        return None
    return row.winner_hash, row.reason or ""
def _cache_put(
    db: Session | None,
    key: str,
    *,
    jd_hash: str,
    hash_a: str,
    hash_b: str,
    winner_hash: str,
    reason: str,
) -> None:
    if db is None:
        return
    a, b = order_normalized_pair(hash_a, hash_b)
    existing = db.query(PairwiseJudgeCache).filter(PairwiseJudgeCache.cache_key == key).one_or_none()
    try:
        if existing is not None:
            existing.winner_hash = winner_hash
            existing.reason = reason
            db.add(existing)
        else:
            db.add(
                PairwiseJudgeCache(
                    cache_key=key,
                    jd_hash=jd_hash,
                    hash_a=a,
                    hash_b=b,
                    winner_hash=winner_hash,
                    reason=reason,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("pairwise_tournament.cache_put_failed", error=str(exc))
def _judge_pair(
    job: Job,
    requirements: list[JdRequirement],
    a: AlignmentEvidence,
    b: AlignmentEvidence,
    *,
    db: Session | None,
    jd_hash: str,
) -> tuple[str, str, bool, float]:
    """Return (winner_resume_id, reason, cache_hit, cost_usd)."""
    key = pairwise_cache_key(jd_hash, a.content_hash, b.content_hash)
    cached = _cache_get(db, key)
    if cached is not None:
        winner_hash, reason = cached
        if winner_hash in (a.content_hash, b.content_hash):
            winner_id = a.resume_id if winner_hash == a.content_hash else b.resume_id
            return winner_id, reason, True, 0.0
    flip = random.random() < 0.5
    left, right = (b, a) if flip else (a, b)
    tmpl = load_prompt("pairwise_judge")
    req_lines = [f"- [{r.kind}/{r.category} w={r.weight}] {r.text}" for r in requirements[:14]]
    prompt = "\n".join(
        [
            tmpl.body.strip(),
            "",
            f"Job: {job.title} @ {job.company}",
            f"Description excerpt: {job.description[:800]}",
            "",
            "Requirements:",
            *req_lines,
            "",
            "Resume A evidence units:",
            *([f"- {u}" for u in left.top_units[:8]] or ["- (none)"]),
            "",
            "Resume B evidence units:",
            *([f"- {u}" for u in right.top_units[:8]] or ["- (none)"]),
        ]
    )
    max_tokens = int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("pairwise_judge"))
    est_in = observability.approx_token_count(prompt + (tmpl.system or ""))
    est_cost = observability.estimate_llm_cost_usd(
        model=settings.LLM_MODEL, input_tokens=est_in, output_tokens=max_tokens // 4
    )
    response = llm.complete_json(
        prompt,
        _PairwiseResponse,
        system=tmpl.system or "Return JSON only.",
        max_tokens=max_tokens,
        operation="pairwise_judge",
        prompt_meta=tmpl,
    )
    winner_label = (response.winner or "").strip().upper()
    if winner_label not in {"A", "B"}:
        from app.errors import ServiceFailingError
        raise ServiceFailingError("LLM", f"pairwise_judge invalid winner: {response.winner!r}")
    winner_ev = left if winner_label == "A" else right
    reason = (response.reason or "").strip()
    _cache_put(
        db,
        key,
        jd_hash=jd_hash,
        hash_a=a.content_hash,
        hash_b=b.content_hash,
        winner_hash=winner_ev.content_hash,
        reason=reason,
    )
    return winner_ev.resume_id, reason, False, float(est_cost)
def maybe_run_tournament(
    job: Job,
    requirements: list[JdRequirement],
    ordered_by_coverage: list[AlignmentEvidence],
    *,
    use_llm: bool = True,
    db: Session | None = None,
    top_k: int = TOURNAMENT_TOP_K,
    gap: float = TOURNAMENT_GAP,
) -> TournamentResult:
    """Round-robin only among candidates within `gap` of the leader (capped at top_k)."""
    ids = [e.resume_id for e in ordered_by_coverage]
    if not use_llm or len(ordered_by_coverage) < 2:
        return TournamentResult(ran=False, ordered_ids=ids)
    cov_pairs = [(e.resume_id, e.coverage) for e in ordered_by_coverage]
    band_ids = close_call_band(cov_pairs, gap=gap, top_k=top_k)
    if len(band_ids) < 2:
        return TournamentResult(ran=False, ordered_ids=ids)
    by_id = {e.resume_id: e for e in ordered_by_coverage}
    contested = [by_id[i] for i in band_ids]
    contested_ids = list(band_ids)
    jd_hash = tournament_jd_key(job)
    pairwise_winners: dict[tuple[str, str], str] = {}
    reasons: dict[tuple[str, str], str] = {}
    comparisons = 0
    cache_hits = 0
    cost_usd = 0.0
    for i in range(len(contested)):
        for j in range(i + 1, len(contested)):
            a = contested[i]
            b = contested[j]
            winner_id, reason, hit, pair_cost = _judge_pair(job, requirements, a, b, db=db, jd_hash=jd_hash)
            key = (a.resume_id, b.resume_id) if a.resume_id <= b.resume_id else (b.resume_id, a.resume_id)
            pairwise_winners[key] = winner_id
            reasons[key] = reason
            comparisons += 1
            cost_usd += pair_cost
            if hit:
                cache_hits += 1
    wins: dict[str, int] = {i: 0 for i in contested_ids}
    for (_a, _b), w in pairwise_winners.items():
        if w in wins:
            wins[w] += 1
    coverage_tb = {e.resume_id: e.coverage for e in contested}
    contested_ordered = borda_order(contested_ids, pairwise_winners, coverage_tiebreak=coverage_tb)
    final = merge_tournament_order(ids, contested_ordered)
    with observability.traced_call(
        "pairwise_tournament",
        model=settings.LLM_MODEL,
        check_llm_ceiling=False,
    ) as trace:
        trace.input_tokens = 0
        trace.output_tokens = 0
        trace.cost_usd = cost_usd
        trace.cache_hit = cache_hits > 0 and cache_hits == comparisons
        logger.info(
            "pairwise_tournament.complete",
            comparisons=comparisons,
            cache_hits=cache_hits,
            contested=contested_ids,
            order=contested_ordered,
            cost_usd=cost_usd,
        )
    return TournamentResult(
        ran=True,
        ordered_ids=final,
        contested_ids=contested_ids,
        comparisons=comparisons,
        cache_hits=cache_hits,
        cost_usd=cost_usd,
        reasons=reasons,
        wins=wins,
        pairwise_winners=pairwise_winners,
    )
