import re
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logging import get_logger
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job, RankedJob, ScoreBreakdown, SearchParams
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.ranking.hybrid import Rankable, RerankResult, hybrid_rank
from app.services.jobs_svc.filters import soft_boost_score
from app.services.ranking.listwise import (
    ListwiseResponse,
    PermutationError,
    listwise_token_budget,
    parse_listwise_ranking,
    ranks_to_fit_scores,
)
from app.services.ranking.config import DEFAULT_MMR_LAMBDA
from app.services.ranking.math import (
    apply_company_soft_cap,
    cosine_similarity,
    experience_fit_score,
    mmr,
    parse_required_years,
    recency_score,
    requirements_met_score,
    skill_jaccard,
)
logger = get_logger(__name__)
class _RerankItem(BaseModel):
    job_id: str
    fit_score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
class _RerankResponse(BaseModel):
    results: list[_RerankItem]
def _job_to_rankable(job: Job) -> Rankable:
    return Rankable(id=job.id, dense_text=job.embedding_text(), lexical_text=job.lexical_text())
_RERANK_BATCH_SIZE = 6
_RERANK_DESC_CHARS = 220
def _alias_jobs(jobs: list[Job]) -> tuple[list[tuple[str, Job]], dict[str, str]]:
    pairs: list[tuple[str, Job]] = []
    alias_to_real: dict[str, str] = {}
    for index, job in enumerate(jobs):
        alias = f"j{index}"
        pairs.append((alias, job))
        alias_to_real[alias] = job.id
    return pairs, alias_to_real
def _profile_header(profile: ResumeProfile) -> list[str]:
    lines = [
        f"Candidate title: {profile.title}",
        f"Candidate years_of_experience: {profile.years_of_experience}",
        f"Candidate location: {profile.location}",
        f"Candidate skills: {', '.join(profile.skills[:20])}",
        f"Candidate summary: {(profile.summary or '')[:400]}",
    ]
    if profile.work_experience:
        lines.append("Candidate recent roles:")
        for role in profile.work_experience[:3]:
            bullet = "; ".join(role.bullets[:1])
            lines.append(f"  - {role.title} @ {role.company}: {bullet[:160]}")
    return lines
def _job_line(alias: str, job: Job) -> str:
    snippet = re.sub(r"\s+", " ", job.description[:_RERANK_DESC_CHARS]).strip()
    req_years = parse_required_years(f"{job.title}\n{job.description}")
    yoe_note = f"min_years={req_years}; " if req_years is not None else ""
    skills = ", ".join(job.skills[:10])
    return (
        f"- job_id={alias}; title={job.title}; company={job.company}; "
        f"location={job.location}; {yoe_note}skills={skills}; desc={snippet}"
    )
def _build_rerank_prompt(profile: ResumeProfile, alias_jobs: list[tuple[str, Job]], instructions: str) -> str:
    aliases = [alias for alias, _ in alias_jobs]
    lines = [
        instructions.strip(),
        "",
        *_profile_header(profile),
        "",
        f"Jobs ({len(alias_jobs)}). Score EVERY job_id in this exact list: {', '.join(aliases)}.",
        "Use those job_id strings verbatim in your JSON (e.g. j0, j1).",
    ]
    lines.extend(_job_line(a, j) for a, j in alias_jobs)
    return "\n".join(lines)
def _build_listwise_prompt(profile: ResumeProfile, alias_jobs: list[tuple[str, Job]], instructions: str) -> str:
    aliases = [alias for alias, _ in alias_jobs]
    lines = [
        instructions.strip(),
        "",
        *_profile_header(profile),
        "",
        f"Jobs ({len(alias_jobs)}). Return a ranking that is a permutation of ALL ids: {', '.join(aliases)}.",
        "Best fit first. Use job_id strings verbatim.",
    ]
    for i, (alias, job) in enumerate(alias_jobs, start=1):
        lines.append(f"{i}. {_job_line(alias, job)}")
    return "\n".join(lines)
def _skills_chips(profile: ResumeProfile, job: Job) -> tuple[list[str], list[str]]:
    from app.services.ranking.math_align import skill_equals
    profile_skills = [s for s in profile.skills if s and s.strip()]
    job_skills = [s for s in job.skills if s and s.strip()]
    matched = [s for s in profile_skills if any(skill_equals(s, js) for js in job_skills)][:5]
    missing = [s for s in job_skills if not any(skill_equals(s, ps) for ps in profile_skills)][:5]
    return matched, missing
