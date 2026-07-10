"""Property tests for MaxSim coverage, clustering, Borda, and lexical honesty."""

from __future__ import annotations

import math
import random

import pytest
from app.services.ranking_math_align import (
    align_resume,
    borda_order,
    close_call_band,
    coverage_from_evidence,
    maxsim_best_unit_index,
    maxsim_evidence,
    merge_tournament_order,
    order_normalized_pair,
    phrase_in_text,
    single_linkage_clusters,
    skill_equals,
    skill_match_bonus_applies,
    unit_evidence_score,
)


def _norm(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / n for x in vec]


def test_maxsim_is_max_not_mean() -> None:
    req = _norm([1.0, 0.0, 0.0])
    units = [_norm([0.0, 1.0, 0.0]), _norm([1.0, 0.0, 0.0]), _norm([0.5, 0.5, 0.0])]
    score = maxsim_evidence(req, units)
    assert score == pytest.approx(1.0, abs=1e-6)
    idx, raw = maxsim_best_unit_index(req, units)
    assert idx == 1
    assert raw == pytest.approx(1.0, abs=1e-6)


def test_lexical_floor_beats_near_miss_skill_unit() -> None:
    req = _norm([0.2, 0.8, 0.0])
    python_skill = _norm([0.25, 0.75, 0.0])
    decisive = _norm([0.0, 0.1, 0.9])
    idx, score = maxsim_best_unit_index(
        req,
        [python_skill, decisive],
        requirement_text="PyTorch",
        unit_texts=["Python", "Deployed PyTorch ranking models tracked in MLflow"],
        skills=["Python", "SQL"],
    )
    assert idx == 1
    assert score == pytest.approx(1.0)


def test_phrase_in_text_rejects_substring_false_positives() -> None:
    assert phrase_in_text("Java", "Maintained JavaScript widgets") is False
    assert phrase_in_text("Go", "Good communication and ownership") is False
    assert phrase_in_text("React", "Built reactive data pipelines") is False
    assert phrase_in_text("SQL", "Tuned MySQL replicas") is False
    assert phrase_in_text("AWS", "handled claws carefully") is False
    assert phrase_in_text("machine learning", "machine shop learning curve") is False
    # true positives
    assert phrase_in_text("Java", "Built Java services") is True
    assert phrase_in_text("Go", "Wrote Go microservices") is True
    assert phrase_in_text("golang", "Wrote Go microservices") is True
    assert phrase_in_text("machine learning", "Applied machine learning models") is True
    assert phrase_in_text("C++", "Optimized C++ kernels") is True


def test_skill_bonus_rejects_java_for_javascript_requirement() -> None:
    from app.services.ranking_math_align import resume_has_skill

    assert skill_equals("JavaScript", "Java") is False
    assert skill_equals("Java", "Java") is True
    # Per-unit skill bonus is unit-local only (no resume-global +0.15 on every unit)
    assert (
        skill_match_bonus_applies(
            "Java",
            unit_text="Other work",
            skills=["Java"],
        )
        is False
    )
    assert (
        skill_match_bonus_applies(
            "Java",
            unit_text="Built Java services",
            skills=[],
        )
        is True
    )
    assert resume_has_skill("Java", ["Java"]) is True
    assert resume_has_skill("JavaScript", ["Java"]) is False
    # Cosine only ~0.2; lexical must not floor Java via JavaScript substring
    score = unit_evidence_score(
        _norm([1.0, 0.0]),
        _norm([0.2, 0.98]),
        requirement_text="Java",
        unit_text="Maintained JavaScript widgets",
        skills=[],
    )
    assert phrase_in_text("Java", "Maintained JavaScript widgets") is False
    assert score < 0.5


