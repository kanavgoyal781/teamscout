"""M21: headline / table / tournament display scale coherence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services.ranking.math_align import evidence_strength
from app.services.resume.jd_decompose import JdRequirement
from app.services.resume.ranking import rank_resumes_for_job
from app.services.resume.tournament import _format_must_rows


def test_tournament_must_rows_use_strength_not_raw_score() -> None:
    rows = [
        {
            "kind": "must",
            "requirement": "Strong SQL skills",
            "evidence_unit": "SQL",
            "evidence_score": 1.0,
            "strength": "strong",
            "status": "hit",
        },
        {
            "kind": "must",
            "requirement": "Domain experience",
            "evidence_unit": "No clear evidence",
            "evidence_score": 0.0,
            "strength": "none",
            "status": "miss",
        },
        {
            "kind": "must",
            "requirement": "Soft skill",
            "evidence_unit": "related work",
            "evidence_score": 0.11,
            "strength": "weak",
            "status": "hit",
        },
    ]
    lines = _format_must_rows(rows)
    joined = "\n".join(lines)
    assert "strength: strong" in joined
    assert "strength: none" in joined
    assert "strength: weak" in joined
    assert "score: 0." not in joined
    assert "score: 1." not in joined
    assert "score: 0.11" not in joined
    assert "score: 0.20" not in joined


def test_evidence_strength_buckets_match_ui_thresholds() -> None:
    assert evidence_strength(0.0) == "none"
    assert evidence_strength(0.2) == "weak"
    assert evidence_strength(0.5) == "solid"
    assert evidence_strength(0.9) == "strong"
    assert evidence_strength(1.0) == "strong"


def _norm_bag(text: str, dim: int = 32) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().replace("/", " ").split():
        h = hash(token) % dim
        vec[h] += 1.0
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    return [_norm_bag(t) for t in texts]


def _cand(rid: str, skills: list[str], bullet: str) -> ResumeCandidate:
    return ResumeCandidate(
        resume_id=rid,
        filename=f"{rid}.pdf",
        content_hash=f"hash-{rid}",
        profile=ResumeProfile(
            name=rid,
            title="Engineer",
            years_of_experience=5,
            location="Remote",
            skills=skills,
            work_experience=[WorkExperience(title="Eng", company="Co", bullets=[bullet])],
            summary=bullet,
        ),
    )


def _force_tournament_override_rank():
    """Equal MaxSim coverage (close band) + pairwise flip + lower skill jaccard on winner.

    Coverage order: cov-leader first (equal cov, id sort). Tournament flips to tour-winner.
    tour-winner has fewer listed skills → lower final_score while ranked #1 — the old
    match_score fudge would lift the headline and diverge from final_score.
    """
    bullet = "Python and antibody engineering campaigns with phage display"
    job = Job(
        id="coh-job",
        source="fixture",
        source_job_id="coh",
        title="ML Engineer",
        company="Co",
        location="Remote",
        description="Need antibody engineering and Python.",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python", "antibody engineering"],
    )
    # Equal unit evidence → equal coverage; skill list differs for final_score gap
    cov_leader = _cand("cov-leader", ["Python", "antibody engineering"], bullet)
    tour_winner = _cand("tour-winner", ["Python"], bullet)
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="antibody engineering", kind="must", category="skill", weight=2.0),
    ]

    def fake_complete(prompt, schema, **kwargs):
        fields = getattr(schema, "model_fields", {}) or {}
        if "results" in fields:
            return schema(
                results=[
                    {
                        "resume_id": "tour-winner",
                        "fit_score": 88,
                        "matched_skills": ["Python"],
                        "missing_skills": [],
                        "rationale": f"{bullet}.",
                        "coverage": [],
                    },
                    {
                        "resume_id": "cov-leader",
                        "fit_score": 88,
                        "matched_skills": ["Python"],
                        "missing_skills": [],
                        "rationale": f"{bullet}.",
                        "coverage": [],
                    },
                ]
            )
        if "tour-winner" in prompt and "Resume A (tour-winner" in prompt:
            return schema(
                winner="A",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="tour-winner preferred on antibody depth",
            )
        if "tour-winner" in prompt:
            return schema(
                winner="B",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="tour-winner preferred on antibody depth",
            )
        return schema(
            winner="A",
            margin="slight",
            key_differences=["tie"],
            reason="slight edge on shared skills",
        )

    prompt_meta = MagicMock(
        body="Judge",
        system="json",
        version="2",
        content_hash="ph",
        name="pairwise_judge",
        model_params={},
    )
    with patch("app.services.inference.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.inference.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume.ranking.decompose_jd", return_value=reqs):
                with patch("app.services.resume.tournament.llm.complete_json", side_effect=fake_complete):
                    with patch("app.services.resume.justify.llm.complete_json", side_effect=fake_complete):
                        with patch("app.services.resume.tournament.load_prompt", return_value=prompt_meta):
                            with patch("app.services.resume.justify.load_prompt", return_value=prompt_meta):
                                return rank_resumes_for_job(
                                    job, [cov_leader, tour_winner], use_llm=True
                                )


def test_rank_with_tournament_override_headline_equals_final_blend() -> None:
    """HARD: overrode_coverage must be True; every card match_score == final_score.

    Reintroducing the post-tournament match_score lift/cap would break equality
    when the tournament winner has a lower weighted blend than the coverage leader.
    """
    ranked = _force_tournament_override_rank()
    assert len(ranked) >= 2

    # Hard requirements — soft if overrode: is not allowed
    assert ranked[0].tournament is not None
    assert ranked[0].tournament.ran is True
    assert ranked[0].tournament.overrode_coverage is True, (
        "fixture failed to flip coverage order via tournament — test is inert"
    )
    assert ranked[0].resume_id == "tour-winner"
    assert ranked[1].resume_id == "cov-leader"

    # Inverted blends (winner lower) — the old fudge would mutate #1's match_score
    assert ranked[0].score_breakdown.final_score + 1e-9 < ranked[1].score_breakdown.final_score

    for rec in ranked:
        assert rec.match_score == pytest.approx(rec.score_breakdown.final_score), (
            f"{rec.resume_id}: match={rec.match_score} final={rec.score_breakdown.final_score}"
        )
        for row in rec.alignment:
            assert row.strength in {"none", "weak", "solid", "strong"}
            if row.status == "miss":
                assert row.strength == "none"
            if row.status == "hit":
                assert row.strength != "none"
        if rec.tournament and rec.tournament.reasons:
            for reason in rec.tournament.reasons:
                assert "score 0." not in reason.lower()
                assert "score: 0." not in reason.lower()
        must = [r for r in rec.alignment if r.kind == "must"]
        if must:
            assert rec.must_haves_total == len(must)
            assert rec.must_haves_hit == sum(1 for r in must if r.status == "hit")
