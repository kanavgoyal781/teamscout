from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.schemas.jobs import Job
from app.schemas.library import RequirementCoverage, ResumeCandidate
from app.schemas.resume import ResumeProfile
from app.services import resume_ranking
from app.services.resume_ranking import (
    _rationale_references_resume,
    _ResumeRerankItem,
    _ResumeRerankResponse,
    rank_resumes_for_job,
)


def _candidate(resume_id: str, title: str, skills: list[str], summary: str) -> ResumeCandidate:
    return ResumeCandidate(
        resume_id=resume_id,
        filename=f"{resume_id}.pdf",
        profile=ResumeProfile(
            name=title,
            title=title,
            years_of_experience=6,
            location="Remote",
            skills=skills,
            work_experience=[],
            summary=summary,
        ),
    )


def test_rank_resumes_for_job_orders_best_first() -> None:
    job = Job(
        id="rank-job-1",
        source="fixture",
        source_job_id="rank-fixture-1",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI PostgreSQL AWS required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
    )
    candidates = [
        _candidate("weak", "Java Engineer", ["Java"], "Java microservices"),
        _candidate(
            "best",
            "Senior Python Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Built Python APIs at Acme with FastAPI and PostgreSQL on AWS",
        ),
        _candidate("mid", "Python Developer", ["Python", "Django"], "Django web apps"),
    ]

    rerank = {
        "weak": _ResumeRerankItem(
            resume_id="weak",
            fit_score=20,
            matched_skills=["Java"],
            missing_skills=["Python"],
            rationale="Java only",
            coverage=[],
        ),
        "best": _ResumeRerankItem(
            resume_id="best",
            fit_score=95,
            matched_skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
            missing_skills=[],
            rationale="Built Python APIs at Acme with FastAPI and PostgreSQL on AWS",
            coverage=[
                RequirementCoverage(requirement="Python", status="hit", evidence="Python APIs at Acme"),
            ],
        ),
        "mid": _ResumeRerankItem(
            resume_id="mid",
            fit_score=55,
            matched_skills=["Python"],
            missing_skills=["FastAPI"],
            rationale="Django background",
            coverage=[],
        ),
    }

    with patch("app.services.hybrid_rank.dense_ranking", return_value=["best", "mid", "weak"]):
        with patch("app.services.hybrid_rank.lexical_ranking", return_value=["best", "weak", "mid"]):
            with patch("app.services.resume_ranking._llm_rerank", return_value=rerank):
                ranked = rank_resumes_for_job(job, candidates)

    assert ranked[0].resume_id == "best"
    assert ranked[0].coverage[0].status == "hit"


def test_rank_resumes_for_job_scores_full_library_beyond_rerank_top_n() -> None:
    job = Job(
        id="rank-job-full-pool",
        source="fixture",
        source_job_id="rank-fixture-full",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI PostgreSQL AWS required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
    )
    candidates = [
        _candidate(f"resume-{index}", f"Engineer {index}", ["Java"], f"Summary {index}") for index in range(1, 36)
    ]
    candidates.append(
        _candidate(
            "rrf-outlier",
            "Senior Python Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Built Python APIs at Acme with FastAPI and PostgreSQL on AWS",
        ),
    )

    dense_order = [f"resume-{index}" for index in range(1, 36)] + ["rrf-outlier"]
    lexical_order = list(reversed(dense_order))

    top_rerank_ids = dense_order[:30]
    rerank = {
        resume_id: _ResumeRerankItem(
            resume_id=resume_id,
            fit_score=10.0,
            matched_skills=[],
            missing_skills=["Python"],
            rationale=f"Generic fit for {resume_id}",
            coverage=[],
        )
        for resume_id in top_rerank_ids
    }

    with patch("app.services.hybrid_rank.dense_ranking", return_value=dense_order):
        with patch("app.services.hybrid_rank.lexical_ranking", return_value=lexical_order):
            with patch("app.services.resume_ranking._llm_rerank", return_value=rerank):
                ranked = rank_resumes_for_job(job, candidates)

    ranked_ids = {item.resume_id for item in ranked}
    assert "rrf-outlier" in ranked_ids
    outlier = next(item for item in ranked if item.resume_id == "rrf-outlier")
    assert outlier.score_breakdown.llm_fit == 0.0
    assert outlier.score_breakdown.rrf_normalized > 0.0
    assert outlier.score_breakdown.experience_fit is not None


def test_rationale_references_resume_rejects_generic_praise() -> None:
    profile = ResumeProfile(
        name="Alex Rivera",
        title="Senior Python Engineer",
        years_of_experience=6,
        location="Remote",
        skills=["Python", "FastAPI"],
        work_experience=[],
        summary="Built Python APIs at Acme",
    )
    assert _rationale_references_resume("Great candidate with strong overall fit.", profile) is False
    assert (
        _rationale_references_resume(
            "Built Python APIs at Acme with FastAPI on AWS.",
            profile,
        )
        is True
    )


def test_llm_rerank_retries_then_rejects_generic_rationale() -> None:
    job = Job(
        id="rank-job-2",
        source="fixture",
        source_job_id="rank-fixture-2",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI"],
    )
    candidate = _candidate(
        "best",
        "Senior Python Engineer",
        ["Python", "FastAPI"],
        "Built Python APIs at Acme",
    )
    generic = _ResumeRerankItem(
        resume_id="best",
        fit_score=90,
        matched_skills=["Python"],
        missing_skills=[],
        rationale="Excellent overall fit for this role.",
        coverage=[],
    )
    concrete = _ResumeRerankItem(
        resume_id="best",
        fit_score=95,
        matched_skills=["Python", "FastAPI"],
        missing_skills=[],
        rationale="Built Python APIs at Acme with FastAPI.",
        coverage=[],
    )

    with patch(
        "app.services.resume_ranking.llm.complete_json",
        side_effect=[
            _ResumeRerankResponse(results=[generic]),
            _ResumeRerankResponse(results=[concrete]),
        ],
    ) as llm_mock:
        result = resume_ranking._llm_rerank(job, [candidate])

    assert llm_mock.call_count == 2
    assert result["best"].rationale.startswith("Built Python")


def test_llm_rerank_raises_after_generic_retry_exhausted() -> None:
    from app.errors import ServiceFailingError

    job = Job(
        id="rank-job-3",
        source="fixture",
        source_job_id="rank-fixture-3",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python"],
    )
    candidate = _candidate("best", "Senior Python Engineer", ["Python"], "Python at Acme")
    generic = _ResumeRerankItem(
        resume_id="best",
        fit_score=90,
        matched_skills=["Python"],
        missing_skills=[],
        rationale="Excellent overall fit for this role.",
        coverage=[],
    )

    with patch(
        "app.services.resume_ranking.llm.complete_json",
        return_value=_ResumeRerankResponse(results=[generic]),
    ):
        with pytest.raises(ServiceFailingError) as exc:
            resume_ranking._llm_rerank(job, [candidate])

    assert "lacks concrete resume references" in exc.value.message
