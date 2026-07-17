from __future__ import annotations
import hashlib, random, re
from collections import Counter
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import PairwiseJudgeCache
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.services import llm, observability
from app.services.resume.jd_decompose import JdRequirement, jd_content_hash
from app.services.ranking.math_align import (
    TOURNAMENT_GAP, TOURNAMENT_TOP_K, borda_order, borda_points_for_margin,
    close_call_band, merge_tournament_order, order_normalized_pair,
)
logger = get_logger(__name__)
_WEIGHT_NOTATION = re.compile(r"\s*\(w=\d+(?:\.\d+)?\)")
_AB_COMPARE = re.compile(r"\b(?:beats|wins|leads|shows|has|is|over|with|than|versus|vs\.?|prefer|between|and|or)\b", re.I)
class _PairwiseResponse(BaseModel):
    winner: str; margin: str = "decisive"; key_differences: list[str] = Field(default_factory=list); reason: str = ""
class _AdvocateResponse(BaseModel):
    argument: str = ""
@dataclass
class AlignmentEvidence:
    resume_id: str; content_hash: str; coverage: float
    top_units: list[str] = field(default_factory=list)
    alignment_rows: list[dict] = field(default_factory=list); filename: str = ""
@dataclass
class AdversarialCritique:
    side_a_resume_id: str; side_a_filename: str; side_a_model: str; side_a_argument: str
    side_b_resume_id: str; side_b_filename: str; side_b_model: str; side_b_argument: str
    verdict_winner_resume_id: str; verdict_winner_filename: str; verdict_model: str
    verdict_reason: str; verdict_margin: str = "decisive"
@dataclass
class TournamentResult:
    ran: bool; ordered_ids: list[str]
    contested_ids: list[str] = field(default_factory=list)
    comparisons: int = 0; cache_hits: int = 0; cost_usd: float = 0.0
    reasons: dict[tuple[str, str], str] = field(default_factory=dict)
    wins: dict[str, int] = field(default_factory=dict)
    borda_scores: dict[str, float] = field(default_factory=dict)
    pairwise_winners: dict[tuple[str, str], str] = field(default_factory=dict)
    pairwise_margins: dict[tuple[str, str], str] = field(default_factory=dict)
    overrode_coverage: bool = False
    judge_agreement_mean: float | None = None
    pair_agreements: dict[tuple[str, str], float] = field(default_factory=dict)
    panel_models: list[str] = field(default_factory=list)
    adversarial: AdversarialCritique | None = None
def tournament_jd_key(job: Job) -> str:
    tmpl = load_prompt("pairwise_judge")
    raw = f"{jd_content_hash(job)}:pairwise_judge:{tmpl.version}:{tmpl.content_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()
def pairwise_cache_key(jd_hash: str, hash_a: str, hash_b: str, model: str | None = None) -> str:
    a, b = order_normalized_pair(hash_a, hash_b)
    base = f"{jd_hash}:{a}:{b}"; m = (model or "").strip()
    return hashlib.sha256((f"{base}:{m}" if m else base).encode()).hexdigest()
def strip_weight_notation(text: str) -> str:
    return _WEIGHT_NOTATION.sub("", text or "").strip()
def materialize_ab_labels(text: str, *, name_a: str, name_b: str) -> str:
    out, pa, pb = text or "", "<<PAIR_LEFT>>", "<<PAIR_RIGHT>>"
    for pat, rep in ((r"\bResume A\b", pa), (r"\bResume B\b", pb), (r"\bresume A\b", pa), (r"\bresume B\b", pb)):
        out = re.sub(pat, rep, out)
    if _AB_COMPARE.search(out) and re.search(r"\b[AB]\b", out):
        out = re.sub(r"\bA\b", pa, out); out = re.sub(r"\bB\b", pb, out)
    return strip_weight_notation(out.replace(pa, name_a).replace(pb, name_b))
def agreement_label(agree: float | None, n_judges: int) -> str | None:
    if agree is None or n_judges <= 0: return None
    n = max(1, int(round(agree * n_judges)))
    return f"{n}/{n_judges} judges agree" if agree >= 1.0 - 1e-9 else f"{n}/{n_judges} split"
