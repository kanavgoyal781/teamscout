"""Property tests for MaxSim coverage, clustering, Borda, and lexical honesty."""

from __future__ import annotations

import math
import random

import pytest
from app.services.ranking_math_align import (
    DEFAULT_EVIDENCE_FLOOR,
    NO_CLEAR_EVIDENCE,
    align_resume,
    apply_evidence_floor,
    borda_order,
    borda_points_for_margin,
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
    skill_match_level,
    skill_requirement_score,
    under_segmented_units,
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


def test_apply_evidence_floor_rescale() -> None:
    floor = DEFAULT_EVIDENCE_FLOOR
    assert apply_evidence_floor(0.0, floor=floor) == 0.0
    assert apply_evidence_floor(floor - 0.01, floor=floor) == 0.0
    assert apply_evidence_floor(floor, floor=floor) == pytest.approx(0.0)
    assert apply_evidence_floor(1.0, floor=floor) == pytest.approx(1.0)
    mid = floor + (1.0 - floor) * 0.5
    assert apply_evidence_floor(mid, floor=floor) == pytest.approx(0.5)


def test_skill_requirement_exact_alias_semantic_cap() -> None:
    assert skill_match_level("Python", "Python") == "exact"
    assert skill_match_level("Go", "Golang") == "alias"
    exact = skill_requirement_score(
        "Python", skills=["Python"], unit_texts=["other work"], semantic_score=0.2
    )
    assert exact == pytest.approx(1.0)
    alias = skill_requirement_score(
        "Go", skills=["Golang"], unit_texts=[], semantic_score=0.95
    )
    assert alias == pytest.approx(0.9)
    # No skill match: semantic capped at 0.6 even if raw MaxSim is high
    soft = skill_requirement_score(
        "Rust", skills=[], unit_texts=["systems programming"], semantic_score=0.92
    )
    assert soft == pytest.approx(0.6)


def test_skill_requirement_score_order_independent_over_units() -> None:
    """Phrase hits take max(exact, alias) across ALL units — no first-unit break."""
    alias_first = skill_requirement_score(
        "Go",
        skills=[],
        unit_texts=["Wrote Golang services", "Expert in Go systems"],
        semantic_score=0.1,
    )
    exact_first = skill_requirement_score(
        "Go",
        skills=[],
        unit_texts=["Expert in Go systems", "Wrote Golang services"],
        semantic_score=0.1,
    )
    assert alias_first == pytest.approx(1.0)
    assert exact_first == pytest.approx(1.0)


def test_align_resume_rows_and_coverage() -> None:
    reqs = [_norm([1.0, 0.0, 0.0]), _norm([0.0, 1.0, 0.0])]
    units = [_norm([1.0, 0.0, 0.0]), _norm([0.0, 0.0, 1.0])]
    texts = ["python", "java"]
    unit_texts = ["Built python APIs", "Managed networks"]
    cov, rows = align_resume(reqs, texts, [2.0, 1.0], units, unit_texts, ["python"])
    assert 0.0 <= cov <= 1.0
    assert len(rows) == 2
    assert rows[0]["status"] == "hit"
    assert rows[0]["evidence_unit"] == "Built python APIs"
    # python skill exact → raw 1.0 → floor-rescaled 1.0
    assert rows[0]["evidence_score"] == pytest.approx(1.0)


def test_align_skill_vs_experience_paths() -> None:
    """Skill category uses matcher; experience uses MaxSim (no 0.6 semantic cap)."""
    req = _norm([1.0, 0.0, 0.0])
    unit = _norm([0.9, 0.1, 0.0])  # high semantic
    # skill without list match: capped then floored
    cov_s, rows_s = align_resume(
        [req],
        ["obscure-framework"],
        [2.0],
        [unit],
        ["related systems work with obscure-framework patterns"],
        [],
        categories=["skill"],
        evidence_floor=0.55,
    )
    # phrase hit on unit → exact 1.0
    assert rows_s[0]["status"] == "hit"

    # experience category: high MaxSim can pass floor without skill list
    strong = _norm([1.0, 0.0, 0.0])
    cov_e, rows_e = align_resume(
        [strong],
        ["5+ years leading platform teams"],
        [2.0],
        [strong],
        ["Led platform engineering for five years at scale"],
        [],
        categories=["experience"],
        evidence_floor=0.55,
    )
    assert rows_e[0]["raw_evidence_score"] >= 0.55
    assert rows_e[0]["status"] == "hit"
    assert cov_e > 0


def test_align_below_floor_is_no_clear_evidence() -> None:
    req = _norm([1.0, 0.0, 0.0])
    weak = _norm([0.0, 1.0, 0.0])  # orthogonal → cosine ~0
    cov, rows = align_resume(
        [req],
        ["TotallyUnrelatedSkillXYZ"],
        [2.0],
        [weak],
        ["Managed office supplies inventory"],
        [],
        categories=["skill"],
        evidence_floor=0.55,
    )
    assert rows[0]["status"] == "miss"
    assert rows[0]["evidence_score"] == 0.0
    assert rows[0]["evidence_unit"] == NO_CLEAR_EVIDENCE
    assert cov == 0.0


def test_one_must_have_difference_coverage_gap_at_least_8_points() -> None:
    """Two resumes differing in exactly one must-have → coverage gap ≥ 0.08 (0–1 scale).

    Coverage is a weighted mean of floor-rescaled evidences in [0, 1]. An 8-point
    gap means absolute difference ≥ 0.08 on that scale (equivalent to 8 percentage
    points when displayed as percent).

    Guarantee is for exact/alias skill list (or phrase) hits vs miss — NOT for
    semantic-only near-misses (cap 0.6 → ~0.111 after floor → gap ≈0.028/must).
    Close semantic-only skill deltas may still enter the tournament band (0.05).
    """
    # Abstract: four equal must-weights; only the first evidence differs.
    weights = [2.0, 2.0, 2.0, 2.0]
    shared = [1.0, 1.0, 1.0]
    full = coverage_from_evidence(weights, [1.0, *shared])
    missing = coverage_from_evidence(weights, [0.0, *shared])
    gap = full - missing
    assert gap >= 0.08, f"expected ≥0.08 coverage gap, got {gap}"
    assert gap == pytest.approx(0.25)

    # Production path: align_resume + evidence floor + kind-aware skill scoring
    dim = 4
    req_texts = ["Python", "FastAPI", "PostgreSQL", "AWS"]
    req_embs = [_norm([1.0 if i == j else 0.0 for i in range(dim)]) for j in range(4)]
    weights = [2.0, 2.0, 2.0, 2.0]
    unit_embs = [_norm([0.25, 0.25, 0.25, 0.25])]
    unit_texts = ["General platform engineering work"]
    cov_full, rows_full = align_resume(
        req_embs, req_texts, weights, unit_embs, unit_texts,
        ["Python", "FastAPI", "PostgreSQL", "AWS"],
        categories=["skill"] * 4, evidence_floor=0.55,
    )
    cov_miss, rows_miss = align_resume(
        req_embs, req_texts, weights, unit_embs, unit_texts,
        ["Python", "FastAPI", "PostgreSQL"],  # missing AWS
        categories=["skill"] * 4, evidence_floor=0.55,
    )
    align_gap = cov_full - cov_miss
    assert align_gap >= 0.08, f"align_resume gap {align_gap} < 0.08"
    assert rows_full[3]["status"] == "hit"
    assert rows_miss[3]["status"] == "miss"
    assert rows_miss[3]["evidence_unit"] == NO_CLEAR_EVIDENCE


def test_floor_equality_miss_clears_evidence_unit() -> None:
    """raw == floor rescales to 0 → miss with No clear evidence (not a leftover unit)."""
    assert apply_evidence_floor(0.55, floor=0.55) == pytest.approx(0.0)
    # Alias skill score is 0.9; set floor=0.9 so raw == floor → rescaled 0 / miss.
    req = _norm([1.0, 0.0, 0.0])
    unit = _norm([0.0, 1.0, 0.0])
    cov, rows = align_resume(
        [req],
        ["Go"],
        [2.0],
        [unit],
        ["Wrote Golang microservices at scale"],  # unit mentions alias form
        ["Golang"],
        categories=["skill"],
        evidence_floor=0.9,
    )
    assert rows[0]["raw_evidence_score"] == pytest.approx(0.9) or rows[0]["raw_evidence_score"] == pytest.approx(1.0)
    # When raw is alias 0.9 or exact 1.0 via unit phrase:
    # If exact (phrase): raw 1.0 → hit. Prefer unit without exact token form.
    cov2, rows2 = align_resume(
        [req],
        ["Go"],
        [2.0],
        [unit],
        ["Unrelated systems work only"],
        ["Golang"],  # alias on skill list only → raw 0.9
        categories=["skill"],
        evidence_floor=0.9,
    )
    assert rows2[0]["raw_evidence_score"] == pytest.approx(0.9)
    assert rows2[0]["evidence_score"] == pytest.approx(0.0)
    assert rows2[0]["status"] == "miss"
    assert rows2[0]["evidence_unit"] == NO_CLEAR_EVIDENCE


def test_under_segmented_units_detects_over_citation() -> None:
    rows = [
        {"evidence_unit": "same bullet", "status": "hit"},
        {"evidence_unit": "same bullet", "status": "hit"},
        {"evidence_unit": "same bullet", "status": "hit"},
        {"evidence_unit": "same bullet", "status": "hit"},
        {"evidence_unit": "other", "status": "hit"},
    ]
    assert "same bullet" in under_segmented_units(rows, max_citations=3)


def test_borda_margin_points() -> None:
    assert borda_points_for_margin("decisive") == 1.0
    assert borda_points_for_margin("slight") == 0.5
    contested = ["r1", "r2", "r3"]
    wins = {("r1", "r2"): "r2", ("r1", "r3"): "r1", ("r2", "r3"): "r2"}
    # slight win for r2 over r1; decisive elsewhere — r2 still leads on points
    margins = {("r1", "r2"): "slight", ("r1", "r3"): "decisive", ("r2", "r3"): "decisive"}
    ordered = borda_order(contested, wins, pairwise_margins=margins)
    assert ordered[0] == "r2"


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


def test_evidence_floor_settings_matches_math_default() -> None:
    from app.core.config import settings
    from app.services.ranking_math_align import DEFAULT_EVIDENCE_FLOOR

    assert settings.EVIDENCE_FLOOR == DEFAULT_EVIDENCE_FLOOR
