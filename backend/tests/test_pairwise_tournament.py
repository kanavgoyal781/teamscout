"""maybe_run_tournament integration tests (mocked LLM)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.errors import ServiceFailingError
from app.schemas.jobs import Job
from app.services.jd_decompose import JdRequirement
from app.services.pairwise_tournament import AlignmentEvidence, maybe_run_tournament
from app.services.ranking_math_align import TOURNAMENT_GAP


def _job() -> Job:
    return Job(
        id="j1",
        source="t",
        source_job_id="s1",
        title="ML Engineer",
        company="Co",
        location="Remote",
        description="Need PyTorch and MLflow.",
        apply_url="https://example.com/j",
        skills=["PyTorch"],
    )


def _ev(rid: str, cov: float, ch: str | None = None) -> AlignmentEvidence:
    return AlignmentEvidence(
        resume_id=rid,
        content_hash=ch or rid,
        coverage=cov,
        top_units=[f"evidence for {rid}"],
    )


def test_tournament_skipped_when_use_llm_false() -> None:
    ordered = [_ev("a", 0.9), _ev("b", 0.88), _ev("c", 0.5)]
    result = maybe_run_tournament(_job(), [], ordered, use_llm=False)
    assert result.ran is False
    assert result.ordered_ids == ["a", "b", "c"]


def test_tournament_skipped_when_gap_large() -> None:
    ordered = [_ev("a", 0.9), _ev("b", 0.8), _ev("c", 0.5)]  # gap 0.1 >= 0.05
    result = maybe_run_tournament(_job(), [], ordered, use_llm=True)
    assert result.ran is False
    assert result.ordered_ids == ["a", "b", "c"]


def test_tournament_close_band_reorders_only_band() -> None:
    reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
    ordered = [
        _ev("a", 0.90, "ha"),
        _ev("b", 0.88, "hb"),
        _ev("c", 0.87, "hc"),
        _ev("d", 0.50, "hd"),  # far — must stay last
    ]

    def fake_complete_json(prompt, schema, **kwargs):
        # Always prefer resume with higher lexical order of left evidence? Return B wins
        # Prompt contains Resume A then B evidence units; force winner B for each pair.
        return schema(winner="B", reason="decisive unit")

    with patch("app.services.pairwise_tournament.llm.complete_json", side_effect=fake_complete_json):
        with patch("app.services.pairwise_tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge which resume is better.",
                system="json",
                version="1",
                content_hash="ph",
                name="pairwise_judge",
                model_params={},
            )
            result = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=None)

    assert result.ran is True
    assert result.comparisons == 3  # band a,b,c
    assert result.ordered_ids[-1] == "d"
    assert set(result.contested_ids) == {"a", "b", "c"}
    assert "d" not in result.contested_ids


def test_tournament_invalid_winner_raises() -> None:
    reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
    ordered = [_ev("a", 0.90, "ha"), _ev("b", 0.88, "hb")]

    def bad_json(prompt, schema, **kwargs):
        return schema(winner="maybe", reason="nope")

    with patch("app.services.pairwise_tournament.llm.complete_json", side_effect=bad_json):
        with patch("app.services.pairwise_tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge",
                system="json",
                version="1",
                content_hash="ph",
                name="pairwise_judge",
                model_params={},
            )
            with pytest.raises(ServiceFailingError):
                maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=None)


def test_tournament_gap_boundary_exact() -> None:
    # leader - second == TOURNAMENT_GAP → skip
    ordered = [_ev("a", 0.90), _ev("b", 0.90 - TOURNAMENT_GAP), _ev("c", 0.5)]
    result = maybe_run_tournament(_job(), [], ordered, use_llm=True)
    assert result.ran is False


def test_tournament_cache_hits_skip_second_llm() -> None:
    """Order-normalized cache: second tournament reuses judgments."""
    from app.db.session import SessionLocal, ensure_db

    ensure_db()
    db = SessionLocal()
    try:
        reqs = [JdRequirement(text="PyTorch", kind="must", category="skill", weight=2.0)]
        ordered = [_ev("a", 0.90, "hash-a"), _ev("b", 0.88, "hash-b")]
        calls = {"n": 0}

        def fake_complete_json(prompt, schema, **kwargs):
            calls["n"] += 1
            return schema(winner="A", reason="cached-path")

        with patch("app.services.pairwise_tournament.llm.complete_json", side_effect=fake_complete_json):
            with patch("app.services.pairwise_tournament.load_prompt") as lp:
                lp.return_value = MagicMock(
                    body="Judge",
                    system="json",
                    version="1",
                    content_hash="ph",
                    name="pairwise_judge",
                    model_params={},
                )
                r1 = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=db)
                n_first = calls["n"]
                r2 = maybe_run_tournament(_job(), reqs, ordered, use_llm=True, db=db)
        assert r1.ran and r2.ran
        assert r1.comparisons == 1
        assert r2.cache_hits == r2.comparisons
        assert calls["n"] == n_first  # no additional LLM on second run
        assert r2.ordered_ids[0] == r1.ordered_ids[0]
    finally:
        db.close()