def majority_from_votes(votes: list[tuple[str, str]]) -> tuple[str, str, float]:
    if not votes: raise ValueError("empty votes")
    winner, top = Counter(w for w, _ in votes).most_common(1)[0]
    n = len(votes); return winner, ("decisive" if top == n else "slight"), top / n
def select_pairs_by_gap(contested: list[AlignmentEvidence], max_pairs: int | None) -> list[tuple[AlignmentEvidence, AlignmentEvidence]]:
    pairs = [(contested[i], contested[j]) for i in range(len(contested)) for j in range(i + 1, len(contested))]
    if max_pairs is None or max_pairs >= len(pairs): return pairs
    pairs.sort(key=lambda ab: abs(ab[0].coverage - ab[1].coverage)); return pairs[:max_pairs]
def evidence_phrases(ev: AlignmentEvidence) -> set[str]:
    phrases: set[str] = set()
    for r in ev.alignment_rows:
        t = strip_weight_notation(str(r.get("evidence_unit") or "")).strip()
        if t and t.lower() not in {"(none)", "no clear evidence"}: phrases.add(t.lower())
    for u in ev.top_units:
        t = strip_weight_notation(u).strip()
        if t and t.lower() not in {"(none)", "no clear evidence"}: phrases.add(t.lower())
    return phrases
def argument_grounded(argument: str, phrases: set[str]) -> bool:
    arg = (argument or "").strip()
    if not arg or len(arg.split()) > 90: return False
    if not phrases: return False  # no evidence rows → cannot invent
    al = arg.lower()
    if any(p in al for p in phrases if len(p) >= 8): return True
    tokens = set(re.findall(r"[a-z0-9+]{4,}", al))
    ev_tok: set[str] = set()
    for p in phrases: ev_tok.update(re.findall(r"[a-z0-9+]{4,}", p))
    # Need ≥3 overlapping content tokens with evidence units (stricter than requirement-name leak)
    return len(tokens & ev_tok) >= 3
def _cache_get(db: Session | None, key: str) -> tuple[str, str] | None:
    if db is None: return None
    row = db.query(PairwiseJudgeCache).filter(PairwiseJudgeCache.cache_key == key).one_or_none()
    return (row.winner_hash, row.reason or "") if row else None
def _cache_put(db: Session | None, key: str, *, jd_hash: str, hash_a: str, hash_b: str, winner_hash: str, reason: str) -> None:
    if db is None: return
    a, b = order_normalized_pair(hash_a, hash_b)
    existing = db.query(PairwiseJudgeCache).filter(PairwiseJudgeCache.cache_key == key).one_or_none()
    try:
        if existing is not None: existing.winner_hash, existing.reason = winner_hash, reason; db.add(existing)
        else: db.add(PairwiseJudgeCache(cache_key=key, jd_hash=jd_hash, hash_a=a, hash_b=b, winner_hash=winner_hash, reason=reason))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback(); logger.warning("pairwise_tournament.cache_put_failed", error=str(exc))
def _format_must_rows(rows: list[dict]) -> list[str]:
    from app.services.ranking.math_align import evidence_strength
    lines: list[str] = []
    for r in rows:
        if str(r.get("kind") or "must") != "must": continue
        req = strip_weight_notation(str(r.get("requirement") or ""))
        strength = str(r.get("strength") or "").strip().lower()
        if strength not in {"none", "weak", "solid", "strong"}:
            try: strength = evidence_strength(float(r.get("evidence_score") or 0.0))
            except (TypeError, ValueError): strength = "none"
        lines.append(f"- {req} | evidence: {r.get('evidence_unit') or '(none)'} | strength: {strength} | status: {r.get('status') or 'miss'}")
    return lines
def _nice_summary(rows: list[dict]) -> str:
    nice = [r for r in rows if str(r.get("kind") or "") == "nice"]
    return "nice-to-have: none listed" if not nice else f"nice-to-have: {sum(1 for r in nice if r.get('status') == 'hit')}/{len(nice)} hit"
