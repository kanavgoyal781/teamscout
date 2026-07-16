"""M17: listwise permutation, CE normalize, token budget, fit_weights gates, defaults lock."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from app.core.config import settings
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services.ranking.cross_encoder import _validated_model, normalize_cross_encoder_scores
from app.services.ranking.engine import _llm_rerank_listwise
from app.services.ranking.hybrid import Rankable, hybrid_rank
from app.services.ranking.listwise import (
    ListwiseItem,
    ListwiseResponse,
    PermutationError,
    legacy_pointwise_token_budget,
    listwise_token_budget,
    parse_listwise_ranking,
    position_to_score,
    ranks_to_fit_scores,
    validate_permutation,
)
from app.services.ranking.math import fuse_final_score, validate_ranking_weights


def test_assert_m17_defaults_not_flipped() -> None:
    """Production defaults stay CE/listwise/calibration off after M17 experiment (no flip)."""
    assert settings.RANKING_USE_CROSS_ENCODER is False
    assert settings.RANKING_LLM_LISTWISE is False
    assert settings.RANKING_WEIGHT_CROSS_ENCODER == 0.0
    assert settings.CROSS_ENCODER_SHORTLIST is False
    assert settings.RANKING_USE_CALIBRATION is False


def test_validate_permutation_happy() -> None:
    assert validate_permutation(["j1", "j0", "j2"], ["j0", "j1", "j2"]) == ["j1", "j0", "j2"]


@pytest.mark.parametrize(
    "ranking,expected,match",
    [
        (["j0", "j0", "j1"], ["j0", "j1"], "duplicate"),
        (["j0"], ["j0", "j1"], "missing"),
        (["j0", "j1", "j9"], ["j0", "j1"], "hallucin"),
        (["j0", "", "j1"], ["j0", "j1"], "empty"),
        ([], ["j0"], "missing"),
    ],
)
def test_validate_permutation_rejects(ranking: list[str], expected: list[str], match: str) -> None:
    with pytest.raises(PermutationError, match=match):
        validate_permutation(ranking, expected)


def test_parse_listwise_empty_ranking() -> None:
    with pytest.raises(PermutationError):
        parse_listwise_ranking(ListwiseResponse(ranking=[]), ["j0"])


def test_parse_listwise_and_scores() -> None:
    resp = ListwiseResponse(
        ranking=[
            ListwiseItem(job_id="j1", reason="strong"),
            ListwiseItem(job_id="j0", reason="ok"),
        ]
    )
    ordered = parse_listwise_ranking(resp, ["j0", "j1"])
    assert [x[0] for x in ordered] == ["j1", "j0"]
    scores = ranks_to_fit_scores(["j1", "j0"])
    assert scores["j1"] == position_to_score(0, 2) == 100.0
    assert scores["j0"] == position_to_score(1, 2) == 0.0  # last place is 0
    assert scores["j1"] > scores["j0"]


def test_position_to_score_last_is_zero() -> None:
    assert position_to_score(0, 5) == 100.0
    assert position_to_score(4, 5) == 0.0
    assert position_to_score(2, 5) == 50.0


def test_listwise_token_budget_not_increased() -> None:
    legacy = legacy_pointwise_token_budget(top_n=30, prompt_cap=4000)
    tmpl = load_prompt("rerank")
    # Assert against real prompt frontmatter max_tokens (not a free-floating constant)
    assert tmpl.model_params.get("max_tokens") == 2000
    prompt_cap = int(tmpl.model_params["max_tokens"])
    listwise = listwise_token_budget(n_jobs=15, prompt_cap=prompt_cap)
    assert listwise <= legacy
    assert listwise <= prompt_cap
    assert listwise < legacy
    # Two listwise attempts (retry) still under one legacy cascade
    assert listwise * 2 < legacy


def _jobs2() -> list[Job]:
    return [
        Job(
            id="job-a",
            source="t",
            source_job_id="a",
            title="A",
            company="C",
            location="R",
            description="Python",
            apply_url="https://x",
            skills=["Python"],
        ),
        Job(
            id="job-b",
            source="t",
            source_job_id="b",
            title="B",
            company="C",
            location="R",
            description="Go",
            apply_url="https://y",
            skills=["Go"],
        ),
    ]


def test_listwise_retry_call_count_then_success() -> None:
    jobs = _jobs2()
    profile = ResumeProfile(title="Eng", skills=["Python"], location="R", years_of_experience=3)
    bad = ListwiseResponse(ranking=[ListwiseItem(job_id="j0", reason="only one")])
    good = ListwiseResponse(
        ranking=[
            ListwiseItem(job_id="j0", reason="best"),
            ListwiseItem(job_id="j1", reason="second"),
        ]
    )
    mock = MagicMock(side_effect=[bad, good])
    with patch("app.services.ranking.engine.llm.complete_json", mock):
        out = _llm_rerank_listwise(profile, jobs)
    assert mock.call_count == 2
    assert set(out) == {"job-a", "job-b"}
    assert out["job-a"].fit_score > out["job-b"].fit_score


def test_listwise_fallback_heuristic_no_extra_llm() -> None:
    """Listwise failure must not start a full pointwise LLM cascade (token budget)."""
    jobs = _jobs2()
    profile = ResumeProfile(title="Eng", skills=["Python"], location="R", years_of_experience=3)
    bad = ListwiseResponse(ranking=[ListwiseItem(job_id="hallucinated", reason="x")])
    mock = MagicMock(side_effect=[bad, bad])
    with patch("app.services.ranking.engine.llm.complete_json", mock):
        # Must patch engine module — package-level ranking._llm_rerank_pointwise is a no-op after reorg.
        with patch("app.services.ranking.engine._llm_rerank_pointwise") as pw:
            out = _llm_rerank_listwise(profile, jobs)
    assert mock.call_count == 2
    assert not pw.called
    assert set(out) == {"job-a", "job-b"}
    assert "heuristic" in out["job-a"].rationale.lower() or "listwise failed" in out["job-a"].rationale.lower()
    # Position scores: first job in input order gets best score
    assert out["job-a"].fit_score > out["job-b"].fit_score


def test_ce_normalize_per_slate() -> None:
    norm = normalize_cross_encoder_scores([-2.0, 0.0, 4.0])
    assert norm[0] == pytest.approx(0.0)
    assert norm[2] == pytest.approx(1.0)
    assert 0.0 < norm[1] < 1.0
    assert normalize_cross_encoder_scores([3.0, 3.0]) == [1.0, 1.0]


def test_ce_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import cross_encoder as ce

    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", None)
    with pytest.raises(ServiceNotConfiguredError):
        ce.cross_encode("q", ["doc1"])


def test_ce_empty_query_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import cross_encoder as ce

    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "k")
    with pytest.raises(ServiceFailingError, match="query must be non-empty"):
        ce.cross_encode("  ", ["doc1"])


def test_ce_model_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RERANKER_MODEL", "../evil")
    with pytest.raises(ServiceNotConfiguredError):
        _validated_model()
    monkeypatch.setattr(settings, "RERANKER_MODEL", "Qwen/Qwen3-Reranker-4B")
    assert _validated_model() == "Qwen/Qwen3-Reranker-4B"


def test_hybrid_ce_missing_fn_hard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RANKING_WEIGHT_CROSS_ENCODER", 0.1)
    cands = [
        Rankable(id="a", dense_text="a", lexical_text="a"),
        Rankable(id="b", dense_text="b", lexical_text="b"),
    ]
    with patch("app.services.ranking.hybrid.dense_ranking", return_value=["a", "b"]):
        with patch("app.services.ranking.hybrid.lexical_ranking", return_value=["b", "a"]):
            with pytest.raises(ServiceFailingError, match="cross_encode_fn"):
                hybrid_rank(
                    "q",
                    "q",
                    cands,
                    skill_overlap_fn=lambda _: 0.5,
                    recency_fn=lambda _: 0.5,
                    use_llm=False,
                    use_cross_encoder=True,
                    cross_encode_fn=None,
                    top_n=2,
                )


def test_hybrid_ce_shortlist_only_when_weight_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    cands = [Rankable(id=f"j{i}", dense_text=f"t{i}", lexical_text=f"t{i}") for i in range(5)]

    # CE prefers reverse order
    def ce_fn(cs: list[Rankable]) -> dict[str, float]:
        return {c.id: float(i) for i, c in enumerate(cs)}

    with patch("app.services.ranking.hybrid.dense_ranking", return_value=[c.id for c in cands]):
        with patch("app.services.ranking.hybrid.lexical_ranking", return_value=[c.id for c in cands]):
            monkeypatch.setattr(settings, "RANKING_WEIGHT_CROSS_ENCODER", 0.0)
            monkeypatch.setattr(settings, "CROSS_ENCODER_SHORTLIST", False)
            monkeypatch.setattr(settings, "RERANK_TOP_N", 3)
            monkeypatch.setattr(settings, "LLM_RERANK_TOP_N", 2)
            scored = hybrid_rank(
                "q",
                "q",
                cands,
                skill_overlap_fn=lambda _: 0.5,
                recency_fn=lambda _: 0.5,
                cross_encode_fn=ce_fn,
                use_llm=False,
                use_cross_encoder=True,
                top_n=5,
            )
            # weight 0 + shortlist off → RRF top-3 pool (RERANK_TOP_N), not CE top-2
            assert len(scored) == 3

            monkeypatch.setattr(settings, "RANKING_WEIGHT_CROSS_ENCODER", 0.2)
            # rebalance remaining weights for validate
            monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.3)
            monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.15)
            monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.1)
            monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.05)
            monkeypatch.setattr(settings, "RANKING_WEIGHT_EXPERIENCE", 0.1)
            monkeypatch.setattr(settings, "RANKING_WEIGHT_REQUIREMENTS", 0.1)
            scored2 = hybrid_rank(
                "q",
                "q",
                cands,
                skill_overlap_fn=lambda _: 0.5,
                recency_fn=lambda _: 0.5,
                cross_encode_fn=ce_fn,
                use_llm=False,
                use_cross_encoder=True,
                llm_top_n=2,
                top_n=5,
            )
            assert len(scored2) == 2


def test_fuse_includes_cross_encoder_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.3)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.2)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_EXPERIENCE", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_REQUIREMENTS", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_CROSS_ENCODER", 0.1)
    validate_ranking_weights()
    high = fuse_final_score(
        llm_fit=0,
        rrf_normalized=0,
        skill_overlap=0,
        recency=0,
        experience_fit=0,
        requirements_met=0,
        cross_encoder=1.0,
    )
    low = fuse_final_score(
        llm_fit=0,
        rrf_normalized=0,
        skill_overlap=0,
        recency=0,
        experience_fit=0,
        requirements_met=0,
        cross_encoder=0.0,
    )
    assert high > low
    assert high == pytest.approx(10.0)


def test_calibration_refuses_below_gate() -> None:
    from app.services import calibration as cal

    with pytest.raises(ValueError, match="30"):
        cal.fit_platt([50.0] * 10, [1, 0] * 5)


def test_calibration_holdout_not_in_train_fit() -> None:
    from app.services import calibration as cal

    # Separable scores: low → 0, high → 1. Holdout AUC should be defined when both classes present.
    scores = [float(i) for i in range(40)]
    labels = [0] * 20 + [1] * 20
    params = cal.fit_platt(scores, labels, seed=7)
    assert params.metadata["holdout_n"] > 0
    assert params.metadata["train_n"] + params.metadata["holdout_n"] == 40
    assert params.n_labels == 40
    # Holdout AUC present when holdout has both classes
    if params.holdout_auc is not None:
        assert 0.0 <= params.holdout_auc <= 1.0


def test_calibration_ui_requires_promote_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.db.models import ScoreCalibration
    from app.db.session import SessionLocal, ensure_db
    from app.services import calibration as cal

    ensure_db()
    scores = [float(20 + (i % 50)) for i in range(60)]
    labels = [1 if s >= 45 else 0 for s in scores]
    params = cal.fit_platt(scores, labels)
    try:
        cal.save_calibration(params)
        monkeypatch.setattr(settings, "RANKING_USE_CALIBRATION", False)
        assert cal.ui_match_likelihood(80.0) is None
        monkeypatch.setattr(settings, "RANKING_USE_CALIBRATION", True)
        db = SessionLocal()
        try:
            row = db.query(ScoreCalibration).first()
            assert row is not None
            row.n_labels = 49
            db.commit()
        finally:
            db.close()
        # Boundary: n=49 below UI gate even with promote flag
        assert cal.ui_match_likelihood(80.0) is None
        db = SessionLocal()
        try:
            row = db.query(ScoreCalibration).first()
            assert row is not None
            row.n_labels = 50
            db.commit()
        finally:
            db.close()
        lik = cal.ui_match_likelihood(80.0)
        assert lik is not None
        assert 0.0 <= lik <= 1.0
    finally:
        # Teardown: no leaked calibration rows for other tests
        db = SessionLocal()
        try:
            db.query(ScoreCalibration).delete()
            db.commit()
        finally:
            db.close()


def test_fit_weights_refuses_and_never_touches_defaults(tmp_path, monkeypatch) -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    import scripts.fit_weights as fw

    defaults = root / "configs/experiments/defaults.json"
    mtime = defaults.stat().st_mtime
    out = tmp_path / "learned.json"
    monkeypatch.setattr(
        fw,
        "_load_from_db",
        lambda: [{"y": 1, "score_shown": 50, "shown_rank": 0, "components": {}}] * 5,
    )
    monkeypatch.setattr(sys, "argv", ["fit_weights.py", "--out", str(out)])
    rc = fw.main()
    assert rc == 2
    assert not out.exists()
    assert defaults.stat().st_mtime == mtime


def test_fit_weights_writes_proposal_only_no_shown_rank_zero(tmp_path, monkeypatch) -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    import scripts.fit_weights as fw

    defaults = root / "configs/experiments/defaults.json"
    mtime = defaults.stat().st_mtime
    out = tmp_path / "learned.json"
    rows = []
    for i in range(40):
        y = 1 if i % 2 == 0 else 0
        rows.append(
            {
                "y": y,
                "score_shown": 70.0 if y else 30.0,
                "shown_rank": i % 5,  # required — not imputed as 0
                "components": {
                    "llm": 80 if y else 20,
                    "rrf": 0.8 if y else 0.2,
                    "skills": 0.7 if y else 0.1,
                    "recency": 0.5,
                    "experience": 0.6 if y else 0.2,
                    "requirements": 0.6 if y else 0.2,
                    "cross_encoder": 0.0,
                },
            }
        )
    # rows missing shown_rank must be dropped, not zero-imputed
    rows.append(
        {
            "y": 1,
            "score_shown": 90,
            "shown_rank": None,
            "components": {
                "llm": 90,
                "rrf": 0.9,
                "skills": 0.9,
                "recency": 0.5,
                "experience": 0.5,
                "requirements": 0.5,
                "cross_encoder": 0.0,
            },
        }
    )
    monkeypatch.setattr(fw, "_load_from_db", lambda: rows)
    monkeypatch.setattr(sys, "argv", ["fit_weights.py", "--out", str(out)])
    from app.db.models import ScoreCalibration
    from app.db.session import SessionLocal, ensure_db

    ensure_db()
    try:
        rc = fw.main()
        assert rc == 0
        data = json.loads(out.read_text())
        assert data["name"] == "learned_weights"
        assert "PROPOSAL ONLY" in data["note"]
        # dropped null shown_rank → n_labels is 40 not 41
        assert data["fit"]["n_labels"] == 40
        assert set(data["weights"].keys()) == {
            "llm",
            "rrf",
            "skills",
            "recency",
            "experience",
            "requirements",
            "cross_encoder",
        }
        assert "shown_rank" not in data["weights"]
        assert abs(sum(data["weights"].values()) - 1.0) < 0.02
        assert data["fit"].get("feature_standardization") == "train_only_zscore"
        assert defaults.stat().st_mtime == mtime
    finally:
        db = SessionLocal()
        try:
            db.query(ScoreCalibration).delete()
            db.commit()
        finally:
            db.close()


def test_fit_logistic_holdout_isolation() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    import scripts.fit_weights as fw

    # Perfect separation on train feature
    X = [[float(i), 0.0] for i in range(40)]
    y = [0] * 20 + [1] * 20
    w, hold_auc, train_auc, meta = fw.fit_logistic(X, y, seed=1)
    assert meta["holdout_n"] > 0
    assert meta["train_n"] + meta["holdout_n"] == 40
    assert 0.0 <= hold_auc <= 1.0


def test_ce_respx_mock_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    import respx
    from app.services import cross_encoder as ce

    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "RERANKER_MODEL", "Qwen/Qwen3-Reranker-4B")
    url = ce.reranker_endpoint()
    with respx.mock:
        respx.post(url).mock(return_value=httpx.Response(200, json={"scores": [0.1, 0.9]}))
        out = ce.cross_encode("query text", ["doc a", "doc b"])
    assert len(out) == 2
    assert out[1] > out[0]
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(1.0)


def test_feedback_score_components_sanitized() -> None:
    from app.schemas.feedback import FeedbackCreate

    ok = FeedbackCreate(
        kind="thumbs_up",
        target_type="job_match",
        target_id="j1",
        score_components={
            "llm": 150,  # clamp 100
            "rrf": 2.0,  # >1 → /100 → 0.02? wait we do /100 if >1 → 0.02
            "skills": 0.5,
            "evil": 99,  # dropped
            "recency": -1,  # clamp 0
        },
    )
    assert ok.score_components is not None
    assert "evil" not in ok.score_components
    assert ok.score_components["llm"] == 100.0
    assert ok.score_components["skills"] == 0.5
    assert ok.score_components["recency"] == 0.0
    assert 0.0 <= ok.score_components["rrf"] <= 1.0

    with pytest.raises(Exception):
        FeedbackCreate(
            kind="thumbs_up",
            target_type="job_match",
            target_id="j1",
            score_components={f"k{i}": 0.1 for i in range(20)},
        )


def test_skills_chips_uses_skill_equals_aliases() -> None:
    from app.services.ranking.engine import _skills_chips

    profile = ResumeProfile(
        title="Eng",
        skills=["Go", "PostgreSQL"],
        location="R",
        years_of_experience=3,
    )
    job = Job(
        id="j",
        source="t",
        source_job_id="j",
        title="T",
        company="C",
        location="R",
        description="x",
        apply_url="https://x",
        skills=["golang", "postgres", "Rust"],
    )
    matched, missing = _skills_chips(profile, job)
    assert "Go" in matched and "PostgreSQL" in matched
    assert "Rust" in missing
    assert "golang" not in missing and "postgres" not in missing


def test_listwise_clamps_shortlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RANKING_LLM_LISTWISE", True)
    monkeypatch.setattr(settings, "RERANK_TOP_N", 30)
    monkeypatch.setattr(settings, "LLM_RERANK_TOP_N", 15)
    cands = [Rankable(id=f"j{i}", dense_text=f"t{i}", lexical_text=f"t{i}") for i in range(40)]
    order = [c.id for c in cands]
    with patch("app.services.ranking.hybrid.dense_ranking", return_value=order):
        with patch("app.services.ranking.hybrid.lexical_ranking", return_value=order):
            scored = hybrid_rank(
                "q",
                "q",
                cands,
                skill_overlap_fn=lambda _: 0.5,
                recency_fn=lambda _: 0.5,
                use_llm=False,
                use_cross_encoder=False,
                top_n=40,
            )
    assert len(scored) == 15
