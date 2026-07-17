"""M22: justification inference-excuse grounding (pandas/numpy caliber live bug)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services.resume.jd_decompose import JdRequirement
from app.services.resume.justify import (
    ResumeRerankItem,
    ResumeRerankResponse,
    llm_justify,
    rationale_has_inference_excuse,
)


def test_inference_excuse_detector_flags_caliber_and_standard_for() -> None:
    assert rationale_has_inference_excuse(
        "Missing pandas/numpy is fine — they are standard libraries for a data scientist of this caliber."
    )
    assert rationale_has_inference_excuse("Would typically know SQL at this level.")
    assert rationale_has_inference_excuse("Presumably has cloud experience.")
    # Legitimate grounded text without excuse patterns
    assert not rationale_has_inference_excuse(
        "Evidence: Built production FastAPI services on AWS with PostgreSQL. "
        "Missing: pandas and numpy are not listed in resume evidence."
    )
    # "standard" alone in other contexts should not trip without "for/of"
    assert not rationale_has_inference_excuse("Followed company standard operating procedures for releases.")


def test_llm_justify_rejects_pandas_numpy_caliber_excuse() -> None:
    """Shipped path: first LLM response with caliber excuse is retried then fails closed."""
    job = Job(
        id="j1",
        source="fixture",
        source_job_id="j1",
        title="Data Scientist",
        company="Acme",
        location="Remote",
        description="Need Python, pandas, numpy.",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python", "pandas", "numpy"],
    )
    candidate = ResumeCandidate(
        resume_id="r1",
        filename="r1.pdf",
        content_hash="h1",
        profile=ResumeProfile(
            name="Pat",
            title="Data Scientist",
            years_of_experience=8,
            location="Remote",
            skills=["Python", "scikit-learn"],
            work_experience=[
                WorkExperience(
                    title="DS",
                    company="Past",
                    bullets=["Built scikit-learn models in Python for churn prediction."],
                )
            ],
            summary="Senior data scientist with Python.",
        ),
    )
    alignment = {
        "r1": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": "Built scikit-learn models in Python for churn prediction.",
                "evidence_score": 1.0,
                "kind": "must",
            },
            {
                "requirement": "pandas",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
            {
                "requirement": "numpy",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
        ]
    }
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="pandas", kind="must", category="skill", weight=2.0),
        JdRequirement(text="numpy", kind="must", category="skill", weight=2.0),
    ]
    excuse = (
        "Strong Python ML delivery. Missing pandas and numpy are standard libraries "
        "for a data scientist of this caliber."
    )
    good = (
        "Built scikit-learn models in Python for churn prediction. "
        "Missing: pandas and numpy are not evidenced on the resume."
    )
    calls = {"n": 0}

    def fake_complete(prompt, schema, **kwargs):
        calls["n"] += 1
        text = excuse if calls["n"] <= 2 else good
        return ResumeRerankResponse(
            results=[
                ResumeRerankItem(
                    resume_id="r1",
                    fit_score=70,
                    matched_skills=["Python"],
                    missing_skills=["pandas", "numpy"],
                    rationale=text,
                    coverage=[],
                )
            ]
        )

    prompt_meta = MagicMock(
        body="justify body",
        system="json",
        version="3",
        content_hash="jh",
        name="justify",
        model_params={},
    )
    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
        with patch("app.services.resume.justify.load_prompt", return_value=prompt_meta):
            with patch("app.services.ops.observability.record_trace"):
                out = llm_justify(
                    job,
                    [candidate],
                    alignment,
                    reqs,
                    rank_by_id={"r1": 1},
                )
    # After retry still excuse → structured fallback (never ServiceFailingError / kill ranking)
    assert calls["n"] >= 2
    assert out["r1"].justification_status == "fallback"
    assert "Must-haves without clear evidence" in out["r1"].rationale
    assert "caliber" not in out["r1"].rationale.lower()


def test_llm_justify_accepts_honest_missing_must_haves() -> None:
    job = Job(
        id="j2",
        source="fixture",
        source_job_id="j2",
        title="Data Scientist",
        company="Acme",
        location="Remote",
        description="Need Python, pandas.",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python", "pandas"],
    )
    candidate = ResumeCandidate(
        resume_id="r1",
        filename="r1.pdf",
        content_hash="h1",
        profile=ResumeProfile(
            name="Pat",
            title="Data Scientist",
            years_of_experience=5,
            location="Remote",
            skills=["Python"],
            work_experience=[
                WorkExperience(
                    title="DS",
                    company="Past",
                    bullets=["Built scikit-learn models in Python for churn prediction."],
                )
            ],
            summary="Python DS.",
        ),
    )
    alignment = {
        "r1": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": "Built scikit-learn models in Python for churn prediction.",
                "evidence_score": 1.0,
                "kind": "must",
            },
            {
                "requirement": "pandas",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
        ]
    }
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="pandas", kind="must", category="skill", weight=2.0),
    ]
    prompt_meta = MagicMock(
        body="justify body",
        system="json",
        version="3",
        content_hash="jh",
        name="justify",
        model_params={},
    )

    def fake_complete(prompt, schema, **kwargs):
        return ResumeRerankResponse(
            results=[
                ResumeRerankItem(
                    resume_id="r1",
                    fit_score=65,
                    matched_skills=["Python"],
                    missing_skills=["pandas"],
                    rationale=(
                        "Built scikit-learn models in Python for churn prediction. Missing: pandas is not evidenced."
                    ),
                    coverage=[],
                )
            ]
        )

    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
        with patch("app.services.resume.justify.load_prompt", return_value=prompt_meta):
            out = llm_justify(job, [candidate], alignment, reqs, rank_by_id={"r1": 1})
    assert "r1" in out
    assert "pandas" in (out["r1"].missing_skills or ["pandas"])