def _build_judge_prompt(job: Job, requirements: list[JdRequirement], left: AlignmentEvidence, right: AlignmentEvidence, tmpl) -> tuple[str, str, str]:
    name_a, name_b = left.filename or left.resume_id, right.filename or right.resume_id
    must_a = _format_must_rows(left.alignment_rows) or [f"- (unit) {u}" for u in left.top_units[:12]]
    must_b = _format_must_rows(right.alignment_rows) or [f"- (unit) {u}" for u in right.top_units[:12]]
    req_lines = [f"- [{r.kind}/{r.category} weight={float(r.weight):.2f}] {strip_weight_notation(r.text)}" for r in requirements[:14]]
    prompt = "\n".join([tmpl.body.strip(), "", f"Job: {job.title} @ {job.company}", f"Description excerpt: {job.description[:800]}", "",
        "Requirements (weight is internal scoring weight; prefer higher-weight musts):", *req_lines, "",
        f"Resume A ({name_a}) must-requirement alignment:", *(must_a or ["- (none)"]), _nice_summary(left.alignment_rows), "",
        f"Resume B ({name_b}) must-requirement alignment:", *(must_b or ["- (none)"]), _nice_summary(right.alignment_rows)])
    return prompt, name_a, name_b
def _judge_pair_once(job: Job, requirements: list[JdRequirement], a: AlignmentEvidence, b: AlignmentEvidence, *,
    db: Session | None, jd_hash: str, model: str | None, rng: random.Random | None = None,
) -> tuple[str, str, str, bool, float]:
    key = pairwise_cache_key(jd_hash, a.content_hash, b.content_hash, model)
    cached = _cache_get(db, key)
    if cached is not None:
        winner_hash, reason = cached
        if winner_hash in (a.content_hash, b.content_hash):
            winner_id = a.resume_id if winner_hash == a.content_hash else b.resume_id
            margin = "decisive"
            if reason.startswith("[slight] "): margin, reason = "slight", reason[len("[slight] "):]
            elif reason.startswith("[decisive] "): reason = reason[len("[decisive] "):]
            return winner_id, reason, margin, True, 0.0
    r = rng or random; flip = r.random() < 0.5; left, right = (b, a) if flip else (a, b)
    tmpl = load_prompt("pairwise_judge"); prompt, name_a, name_b = _build_judge_prompt(job, requirements, left, right, tmpl)
    max_tokens = int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("pairwise_judge"))
    use_model = (model or settings.LLM_MODEL).strip() or settings.LLM_MODEL
    est_in = observability.approx_token_count(prompt + (tmpl.system or ""))
    est_cost = observability.estimate_llm_cost_usd(model=use_model, input_tokens=est_in, output_tokens=max_tokens // 4)
    response = llm.complete_json(prompt, _PairwiseResponse, system=tmpl.system or "Return JSON only.",
        max_tokens=max_tokens, operation="pairwise_judge", prompt_meta=tmpl, llm_model=use_model if model else None)
    winner_label = (response.winner or "").strip().upper()
    if winner_label not in {"A", "B"}: raise ServiceFailingError("LLM", f"pairwise_judge invalid winner: {response.winner!r}")
    margin_raw = (response.margin or "decisive").strip().lower()
    margin = margin_raw if margin_raw in {"decisive", "slight"} else "decisive"
    winner_ev = left if winner_label == "A" else right
    diffs = [strip_weight_notation(d) for d in (response.key_differences or []) if d and str(d).strip()]
    reason = materialize_ab_labels(strip_weight_notation(response.reason or "") or "; ".join(diffs[:3]), name_a=name_a, name_b=name_b)
    if not diffs and len(reason) < 24:
        raise ServiceFailingError("LLM", "pairwise_judge missing key_differences / substantive reason (anti skill-token-only)")
    _cache_put(db, key, jd_hash=jd_hash, hash_a=a.content_hash, hash_b=b.content_hash, winner_hash=winner_ev.content_hash, reason=f"[{margin}] {reason}")
    return winner_ev.resume_id, reason, margin, False, float(est_cost)
def _judge_pair_panel(job, requirements, a, b, *, db, jd_hash, panel) -> tuple[str, str, str, bool, float, float]:
    if not panel:
        w, r, m, hit, cost = _judge_pair_once(job, requirements, a, b, db=db, jd_hash=jd_hash, model=None)
        return w, r, m, hit, cost, 1.0
    votes: list[tuple[str, str]] = []; reasons: list[str] = []; cost = 0.0; all_hit = True
    for model in panel:
        rng = random.Random(f"{jd_hash}:{a.content_hash}:{b.content_hash}:{model}")
        w, reason, margin, hit, pair_cost = _judge_pair_once(job, requirements, a, b, db=db, jd_hash=jd_hash, model=model, rng=rng)
        votes.append((w, margin)); reasons.append(reason); cost += pair_cost
        if not hit: all_hit = False
    winner, agg_margin, rate = majority_from_votes(votes)
    reason = next((rs for (w, _), rs in zip(votes, reasons) if w == winner), reasons[0] if reasons else "")
    return winner, reason, agg_margin, all_hit, cost, rate
def maybe_run_adversarial_critique(job: Job, requirements: list[JdRequirement], top: list[AlignmentEvidence], *, db: Session | None = None) -> AdversarialCritique | None:
    if not settings.ADVERSARIAL_CRITIQUE or len(top) < 2: return None
    a, b = top[0], top[1]
    models = list(settings.judge_panel_models) or [settings.LLM_MODEL]
    while len(models) < 3: models.append(models[-1] if models else settings.LLM_MODEL)
    rng = random.Random(f"adv:{a.content_hash}:{b.content_hash}:{job.id}"); pool = models[:3]; rng.shuffle(pool)
    model_a, model_b, model_v = pool[0], pool[1], pool[2]
    if model_a == model_b and len(set(models)) > 1:
        alts = [m for m in models if m != model_a]
        if alts: model_b = alts[0]
    try: tmpl = load_prompt("advocate")
    except (OSError, KeyError, ValueError, FileNotFoundError): return None
    def _argue(ev: AlignmentEvidence, model: str) -> str:
        rows = _format_must_rows(ev.alignment_rows) or [f"- {u}" for u in ev.top_units[:10]]
        prompt = "\n".join([tmpl.body.strip(), "", f"Job: {job.title} @ {job.company}", f"Resume: {ev.filename or ev.resume_id}",
            "Alignment evidence (cite ONLY these):", *(rows or ["- (none)"]), "", 'Write ≤80 words arguing FOR this resume. JSON: {"argument": "..."}'])
        max_tok = int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("advocate"))
        resp = llm.complete_json(prompt, _AdvocateResponse, system=tmpl.system or "Return JSON only.", max_tokens=max_tok, operation="advocate", prompt_meta=tmpl, llm_model=model)
        arg = strip_weight_notation(resp.argument or "").strip()
        if not argument_grounded(arg, evidence_phrases(ev)): raise ServiceFailingError("LLM", "advocate argument failed grounding check")
        return " ".join(arg.split()[:80])
    try: arg_a, arg_b = _argue(a, model_a), _argue(b, model_b)
    except (ServiceFailingError, ServiceNotConfiguredError, OSError, ValueError) as exc:
        logger.warning("adversarial_critique.failed", error=str(exc)); return None
    try: w_id, reason, margin, _, _ = _judge_pair_once(job, requirements, a, b, db=db, jd_hash=tournament_jd_key(job), model=model_v)
    except (ServiceFailingError, ServiceNotConfiguredError, OSError, ValueError) as exc:
        logger.warning("adversarial_critique.verdict_failed", error=str(exc)); return None
    winner_ev = a if w_id == a.resume_id else b
    return AdversarialCritique(
        side_a_resume_id=a.resume_id, side_a_filename=a.filename or a.resume_id, side_a_model=model_a, side_a_argument=arg_a,
        side_b_resume_id=b.resume_id, side_b_filename=b.filename or b.resume_id, side_b_model=model_b, side_b_argument=arg_b,
        verdict_winner_resume_id=winner_ev.resume_id, verdict_winner_filename=winner_ev.filename or winner_ev.resume_id,
        verdict_model=model_v, verdict_reason=reason, verdict_margin=margin,
    )