def _heuristic_rerank_item(profile: ResumeProfile, job: Job) -> _RerankItem:
    profile_text = profile.search_text()
    skill = skill_jaccard(profile.skills, job.skills)
    exp = experience_fit_score(profile.years_of_experience, title=job.title, description=job.description)
    req = requirements_met_score(
        profile_skills=profile.skills, profile_text=profile_text,
        job_skills=job.skills, job_description=job.description,
    )
    fit = round((0.45 * skill + 0.35 * exp + 0.20 * req) * 100.0, 1)
    matched, missing = _skills_chips(profile, job)
    return _RerankItem(
        job_id=job.id, fit_score=fit, matched_skills=matched, missing_skills=missing,
        rationale="Heuristic fill: model omitted this job_id; used skills/experience/requirements.",
    )
def _map_alias_results(response: _RerankResponse, alias_to_real: dict[str, str]) -> dict[str, _RerankItem]:
    real_to_item: dict[str, _RerankItem] = {}
    for item in response.results:
        raw_id = (item.job_id or "").strip()
        real_id = alias_to_real.get(raw_id)
        if real_id is None and raw_id in alias_to_real.values():
            real_id = raw_id
        if real_id is None:
            cleaned = re.sub(r"[^a-z0-9]", "", raw_id.lower())
            for alias, rid in alias_to_real.items():
                if cleaned == alias.lower() or cleaned == f"job{alias[1:]}":
                    real_id = rid
                    break
        if real_id is None:
            logger.warning("jobs.rerank_unknown_id", job_id=raw_id)
            continue
        if real_id in real_to_item: continue
        real_to_item[real_id] = item.model_copy(update={"job_id": real_id})
    return real_to_item
def _call_rerank_llm(profile: ResumeProfile, alias_jobs: list[tuple[str, Job]], *, max_retries: int = 2) -> _RerankResponse:
    tmpl = load_prompt("rerank_pointwise")
    base_budget = int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("rerank"))
    budget = min(base_budget, max(1400, 500 + 200 * len(alias_jobs)))
    return llm.complete_json(
        _build_rerank_prompt(profile, alias_jobs, tmpl.body),
        _RerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=budget, max_retries=max_retries, operation="rerank", prompt_meta=tmpl,
    )
