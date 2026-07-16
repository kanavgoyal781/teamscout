from datetime import UTC, datetime, timedelta

import pytest
from app.errors import ValidationError
from app.services.ranking.math import (
    experience_fit_score,
    extract_requirement_terms,
    fuse_final_score,
    infer_seniority,
    normalize_scores,
    parse_required_years,
    recency_score,
    reciprocal_rank_fusion,
    requirements_met_score,
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
    recent = recency_score(datetime.now(UTC) - timedelta(days=1), half_life_days=7)
    older = recency_score(datetime.now(UTC) - timedelta(days=14), half_life_days=7)
    assert recent > older
    assert 0 < older < 1


def test_parse_required_years_range_and_plus() -> None:
    assert parse_required_years("Requires 5+ years of experience") == 5.0
    assert parse_required_years("2-4 years of experience with Python") == 2.0
    assert parse_required_years("minimum of 3 years") == 3.0
    assert parse_required_years("no years mentioned") is None


def test_infer_seniority_from_title() -> None:
    assert infer_seniority("Staff Software Engineer") == "staff"
    assert infer_seniority("Junior Backend Engineer") == "junior"
    assert infer_seniority("Principal Scientist") == "principal"
    assert infer_seniority("Software Engineer", "mid-level backend role") == "mid"


def test_experience_fit_penalizes_underqualified_for_staff() -> None:
    good = experience_fit_score(
        3.0,
        title="Software Engineer",
        description="Requirements: 2-4 years of experience with Python.",
    )
    bad = experience_fit_score(
        3.0,
        title="Staff Software Engineer",
        description="Minimum 10+ years of experience. Lead multi-team architecture.",
    )
    assert good > 0.75
    assert bad < 0.4
    assert good > bad


def test_experience_fit_penalizes_overqualified_for_junior() -> None:
    mid = experience_fit_score(8.0, title="Junior Software Engineer", description="Entry-level 0-2 years.")
    match = experience_fit_score(1.0, title="Junior Software Engineer", description="Entry-level 0-2 years.")
    assert match > mid


def test_requirements_met_prefers_covered_skills() -> None:
    profile_skills = ["Python", "Django", "PostgreSQL", "Docker"]
    profile_text = "Built Django REST APIs on PostgreSQL with Docker"
    high = requirements_met_score(
        profile_skills=profile_skills,
        profile_text=profile_text,
        job_skills=["Python", "Django", "PostgreSQL"],
        job_description="Requirements: Python, Django, PostgreSQL. 3 years experience.",
    )
    low = requirements_met_score(
        profile_skills=profile_skills,
        profile_text=profile_text,
        job_skills=["PyTorch", "CUDA", "Kubernetes"],
        job_description="Must have: PyTorch, CUDA, Kubernetes operators.",
    )
    assert high > low
    assert high >= 0.6
    assert low <= 0.35


def test_requirements_met_rejects_substring_false_positives() -> None:
    """JavaScript must not satisfy a Java requirement; Go ≠ Good."""
    js_only = requirements_met_score(
        profile_skills=["JavaScript", "TypeScript"],
        profile_text="Built JavaScript widgets and TypeScript apps",
        job_skills=["Java"],
        job_description="Requirements: Java",
    )
    java_real = requirements_met_score(
        profile_skills=["Java"],
        profile_text="Built Java services on the JVM",
        job_skills=["Java"],
        job_description="Requirements: Java",
    )
    assert java_real > js_only
    assert js_only == 0.0
    assert java_real == 1.0

    go_fp = requirements_met_score(
        profile_skills=["Python"],
        profile_text="Good communication and ownership",
        job_skills=["Go"],
        job_description="Must have: Go",
    )
    go_hit = requirements_met_score(
        profile_skills=["Go"],
        profile_text="Wrote Go microservices",
        job_skills=["Go"],
        job_description="Must have: Go",
    )
    assert go_fp == 0.0
    assert go_hit == 1.0


def test_extract_requirement_terms_includes_skills() -> None:
    terms = extract_requirement_terms(
        ["Python", "Django"],
        "Requirements:\n- PostgreSQL\n- Docker experience\n",
    )
    assert "python" in terms
    assert "django" in terms


def test_validate_ranking_weights_accepts_defaults() -> None:
    validate_ranking_weights()


def test_validate_ranking_weights_rejects_misconfiguration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.9)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.3)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_EXPERIENCE", 0.1)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_REQUIREMENTS", 0.1)

    with pytest.raises(ValidationError) as exc:
        validate_ranking_weights()

    assert exc.value.status_code == 400
    assert exc.value.error_code == "validation_error"


def test_fuse_final_score_weights_components() -> None:
    # With all components at 1.0 / 100 llm → final should be 100
    final = fuse_final_score(
        llm_fit=100,
        rrf_normalized=1.0,
        skill_overlap=1.0,
        recency=1.0,
        experience_fit=1.0,
        requirements_met=1.0,
    )
    assert final == pytest.approx(100.0)


def test_fuse_final_score_experience_moves_score() -> None:
    high = fuse_final_score(
        llm_fit=0,
        rrf_normalized=0.0,
        skill_overlap=0.0,
        recency=0.0,
        experience_fit=1.0,
        requirements_met=0.0,
    )
    low = fuse_final_score(
        llm_fit=0,
        rrf_normalized=0.0,
        skill_overlap=0.0,
        recency=0.0,
        experience_fit=0.0,
        requirements_met=0.0,
    )
    assert high > low


def test_fuse_final_score_surfaces_validation_error_for_bad_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "RANKING_WEIGHT_LLM", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RRF", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_SKILLS", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_RECENCY", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_EXPERIENCE", 0.5)
    monkeypatch.setattr(settings, "RANKING_WEIGHT_REQUIREMENTS", 0.5)

    with pytest.raises(ValidationError) as exc:
        fuse_final_score(llm_fit=80, rrf_normalized=0.9, skill_overlap=0.5, recency=0.8)

    assert exc.value.error_code == "validation_error"


def test_skill_jaccard_aliases() -> None:
    assert skill_jaccard(["Go"], ["golang"]) == 1.0
    assert skill_jaccard(["Java"], ["JavaScript"]) == 0.0