def maybe_run_tournament(job: Job, requirements: list[JdRequirement], ordered_by_coverage: list[AlignmentEvidence], *,
    use_llm: bool = True, db: Session | None = None, top_k: int = TOURNAMENT_TOP_K, gap: float = TOURNAMENT_GAP,
) -> TournamentResult:
    ids = [e.resume_id for e in ordered_by_coverage]
    if not use_llm or len(ordered_by_coverage) < 2: return TournamentResult(ran=False, ordered_ids=ids)
    band_ids = close_call_band([(e.resume_id, e.coverage) for e in ordered_by_coverage], gap=gap, top_k=top_k)
    if len(band_ids) < 2: return TournamentResult(ran=False, ordered_ids=ids)
    by_id = {e.resume_id: e for e in ordered_by_coverage}
    contested = [by_id[i] for i in band_ids]; contested_ids = list(band_ids); jd_hash = tournament_jd_key(job)
    panel = list(settings.judge_panel_models)
    pairs = select_pairs_by_gap(contested, int(settings.PAIRWISE_PANEL_MAX_PAIRS) if panel else None)
    pairwise_winners: dict[tuple[str, str], str] = {}; pairwise_margins: dict[tuple[str, str], str] = {}
    pairwise_points: dict[tuple[str, str], float] = {}; reasons: dict[tuple[str, str], str] = {}
    pair_agreements: dict[tuple[str, str], float] = {}; comparisons = cache_hits = 0; cost_usd = 0.0
    for a, b in pairs:
        winner_id, reason, margin, hit, pair_cost, agree = _judge_pair_panel(job, requirements, a, b, db=db, jd_hash=jd_hash, panel=panel)
        key = (a.resume_id, b.resume_id) if a.resume_id <= b.resume_id else (b.resume_id, a.resume_id)
        pairwise_winners[key] = winner_id; pairwise_margins[key] = margin
        pairwise_points[key] = borda_points_for_margin(margin); reasons[key] = reason; pair_agreements[key] = agree
        comparisons += 1; cost_usd += pair_cost
        if hit: cache_hits += 1
    wins = {i: 0 for i in contested_ids}; borda_scores = {i: 0.0 for i in contested_ids}
    for key, w in pairwise_winners.items():
        if w in wins: wins[w] += 1; borda_scores[w] += pairwise_points.get(key, 1.0)
    coverage_tb = {e.resume_id: e.coverage for e in contested}
    contested_ordered = borda_order(contested_ids, pairwise_winners, coverage_tiebreak=coverage_tb, pairwise_points=pairwise_points)
    final = merge_tournament_order(ids, contested_ordered); overrode = final != ids
    agree_mean = (sum(pair_agreements.values()) / len(pair_agreements)) if pair_agreements else None
    top2 = [by_id[rid] for rid in final[:2] if rid in by_id] if settings.ADVERSARIAL_CRITIQUE and len(final) >= 2 else []
    adv = maybe_run_adversarial_critique(job, requirements, top2, db=db) if len(top2) == 2 else None
    with observability.traced_call("pairwise_tournament", model=settings.LLM_MODEL, check_llm_ceiling=False) as trace:
        trace.input_tokens = trace.output_tokens = 0; trace.cost_usd = cost_usd; trace.cache_hit = cache_hits > 0 and cache_hits == comparisons
        if agree_mean is not None and panel:
            trace.prompt_name, trace.prompt_version = "judge_agreement", f"{agree_mean:.4f}"
        logger.info("pairwise_tournament.complete", comparisons=comparisons, cache_hits=cache_hits, contested=contested_ids, order=contested_ordered, overrode_coverage=overrode, cost_usd=cost_usd, panel=panel, judge_agreement_mean=agree_mean)
    return TournamentResult(ran=True, ordered_ids=final, contested_ids=contested_ids, comparisons=comparisons, cache_hits=cache_hits, cost_usd=cost_usd, reasons=reasons, wins=wins, borda_scores=borda_scores, pairwise_winners=pairwise_winners, pairwise_margins=pairwise_margins, overrode_coverage=overrode, judge_agreement_mean=agree_mean, pair_agreements=pair_agreements, panel_models=panel, adversarial=adv)
