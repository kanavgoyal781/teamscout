from pydantic import BaseModel, Field

from app.core.config import settings
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job, ScoreBreakdown
from app.schemas.library import RankedResumeRecommendation, RequirementCoverage, ResumeCandidate
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.hybrid_rank import Rankable, RerankResult, hybrid_rank
from app.services.ranking_math import (
    experience_fit_score,
    requirements_met_score,
    skill_jaccard,
)


class _ResumeRerankItem(BaseModel):
    resume_id: str
    fit_score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
    coverage: list[RequirementCoverage] = Field(default_factory=list)


class _ResumeRerankResponse(BaseModel):
    results: list[_ResumeRerankItem]


def _job_query_text(job: Job) -> str:
    return "\n".join(
        part
        for part in [
            job.title,
            job.company,
            job.location,
            ", ".join(job.skills),
            job.description[:2000],
        ]
        if part
    )


def _candidate_to_rankable(candidate: ResumeCandidate) -> Rankable:
    return Rankable(
        id=candidate.resume_id,
        dense_text=candidate.profile.search_text(),
        lexical_text=candidate.profile.search_text(),
    )


def _experience_score(job: Job, profile: ResumeProfile) -> float:
    return experience_fit_score(
        profile.years_of_experience,
        title=job.title,
        description=job.description,
    )


def _requirements_score(job: Job, profile: ResumeProfile) -> float:
    return requirements_met_score(
        profile_skills=profile.skills,
        profile_text=profile.search_text(),
        job_skills=job.skills,
        job_description=job.description,
    )


def _build_rerank_prompt(job: Job, candidates: list[ResumeCandidate], instructions: str) -> str:
    lines = [
        instructions.strip(),
        "",
        f"Job title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location}",
        f"Required skills: {', '.join(job.skills)}",
        f"Description: {job.description[:1200]}",
        "",
        "Resumes:",
    ]
    for candidate in candidates:
        profile = candidate.profile
        bullets = []
        for role in profile.work_experience[:3]:
            bullets.extend(role.bullets[:2])
        lines.append(
            f"- resume_id={candidate.resume_id}; filename={candidate.filename}; "
            f"title={profile.title}; years={profile.years_of_experience}; "
            f"skills={', '.join(profile.skills)}; summary={profile.summary[:300]}; "
            f"bullets={' | '.join(bullets[:4])}"
        )
    return "\n".join(lines)


def _resume_reference_tokens(profile: ResumeProfile) -> set[str]:
    tokens: set[str] = set()
    for skill in profile.skills:
        cleaned = skill.strip().lower()
        if len(cleaned) >= 3:
            tokens.add(cleaned)
    if profile.title.strip():
        tokens.add(profile.title.strip().lower())
    if profile.name.strip():
        tokens.add(profile.name.strip().lower())
    for role in profile.work_experience:
        if role.company.strip():
            tokens.add(role.company.strip().lower())
        if role.title.strip():
            tokens.add(role.title.strip().lower())
        for bullet in role.bullets:
            for word in bullet.split():
                cleaned = word.strip(".,;:").lower()
                if len(cleaned) >= 4:
                    tokens.add(cleaned)
    return tokens


def _rationale_references_resume(rationale: str, profile: ResumeProfile) -> bool:
    text = rationale.strip()
    if len(text) < 20:
        return False
    lowered = text.lower()
    tokens = _resume_reference_tokens(profile)
    if not tokens:
        return True
    return any(token in lowered for token in tokens)


