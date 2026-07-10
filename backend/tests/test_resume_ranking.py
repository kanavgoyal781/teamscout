"""Tests for requirement-level resume ranking (MaxSim + grounding)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.errors import ServiceFailingError
from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services import resume_ranking
from app.services.resume_ranking import (
    _rationale_cites_units,
    _rationale_references_resume,
    _ResumeRerankItem,
    _ResumeRerankResponse,
    rank_resumes_for_job,
)


def _norm_bag(text: str, dim: int = 32) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().replace("/", " ").split():
        h = hash(token) % dim
        vec[h] += 1.0
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    return [_norm_bag(t) for t in texts]


def _candidate(
    resume_id: str, title: str, skills: list[str], summary: str, bullets: list[str] | None = None
) -> ResumeCandidate:
    return ResumeCandidate(
        resume_id=resume_id,
        filename=f"{resume_id}.pdf",
        content_hash=f"hash-{resume_id}",
        profile=ResumeProfile(
            name=title,
            title=title,
            years_of_experience=6,
            location="Remote",
            skills=skills,
            work_experience=[
                WorkExperience(title=title, company="Acme", bullets=bullets or [summary]),
            ],
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
        _candidate("weak", "Java Engineer", ["Java"], "Java microservices", ["Java Spring only"]),
        _candidate(
            "best",
            "Senior Python Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Built Python APIs at Acme with FastAPI and PostgreSQL on AWS",
            ["Built Python APIs at Acme with FastAPI and PostgreSQL on AWS"],
        ),
        _candidate("mid", "Python Developer", ["Python", "Django"], "Django web apps", ["Django apps"]),
    ]

    with patch("app.services.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume_ranking.decompose_jd") as dec:
                from app.services.jd_decompose import JdRequirement

                dec.return_value = [
                    JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="FastAPI", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="PostgreSQL", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="AWS", kind="must", category="skill", weight=1.0),
                ]
                ranked = rank_resumes_for_job(job, candidates, use_llm=False)

    assert ranked[0].resume_id == "best"
    assert ranked[0].coverage_score >= ranked[-1].coverage_score
    assert ranked[0].alignment
    assert ranked[0].cluster_id is not None


def test_rank_resumes_includes_alignment_matrix() -> None:
    job = Job(
        id="rank-job-align",
        source="fixture",
        source_job_id="rank-align",
        title="Python Engineer",
        company="Acme",
        location="Remote",
        description="Python required.",
        apply_url="https://example.com/apply",
        posted_at=None,
        skills=["Python"],
    )
    candidates = [_candidate("only", "Python Engineer", ["Python"], "Python services")]
    with patch("app.services.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.resume_ranking.decompose_jd") as dec:
            from app.services.jd_decompose import JdRequirement

            dec.return_value = [
                JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
            ]
            ranked = rank_resumes_for_job(job, candidates, use_llm=False)
    assert len(ranked) == 1
    assert ranked[0].alignment[0].requirement == "Python"
    assert 0.0 <= ranked[0].coverage_score <= 1.0


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


def test_rationale_cites_units_grounding() -> None:
    units = ["Shipped FastAPI microservices on AWS with PostgreSQL"]
    assert _rationale_cites_units("Excellent overall culture fit and communication.", units) is False
    assert _rationale_cites_units(
        "Strong match because they Shipped FastAPI microservices on AWS with PostgreSQL in production.",
        units,
    )


def test_llm_justify_retries_then_rejects_generic_rationale() -> None:
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
        ["Built Python APIs at Acme with FastAPI"],
    )
    alignment = {
        "best": [
            {
                "requirement": "Python",
                "evidence_unit": "Built Python APIs at Acme with FastAPI",
                "evidence_score": 0.9,
                "status": "hit",
            }
        ]
    }
    from app.services.jd_decompose import JdRequirement

    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]
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
        "app.services.resume_justify.llm.complete_json",
        side_effect=[
            _ResumeRerankResponse(results=[generic]),
            _ResumeRerankResponse(results=[concrete]),
        ],
    ) as llm_mock:
        result = resume_ranking._llm_justify(job, [candidate], alignment, reqs)

    assert llm_mock.call_count == 2
    assert result["best"].rationale.startswith("Built Python")


def test_llm_justify_raises_after_generic_retry_exhausted() -> None:
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
    alignment = {
        "best": [
            {
                "requirement": "Python",
                "evidence_unit": "Python services at Acme cloud",
                "evidence_score": 0.8,
                "status": "hit",
            }
        ]
    }
    from app.services.jd_decompose import JdRequirement

    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]
    generic = _ResumeRerankItem(
        resume_id="best",
        fit_score=90,
        matched_skills=["Python"],
        missing_skills=[],
        rationale="Excellent overall fit for this role.",
        coverage=[],
    )

    with patch(
        "app.services.resume_justify.llm.complete_json",
        return_value=_ResumeRerankResponse(results=[generic]),
    ):
        with pytest.raises(ServiceFailingError) as exc:
            resume_ranking._llm_justify(job, [candidate], alignment, reqs)

    assert "evidence units" in exc.value.message or "concrete" in exc.value.message


def test_rationale_cites_units_rejects_skill_name_only() -> None:
    units = ["Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards"]
    assert (
        _rationale_cites_units(
            "Candidate has strong FastAPI and PostgreSQL experience overall.",
            units,
        )
        is False
    )
    assert (
        _rationale_cites_units(
            "Strong match: Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards.",
            units,
        )
        is True
    )


def test_rationale_cites_units_rejects_skill_label_when_long_unit_present() -> None:
    units = ["Python", "Shipped Python FastAPI services on AWS with PostgreSQL at scale"]
    assert (
        _rationale_cites_units(
            "Excellent culture fit with solid Python background for the team.",
            units,
        )
        is False
    )
    assert (
        _rationale_cites_units(
            "Evidence: Shipped Python FastAPI services on AWS with PostgreSQL at scale.",
            units,
        )
        is True
    )


def test_rationale_cites_units_allows_short_when_only_short_units() -> None:
    assert (
        _rationale_cites_units(
            "Candidate has solid Python experience for this backend role.",
            ["Python"],
        )
        is True
    )


def test_rationale_cites_units_fail_closed_on_empty() -> None:
    assert _rationale_cites_units("Built Python APIs at Acme with FastAPI on AWS.", []) is False


def test_pairwise_cache_key_includes_prompt_version_and_is_ab_symmetric() -> None:
    from unittest.mock import patch

    from app.prompts import load_prompt
    from app.schemas.jobs import Job
    from app.services.pairwise_tournament import pairwise_cache_key, tournament_jd_key

    job = Job(
        id="j1",
        source="fixture",
        source_job_id="j1",
        title="Engineer",
        company="Co",
        location="Remote",
        description="Python FastAPI",
        apply_url="https://example.com",
        posted_at=None,
        skills=["Python"],
    )
    key = tournament_jd_key(job)
    k1 = pairwise_cache_key(key, "hash-a", "hash-b")
    k2 = pairwise_cache_key(key, "hash-b", "hash-a")
    assert k1 == k2
    # Prompt version is folded into tournament_jd_key
    tmpl = load_prompt("pairwise_judge")
    with patch("app.services.pairwise_tournament.load_prompt") as lp:

        class T:
            version = tmpl.version + "-mutated"
            content_hash = "deadbeef"
            name = "pairwise_judge"
            body = tmpl.body
            system = tmpl.system
            model_params = tmpl.model_params

        lp.return_value = T()
        key2 = tournament_jd_key(job)
    assert key2 != key
