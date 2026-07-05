import pytest
from datetime import datetime, timedelta, timezone

from app.errors import ValidationError
from app.services.ranking_math import (
    fuse_final_score,
    normalize_scores,
    recency_score,
    reciprocal_rank_fusion,
    skill_jaccard,
    tokenize,
    validate_ranking_weights,
)


def test_tokenize_lowercases_and_splits() -> None:
    tokens = tokenize("Python, FastAPI and PostgreSQL 12")
    assert "python" in tokens
    assert "fastapi" in tokens
    assert "postgresql" in tokens


def test_reciprocal_rank_fusion_combines_lists() -> None:
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]], k=60)
    assert scores["a"] > scores["c"]
    assert scores["b"] > scores["d"]
    assert scores["a"] == pytest.approx(1 / 61 + 1 / 62, rel=1e-6)
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61, rel=1e-6)
    assert scores["c"] == pytest.approx(1 / 63, rel=1e-6)
    assert scores["d"] == pytest.approx(1 / 63, rel=1e-6)


def test_normalize_scores_spreads_range() -> None:
    normalized = normalize_scores({"a": 1.0, "b": 3.0, "c": 2.0})
    assert normalized["a"] == 0.0
    assert normalized["b"] == 1.0
    assert normalized["c"] == 0.5


def test_normalize_scores_handles_flat_values() -> None:
    normalized = normalize_scores({"a": 2.0, "b": 2.0})
    assert normalized == {"a": 1.0, "b": 1.0}


def test_skill_jaccard_overlap() -> None:
    score = skill_jaccard(["Python", "SQL"], ["python", "Redis", "SQL"])
    assert score == 2 / 3


def test_recency_score_decays_with_age() -> None:
    recent = recency_score(datetime.now(timezone.utc) - timedelta(days=1), half_life_days=7)
    older = recency_score(datetime.now(timezone.utc) - timedelta(days=14), half_life_days=7)
    assert recent > older
    assert 0 < older < 1


def test_validate_ranking_weights_accepts_defaults() -> None:
    validate_ranking_weights()


def test_validate_ranking_weights_rejects_misconfiguration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.9)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.3)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.1)

    with pytest.raises(ValidationError) as exc:
        validate_ranking_weights()

    assert exc.value.status_code == 400
    assert exc.value.error_code == "validation_error"


def test_fuse_final_score_weights_components() -> None:
    final = fuse_final_score(
        llm_fit=80,
        rrf_normalized=0.9,
        skill_overlap=0.5,
        recency=0.8,
    )
    assert final == pytest.approx(80.0)


def test_fuse_final_score_surfaces_validation_error_for_bad_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.5)

    with pytest.raises(ValidationError) as exc:
        fuse_final_score(llm_fit=80, rrf_normalized=0.9, skill_overlap=0.5, recency=0.8)

    assert exc.value.error_code == "validation_error"