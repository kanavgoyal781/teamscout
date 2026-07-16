"""JobMetadata validators, sparse honesty, cache, and API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from app.db.session import SessionLocal, init_db
from app.main import app
from app.schemas.job_metadata import JobMetadata, parse_salary_range, parse_salary_token
from app.services.jobs_svc import jd_metadata as jd_meta_mod
from fastapi.testclient import TestClient

FIXDIR = Path(__file__).parent / "fixtures" / "jd_metadata"
PRESENT_FIELDS = (
    "title",
    "company",
    "location",
    "remote_mode",
    "salary_min",
    "salary_max",
    "salary_currency",
    "seniority",
    "department",
)


def test_salary_token_k_suffix() -> None:
    assert parse_salary_token("$230K") == 230_000


def test_salary_up_to() -> None:
    mn, mx, cur = parse_salary_range("up to $300K")
    assert mn is None and mx == 300_000 and cur == "USD"


def test_salary_gbp_range() -> None:
    mn, mx, cur = parse_salary_range("£60-70k")
    assert mn == 60_000 and mx == 70_000 and cur == "GBP"


def test_salary_hourly_not_annualized() -> None:
    assert parse_salary_token("$80/hr") is None


def test_title_company_strip_punct() -> None:
    m = JobMetadata(title="Engineer,,,", company="Acme Inc.—")
    assert m.title == "Engineer"
    assert m.company == "Acme Inc"


def test_currency_upper() -> None:
    assert JobMetadata(salary_currency="usd").salary_currency == "USD"


def test_sparse_fixture_expected_all_null() -> None:
    exp = json.loads((FIXDIR / "09_sparse_nulls.json").read_text())["expected"]
    for k in PRESENT_FIELDS:
        assert exp.get(k) is None


def test_fixture_suite_shapes_are_diverse() -> None:
    shapes = [json.loads(p.read_text())["shape"] for p in sorted(FIXDIR.glob("*.json"))]
    assert len(shapes) >= 10
    assert len(set(shapes)) >= 10


def assert_no_hallucinations(expected: dict, actual: JobMetadata) -> None:
    act = actual.model_dump()
    for f in PRESENT_FIELDS:
        if expected.get(f) is None and act.get(f) is not None:
            raise AssertionError(f"hallucinated {f}={act.get(f)!r}")


def test_sparse_hallucination_hard_fail() -> None:
    sparse = json.loads((FIXDIR / "09_sparse_nulls.json").read_text())["expected"]
    assert_no_hallucinations(sparse, JobMetadata())
    with pytest.raises(AssertionError):
        assert_no_hallucinations(sparse, JobMetadata(company="Google"))


def test_extract_metadata_uses_cache() -> None:
    init_db()
    db = SessionLocal()
    fake = JobMetadata(title="X", company="Y", confidence={"title": "high", "company": "high"})
    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return fake

    text = "We need a backend engineer at ExampleCo in NYC for five years of Python work please."
    try:
        with patch.object(jd_meta_mod.llm, "complete_json", side_effect=_fake):
            _, hit1, h1 = jd_meta_mod.extract_job_metadata(text, db=db)
            _, hit2, h2 = jd_meta_mod.extract_job_metadata(text, db=db)
        assert hit1 is False and hit2 is True and h1 == h2 and calls["n"] == 1
    finally:
        db.close()


def test_api_extract_metadata_endpoint() -> None:
    init_db()
    client = TestClient(app)
    fake = JobMetadata(title="Role", company=None, confidence={"title": "high"})
    with patch("app.services.jobs_svc.jd_metadata.llm.complete_json", return_value=fake):
        r = client.post(
            "/jobs/extract-metadata",
            json={"description": "Role for a person who likes APIs and tests. " * 5},
        )
    assert r.status_code == 200, r.text
    assert r.json()["metadata"]["title"] == "Role"
    assert r.json()["metadata"]["company"] is None


def test_one_llm_call_per_unique_jd_hash() -> None:
    init_db()
    db = SessionLocal()
    meta = JobMetadata(title="Backend Engineer", company="Acme", confidence={"title": "high", "company": "high"})
    calls = {"n": 0}

    def _llm(*a, **k):
        calls["n"] += 1
        return meta

    jd = "Backend Engineer\nAcme Robotics\nSan Francisco\n" + ("Build APIs. " * 30)
    try:
        with patch.object(jd_meta_mod.llm, "complete_json", side_effect=_llm):
            jd_meta_mod.extract_job_metadata(jd, db=db)
            jd_meta_mod.extract_job_metadata(jd, db=db)
            # downstream consumers reuse cache — still one call
            jd_meta_mod.extract_job_metadata(jd, db=db)
        assert calls["n"] == 1
    finally:
        db.close()


def test_feature2_recommend_from_jd_one_metadata_call(client: TestClient) -> None:
    """Drive real POST /library/recommend-from-jd; jd_metadata LLM once; ranking still runs with hints."""
    from app.db.models import Resume
    from app.db.session import SessionLocal, init_db
    from app.schemas.job_metadata import JobMetadata
    from app.schemas.jobs import ScoreBreakdown
    from app.schemas.library import RankedResumeRecommendation, RequirementCoverage
    from app.schemas.resume import ResumeProfile

    init_db()
    wid = client.get("/workspace").json()["workspace_id"]
    profile = ResumeProfile(
        name="Alex",
        title="Backend Engineer",
        years_of_experience=5,
        location="SF",
        skills=["Python", "FastAPI"],
        work_experience=[],
        summary="Python APIs",
    )
    db = SessionLocal()
    try:
        db.add(
            Resume(
                workspace_id=wid,
                filename="alex.pdf",
                content_hash="f2-meta-one-call",
                file_path="/tmp/alex.pdf",
                parsed_json=profile.model_dump_json(),
                confirmed=True,
                in_library=True,
            )
        )
        db.commit()
    finally:
        db.close()

    meta = JobMetadata(
        title="Backend Engineer",
        company="Acme Robotics",
        location="SF",
        confidence={"title": "high", "company": "high", "location": "high"},
    )
    recs = [
        RankedResumeRecommendation(
            resume_id="x",
            filename="alex.pdf",
            match_score=90.0,
            score_breakdown=ScoreBreakdown(
                llm_fit=90,
                rrf_normalized=0.9,
                skill_jaccard=0.8,
                recency=0.5,
                final_score=90.0,
                matched_skills=["Python"],
                missing_skills=[],
                rationale="fit",
            ),
            coverage=[RequirementCoverage(requirement="Python", status="hit", evidence="Python")],
        )
    ]
    llm_ops: list[str] = []

    def _complete_json(*args, **kwargs):
        op = kwargs.get("operation") or "llm"
        llm_ops.append(op)
        return meta

    jd = "Backend Engineer\nAcme Robotics\nSan Francisco, CA\n" + ("Build Python APIs. " * 25)
    with (
        patch("app.services.jobs_svc.jd_metadata.llm.complete_json", side_effect=_complete_json),
        patch("app.api.routers.library.resume_ranking.rank_resumes_for_job", return_value=recs) as rank_mock,
    ):
        r = client.post(
            "/library/recommend-from-jd",
            json={"job_description": jd},
        )
    assert r.status_code == 200, r.text
    assert llm_ops.count("jd_metadata") == 1, llm_ops
    assert sum(1 for o in llm_ops if o == "jd_metadata") == 1
    rank_mock.assert_called_once()
    # metadata_hints passed into ranking
    kwargs = rank_mock.call_args.kwargs
    assert kwargs.get("metadata_hints") is not None
    assert kwargs["metadata_hints"].company == "Acme Robotics"
