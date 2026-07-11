from pydantic import BaseModel, Field

from app.core.config import settings
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.hybrid_rank import Rankable, RerankResult, hybrid_rank
from app.services.ranking_math import (
    experience_fit_score,
    parse_required_years,
    recency_score,
    requirements_met_score,
    skill_jaccard,
)


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


def _build_rerank_prompt(profile: ResumeProfile, jobs: list[Job], instructions: str) -> str:
    lines = [
        instructions.strip(),
        "",
        f"Candidate title: {profile.title}",
        f"Candidate years_of_experience: {profile.years_of_experience}",
        f"Candidate location: {profile.location}",
        f"Candidate skills: {', '.join(profile.skills)}",
        f"Candidate summary: {profile.summary}",
    ]
    if profile.work_experience:
        lines.append("Candidate recent roles:")
        for role in profile.work_experience[:4]:
            lines.append(f"  - {role.title} @ {role.company}: {'; '.join(role.bullets[:2])}")
    lines.append("")
    lines.append("Jobs:")
    for job in jobs:
        snippet = job.description[:700].replace("\n", " ")
        req_years = parse_required_years(f"{job.title}\n{job.description}")
        yoe_note = f"parsed_min_years={req_years}; " if req_years is not None else ""
        lines.append(
            f"- job_id={job.id}; title={job.title}; company={job.company}; "
            f"location={job.location}; {yoe_note}skills={', '.join(job.skills)}; description={snippet}"
        )
    return "\n".join(lines)


def _llm_rerank(profile: ResumeProfile, jobs: list[Job]) -> dict[str, _RerankItem]:
    if not jobs:
        return {}

    expected_ids = {job.id for job in jobs}
    tmpl = load_prompt("rerank")
    response = llm.complete_json(
        _build_rerank_prompt(profile, jobs, tmpl.body),
        _RerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("rerank")),
        operation="rerank",
        prompt_meta=tmpl,
    )

    if not response.results:
        raise ServiceFailingError("LLM", "rerank returned no results")

    returned_ids = [item.job_id for item in response.results]
    if len(returned_ids) != len(set(returned_ids)):
        raise ServiceFailingError("LLM", "rerank returned duplicate job_ids")

    returned_set = set(returned_ids)
    if returned_set != expected_ids:
        missing = sorted(expected_ids - returned_set)
        extra = sorted(returned_set - expected_ids)
        raise ServiceFailingError(
            "LLM",
            f"rerank job_id mismatch: missing={missing}, extra={extra}",
        )

    return {item.job_id: item for item in response.results}


def rank_jobs(profile: ResumeProfile, jobs: list[Job], *, use_llm: bool = True) -> list[RankedJob]:
    if not jobs:
        return []

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
        top_n=settings.SEARCH_RESULTS_TOP_N,
    )

    ranked: list[RankedJob] = []
    for item in scored:
        job = jobs_by_id[item.id]
        required_years = parse_required_years(f"{job.title}\n{job.description}")
        ranked.append(
            RankedJob(
                job=job,
                match_score=item.final_score,
                score_breakdown=ScoreBreakdown(
                    llm_fit=item.llm_fit,
                    rrf_normalized=item.rrf_normalized,
                    skill_jaccard=item.skill_overlap,
                    recency=item.recency,
                    experience_fit=item.experience_fit,
                    requirements_met=item.requirements_met,
                    required_years=required_years,
                    final_score=item.final_score,
                    matched_skills=item.matched_skills,
                    missing_skills=item.missing_skills,
                    rationale=item.rationale,
                ),
            )
        )
    return ranked


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
