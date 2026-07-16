"""M21: junk unit filter, segmenter version stamp, SQL exact short-circuit via rank path."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services.resume.ranking import rank_resumes_for_job
from app.services.resume.units import (
    SEGMENTER_VERSION,
    extract_units,
    is_junk_fragment,
    segment_text_units,
    units_stamp,
)


def test_junk_fragment_leading_lowercase_orphan() -> None:
    assert is_junk_fragment("in Applied Data Science.", section="experience") is True
    assert is_junk_fragment("Built production pipelines with SQL.", section="experience") is False
    assert is_junk_fragment("SQL", section="skills") is False


def test_segmenter_merges_orphan_into_preceding() -> None:
    parts = segment_text_units(
        "Built dashboards for leadership. in Applied Data Science. "
        "Shipped production pipelines with SQL and Python across regions.",
        section="experience",
    )
    joined = " ".join(parts)
    assert "in Applied Data Science" in joined
    # Orphan must not stand alone as its own unit
    assert not any(p.strip().lower().startswith("in applied") for p in parts)
    assert any("Shipped production pipelines" in p for p in parts)


def test_extract_units_no_standalone_junk_fragments() -> None:
    profile = ResumeProfile(
        name="Pat",
        title="Data Scientist",
        years_of_experience=4,
        location="Remote",
        skills=["SQL", "Python"],
        summary="Experienced analyst delivering reliable insights for product teams.",
        work_experience=[
            WorkExperience(
                title="Data Scientist",
                company="Acme",
                bullets=[
                    "Built dashboards. in Applied Data Science. "
                    "Owned weekly KPI reviews with stakeholders across regions.",
                ],
            )
        ],
    )
    units = extract_units(profile)
    texts = [u.unit_text for u in units]
    assert "SQL" in texts
    assert not any(t.strip().lower().startswith("in applied") and len(t.split()) < 6 for t in texts)
    # No ultra-short experience fragments with leading lowercase
    for u in units:
        if u.section == "experience":
            assert not is_junk_fragment(u.unit_text, section=u.section)


def test_units_stamp_includes_segmenter_version() -> None:
    profile = ResumeProfile(
        name="A",
        title="T",
        years_of_experience=1,
        location="",
        skills=["Go"],
        summary="",
        work_experience=[],
    )
    units = extract_units(profile)
    stamp = units_stamp(units)
    # Changing version changes stamp even if unit hashes identical
    import app.services.resume.units as units_mod

    original = units_mod.SEGMENTER_VERSION
    try:
        units_mod.SEGMENTER_VERSION = original + "-test"
        assert units_stamp(units) != stamp
    finally:
        units_mod.SEGMENTER_VERSION = original
    assert SEGMENTER_VERSION  # version is non-empty


def _norm_bag(text: str, dim: int = 32) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().replace("/", " ").split():
        h = hash(token) % dim
        vec[h] += 1.0
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def test_sql_exact_match_ranks_at_full_skill_score() -> None:
    """Resume with skills=['SQL'] scores 1.0 on requirement 'Strong SQL skills'."""
    job = Job(
        id="sql-job",
        source="fixture",
        source_job_id="sql-1",
        title="Data Analyst",
        company="Acme",
        location="Remote",
        description="Need Strong SQL skills and Python for analytics.",
        apply_url="https://example.com/sql",
        posted_at=datetime.now(UTC),
        skills=["SQL", "Python"],
    )
    candidate = ResumeCandidate(
        resume_id="sql-resume",
        filename="sql.pdf",
        content_hash="hash-sql",
        profile=ResumeProfile(
            name="Alex",
            title="Data Analyst",
            years_of_experience=5,
            location="Remote",
            skills=["SQL", "Python", "Tableau"],
            work_experience=[
                WorkExperience(
                    title="Analyst",
                    company="PastCo",
                    bullets=["Wrote complex SQL queries for revenue dashboards."],
                )
            ],
            summary="Analyst with Strong SQL skills and Python reporting.",
        ),
    )
    with patch(
        "app.services.inference.embeddings.embed_batch", side_effect=lambda texts: [_norm_bag(t) for t in texts]
    ):
        with patch("app.services.inference.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume.ranking.decompose_jd") as dec:
                from app.services.resume.jd_decompose import JdRequirement

                dec.return_value = [
                    JdRequirement(text="Strong SQL skills", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
                ]
                ranked = rank_resumes_for_job(job, [candidate], use_llm=False)

    assert ranked
    sql_row = next(r for r in ranked[0].alignment if "SQL" in r.requirement)
    assert sql_row.evidence_score == pytest.approx(1.0)
    assert sql_row.status == "hit"
    assert sql_row.strength == "strong"
    # Headline uses weighted final blend; with full skill coverage should be healthy
    assert ranked[0].match_score >= 60.0
    assert ranked[0].must_haves_hit == ranked[0].must_haves_total
    # match_score equals final_score (one coherent scale)
    assert ranked[0].match_score == pytest.approx(ranked[0].score_breakdown.final_score)


def test_exact_skills_high_llm_headline_match_fixture() -> None:
    """Live-failure shape: exact must skills + high LLM fit → headline match ≥ 60."""
    from app.services.resume.justify import ResumeRerankItem

    job = Job(
        id="live-shape",
        source="fixture",
        source_job_id="live-1",
        title="Data Scientist",
        company="Target",
        location="Remote",
        description="Strong SQL skills. Python. Machine learning experience required.",
        apply_url="https://example.com/live",
        posted_at=datetime.now(UTC),
        skills=["SQL", "Python", "Machine Learning"],
    )
    candidate = ResumeCandidate(
        resume_id="live-resume",
        filename="live.pdf",
        content_hash="hash-live",
        profile=ResumeProfile(
            name="Sam",
            title="Data Scientist",
            years_of_experience=6,
            location="Remote",
            skills=["SQL", "Python", "Machine Learning", "PyTorch"],
            work_experience=[
                WorkExperience(
                    title="Data Scientist",
                    company="Past",
                    bullets=[
                        "Built ML models in Python with production SQL feature stores.",
                        "Deployed ranking systems monitored with online metrics.",
                    ],
                )
            ],
            summary="Data scientist with SQL, Python, and machine learning.",
        ),
    )

    def fake_justify(*_a, **_k):
        return {
            "live-resume": ResumeRerankItem(
                resume_id="live-resume",
                fit_score=92,
                matched_skills=["SQL", "Python", "Machine Learning"],
                missing_skills=[],
                rationale="Strong SQL and Python ML delivery evidenced in production bullets.",
                coverage=[],
            )
        }

    with patch(
        "app.services.inference.embeddings.embed_batch", side_effect=lambda texts: [_norm_bag(t) for t in texts]
    ):
        with patch("app.services.inference.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume.ranking.decompose_jd") as dec:
                from app.services.resume.jd_decompose import JdRequirement

                dec.return_value = [
                    JdRequirement(text="Strong SQL skills", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="Machine Learning", kind="must", category="skill", weight=2.0),
                ]
                with patch("app.services.resume.ranking.llm_justify", side_effect=fake_justify):
                    ranked = rank_resumes_for_job(job, [candidate], use_llm=True)

    assert ranked
    rec = ranked[0]
    assert rec.score_breakdown.llm_fit == pytest.approx(92.0)
    for row in rec.alignment:
        if row.kind == "must" and row.category == "skill":
            assert row.status == "hit", row
            assert row.evidence_score >= 0.9
    assert rec.match_score >= 60.0
    assert rec.match_score == pytest.approx(rec.score_breakdown.final_score)
    assert rec.must_haves_hit == rec.must_haves_total >= 1


def test_segmenter_version_mismatch_forces_lazy_reindex(client, monkeypatch) -> None:
    """Stale junk units with old stamp must regenerate when SEGMENTER_VERSION changes."""
    import json

    from app.db.models import Resume, ResumeUnit
    from app.db.session import SessionLocal
    from app.services.resume.units import extract_units, index_resume_units, units_stamp

    profile = ResumeProfile(
        name="Pat",
        title="Data Scientist",
        years_of_experience=4,
        location="Remote",
        skills=["SQL", "Python"],
        summary="Experienced analyst delivering reliable insights for product teams.",
        work_experience=[
            WorkExperience(
                title="Data Scientist",
                company="Acme",
                bullets=[
                    "Built dashboards. in Applied Data Science. "
                    "Owned weekly KPI reviews with stakeholders across regions.",
                ],
            )
        ],
    )
    # Seed resume via API path with fixed hash
    from unittest.mock import patch

    with (
        patch("app.services.library.store.parser.content_hash", return_value="m21-junk-hash"),
        patch("app.services.library.store.parser.extract_text", return_value="text"),
        patch("app.services.library.store.parser.parse_resume_text", return_value=profile),
        patch("app.services.library.store.is_set", return_value=False),  # skip embed on ingest
    ):
        r = client.post(
            "/library/upload",
            files={"files": ("junk.pdf", b"%PDF m21-junk-body", "application/pdf")},
        )
    assert r.status_code == 200, r.text
    resume_id = r.json()["resumes"][0]["id"]

    db = SessionLocal()
    try:
        row = db.query(Resume).filter(Resume.id == resume_id).one()
        # Plant stale junk unit as if indexed under segmenter v1
        junk_text = "in Applied Data Science."
        db.query(ResumeUnit).filter(ResumeUnit.resume_id == resume_id).delete()
        db.add(
            ResumeUnit(
                workspace_id=row.workspace_id,
                resume_id=resume_id,
                unit_text=junk_text,
                section="experience",
                unit_hash="deadbeef" * 8,
                embedding_json=json.dumps([0.1] * 4),
            )
        )
        row.units_content_hash = "stale-v1-stamp"
        db.add(row)
        db.commit()

        monkeypatch.setattr(
            "app.services.inference.embeddings.embed_batch",
            lambda texts: [[0.1] * 4 for _ in texts],
        )

        fresh = index_resume_units(db, resume_id, profile, force=False)
        texts = [u.unit_text for u in fresh]
        assert junk_text not in texts
        assert not any(t.strip().lower().startswith("in applied") and len(t.split()) < 6 for t in texts)
        db.refresh(row)
        assert row.units_content_hash == units_stamp(extract_units(profile))
        assert all(not is_junk_fragment(u.unit_text, section=u.section) for u in fresh)
        # Stale junk unit row gone from DB
        remaining = db.query(ResumeUnit).filter(ResumeUnit.resume_id == resume_id).all()
        assert not any(u.unit_text == junk_text for u in remaining)
    finally:
        db.close()
