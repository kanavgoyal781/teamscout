from unittest.mock import patch

import pytest

from app.errors import ServiceFailingError
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services.ranking import _RerankItem, _RerankResponse, _llm_rerank, rank_jobs


def _job(job_id: str) -> Job:
    return Job(
        id=job_id,
        source="fixture",
        source_job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI PostgreSQL",
        apply_url="https://example.com/apply",
        skills=["Python"],
    )


def _profile() -> ResumeProfile:
    return ResumeProfile(title="Backend Engineer", skills=["Python"], location="Remote")


def test_llm_rerank_requires_all_job_ids() -> None:
    jobs = [_job("job-1"), _job("job-2")]
    partial = _RerankResponse(
        results=[
            _RerankItem(
                job_id="job-1",
                fit_score=90,
                matched_skills=["Python"],
                missing_skills=[],
                rationale="Strong fit",
            )
        ]
    )
    with patch("app.services.ranking.llm.complete_json", return_value=partial):
        with pytest.raises(ServiceFailingError) as exc:
            _llm_rerank(_profile(), jobs)
    assert "job_id mismatch" in exc.value.message


def test_llm_rerank_rejects_empty_results() -> None:
    jobs = [_job("job-1")]
    with patch("app.services.ranking.llm.complete_json", return_value=_RerankResponse(results=[])):
        with pytest.raises(ServiceFailingError) as exc:
            _llm_rerank(_profile(), jobs)
    assert "no results" in exc.value.message


def test_llm_rerank_rejects_duplicate_job_ids() -> None:
    jobs = [_job("job-1"), _job("job-2")]
    duplicate = _RerankResponse(
        results=[
            _RerankItem(job_id="job-1", fit_score=90, rationale="a"),
            _RerankItem(job_id="job-1", fit_score=80, rationale="b"),
        ]
    )
    with patch("app.services.ranking.llm.complete_json", return_value=duplicate):
        with pytest.raises(ServiceFailingError) as exc:
            _llm_rerank(_profile(), jobs)
    assert "duplicate job_ids" in exc.value.message


def test_rank_jobs_raises_on_partial_llm_rerank() -> None:
    jobs = [_job("job-1"), _job("job-2")]
    partial = _RerankResponse(
        results=[_RerankItem(job_id="job-1", fit_score=90, rationale="fit")]
    )
    with patch("app.services.hybrid_rank.dense_ranking", return_value=["job-1", "job-2"]):
        with patch("app.services.hybrid_rank.lexical_ranking", return_value=["job-2", "job-1"]):
            with patch("app.services.ranking.llm.complete_json", return_value=partial):
                with pytest.raises(ServiceFailingError):
                    rank_jobs(_profile(), jobs, use_llm=True)