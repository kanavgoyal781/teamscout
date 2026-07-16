#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ensure_db
from app.prompts import prompt_versions
from app.services import ranking
from scripts.fixtures.ranking_fixtures import PERSONAS, PersonaFixture


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return settings.GIT_SHA or "unknown"


def append_eval_history(metrics: dict, *, suite: str = "ranking") -> None:
    history = ROOT / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "suite": suite,
        "metrics": metrics,
        "prompt_versions": prompt_versions(),
        "model": settings.LLM_MODEL,
        "embeddings_model": settings.EMBEDDINGS_MODEL,
        "git_sha": _git_sha(),
    }
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def dcg(relevances: list[float]) -> float:
    score = relevances[0] if relevances else 0.0
    for index, rel in enumerate(relevances[1:], start=2):
        score += rel / math.log2(index + 1)
    return score


def ndcg_at_k(ranked_relevances: list[float], k: int = 10) -> float:
    ideal = sorted(ranked_relevances, reverse=True)[:k]
    actual = ranked_relevances[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0:
        return 0.0
    return dcg(actual) / ideal_dcg


def mrr(ranked_relevances: list[float], threshold: float = 2.0) -> float:
    for index, relevance in enumerate(ranked_relevances, start=1):
        if relevance >= threshold:
            return 1.0 / index
    return 0.0


def evaluate_persona(
    persona: PersonaFixture,
    *,
    diversify: bool = False,
) -> dict[str, float]:
    jobs = [labeled.job for labeled in persona.jobs]
    relevance_by_id = {labeled.job.id: labeled.relevance for labeled in persona.jobs}

    hybrid = ranking.rank_jobs(persona.profile, jobs, use_llm=False, diversify=diversify)
    dense = ranking.rank_jobs_dense_only(persona.profile, jobs)

    hybrid_rels = [relevance_by_id[item.job.id] for item in hybrid]
    dense_rels = [relevance_by_id[item.job.id] for item in dense]

    return {
        "hybrid_ndcg10": ndcg_at_k(hybrid_rels, 10),
        "hybrid_mrr": mrr(hybrid_rels),
        "dense_ndcg10": ndcg_at_k(dense_rels, 10),
        "dense_mrr": mrr(dense_rels),
    }


def evaluate_diversity(
    *,
    mmr_lambda: float | None = None,
    use_mmr: bool = True,
) -> dict[str, float]:
    """MMR top-10 company diversity vs relevance-only; NDCG drop gate.

    Pure ranking_math (no embeddings I/O). Fixture where one company would dominate.
    When use_mmr=False, diversified order is pure relevance (no MMR / soft-cap).
    """
    from app.services.ranking.config import DEFAULT_MMR_LAMBDA
    from app.services.ranking.math import apply_company_soft_cap, mmr

    if mmr_lambda is None:
        mmr_lambda = DEFAULT_MMR_LAMBDA

    ids: list[str] = []
    relevance: dict[str, float] = {}
    company: dict[str, str] = {}
    pairwise: dict[tuple[str, str], float] = {}

    # MegaCorp dominates pure relevance; alts close enough that MMR NDCG drop ≤ 0.03.
    for i in range(8):
        jid = f"mega-{i}"
        ids.append(jid)
        relevance[jid] = 1.0 - i * 0.001
        company[jid] = "MegaCorp"
    for i in range(8):
        jid = f"alt-{i}"
        ids.append(jid)
        relevance[jid] = 0.97 - i * 0.001
        company[jid] = f"AltCo{i}"

    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if company[a] == company[b] == "MegaCorp":
                pairwise[(a, b)] = 0.98
            else:
                pairwise[(a, b)] = 0.05

    rel_order = sorted(ids, key=lambda x: (-relevance[x], x))
    if use_mmr:
        mmr_order = mmr(ids, relevance, pairwise, lambda_=mmr_lambda, k=10)
        mmr_order = apply_company_soft_cap(mmr_order, company, top_k=10, max_per_company=3)
    else:
        mmr_order = rel_order[:10]

    rel_companies = len({company[i] for i in rel_order[:10]})
    mmr_companies = len({company[i] for i in mmr_order[:10]})

    # NDCG vs global ideal (relevance-only top-10), not per-list re-idealization.
    ideal_rels = [relevance[i] for i in rel_order[:10]]
    ideal_dcg = dcg(ideal_rels)

    def _ndcg(order: list[str]) -> float:
        if ideal_dcg == 0:
            return 0.0
        return dcg([relevance[i] for i in order[:10]]) / ideal_dcg

    rel_ndcg = _ndcg(rel_order)
    mmr_ndcg = _ndcg(mmr_order)
    return {
        "rel_only_companies_top10": float(rel_companies),
        "mmr_companies_top10": float(mmr_companies),
        "rel_only_ndcg10": rel_ndcg,
        "mmr_ndcg10": mmr_ndcg,
        "mmr_ndcg_drop": rel_ndcg - mmr_ndcg,
    }


def _check_diversity(div: dict[str, float]) -> list[str]:
    failures: list[str] = []
    if div["mmr_companies_top10"] < 4:
        failures.append(f"mmr companies@10 {div['mmr_companies_top10']:.0f} < 4")
    if div["rel_only_companies_top10"] <= 3 and div["mmr_companies_top10"] <= div["rel_only_companies_top10"]:
        failures.append(
            f"mmr did not improve company diversity "
            f"({div['mmr_companies_top10']:.0f} <= {div['rel_only_companies_top10']:.0f})"
        )
    if div["mmr_ndcg_drop"] > 0.03 + 1e-9:
        failures.append(f"mmr NDCG@10 drop {div['mmr_ndcg_drop']:.4f} > 0.03")
    return failures


FEEDBACK_MIN_LABELS = 30
FEEDBACK_SET = ROOT / "evals" / "feedback_set.jsonl"


def evaluate_feedback_suite() -> int:
    """Label-volume + score-separation health check (not offline re-ranking).

    Requires rehydrated job/profile content for true NDCG-on-feedback (not yet stored).
    Exit 0 loudly when <30 labels (not a hard fail).
    """
    if not FEEDBACK_SET.is_file():
        print(f"insufficient labels: 0/{FEEDBACK_MIN_LABELS} (missing {FEEDBACK_SET})")
        print("HINT: python scripts/build_eval_from_feedback.py after collecting feedback")
        return 0
    labels: list[dict] = []
    for line in FEEDBACK_SET.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            labels.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    n = len(labels)
    if n < FEEDBACK_MIN_LABELS:
        print(f"insufficient labels: {n}/{FEEDBACK_MIN_LABELS}")
        append_eval_history({"label_count": n, "insufficient": 1.0}, suite="feedback")
        return 0

    # Score-aware proxy: mean score_shown on positives vs negatives when present.
    pos = [L for L in labels if L.get("kind") in {"thumbs_up", "apply_click"}]
    neg = [L for L in labels if L.get("kind") == "thumbs_down"]
    pos_scores = [float(L["score_shown"]) for L in pos if L.get("score_shown") is not None]
    neg_scores = [float(L["score_shown"]) for L in neg if L.get("score_shown") is not None]
    mean_pos = sum(pos_scores) / len(pos_scores) if pos_scores else 0.0
    mean_neg = sum(neg_scores) / len(neg_scores) if neg_scores else 0.0
    separation = mean_pos - mean_neg
    metrics = {
        "label_count": float(n),
        "positive_count": float(len(pos)),
        "negative_count": float(len(neg)),
        "mean_score_positive": mean_pos,
        "mean_score_negative": mean_neg,
        "score_separation": separation,
    }
    append_eval_history(metrics, suite="feedback")
    print(
        f"FEEDBACK: labels={n} pos={len(pos)} neg={len(neg)} "
        f"mean_score_pos={mean_pos:.2f} mean_score_neg={mean_neg:.2f} sep={separation:.2f}"
    )
    # Soft gate: positives should show higher match scores when both have scores.
    if pos_scores and neg_scores and separation < 0:
        print(f"FAIL: score_separation {separation:.4f} < 0 (positives ranked lower than negatives)")
        return 1
    print("PASS feedback suite")
    return 0


def run_synthetic_suite() -> int:
    ensure_db()

    from app.services.inference.embeddings import embeddings_endpoint

    div = evaluate_diversity()
    print(
        f"DIVERSITY: rel companies@10={div['rel_only_companies_top10']:.0f} "
        f"mmr companies@10={div['mmr_companies_top10']:.0f} "
        f"ndcg_drop={div['mmr_ndcg_drop']:.4f}"
    )
    append_eval_history(div, suite="diversity")
    div_failures = _check_diversity(div)

    if not is_set(settings.EMBEDDINGS_API_KEY) or not embeddings_endpoint():
        print(
            "SKIP ranking personas: embeddings not configured — set EMBEDDINGS_API_KEY and "
            "EMBEDDINGS_API (or LLM_API_BASE) to run full ranking eval"
        )
        if div_failures:
            print("FAIL diversity:")
            for f in div_failures:
                print(f"  - {f}")
            return 1
        print("PASS diversity (ranking personas skipped)")
        return 0

    if not is_set(settings.LLM_API_KEY) or not is_set(settings.LLM_API_BASE):
        print("NOTE: LLM not configured — eval runs hybrid retrieval without LLM rerank")

    print(f"Embeddings endpoint: {embeddings_endpoint()}")

    totals = {
        "hybrid_ndcg10": 0.0,
        "hybrid_mrr": 0.0,
        "dense_ndcg10": 0.0,
        "dense_mrr": 0.0,
    }

    print("TeamScout ranking eval")
    for persona in PERSONAS:
        metrics = evaluate_persona(persona)
        for key, value in metrics.items():
            totals[key] += value
        print(
            f"{persona.name}: "
            f"HYBRID NDCG@10={metrics['hybrid_ndcg10']:.4f} MRR={metrics['hybrid_mrr']:.4f} | "
            f"DENSE NDCG@10={metrics['dense_ndcg10']:.4f} MRR={metrics['dense_mrr']:.4f}"
        )

    count = len(PERSONAS)
    avg_hybrid_ndcg = totals["hybrid_ndcg10"] / count
    avg_hybrid_mrr = totals["hybrid_mrr"] / count
    avg_dense_ndcg = totals["dense_ndcg10"] / count
    avg_dense_mrr = totals["dense_mrr"] / count

    print(
        f"OVERALL: HYBRID NDCG@10={avg_hybrid_ndcg:.4f} MRR={avg_hybrid_mrr:.4f} | "
        f"DENSE NDCG@10={avg_dense_ndcg:.4f} MRR={avg_dense_mrr:.4f}"
    )

    failures: list[str] = list(div_failures)
    if avg_hybrid_ndcg < 0.85:
        failures.append(f"hybrid NDCG@10 {avg_hybrid_ndcg:.4f} < 0.85")
    if avg_hybrid_mrr < 0.8:
        failures.append(f"hybrid MRR {avg_hybrid_mrr:.4f} < 0.8")
    if avg_hybrid_ndcg <= avg_dense_ndcg:
        failures.append(f"hybrid NDCG@10 {avg_hybrid_ndcg:.4f} did not beat dense {avg_dense_ndcg:.4f}")

    metrics_out = {
        "hybrid_ndcg10": avg_hybrid_ndcg,
        "hybrid_mrr": avg_hybrid_mrr,
        "dense_ndcg10": avg_dense_ndcg,
        "dense_mrr": avg_dense_mrr,
    }
    append_eval_history(metrics_out, suite="ranking")

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="TeamScout ranking eval")
    parser.add_argument(
        "--suite",
        choices=("synthetic", "feedback", "all"),
        default="synthetic",
        help="synthetic=personas+diversity (default); feedback=labels from feedback_set; all=both",
    )
    args = parser.parse_args()

    codes: list[int] = []
    if args.suite in {"synthetic", "all"}:
        codes.append(run_synthetic_suite())
    if args.suite in {"feedback", "all"}:
        codes.append(evaluate_feedback_suite())
    return 1 if any(c != 0 for c in codes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
