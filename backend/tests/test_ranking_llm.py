from unittest.mock import patch

import pytest
from app.errors import ServiceFailingError
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services.ranking.engine import _llm_rerank, _RerankItem, _RerankResponse, rank_jobs


def _job(job_id: str) -> Job:
    return Job(
        id=job_id,
        source="fixture",
        source_job_id=job_id,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI PostgreSQL. 3 years experience.",
        apply_url="https://example.com/apply",
        skills=["Python"],
    )


def _profile() -> ResumeProfile:
    return ResumeProfile(
        title="Backend Engineer",
        skills=["Python"],
        location="Remote",
        years_of_experience=3,
    )


def test_llm_rerank_fills_missing_aliases_with_heuristic() -> None:
    """Partial LLM results no longer hard-fail the search.

    Retry on missing IDs re-aliases remaining jobs as j0.. — a constant
    partial return would map onto the retry set. Force empty retry so
    heuristic fill is exercised.
    """
    jobs = [_job("job-1"), _job("job-2")]
    partial = _RerankResponse(
        results=[
            _RerankItem(
                job_id="j0",
                fit_score=90,
                matched_skills=["Python"],
                missing_skills=[],
                rationale="Strong fit",
            )
        ]
    )
    calls = {"n": 0}

    def _side_effect(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return partial
        return _RerankResponse(results=[])

    with patch("app.services.ranking.engine.llm.complete_json", side_effect=_side_effect):
        out = _llm_rerank(_profile(), jobs)
    assert set(out) == {"job-1", "job-2"}
    assert out["job-1"].fit_score == 90
    assert "heuristic" in out["job-2"].rationale.lower()


def test_llm_rerank_rejects_empty_results() -> None:
    jobs = [_job("job-1")]
    with patch("app.services.ranking.engine.llm.complete_json", return_value=_RerankResponse(results=[])):
        with pytest.raises(ServiceFailingError) as exc:
            _llm_rerank(_profile(), jobs)
    assert "no results" in exc.value.message


def test_llm_rerank_ignores_duplicate_aliases_first_wins() -> None:
    jobs = [_job("job-1"), _job("job-2")]
    duplicate = _RerankResponse(
        results=[
            _RerankItem(job_id="j0", fit_score=90, rationale="a"),
            _RerankItem(job_id="j0", fit_score=80, rationale="b"),
            _RerankItem(job_id="j1", fit_score=50, rationale="c"),
        ]
    )
    with patch("app.services.ranking.engine.llm.complete_json", return_value=duplicate):
        out = _llm_rerank(_profile(), jobs)
    assert out["job-1"].fit_score == 90
    assert out["job-2"].fit_score == 50


def test_rank_jobs_survives_partial_llm_rerank() -> None:
    jobs = [_job("job-1"), _job("job-2")]
    partial = _RerankResponse(results=[_RerankItem(job_id="j0", fit_score=90, rationale="fit")])
    with patch("app.services.ranking.hybrid.dense_ranking", return_value=["job-1", "job-2"]):
        with patch("app.services.ranking.hybrid.lexical_ranking", return_value=["job-2", "job-1"]):
            with patch("app.services.ranking.engine.llm.complete_json", return_value=partial):
                ranked = rank_jobs(_profile(), jobs, use_llm=True)
    assert len(ranked) >= 1
    ids = {r.job.id for r in ranked}
    assert ids <= {"job-1", "job-2"}
