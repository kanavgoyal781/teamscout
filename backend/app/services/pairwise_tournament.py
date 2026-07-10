from __future__ import annotations
import hashlib
import random
import re
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
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
    borda_points_for_margin,
    close_call_band,
    merge_tournament_order,
    order_normalized_pair,
)
logger = get_logger(__name__)
_WEIGHT_NOTATION = re.compile(r"\s*\(w=\d+(?:\.\d+)?\)")
class _PairwiseResponse(BaseModel):
    winner: str
    margin: str = "decisive"
    key_differences: list[str] = Field(default_factory=list)
    reason: str = ""
@dataclass
class AlignmentEvidence:
    resume_id: str
    content_hash: str
    coverage: float
    top_units: list[str] = field(default_factory=list)
    alignment_rows: list[dict] = field(default_factory=list)
    filename: str = ""
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
    borda_scores: dict[str, float] = field(default_factory=dict)
    pairwise_winners: dict[tuple[str, str], str] = field(default_factory=dict)
    pairwise_margins: dict[tuple[str, str], str] = field(default_factory=dict)
    overrode_coverage: bool = False
def tournament_jd_key(job: Job) -> str:
    jd = jd_content_hash(job)
    tmpl = load_prompt("pairwise_judge")
    raw = f"{jd}:pairwise_judge:{tmpl.version}:{tmpl.content_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def pairwise_cache_key(jd_hash: str, hash_a: str, hash_b: str) -> str:
    a, b = order_normalized_pair(hash_a, hash_b)
    return hashlib.sha256(f"{jd_hash}:{a}:{b}".encode()).hexdigest()
def strip_weight_notation(text: str) -> str:
    return _WEIGHT_NOTATION.sub("", text or "").strip()
_AB_COMPARE = re.compile(
    r"\b(?:beats|wins|leads|shows|has|is|over|with|than|versus|vs\.?|prefer|between|and|or)\b",
    re.IGNORECASE,
)
def materialize_ab_labels(text: str, *, name_a: str, name_b: str) -> str:
    out, pa, pb = text or "", "<<PAIR_LEFT>>", "<<PAIR_RIGHT>>"
    for pat, rep in ((r"\bResume A\b", pa), (r"\bResume B\b", pb), (r"\bresume A\b", pa), (r"\bresume B\b", pb)):
        out = re.sub(pat, rep, out)
    if _AB_COMPARE.search(out) and re.search(r"\b[AB]\b", out):
        out = re.sub(r"\bA\b", pa, out)
        out = re.sub(r"\bB\b", pb, out)
    return strip_weight_notation(out.replace(pa, name_a).replace(pb, name_b))
