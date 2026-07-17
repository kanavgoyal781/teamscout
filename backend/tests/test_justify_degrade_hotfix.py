"""Hotfix: justify grounding degrades to structured fallback; never kills Feature-2 rankings."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services.resume.jd_decompose import JdRequirement
from app.services.resume.justify import (
    ResumeRerankItem,
    ResumeRerankResponse,
    _span_in_text,
    build_fallback_justification,
    is_sparse_evidence,
    llm_justify,
    rationale_cites_units,
)

UNIT = "Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards for production traffic"


def _job() -> Job:
    return Job(
        id="j-hot",
        source="fixture",
        source_job_id="j-hot",
        title="Senior Backend Engineer",
        company="Acme",
        location="Remote",
        description="Need Python, FastAPI, AWS, PostgreSQL.",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI", "AWS", "PostgreSQL"],
    )


def _cand(rid: str, bullets: list[str], skills: list[str] | None = None) -> ResumeCandidate:
    return ResumeCandidate(
        resume_id=rid,
        filename=f"{rid}.pdf",
        content_hash=f"h-{rid}",
        profile=ResumeProfile(
            name=rid,
            title="Engineer",
            years_of_experience=5,
            location="Remote",
            skills=skills or ["Python"],
            work_experience=[WorkExperience(title="Eng", company="Co", bullets=bullets)],
            summary="Engineer.",
        ),
    )


def _prompt_meta(version: str = "4") -> MagicMock:
    return MagicMock(
        body="justify body",
        system="json",
        version=version,
        content_hash="jh",
        name="justify",
        model_params={},
    )


# --- (a) grounded rationale passes (normalization / ellipsis) ---


def test_citation_match_case_whitespace_and_ellipsis() -> None:
    unit = UNIT
    # case + whitespace
    assert _span_in_text(
        unit,
        "  SHIPPED   fastapi MICROSERVICES on aws with postgresql observability dashboards for production traffic  ",
    )
    # ellipsized ≥8-word quote (fragments land in unit)
    assert _span_in_text(
        unit,
        'Strong: "Shipped FastAPI microservices on AWS ... production traffic"',
    )
    # full continuous cite
    assert rationale_cites_units(
        f"Strong match because they {unit}.",
        [unit],
    )


# --- (b) fabricated citation fails ---


def test_fabricated_citation_fails_validation() -> None:
    unit = UNIT
    assert (
        rationale_cites_units(
            "Excellent overall culture fit and communication skills for this team.",
            [unit],
        )
        is False
    )
    assert (
        rationale_cites_units(
            'Built "quantum blockchain MLOps mesh" with zero relation to evidence.',
            [unit],
        )
        is False
    )
    # Quoted invent fails even if another real unit is cited
    assert (
        rationale_cites_units(
            f'Cited {unit} but also invented "led Series B fundraising at SpaceX".',
            [unit],
        )
        is False
    )


# --- sparse invent-reject + sparse accept ---


def test_sparse_mode_accepts_one_real_unit_and_rejects_invent() -> None:
    short_unit = "Built Python APIs at Acme with FastAPI"
    # sparse accepts short rationale citing the only unit
    assert rationale_cites_units(
        f"Limited evidence: {short_unit}. Missing: AWS not shown.",
        [short_unit],
        sparse_mode=True,
    )
    # invent-only fails even in sparse mode
    assert (
        rationale_cites_units(
            "Sparse resume but clearly a Kubernetes expert and SRE lead.",
            [short_unit],
            sparse_mode=True,
        )
        is False
    )


def test_is_sparse_evidence_uses_floor_and_k() -> None:
    rows = [
        {
            "requirement": "Python",
            "status": "hit",
            "evidence_unit": "Python at Acme",
            "evidence_score": 0.9,
            "kind": "must",
        },
        {
            "requirement": "AWS",
            "status": "miss",
            "evidence_unit": "No clear evidence",
            "evidence_score": 0.1,
            "kind": "must",
        },
        {
            "requirement": "Go",
            "status": "hit",
            "evidence_unit": "tiny",
            "evidence_score": 0.2,
            "kind": "nice",
        },  # below floor
    ]
    assert is_sparse_evidence(rows, k=3, evidence_floor=0.55) is True
    dense = [
        {
            "requirement": f"r{i}",
            "status": "hit",
            "evidence_unit": f"Evidence unit number {i} with enough text",
            "evidence_score": 0.8,
            "kind": "must",
        }
        for i in range(4)
    ]
    assert is_sparse_evidence(dense, k=3, evidence_floor=0.55) is False


def test_fallback_text_from_alignment_only() -> None:
    rows = [
        {
            "requirement": "Python",
            "status": "hit",
            "evidence_unit": "Built Python APIs at Acme with FastAPI",
            "evidence_score": 0.95,
            "kind": "must",
        },
        {
            "requirement": "AWS",
            "status": "miss",
            "evidence_unit": "No clear evidence",
            "evidence_score": 0.0,
            "kind": "must",
        },
        {
            "requirement": "PostgreSQL",
            "status": "miss",
            "evidence_unit": "No clear evidence",
            "evidence_score": 0.0,
            "kind": "must",
        },
    ]
    text = build_fallback_justification(rows)
    assert "Built Python APIs at Acme with FastAPI" in text
    assert "Python" in text
    assert "Must-haves without clear evidence: 2" in text
    # No LLM-ish invention phrases
    assert "caliber" not in text.lower()
    assert "presumably" not in text.lower()


def test_justify_prompt_v4_has_limited_evidence_rules() -> None:
    tmpl = load_prompt("justify")
    assert tmpl.version == "4"
    body = tmpl.body.lower()
    assert "limited-evidence" in body or "limited evidence" in body
    assert "sparse" in body


# --- (c) sparse-evidence resume limited-evidence e2e via llm_justify ---


def test_sparse_evidence_limited_justification_e2e() -> None:
    job = _job()
    cand = _cand("sparse1", ["Built Python APIs at Acme with FastAPI"])
    alignment = {
        "sparse1": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": "Built Python APIs at Acme with FastAPI",
                "evidence_score": 0.9,
                "kind": "must",
            },
            {
                "requirement": "AWS",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
            {
                "requirement": "PostgreSQL",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
        ]
    }
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="AWS", kind="must", category="skill", weight=2.0),
        JdRequirement(text="PostgreSQL", kind="must", category="skill", weight=2.0),
    ]
    assert is_sparse_evidence(alignment["sparse1"], k=3, evidence_floor=0.55)

    def fake_complete(prompt, schema, **kwargs):
        assert "sparse_evidence=true" in prompt or "LIMITED-EVIDENCE" in prompt
        return ResumeRerankResponse(
            results=[
                ResumeRerankItem(
                    resume_id="sparse1",
                    fit_score=55,
                    matched_skills=["Python"],
                    missing_skills=["AWS", "PostgreSQL"],
                    rationale=(
                        "Limited evidence: Built Python APIs at Acme with FastAPI. "
                        "Missing: AWS and PostgreSQL not evidenced."
                    ),
                    coverage=[],
                )
            ]
        )

    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
        with patch("app.services.resume.justify.load_prompt", return_value=_prompt_meta()):
            out = llm_justify(job, [cand], alignment, reqs, rank_by_id={"sparse1": 1})
    assert out["sparse1"].justification_status in {"ok", "limited_evidence"}
    assert "Built Python APIs" in out["sparse1"].rationale
    assert "LLM API is failing" not in out["sparse1"].rationale


# --- (d) forced double-rejection → structured fallback; rankings intact ---


def test_double_rejection_yields_fallback_not_service_failing() -> None:
    job = _job()
    cand = _cand("2f962b30", [UNIT], skills=["Python", "FastAPI"])
    peer = _cand(
        "peer-ok",
        ["Owned Python FastAPI services and PostgreSQL schemas in production on AWS."],
        skills=["Python", "FastAPI", "AWS", "PostgreSQL"],
    )
    alignment = {
        "2f962b30": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": UNIT,
                "evidence_score": 0.92,
                "kind": "must",
            },
            {
                "requirement": "Kubernetes",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
        ],
        "peer-ok": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": "Owned Python FastAPI services and PostgreSQL schemas in production on AWS.",
                "evidence_score": 0.95,
                "kind": "must",
            },
            {
                "requirement": "Kubernetes",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.0,
                "kind": "must",
            },
        ],
    }
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="Kubernetes", kind="must", category="skill", weight=2.0),
    ]
    generic = "Excellent overall culture fit and leadership for this role."
    peer_good = (
        "Owned Python FastAPI services and PostgreSQL schemas in production on AWS. Missing: Kubernetes not evidenced."
    )
    calls = {"n": 0}

    def fake_complete(prompt, schema, **kwargs):
        calls["n"] += 1
        # Always fail grounding for 2f962b30; peer always grounded
        return ResumeRerankResponse(
            results=[
                ResumeRerankItem(
                    resume_id="2f962b30",
                    fit_score=70,
                    matched_skills=["Python"],
                    missing_skills=["Kubernetes"],
                    rationale=generic,
                    coverage=[],
                ),
                ResumeRerankItem(
                    resume_id="peer-ok",
                    fit_score=88,
                    matched_skills=["Python"],
                    missing_skills=["Kubernetes"],
                    rationale=peer_good,
                    coverage=[],
                ),
            ]
        )

    traces: list[dict] = []

    def fake_trace(**kwargs):
        traces.append(kwargs)

    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
        with patch("app.services.resume.justify.load_prompt", return_value=_prompt_meta()):
            with patch("app.services.ops.observability.record_trace", side_effect=fake_trace):
                out = llm_justify(
                    job,
                    [cand, peer],
                    alignment,
                    reqs,
                    rank_by_id={"peer-ok": 1, "2f962b30": 2},
                )

    assert calls["n"] == 2  # attempt 0 + retry
    assert set(out) == {"2f962b30", "peer-ok"}
    assert out["2f962b30"].justification_status == "fallback"
    assert UNIT[:40] in out["2f962b30"].rationale or "Python" in out["2f962b30"].rationale
    assert "Must-haves without clear evidence" in out["2f962b30"].rationale
    assert out["peer-ok"].justification_status in {"ok", "limited_evidence"}
    assert "Owned Python FastAPI" in out["peer-ok"].rationale
    # No ServiceFailingError path
    assert not any("failing" in (out[r].rationale or "").lower() for r in out)
    assert any(t.get("operation") == "justify" and t.get("status") == "grounding_rejected" for t in traces)


def test_rank_resumes_survives_grounding_reject_full_list() -> None:
    """Synthetic analog of live Feature-2 failure: full ranking list intact with fallback."""

    job = _job()
    strong = _cand(
        "strong",
        [
            "Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards for production traffic",
            "Led Python platform migration",
        ],
        skills=["Python", "FastAPI", "AWS", "PostgreSQL"],
    )
    weak = _cand("2f962b30", ["Built internal wiki pages"], skills=["Confluence"])
    candidates = [strong, weak]

    # Force alignment + skip embeddings-heavy path by mocking rank pieces

    generic = "Great overall culture fit for the company values."
    good = (
        "Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards for production traffic. "
        "Strong Python platform work."
    )

    def fake_justify(job, cands, alignment, reqs, **kwargs):
        # Exercise real llm_justify with mocked LLM
        return llm_justify(job, cands, alignment, reqs, **kwargs)

    calls = {"n": 0}

    def fake_complete(prompt, schema, **kwargs):
        calls["n"] += 1
        results = []
        for c in candidates:
            if c.resume_id == "2f962b30":
                results.append(
                    ResumeRerankItem(
                        resume_id=c.resume_id,
                        fit_score=40,
                        matched_skills=[],
                        missing_skills=["Python"],
                        rationale=generic,
                        coverage=[],
                    )
                )
            else:
                results.append(
                    ResumeRerankItem(
                        resume_id=c.resume_id,
                        fit_score=90,
                        matched_skills=["Python", "FastAPI"],
                        missing_skills=[],
                        rationale=good,
                        coverage=[],
                    )
                )
        return ResumeRerankResponse(results=results)

    # Build alignment via real structure but call llm_justify directly as ranking would
    alignment = {
        "strong": [
            {
                "requirement": "Python",
                "status": "hit",
                "evidence_unit": UNIT,
                "evidence_score": 0.95,
                "kind": "must",
            }
        ],
        "2f962b30": [
            {
                "requirement": "Python",
                "status": "miss",
                "evidence_unit": "No clear evidence",
                "evidence_score": 0.05,
                "kind": "must",
            },
            {
                "requirement": "Comms",
                "status": "hit",
                "evidence_unit": "Built internal wiki pages",
                "evidence_score": 0.7,
                "kind": "nice",
            },
        ],
    }
    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]

    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
        with patch("app.services.resume.justify.load_prompt", return_value=_prompt_meta()):
            with patch("app.services.ops.observability.record_trace"):
                out = llm_justify(
                    job,
                    candidates,
                    alignment,
                    reqs,
                    rank_by_id={"strong": 1, "2f962b30": 2},
                )

    assert set(out.keys()) == {"strong", "2f962b30"}
    assert out["2f962b30"].justification_status == "fallback"
    assert "Must-haves without clear evidence" in out["2f962b30"].rationale
    assert out["strong"].justification_status != "fallback" or "FastAPI" in out["strong"].rationale
    # Must not raise ServiceFailingError — if we got here, request survived
    with pytest.raises(ServiceFailingError):
        # control: id mismatch still fails hard
        bad = ResumeRerankResponse(results=[ResumeRerankItem(resume_id="nope", fit_score=1, rationale="x" * 30)])
        with patch("app.services.resume.justify.llm.complete_json", return_value=bad):
            with patch("app.services.resume.justify.load_prompt", return_value=_prompt_meta()):
                llm_justify(job, candidates, alignment, reqs, rank_by_id={"strong": 1, "2f962b30": 2})
