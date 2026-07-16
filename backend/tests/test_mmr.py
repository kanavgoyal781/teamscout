"""Property tests for MMR diversification and company soft cap."""

from __future__ import annotations

from app.services.ranking.math import apply_company_soft_cap, mmr


def _sim_from_vectors(ids: list[str], vectors: dict[str, list[float]]) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            va, vb = vectors[a], vectors[b]
            out[(a, b)] = sum(x * y for x, y in zip(va, vb, strict=True))
    return out


def test_mmr_output_subset_no_dups() -> None:
    ids = ["a", "b", "c", "d"]
    relevance = {"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6}
    pairwise = {("a", "b"): 0.9, ("a", "c"): 0.1, ("a", "d"): 0.2, ("b", "c"): 0.1, ("b", "d"): 0.2, ("c", "d"): 0.8}
    out = mmr(ids, relevance, pairwise, lambda_=0.75, k=3)
    assert len(out) == 3
    assert len(set(out)) == 3
    assert set(out).issubset(set(ids))


def test_mmr_first_is_argmax_relevance() -> None:
    ids = ["a", "b", "c"]
    relevance = {"a": 0.5, "b": 0.95, "c": 0.7}
    pairwise = {("a", "b"): 0.0, ("a", "c"): 0.0, ("b", "c"): 0.0}
    out = mmr(ids, relevance, pairwise, lambda_=0.75)
    assert out[0] == "b"


def test_mmr_lambda_one_reproduces_relevance_order() -> None:
    ids = ["c", "a", "b", "d"]
    relevance = {"a": 0.4, "b": 0.9, "c": 0.7, "d": 0.1}
    pairwise = {
        ("a", "b"): 0.99,
        ("a", "c"): 0.99,
        ("a", "d"): 0.99,
        ("b", "c"): 0.99,
        ("b", "d"): 0.99,
        ("c", "d"): 0.99,
    }
    out = mmr(ids, relevance, pairwise, lambda_=1.0)
    expected = sorted(ids, key=lambda i: (-relevance[i], i))
    assert out == expected


def test_mmr_empty() -> None:
    assert mmr([], {}, {}, lambda_=0.75) == []


def test_mmr_dedupes_input_ids() -> None:
    ids = ["a", "a", "b"]
    relevance = {"a": 1.0, "b": 0.5}
    out = mmr(ids, relevance, {}, lambda_=1.0)
    assert out == ["a", "b"]


def test_company_soft_cap_limits_top10() -> None:
    # 12 companies available so cap applies; Mega dominates relevance head
    ordered = [f"mega-{i}" for i in range(6)] + [f"other-{i}" for i in range(10)]
    company = {f"mega-{i}": "MegaCorp" for i in range(6)}
    company.update({f"other-{i}": f"Co{i}" for i in range(10)})
    capped = apply_company_soft_cap(ordered, company, top_k=10, max_per_company=3)
    head = capped[:10]
    mega_in_head = sum(1 for i in head if company[i] == "MegaCorp")
    assert mega_in_head <= 3
    assert set(capped) == set(ordered)


def test_company_soft_cap_skipped_when_few_companies() -> None:
    ordered = [f"j{i}" for i in range(8)]
    company = {f"j{i}": f"C{i % 3}" for i in range(8)}  # only 3 companies < top_k=10
    capped = apply_company_soft_cap(ordered, company, top_k=10, max_per_company=3)
    assert capped == ordered


def test_mmr_prefers_diversity_when_lambda_mid() -> None:
    # a and b nearly identical and highly relevant; c diverse and slightly less relevant
    ids = ["a", "b", "c"]
    relevance = {"a": 1.0, "b": 0.99, "c": 0.85}
    pairwise = {("a", "b"): 0.99, ("a", "c"): 0.05, ("b", "c"): 0.05}
    out = mmr(ids, relevance, pairwise, lambda_=0.75, k=2)
    assert out[0] == "a"
    assert out[1] == "c"  # not near-duplicate b


def test_mmr_diversifies_with_production_0_100_scores() -> None:
    """Regression: 0–100 scores must be unit-normalized by caller for diversity.

    Pure mmr still needs unit scale; this documents the contract and shows
    0–100 without normalize fails while unit succeeds.
    """
    ids = ["a", "b", "c"]
    # Near-dups a,b high; c diverse lower
    pairwise = {("a", "b"): 0.99, ("a", "c"): 0.05, ("b", "c"): 0.05}

    unit = {"a": 0.92, "b": 0.91, "c": 0.80}
    out_unit = mmr(ids, unit, pairwise, lambda_=0.75, k=2)
    assert out_unit[0] == "a"
    assert out_unit[1] == "c"

    # Production scores without normalize keep near-dup
    raw = {"a": 92.0, "b": 91.0, "c": 80.0}
    out_raw = mmr(ids, raw, pairwise, lambda_=0.75, k=2)
    assert out_raw[1] == "b"  # diversity drowned — documents the bug if unnormalized

    # Call-site fix: normalize by max (as ranking._diversify_ranked does)
    scale = max(raw.values())
    normalized = {k: v / scale for k, v in raw.items()}
    out_norm = mmr(ids, normalized, pairwise, lambda_=0.75, k=2)
    assert out_norm[0] == "a"
    assert out_norm[1] == "c"


def test_diversify_ranked_normalizes_0_100_scores() -> None:
    """Boundary test: ranking._diversify_ranked unit-scales match_score before mmr."""
    from datetime import UTC, datetime
    from unittest.mock import patch

    from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
    from app.services.ranking.engine import _diversify_ranked

    def _rj(jid: str, company: str, title: str, score: float, desc: str) -> RankedJob:
        job = Job(
            id=jid,
            source="fixture",
            source_job_id=jid,
            title=title,
            company=company,
            location="Remote",
            description=desc,
            apply_url=f"https://example.com/{jid}",
            posted_at=datetime.now(UTC),
            skills=["Python"],
        )
        return RankedJob(
            job=job,
            match_score=score,
            score_breakdown=ScoreBreakdown(
                llm_fit=score,
                rrf_normalized=0.5,
                skill_jaccard=0.5,
                recency=0.5,
                final_score=score,
            ),
        )

    ranked = [
        _rj("a", "Acme", "Engineer", 92.0, "Build backend services with Python and APIs daily."),
        _rj("b", "Acme", "Engineer II", 91.0, "Build backend services with Python and APIs daily!!"),
        _rj("c", "OtherCo", "Data Scientist", 80.0, "Causal inference and experiment design for growth."),
    ]

    def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            if "causal" in t.lower() or "data scientist" in t.lower():
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([1.0, 0.0, 0.0])
        return out

    with patch("app.services.inference.embeddings.embed_batch", side_effect=fake_embed_batch):
        out = _diversify_ranked(ranked, lambda_=0.75, top_n=2)
    assert out[0].job.id == "a"
    assert out[1].job.id == "c"


def test_diversify_ranked_company_soft_cap_on_full_pool() -> None:
    """Soft-cap must apply when pool has ≥10 companies even if MMR head is Mega-heavy.

    Regression: previously MMR truncated to top_n first, leaving <10 companies in the
    list so soft-cap skipped and MegaCorp kept 8 of top-10.
    """
    from datetime import UTC, datetime
    from unittest.mock import patch

    from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
    from app.services.ranking.engine import _diversify_ranked

    def _rj(jid: str, company: str, score: float) -> RankedJob:
        # Distinct description per company so embed vectors can differ
        job = Job(
            id=jid,
            source="fixture",
            source_job_id=jid,
            title="Software Engineer",
            company=company,
            location="Remote",
            description=f"Role at {company}: build products with Python and APIs. {jid}",
            apply_url=f"https://example.com/{jid}",
            posted_at=datetime.now(UTC),
            skills=["Python"],
        )
        return RankedJob(
            job=job,
            match_score=score,
            score_breakdown=ScoreBreakdown(
                llm_fit=score,
                rrf_normalized=0.5,
                skill_jaccard=0.5,
                recency=0.5,
                final_score=score,
            ),
        )

    ranked: list[RankedJob] = []
    # 8 MegaCorp near-identical high scores
    for i in range(8):
        ranked.append(_rj(f"mega-{i}", "MegaCorp", 95.0 - i * 0.1))
    # 12 other companies slightly lower
    for i in range(12):
        ranked.append(_rj(f"alt-{i}", f"AltCo{i}", 80.0 - i * 0.2))

    def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        # MegaCorp near-identical; each AltCo unique direction
        out: list[list[float]] = []
        for t in texts:
            if "MegaCorp" in t:
                out.append([1.0, 0.0, 0.0])
            else:
                # hash company into a distinct unit vector on axes
                idx = abs(hash(t)) % 50
                # simple one-hot-ish in 3D with noise via index
                import math

                angle = (idx / 50.0) * math.pi
                out.append([math.cos(angle) * 0.3, math.sin(angle), 0.7])
        # L2 normalize
        normed = []
        for v in out:
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            normed.append([x / n for x in v])
        return normed

    with patch("app.services.inference.embeddings.embed_batch", side_effect=fake_embed_batch):
        out = _diversify_ranked(ranked, lambda_=0.75, top_n=10)

    assert len(out) == 10
    mega_in_top = sum(1 for item in out if item.job.company == "MegaCorp")
    companies = {item.job.company for item in out}
    assert mega_in_top <= 3, f"expected ≤3 MegaCorp in top-10, got {mega_in_top}"
    assert len(companies) >= 4


def test_company_soft_cap_uses_pool_company_count_gate() -> None:
    """Few unique companies in ordered_ids but large pool_company_count → still cap."""
    from app.services.ranking.math import apply_company_soft_cap

    # Only 3 employers in this ordered list (would skip without pool_company_count).
    ordered = [f"m{i}" for i in range(5)] + [f"a{i}" for i in range(5)] + [f"b{i}" for i in range(5)]
    company = {f"m{i}": "Mega" for i in range(5)}
    company.update({f"a{i}": "Alpha" for i in range(5)})
    company.update({f"b{i}": "Beta" for i in range(5)})
    # Without pool count: 3 companies < top_k=10 → skip
    no_gate = apply_company_soft_cap(ordered, company, top_k=10, max_per_company=3)
    assert no_gate == ordered
    # With pool_company_count from full scored pool: gate open → reorders for diversity
    gated = apply_company_soft_cap(ordered, company, top_k=10, max_per_company=3, pool_company_count=12)
    assert gated != ordered
    assert set(gated) == set(ordered)
    # Greedy phase keeps Mega ≤3 before soft-fill; early head is diversified
    assert sum(1 for i in gated[:6] if company.get(i) == "Mega") <= 3
    assert sum(1 for i in gated[:10] if company.get(i) != "Mega") >= 3