def _cache_get(db: Session | None, key: str) -> tuple[str, str] | None:
    if db is None: return None
    row = db.query(PairwiseJudgeCache).filter(PairwiseJudgeCache.cache_key == key).one_or_none()
    return (row.winner_hash, row.reason or "") if row else None
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
            existing.winner_hash, existing.reason = winner_hash, reason
            db.add(existing)
        else:
            db.add(
                PairwiseJudgeCache(
                    cache_key=key, jd_hash=jd_hash, hash_a=a, hash_b=b,
                    winner_hash=winner_hash, reason=reason,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("pairwise_tournament.cache_put_failed", error=str(exc))
def _format_must_rows(rows: list[dict]) -> list[str]:
    lines: list[str] = []
    for r in rows:
        if str(r.get("kind") or "must") != "must": continue
        req = strip_weight_notation(str(r.get("requirement") or ""))
        try:
            score_s = f"{float(r.get('evidence_score')):.2f}"
        except (TypeError, ValueError):
            score_s = "?"
        lines.append(f"- {req} | evidence: {r.get('evidence_unit') or '(none)'} | score: {score_s}")
    return lines
def _nice_summary(rows: list[dict]) -> str:
    nice = [r for r in rows if str(r.get("kind") or "") == "nice"]
    if not nice: return "nice-to-have: none listed"
    return f"nice-to-have: {sum(1 for r in nice if r.get('status') == 'hit')}/{len(nice)} hit"
def _judge_pair(
    job: Job,
    requirements: list[JdRequirement],
    a: AlignmentEvidence,
    b: AlignmentEvidence,
    *,
    db: Session | None,
    jd_hash: str,
) -> tuple[str, str, str, bool, float]:
    key = pairwise_cache_key(jd_hash, a.content_hash, b.content_hash)
    cached = _cache_get(db, key)
    if cached is not None:
        winner_hash, reason = cached
        if winner_hash in (a.content_hash, b.content_hash):
            winner_id = a.resume_id if winner_hash == a.content_hash else b.resume_id
            margin = "decisive"
            if reason.startswith("[slight] "):
                margin, reason = "slight", reason[len("[slight] "):]
            elif reason.startswith("[decisive] "):
                reason = reason[len("[decisive] "):]
            return winner_id, reason, margin, True, 0.0
    flip = random.random() < 0.5
    left, right = (b, a) if flip else (a, b)
    name_a, name_b = left.filename or left.resume_id, right.filename or right.resume_id
    tmpl = load_prompt("pairwise_judge")
    must_a = _format_must_rows(left.alignment_rows) or [f"- (unit) {u}" for u in left.top_units[:12]]
    must_b = _format_must_rows(right.alignment_rows) or [f"- (unit) {u}" for u in right.top_units[:12]]
    req_lines = [
        f"- [{r.kind}/{r.category} weight={float(r.weight):.2f}] {strip_weight_notation(r.text)}"
        for r in requirements[:14]
    ]
    prompt = "\n".join([
        tmpl.body.strip(), "",
        f"Job: {job.title} @ {job.company}",
        f"Description excerpt: {job.description[:800]}", "",
        "Requirements (weight is internal scoring weight; prefer higher-weight musts):",
        *req_lines, "",
        f"Resume A ({name_a}) must-requirement alignment:",
        *(must_a or ["- (none)"]), _nice_summary(left.alignment_rows), "",
        f"Resume B ({name_b}) must-requirement alignment:",
        *(must_b or ["- (none)"]), _nice_summary(right.alignment_rows),
    ])
    max_tokens = int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("pairwise_judge"))
    est_in = observability.approx_token_count(prompt + (tmpl.system or ""))
    est_cost = observability.estimate_llm_cost_usd(
        model=settings.LLM_MODEL, input_tokens=est_in, output_tokens=max_tokens // 4
    )
    response = llm.complete_json(
        prompt, _PairwiseResponse, system=tmpl.system or "Return JSON only.",
        max_tokens=max_tokens, operation="pairwise_judge", prompt_meta=tmpl,
    )
    winner_label = (response.winner or "").strip().upper()
    if winner_label not in {"A", "B"}:
        from app.errors import ServiceFailingError
        raise ServiceFailingError("LLM", f"pairwise_judge invalid winner: {response.winner!r}")
    margin_raw = (response.margin or "decisive").strip().lower()
    margin = margin_raw if margin_raw in {"decisive", "slight"} else "decisive"
    winner_ev = left if winner_label == "A" else right
    diffs = [strip_weight_notation(d) for d in (response.key_differences or []) if d and str(d).strip()]
    reason_core = strip_weight_notation(response.reason or "") or "; ".join(diffs[:3])
    reason = materialize_ab_labels(reason_core, name_a=name_a, name_b=name_b)
    if not diffs and len(reason) < 24:
        from app.errors import ServiceFailingError
        raise ServiceFailingError(
            "LLM", "pairwise_judge missing key_differences / substantive reason (anti skill-token-only)"
        )
    _cache_put(
        db, key, jd_hash=jd_hash, hash_a=a.content_hash, hash_b=b.content_hash,
        winner_hash=winner_ev.content_hash, reason=f"[{margin}] {reason}",
    )
    return winner_ev.resume_id, reason, margin, False, float(est_cost)
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
    ids = [e.resume_id for e in ordered_by_coverage]
    if not use_llm or len(ordered_by_coverage) < 2: return TournamentResult(ran=False, ordered_ids=ids)
    band_ids = close_call_band([(e.resume_id, e.coverage) for e in ordered_by_coverage], gap=gap, top_k=top_k)
    if len(band_ids) < 2: return TournamentResult(ran=False, ordered_ids=ids)
    by_id = {e.resume_id: e for e in ordered_by_coverage}
    contested = [by_id[i] for i in band_ids]
    contested_ids = list(band_ids)
    jd_hash = tournament_jd_key(job)
    pairwise_winners: dict[tuple[str, str], str] = {}
    pairwise_margins: dict[tuple[str, str], str] = {}
    pairwise_points: dict[tuple[str, str], float] = {}
    reasons: dict[tuple[str, str], str] = {}
    comparisons = cache_hits = 0
    cost_usd = 0.0
    for i in range(len(contested)):
        for j in range(i + 1, len(contested)):
            a, b = contested[i], contested[j]
            winner_id, reason, margin, hit, pair_cost = _judge_pair(
                job, requirements, a, b, db=db, jd_hash=jd_hash
            )
            key = (a.resume_id, b.resume_id) if a.resume_id <= b.resume_id else (b.resume_id, a.resume_id)
            pairwise_winners[key] = winner_id
            pairwise_margins[key] = margin
            pairwise_points[key] = borda_points_for_margin(margin)
            reasons[key] = reason
            comparisons += 1
            cost_usd += pair_cost
            if hit:
                cache_hits += 1
    wins = {i: 0 for i in contested_ids}
    borda_scores = {i: 0.0 for i in contested_ids}
    for key, w in pairwise_winners.items():
        if w in wins:
            wins[w] += 1
            borda_scores[w] += pairwise_points.get(key, 1.0)
    coverage_tb = {e.resume_id: e.coverage for e in contested}
    contested_ordered = borda_order(
        contested_ids, pairwise_winners, coverage_tiebreak=coverage_tb, pairwise_points=pairwise_points
    )
    final = merge_tournament_order(ids, contested_ordered)
    overrode = final != ids
    with observability.traced_call("pairwise_tournament", model=settings.LLM_MODEL, check_llm_ceiling=False) as trace:
        trace.input_tokens = trace.output_tokens = 0
        trace.cost_usd = cost_usd
        trace.cache_hit = cache_hits > 0 and cache_hits == comparisons
        logger.info(
            "pairwise_tournament.complete", comparisons=comparisons, cache_hits=cache_hits,
            contested=contested_ids, order=contested_ordered, overrode_coverage=overrode, cost_usd=cost_usd,
        )
    return TournamentResult(
        ran=True, ordered_ids=final, contested_ids=contested_ids, comparisons=comparisons,
        cache_hits=cache_hits, cost_usd=cost_usd, reasons=reasons, wins=wins,
        borda_scores=borda_scores, pairwise_winners=pairwise_winners,
        pairwise_margins=pairwise_margins, overrode_coverage=overrode,
    )