def _llm_rerank_batch(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    if not jobs: return {}
    alias_jobs, alias_to_real = _alias_jobs(jobs)
    jobs_by_id = {job.id: job for job in jobs}
    expected = set(jobs_by_id)
    response = _call_rerank_llm(profile, alias_jobs)
    if not response.results: raise ServiceFailingError("LLM", "rerank returned no results")
    mapped = _map_alias_results(response, alias_to_real)
    missing_ids = sorted(expected - set(mapped))
    if missing_ids:
        retry_jobs = [jobs_by_id[mid] for mid in missing_ids]
        retry_pairs, retry_alias = _alias_jobs(retry_jobs)
        logger.info("jobs.rerank_retry_missing", count=len(missing_ids), ids=missing_ids)
        try:
            retry_resp = _call_rerank_llm(profile, retry_pairs, max_retries=1)
            mapped.update(_map_alias_results(retry_resp, retry_alias))
        except ServiceFailingError as exc:
            logger.warning("jobs.rerank_retry_failed", error=str(exc))
    for mid in sorted(expected - set(mapped)):
        logger.warning("jobs.rerank_heuristic_fill", job_id=mid)
        mapped[mid] = _heuristic_rerank_item(profile, jobs_by_id[mid])
    return mapped
def _llm_rerank_pointwise(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    if not jobs: return {}
    merged: dict[str, _RerankItem] = {}
    for offset in range(0, len(jobs), _RERANK_BATCH_SIZE):
        merged.update(_llm_rerank_batch(profile, jobs[offset : offset + _RERANK_BATCH_SIZE]))
    return merged
def _resolve_listwise_aliases(
    ordered: list[tuple[str, str]], alias_to_real: dict[str, str]
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for raw_id, reason in ordered:
        rid = alias_to_real.get(raw_id.strip())
        if rid is None and raw_id.strip() in alias_to_real.values():
            rid = raw_id.strip()
        if rid is None:
            cleaned = re.sub(r"[^a-z0-9]", "", raw_id.lower())
            for alias, real in alias_to_real.items():
                if cleaned == alias.lower():
                    rid = real
                    break
        if rid is None: raise PermutationError(f"unmapped alias: {raw_id}")
        out.append((rid, reason))
    return out
def _llm_rerank_listwise(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    if not jobs: return {}
    alias_jobs, alias_to_real = _alias_jobs(jobs)
    aliases = [a for a, _ in alias_jobs]
    jobs_by_id = {j.id: j for j in jobs}
    tmpl = load_prompt("rerank")
    budget = listwise_token_budget(n_jobs=len(jobs), prompt_cap=int(tmpl.model_params.get("max_tokens") or 2000))
    prompt = _build_listwise_prompt(profile, alias_jobs, tmpl.body)
    system = tmpl.system or "You are a recruiting matcher. Return JSON only."
    def _once() -> list[tuple[str, str]]:
        resp = llm.complete_json(
            prompt, ListwiseResponse, system=system, max_tokens=budget,
            max_retries=0, operation="rerank", prompt_meta=tmpl,
        )
        ordered_alias = parse_listwise_ranking(resp, aliases)
        return _resolve_listwise_aliases(ordered_alias, alias_to_real)
    ordered: list[tuple[str, str]] | None = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            ordered = _once()
            break
        except (PermutationError, ServiceFailingError, ValueError) as exc:
            last_err = exc
            logger.warning("jobs.listwise_retry", attempt=attempt + 1, error=str(exc))
    if ordered is None:
        logger.warning("jobs.listwise_fallback_heuristic", error=str(last_err))
        return _heuristic_rerank_from_order(profile, jobs)
    real_ids = [jid for jid, _ in ordered]
    if set(real_ids) != set(jobs_by_id) or len(real_ids) != len(jobs_by_id):
        logger.warning("jobs.listwise_fallback_heuristic", error="real-id permutation invalid")
        return _heuristic_rerank_from_order(profile, jobs)
    fit = ranks_to_fit_scores(real_ids)
    reasons = {jid: reason for jid, reason in ordered}
    out: dict[str, _RerankItem] = {}
    for jid in real_ids:
        job = jobs_by_id[jid]
        matched, missing = _skills_chips(profile, job)
        out[jid] = _RerankItem(
            job_id=jid, fit_score=fit[jid], matched_skills=matched, missing_skills=missing,
            rationale=(reasons.get(jid) or "")[:120],
        )
    return out
def _heuristic_rerank_from_order(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    fit = ranks_to_fit_scores([j.id for j in jobs])
    out: dict[str, _RerankItem] = {}
    for job in jobs:
        item = _heuristic_rerank_item(profile, job)
        out[job.id] = item.model_copy(
            update={
                "fit_score": fit.get(job.id, item.fit_score),
                "rationale": "Listwise failed; kept retrieval order + heuristic fit.",
            }
        )
    return out
def _llm_rerank(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    if settings.RANKING_LLM_LISTWISE: return _llm_rerank_listwise(profile, jobs)
    return _llm_rerank_pointwise(profile, jobs)
def _diversify_ranked(
    ranked: list[RankedJob], *, lambda_: float = DEFAULT_MMR_LAMBDA, top_n: int | None = None,
) -> list[RankedJob]:
    if len(ranked) <= 1: return ranked
    from app.services import embeddings
    ids = [item.job.id for item in ranked]
    by_id = {item.job.id: item for item in ranked}
    max_score = max((item.match_score for item in ranked), default=1.0) or 1.0
    relevance = {item.job.id: item.match_score / max_score for item in ranked}
    vectors = embeddings.embed_batch([by_id[i].job.dedup_embedding_text() for i in ids])
    vec_by_id = {i: v for i, v in zip(ids, vectors, strict=True)}
    pairwise: dict[tuple[str, str], float] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            pairwise[(a, b)] = cosine_similarity(vec_by_id[a], vec_by_id[b])
    order = mmr(ids, relevance, pairwise, lambda_=lambda_, k=None)
    company_by_id = {item.job.id: item.job.company for item in ranked}
    limit = top_n if top_n is not None else len(order)
    order = apply_company_soft_cap(
        order, company_by_id, top_k=max(limit, 10), max_per_company=3,
        pool_company_count=len({c for c in company_by_id.values() if c}),
    )
    return [by_id[i] for i in order[:limit] if i in by_id]
def rank_jobs(
    profile: ResumeProfile, jobs: list[Job], *, use_llm: bool = True,
    params: SearchParams | None = None, diversify: bool = True, top_n: int | None = None,
) -> list[RankedJob]:
    if not jobs: return []
    params = params or SearchParams()
    result_n = top_n if top_n is not None else settings.SEARCH_RESULTS_TOP_N
    score_n = max(result_n, min(len(jobs), max(settings.RERANK_TOP_N, result_n * 3)))
    jobs_by_id = {job.id: job for job in jobs}
    rankables = [_job_to_rankable(job) for job in jobs]
    profile_text = profile.search_text()
    use_ce = bool(settings.RANKING_USE_CROSS_ENCODER)
    def rerank_fn(candidates: list[Rankable]) -> dict[str, RerankResult]:
        lookup = _llm_rerank(profile, [jobs_by_id[c.id] for c in candidates])
        return {
            jid: RerankResult(
                fit_score=item.fit_score, matched_skills=item.matched_skills,
                missing_skills=item.missing_skills, rationale=item.rationale,
            )
            for jid, item in lookup.items()
        }
    def cross_encode_fn(candidates: list[Rankable]) -> dict[str, float]:
        from app.services.ranking.cross_encoder import cross_encode_ids
        return cross_encode_ids(
            profile_text,
            [(c.id, jobs_by_id[c.id].embedding_text()) for c in candidates],
        )
    scored = hybrid_rank(
        profile_text, profile_text, rankables,
        rerank_fn=rerank_fn if use_llm else None,
        skill_overlap_fn=lambda r: skill_jaccard(profile.skills, jobs_by_id[r.id].skills),
        recency_fn=lambda r: recency_score(jobs_by_id[r.id].posted_at),
        experience_fn=lambda r: experience_fit_score(
            profile.years_of_experience, title=jobs_by_id[r.id].title, description=jobs_by_id[r.id].description,
        ),
        requirements_fn=lambda r: requirements_met_score(
            profile_skills=profile.skills, profile_text=profile_text,
            job_skills=jobs_by_id[r.id].skills, job_description=jobs_by_id[r.id].description,
        ),
        cross_encode_fn=cross_encode_fn if use_ce else None,
        use_llm=use_llm, use_cross_encoder=use_ce,
        score_pool="rerank_top_n", top_n=score_n,
    )
    from app.services.ranking.calibration import load_active_calibration, ui_match_likelihood
    cal_params = load_active_calibration() if settings.RANKING_USE_CALIBRATION else None
    ranked: list[RankedJob] = []
    for item in scored:
        job = jobs_by_id[item.id]
        required_years = parse_required_years(f"{job.title}\n{job.description}")
        base_final = float(item.final_score)
        boosted = soft_boost_score(job, params, base_final)
        soft_boost = round(boosted - base_final, 1)
        likelihood = ui_match_likelihood(boosted, params=cal_params)
        ranked.append(
            RankedJob(
                job=job, match_score=boosted,
                score_breakdown=ScoreBreakdown(
                    llm_fit=item.llm_fit, rrf_normalized=item.rrf_normalized,
                    skill_jaccard=item.skill_overlap, recency=item.recency,
                    experience_fit=item.experience_fit, requirements_met=item.requirements_met,
                    cross_encoder=item.cross_encoder, required_years=required_years,
                    soft_boost=soft_boost, final_score=boosted,
                    matched_skills=item.matched_skills, missing_skills=item.missing_skills,
                    rationale=item.rationale, match_likelihood=likelihood,
                ),
            )
        )
    ranked.sort(key=lambda r: r.match_score, reverse=True)
    if diversify and len(ranked) > 1:
        from app.core.env_utils import is_set
        from app.services.inference.embeddings import embeddings_endpoint
        if is_set(settings.EMBEDDINGS_API_KEY) and embeddings_endpoint():
            ranked = _diversify_ranked(ranked, lambda_=DEFAULT_MMR_LAMBDA, top_n=result_n)
    return ranked[:result_n]
def rank_jobs_dense_only(profile: ResumeProfile, jobs: list[Job]) -> list[RankedJob]:
    from app.services.ranking.hybrid import dense_ranking
    if not jobs: return []
    rankables = [_job_to_rankable(job) for job in jobs]
    dense_ids = dense_ranking(profile.search_text(), rankables)
    jobs_by_id = {job.id: job for job in jobs}
    profile_text = profile.search_text()
    ranked: list[RankedJob] = []
    for position, job_id in enumerate(dense_ids[: settings.SEARCH_RESULTS_TOP_N]):
        job = jobs_by_id[job_id]
        dense_score = (1.0 - position / max(len(dense_ids), 1)) * 100.0
        ranked.append(
            RankedJob(
                job=job, match_score=round(dense_score, 1),
                score_breakdown=ScoreBreakdown(
                    llm_fit=0.0, rrf_normalized=0.0, dense_rank_score=round(dense_score, 1),
                    skill_jaccard=skill_jaccard(profile.skills, job.skills),
                    recency=recency_score(job.posted_at),
                    experience_fit=experience_fit_score(
                        profile.years_of_experience, title=job.title, description=job.description,
                    ),
                    requirements_met=requirements_met_score(
                        profile_skills=profile.skills, profile_text=profile_text,
                        job_skills=job.skills, job_description=job.description,
                    ),
                    required_years=parse_required_years(f"{job.title}\n{job.description}"),
                    final_score=round(dense_score, 1), rationale="dense-only baseline",
                ),
            )
        )
    return ranked
