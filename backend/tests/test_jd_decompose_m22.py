"""M22: multi-job primary-only decompose + skill atom path for Streamlit."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.services.ranking.math_align import align_resume, skill_match_level, skill_requirement_score
from app.services.resume.jd_decompose import (
    JdRequirement,
    _normalize_requirements,
    decompose_jd,
    extract_primary_posting,
)

PRIMARY = """
Senior Data Platform Engineer — Acme Corp
San Francisco, CA / Remote

About the role
We are looking for a senior engineer to own our analytics platform end to end.
You will design pipelines, partner with product, and ship reliable data products.

Requirements
- 5+ years of software engineering experience
- Strong Python skills
- Data visualization skills (Plotly, Dash, Streamlit, or similar)
- Experience with PostgreSQL and cloud data warehouses
- Excellent written communication

Responsibilities
- Build and operate batch and streaming data pipelines
- Partner with analysts on self-serve tooling
""".strip()

STUBS = """

Recommended for you
Junior Ziglang Developer — ZigLabs — Remote
Ziglang, embedded systems, 1 year experience. Apply now.

People also viewed
COBOL Mainframe Analyst — LegacyBank — Onsite NYC
COBOL, JCL, CICS. 10 openings.

Similar jobs
Fortran Numerical Analyst — SciCo — Hybrid
Fortran 90, numerical recipes, HPC.
""".strip()


def test_jd_decompose_prompt_has_multi_job_and_skill_rules() -> None:
    tmpl = load_prompt("jd_decompose")
    assert tmpl.version == "2"
    body = tmpl.body.lower()
    assert "primary" in body or "most detailed" in body
    assert "skill" in body
    assert "streamlit" in body or "plotly" in body or "split" in body


def test_extract_primary_posting_drops_short_stub_cards() -> None:
    full = PRIMARY + "\n\n" + STUBS
    primary = extract_primary_posting(full)
    assert "Acme Corp" in primary
    assert "Plotly" in primary
    assert "Ziglang" not in primary
    assert "COBOL" not in primary
    assert "Fortran" not in primary


def test_deterministic_decompose_zero_stub_skill_leak() -> None:
    job = Job(
        id="multi",
        source="fixture",
        source_job_id="multi",
        title="Senior Data Platform Engineer",
        company="Acme Corp",
        location="Remote",
        description=PRIMARY + "\n\n" + STUBS,
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python", "PostgreSQL"],
    )
    reqs = decompose_jd(job, use_llm=False)
    joined = " ".join(r.text for r in reqs).lower()
    assert "ziglang" not in joined
    assert "cobol" not in joined
    assert "fortran" not in joined
    # Primary tools may appear via term extract or skills
    assert any("python" in r.text.lower() for r in reqs) or "python" in joined


def test_normalize_splits_compound_tools_as_skill_atoms() -> None:
    items = [
        JdRequirement(
            text="Data visualization skills (Plotly, Dash, Streamlit, or similar)",
            kind="must",
            category="domain",  # wrong category from model — force skill via tools
            weight=2.0,
        )
    ]
    out = _normalize_requirements(items)
    texts = {r.text.lower() for r in out}
    assert any("streamlit" in t for t in texts)
    assert all(r.category == "skill" for r in out if "streamlit" in r.text.lower() or "plotly" in r.text.lower())


def _norm(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def test_streamlit_requirement_scores_via_skill_path() -> None:
    """Visualization phrasing with Streamlit atom hits resume skill 'Streamlit' at 1.0."""
    req_text = "Data visualization skills (Plotly, Dash, Streamlit, or similar)"
    assert skill_match_level(req_text, "Streamlit") == "exact"
    score = skill_requirement_score(
        req_text,
        skills=["Streamlit", "Python"],
        unit_texts=["Streamlit"],
        semantic_score=0.1,
    )
    assert score == pytest.approx(1.0)

    # After normalize split, atom Streamlit also scores
    atoms = _normalize_requirements([JdRequirement(text=req_text, kind="must", category="skill", weight=2.0)])
    streamlit_req = next(r for r in atoms if "streamlit" in r.text.lower())
    req = _norm([1.0, 0.0, 0.0])
    unit = _norm([0.0, 1.0, 0.0])
    cov, rows = align_resume(
        [req],
        [streamlit_req.text],
        [2.0],
        [unit],
        ["Streamlit"],
        ["Streamlit", "Python"],
        unit_sections=["skills"],
        categories=["skill"],
        evidence_floor=0.55,
    )
    assert rows[0]["status"] == "hit"
    assert rows[0]["evidence_score"] == pytest.approx(1.0)
    assert cov == pytest.approx(1.0)