def _llm_rerank(
    job: Job,
    candidates: list[ResumeCandidate],
    *,
    attempt: int = 0,
) -> dict[str, _ResumeRerankItem]:
    if not candidates:
        return {}

    expected_ids = {candidate.resume_id for candidate in candidates}
    tmpl = load_prompt("justify")
    prompt = _build_rerank_prompt(job, candidates, tmpl.body)
    if attempt > 0:
        prompt += (
            "\n\nPrevious rationales were too generic. "
            "Each rationale must mention specific resume skills, titles, companies, or bullets."
        )

    response = llm.complete_json(
        prompt,
        _ResumeRerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("justify")),
        operation="justify",
        prompt_meta=tmpl,
    )

    if not response.results:
        raise ServiceFailingError("LLM", "resume rerank returned no results")

    returned_ids = [item.resume_id for item in response.results]
    if len(returned_ids) != len(set(returned_ids)):
        raise ServiceFailingError("LLM", "resume rerank returned duplicate resume_ids")

    returned_set = set(returned_ids)
    if returned_set != expected_ids:
        missing = sorted(expected_ids - returned_set)
        extra = sorted(returned_set - expected_ids)
        raise ServiceFailingError(
            "LLM",
            f"resume rerank resume_id mismatch: missing={missing}, extra={extra}",
        )

    by_id = {candidate.resume_id: candidate for candidate in candidates}
    for item in response.results:
        profile = by_id[item.resume_id].profile
        if not _rationale_references_resume(item.rationale, profile):
            if attempt == 0:
                return _llm_rerank(job, candidates, attempt=1)
            raise ServiceFailingError(
                "LLM",
                f"resume rerank rationale lacks concrete resume references for {item.resume_id}",
            )

    return {item.resume_id: item for item in response.results}


def rank_resumes_for_job(
    job: Job,
    candidates: list[ResumeCandidate],
    *,
    use_llm: bool = True,
) -> list[RankedResumeRecommendation]:
    if not candidates:
        return []

    by_id = {candidate.resume_id: candidate for candidate in candidates}
    rankables = [_candidate_to_rankable(candidate) for candidate in candidates]
    job_query = _job_query_text(job)
    coverage_lookup: dict[str, list[RequirementCoverage]] = {}

    def rerank_fn(rerank_candidates: list[Rankable]) -> dict[str, RerankResult]:
        rerank_list = [by_id[candidate.id] for candidate in rerank_candidates]
        lookup = _llm_rerank(job, rerank_list)
        for resume_id, item in lookup.items():
            coverage_lookup[resume_id] = item.coverage
        return {
            resume_id: RerankResult(
                fit_score=item.fit_score,
                matched_skills=item.matched_skills,
                missing_skills=item.missing_skills,
                rationale=item.rationale,
            )
            for resume_id, item in lookup.items()
        }

    scored = hybrid_rank(
        job_query,
        job_query,
        rankables,
        rerank_fn=rerank_fn if use_llm else None,
        skill_overlap_fn=lambda rankable: skill_jaccard(by_id[rankable.id].profile.skills, job.skills),
        recency_fn=lambda _rankable: 0.0,
        experience_fn=lambda rankable: _experience_score(job, by_id[rankable.id].profile),
        requirements_fn=lambda rankable: _requirements_score(job, by_id[rankable.id].profile),
        use_llm=use_llm,
        score_pool="all",
        top_n=settings.RESUME_RECOMMEND_TOP_N,
    )

    ranked: list[RankedResumeRecommendation] = []
    for item in scored:
        candidate = by_id[item.id]
        ranked.append(
            RankedResumeRecommendation(
                resume_id=candidate.resume_id,
                filename=candidate.filename,
                match_score=item.final_score,
                score_breakdown=ScoreBreakdown(
                    llm_fit=item.llm_fit,
                    rrf_normalized=item.rrf_normalized,
                    skill_jaccard=item.skill_overlap,
                    recency=0.0,
                    experience_fit=item.experience_fit,
                    requirements_met=item.requirements_met,
                    final_score=item.final_score,
                    matched_skills=item.matched_skills,
                    missing_skills=item.missing_skills,
                    rationale=item.rationale,
                ),
                coverage=coverage_lookup.get(item.id, []),
            )
        )
    return ranked