def test_skill_bonus_applied_once_after_maxsim() -> None:
    """Resume-level skill list adds +0.15 once, not per unit."""
    req = _norm([0.5, 0.5, 0.0])
    # Two unrelated units with moderate cosine; skill list has the requirement
    u1 = _norm([0.5, 0.5, 0.01])
    u2 = _norm([0.5, 0.5, 0.02])
    base = maxsim_evidence(req, [u1, u2], requirement_text="Rust", unit_texts=["A", "B"], skills=[])
    with_skill = maxsim_evidence(req, [u1, u2], requirement_text="Rust", unit_texts=["A", "B"], skills=["Rust"])
    assert with_skill == pytest.approx(min(1.0, base + 0.15), abs=1e-6)
    assert with_skill <= 1.0


def test_maxsim_tie_prefers_experience_bullet_over_skill_label() -> None:
    """When skill + bullet both lexical-hit at 1.0, evidence_unit is the bullet."""
    req = _norm([1.0, 0.0, 0.0])
    skill_emb = _norm([1.0, 0.0, 0.0])
    bullet_emb = _norm([1.0, 0.0, 0.0])
    idx, score = maxsim_best_unit_index(
        req,
        [skill_emb, bullet_emb],
        requirement_text="Python",
        unit_texts=["Python", "Shipped Python FastAPI services on AWS with PostgreSQL"],
        unit_sections=["skills", "experience"],
        skills=["Python"],
    )
    assert score == pytest.approx(1.0)
    assert idx == 1
    # Reverse order still prefers experience
    idx2, _ = maxsim_best_unit_index(
        req,
        [bullet_emb, skill_emb],
        requirement_text="Python",
        unit_texts=["Shipped Python FastAPI services on AWS with PostgreSQL", "Python"],
        unit_sections=["experience", "skills"],
        skills=["Python"],
    )
    assert idx2 == 0


def test_coverage_monotonicity_raising_evidence_never_lowers() -> None:
    weights = [2.0, 1.0, 1.5, 0.5]
    rng = random.Random(0)
    for _ in range(40):
        base = [rng.random() for _ in weights]
        cov0 = coverage_from_evidence(weights, base)
        i = rng.randrange(len(base))
        raised = list(base)
        raised[i] = min(1.0, raised[i] + rng.uniform(0.01, 0.4))
        cov1 = coverage_from_evidence(weights, raised)
        assert cov1 + 1e-12 >= cov0


def test_coverage_permutation_invariance_of_requirements() -> None:
    weights = [2.0, 1.0, 1.5]
    evidences = [0.2, 0.9, 0.5]
    base = coverage_from_evidence(weights, evidences)
    order = [2, 0, 1]
    permuted_w = [weights[i] for i in order]
    permuted_e = [evidences[i] for i in order]
    assert coverage_from_evidence(permuted_w, permuted_e) == pytest.approx(base)


def test_coverage_bounds() -> None:
    assert 0.0 <= coverage_from_evidence([1.0], [0.0]) <= 1.0
    assert 0.0 <= coverage_from_evidence([1.0], [1.0]) <= 1.0
    assert coverage_from_evidence([], []) == 0.0
    assert coverage_from_evidence([0.0, 0.0], [0.5, 0.9]) == 0.0


def test_align_resume_rows_and_coverage() -> None:
    reqs = [_norm([1.0, 0.0, 0.0]), _norm([0.0, 1.0, 0.0])]
    units = [_norm([1.0, 0.0, 0.0]), _norm([0.0, 0.0, 1.0])]
    texts = ["python", "java"]
    unit_texts = ["Built python APIs", "Managed networks"]
    cov, rows = align_resume(reqs, texts, [2.0, 1.0], units, unit_texts, ["python"])
    assert 0.0 <= cov <= 1.0
    assert len(rows) == 2
    assert rows[0]["evidence_unit"] == "Built python APIs"


def test_single_linkage_near_dup_threshold() -> None:
    ids = ["a", "b", "c"]
    embs = [
        _norm([1.0, 0.0, 0.0]),
        _norm([0.999, 0.01, 0.0]),
        _norm([0.0, 1.0, 0.0]),
    ]
    mapping = single_linkage_clusters(ids, embs, threshold=0.95)
    assert mapping["a"] == mapping["b"]
    assert mapping["c"] != mapping["a"]


