import re
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logging import get_logger
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job, RankedJob, ScoreBreakdown, SearchParams
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.hybrid_rank import Rankable, RerankResult, hybrid_rank
from app.services.job_filters import soft_boost_score
from app.services.ranking_config import DEFAULT_MMR_LAMBDA
from app.services.ranking_math import (
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
    return Rankable(
        id=job.id,
        dense_text=job.embedding_text(),
        lexical_text=job.lexical_text(),
    )
_RERANK_BATCH_SIZE = 6
_RERANK_DESC_CHARS = 220
def _alias_jobs(jobs: list[Job]) -> tuple[list[tuple[str, Job]], dict[str, str]]:
    """Map jobs to short ids j0..jn for the LLM; return (pairs, alias→real_id)."""
    pairs: list[tuple[str, Job]] = []
    alias_to_real: dict[str, str] = {}
    for index, job in enumerate(jobs):
        alias = f"j{index}"
        pairs.append((alias, job))
        alias_to_real[alias] = job.id
    return pairs, alias_to_real
def _build_rerank_prompt(
    profile: ResumeProfile,
    alias_jobs: list[tuple[str, Job]],
    instructions: str,
) -> str:
    lines = [
        instructions.strip(),
        "",
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
    aliases = [alias for alias, _ in alias_jobs]
    lines.append("")
    lines.append(
        f"Jobs ({len(alias_jobs)}). Score EVERY job_id in this exact list: {', '.join(aliases)}."
    )
    lines.append("Use those job_id strings verbatim in your JSON (e.g. j0, j1).")
    for alias, job in alias_jobs:
        snippet = re.sub(r"\s+", " ", job.description[:_RERANK_DESC_CHARS]).strip()
        req_years = parse_required_years(f"{job.title}\n{job.description}")
        yoe_note = f"min_years={req_years}; " if req_years is not None else ""
        skills = ", ".join(job.skills[:10])
        lines.append(
            f"- job_id={alias}; title={job.title}; company={job.company}; "
            f"location={job.location}; {yoe_note}skills={skills}; desc={snippet}"
        )
    return "\n".join(lines)
def _heuristic_rerank_item(profile: ResumeProfile, job: Job) -> _RerankItem:
    """Transparent non-LLM fit when the model omits a job_id (not a silent fake success)."""
    profile_text = profile.search_text()
    skill = skill_jaccard(profile.skills, job.skills)
    exp = experience_fit_score(
        profile.years_of_experience,
        title=job.title,
        description=job.description,
    )
    req = requirements_met_score(
        profile_skills=profile.skills,
        profile_text=profile_text,
        job_skills=job.skills,
        job_description=job.description,
    )
    fit = round((0.45 * skill + 0.35 * exp + 0.20 * req) * 100.0, 1)
    matched = [
        s
        for s in profile.skills
        if s.strip() and s.strip().lower() in {js.strip().lower() for js in job.skills if js}
    ][:5]
    missing = [
        s
        for s in job.skills
        if s.strip() and s.strip().lower() not in {ps.strip().lower() for ps in profile.skills if ps}
    ][:5]
    return _RerankItem(
        job_id=job.id,
        fit_score=fit,
        matched_skills=matched,
        missing_skills=missing,
        rationale="Heuristic fill: model omitted this job_id; used skills/experience/requirements.",
    )
def _map_alias_results(
    response: _RerankResponse,
    alias_to_real: dict[str, str],
) -> dict[str, _RerankItem]:
    """Map alias job_ids back to real UUIDs; drop unknown/extra aliases."""
    real_to_item: dict[str, _RerankItem] = {}
    for item in response.results:
        raw_id = (item.job_id or "").strip()
        real_id = alias_to_real.get(raw_id)
        if real_id is None and raw_id in alias_to_real.values():
            # Model echoed a real UUID somehow
            real_id = raw_id
        if real_id is None:
            # fuzzy: j0 vs "j0 " vs job_id=j0
            cleaned = re.sub(r"[^a-z0-9]", "", raw_id.lower())
            for alias, rid in alias_to_real.items():
                if cleaned == alias.lower() or cleaned == f"job{alias[1:]}":
                    real_id = rid
                    break
        if real_id is None:
            logger.warning("jobs.rerank_unknown_id", job_id=raw_id)
            continue
        if real_id in real_to_item:
            continue  # first wins on duplicate
        real_to_item[real_id] = item.model_copy(update={"job_id": real_id})
    return real_to_item
def _call_rerank_llm(
    profile: ResumeProfile,
    alias_jobs: list[tuple[str, Job]],
    *,
    max_retries: int = 2,
) -> _RerankResponse:
    tmpl = load_prompt("rerank")
    base_budget = int(
        tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("rerank")
    )
    per_job = 200
    budget = min(base_budget, max(1400, 500 + per_job * len(alias_jobs)))
    return llm.complete_json(
        _build_rerank_prompt(profile, alias_jobs, tmpl.body),
        _RerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=budget,
        max_retries=max_retries,
        operation="rerank",
        prompt_meta=tmpl,
    )
def _llm_rerank_batch(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    """One (or two) LLM JSON calls for a small job batch with alias ids + recovery."""
    if not jobs:
        return {}
    alias_jobs, alias_to_real = _alias_jobs(jobs)
    jobs_by_id = {job.id: job for job in jobs}
    expected = set(jobs_by_id)
    response = _call_rerank_llm(profile, alias_jobs)
    if not response.results:
        raise ServiceFailingError("LLM", "rerank returned no results")
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
    still_missing = sorted(expected - set(mapped))
    for mid in still_missing:
        logger.warning("jobs.rerank_heuristic_fill", job_id=mid)
        mapped[mid] = _heuristic_rerank_item(profile, jobs_by_id[mid])
    return mapped
def _llm_rerank(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    """Rerank in batches so large top-N shortlists don't truncate mid-JSON."""
    if not jobs:
        return {}
    merged: dict[str, _RerankItem] = {}
    for offset in range(0, len(jobs), _RERANK_BATCH_SIZE):
        batch = jobs[offset : offset + _RERANK_BATCH_SIZE]
        merged.update(_llm_rerank_batch(profile, batch))
    return merged
def _diversify_ranked(
    ranked: list[RankedJob],
    *,
    lambda_: float = DEFAULT_MMR_LAMBDA,
    top_n: int | None = None,
) -> list[RankedJob]:
    """MMR + per-company soft cap over ranked results (uses job dedup embeddings)."""
    if len(ranked) <= 1:
        return ranked
    from app.services import embeddings
    ids = [item.job.id for item in ranked]
    by_id = {item.job.id: item for item in ranked}
    raw_scores = [item.match_score for item in ranked]
    max_score = max(raw_scores) if raw_scores else 1.0
    scale = max_score if max_score > 0 else 1.0
    relevance = {item.job.id: item.match_score / scale for item in ranked}
    texts = [by_id[i].job.dedup_embedding_text() for i in ids]
    vectors = embeddings.embed_batch(texts)
    vec_by_id = {i: v for i, v in zip(ids, vectors, strict=True)}
    pairwise: dict[tuple[str, str], float] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            pairwise[(a, b)] = cosine_similarity(vec_by_id[a], vec_by_id[b])
    order = mmr(ids, relevance, pairwise, lambda_=lambda_, k=None)
    company_by_id = {item.job.id: item.job.company for item in ranked}
    order = apply_company_soft_cap(
        order,
        company_by_id,
        top_k=10,
        max_per_company=3,
        pool_company_count=len({c for c in company_by_id.values() if c}),
    )
    limit = top_n if top_n is not None else len(order)
    order = order[:limit]
    return [by_id[i] for i in order if i in by_id]
def rank_jobs(
    profile: ResumeProfile,
    jobs: list[Job],
    *,
    use_llm: bool = True,
    params: SearchParams | None = None,
    diversify: bool = True,
    top_n: int | None = None,
) -> list[RankedJob]:
    if not jobs:
        return []
    params = params or SearchParams()
    result_n = top_n if top_n is not None else settings.SEARCH_RESULTS_TOP_N
    score_n = max(result_n, min(len(jobs), max(settings.RERANK_TOP_N, result_n * 3)))
    jobs_by_id = {job.id: job for job in jobs}
    rankables = [_job_to_rankable(job) for job in jobs]
    profile_text = profile.search_text()
    def rerank_fn(candidates: list[Rankable]) -> dict[str, RerankResult]:
        rerank_jobs_list = [jobs_by_id[candidate.id] for candidate in candidates]
        lookup = _llm_rerank(profile, rerank_jobs_list)
        return {
            job_id: RerankResult(
                fit_score=item.fit_score,
                matched_skills=item.matched_skills,
                missing_skills=item.missing_skills,
                rationale=item.rationale,
            )
            for job_id, item in lookup.items()
        }
    def experience_fn(rankable: Rankable) -> float:
        job = jobs_by_id[rankable.id]
        return experience_fit_score(
            profile.years_of_experience,
            title=job.title,
            description=job.description,
        )
    def requirements_fn(rankable: Rankable) -> float:
        job = jobs_by_id[rankable.id]
        return requirements_met_score(
            profile_skills=profile.skills,
            profile_text=profile_text,
            job_skills=job.skills,
            job_description=job.description,
        )
    scored = hybrid_rank(
        profile_text,
        profile_text,
        rankables,
        rerank_fn=rerank_fn if use_llm else None,
        skill_overlap_fn=lambda rankable: skill_jaccard(profile.skills, jobs_by_id[rankable.id].skills),
        recency_fn=lambda rankable: recency_score(jobs_by_id[rankable.id].posted_at),
        experience_fn=experience_fn,
        requirements_fn=requirements_fn,
        use_llm=use_llm,
        score_pool="rerank_top_n",
        top_n=score_n,
    )
    ranked: list[RankedJob] = []
    for item in scored:
        job = jobs_by_id[item.id]
        required_years = parse_required_years(f"{job.title}\n{job.description}")
        base_final = float(item.final_score)
        boosted = soft_boost_score(job, params, base_final)
        soft_boost = round(boosted - base_final, 1)
        ranked.append(
            RankedJob(
                job=job,
                match_score=boosted,
                score_breakdown=ScoreBreakdown(
                    llm_fit=item.llm_fit,
                    rrf_normalized=item.rrf_normalized,
                    skill_jaccard=item.skill_overlap,
                    recency=item.recency,
                    experience_fit=item.experience_fit,
                    requirements_met=item.requirements_met,
                    required_years=required_years,
                    soft_boost=soft_boost,
                    final_score=boosted,
                    matched_skills=item.matched_skills,
                    missing_skills=item.missing_skills,
                    rationale=item.rationale,
                ),
            )
        )
    ranked.sort(key=lambda r: r.match_score, reverse=True)
    if diversify and len(ranked) > 1:
        from app.core.env_utils import is_set
        from app.services.embeddings import embeddings_endpoint
        if is_set(settings.EMBEDDINGS_API_KEY) and embeddings_endpoint():
            ranked = _diversify_ranked(ranked, lambda_=DEFAULT_MMR_LAMBDA, top_n=result_n)
    return ranked[:result_n]
def rank_jobs_dense_only(profile: ResumeProfile, jobs: list[Job]) -> list[RankedJob]:
    from app.services.hybrid_rank import dense_ranking
    if not jobs:
        return []
    rankables = [_job_to_rankable(job) for job in jobs]
    dense_ids = dense_ranking(profile.search_text(), rankables)
    jobs_by_id = {job.id: job for job in jobs}
    profile_text = profile.search_text()
    ranked: list[RankedJob] = []
    for position, job_id in enumerate(dense_ids[: settings.SEARCH_RESULTS_TOP_N]):
        job = jobs_by_id[job_id]
        overlap = skill_jaccard(profile.skills, job.skills)
        recency = recency_score(job.posted_at)
        exp = experience_fit_score(
            profile.years_of_experience,
            title=job.title,
            description=job.description,
        )
        req = requirements_met_score(
            profile_skills=profile.skills,
            profile_text=profile_text,
            job_skills=job.skills,
            job_description=job.description,
        )
        dense_score = (1.0 - position / max(len(dense_ids), 1)) * 100.0
        ranked.append(
            RankedJob(
                job=job,
                match_score=round(dense_score, 1),
                score_breakdown=ScoreBreakdown(
                    llm_fit=0.0,
                    rrf_normalized=0.0,
                    dense_rank_score=round(dense_score, 1),
                    skill_jaccard=overlap,
                    recency=recency,
                    experience_fit=exp,
                    requirements_met=req,
                    required_years=parse_required_years(f"{job.title}\n{job.description}"),
                    final_score=round(dense_score, 1),
                    matched_skills=[],
                    missing_skills=[],
                    rationale="dense-only baseline",
                ),
            )
        )
    return ranked