def test_borda_and_merge_order() -> None:
    contested = ["r1", "r2", "r3"]
    wins = {("r1", "r2"): "r2", ("r1", "r3"): "r1", ("r2", "r3"): "r2"}
    ordered = borda_order(contested, wins, coverage_tiebreak={"r1": 0.8, "r2": 0.79, "r3": 0.7})
    assert ordered[0] == "r2"
    full = ["r1", "r2", "r3", "r4"]
    merged = merge_tournament_order(full, ordered)
    assert merged[:3] == ordered
    assert merged[3] == "r4"


def test_order_normalized_pair_symmetric() -> None:
    assert order_normalized_pair("b", "a") == order_normalized_pair("a", "b")


def test_close_call_band_only_near_leader() -> None:
    ordered = [
        ("a", 0.80),
        ("b", 0.76),
        ("c", 0.50),
        ("d", 0.40),
        ("e", 0.30),
    ]
    band = close_call_band(ordered, gap=0.05, top_k=5)
    assert band == ["a", "b"]
    assert "e" not in band


def test_far_fifth_cannot_leapfrog_via_merge() -> None:
    """Contested band is only close candidates; #5 stays after non-band."""
    full = ["a", "b", "c", "d", "e"]
    # Only a,b contested; borda flips to b,a
    merged = merge_tournament_order(full, ["b", "a"])
    assert merged[0] == "b"
    assert merged[1] == "a"
    assert merged[2:] == ["c", "d", "e"]
    assert merged[-1] == "e"


def test_close_call_band_empty_when_gap_large() -> None:
    ordered = [("a", 0.90), ("b", 0.70), ("c", 0.50)]
    assert close_call_band(ordered, gap=0.05, top_k=5) == []


def test_phrase_in_text_single_char_skills_c_and_r() -> None:
    assert phrase_in_text("C", "Expert in C and systems programming") is True
    assert phrase_in_text("R", "Used R for statistics") is True
    assert phrase_in_text("C", "careful coding") is False
    assert phrase_in_text("x", "x marks the spot") is False  # not allowlisted


def test_phrase_in_text_aliases_and_empty() -> None:
    assert phrase_in_text("postgres", "Tuned PostgreSQL indexes") is True
    assert phrase_in_text("postgresql", "postgres") is True
    assert phrase_in_text("ts", "TypeScript apps") is True
    assert phrase_in_text("node", "Node.js services") is True
    assert phrase_in_text("", "anything") is False
    assert phrase_in_text("Java", "") is False


def test_maxsim_empty_units_and_align_errors() -> None:
    req = _norm([1.0, 0.0])
    idx, score = maxsim_best_unit_index(req, [])
    assert idx is None and score == 0.0
    # Empty units → zero coverage (no crash); length mismatches raise
    cov, rows = align_resume([req], ["Java"], [1.0], [], [], [])
    assert cov == 0.0
    assert rows[0]["status"] == "miss"
    with pytest.raises(ValueError):
        align_resume([req], ["Java"], [1.0, 2.0], [], [], [])
    with pytest.raises(ValueError):
        coverage_from_evidence([1.0], [0.5, 0.5])


def test_close_call_band_top_k_and_exact_gap() -> None:
    from app.services.ranking_math_align import TOURNAMENT_GAP, close_call_band

    pairs = [("a", 0.9), ("b", 0.89), ("c", 0.88), ("d", 0.87), ("e", 0.86), ("f", 0.85)]
    band = close_call_band(pairs, gap=0.1, top_k=3)
    assert band == ["a", "b", "c"]
    # exact gap boundary → empty
    assert close_call_band([("a", 0.9), ("b", 0.9 - TOURNAMENT_GAP)], gap=TOURNAMENT_GAP) == []
