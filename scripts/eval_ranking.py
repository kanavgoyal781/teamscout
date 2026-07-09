#!/usr/bin/env python3
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ensure_db
from app.schemas.jobs import Job
from app.services import ranking
from scripts.fixtures.ranking_fixtures import PERSONAS, PersonaFixture


import json
import subprocess
from datetime import UTC, datetime

from app.prompts import prompt_versions


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


def append_eval_history(metrics: dict) -> None:
    history = ROOT / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "suite": "ranking",
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


def evaluate_persona(persona: PersonaFixture) -> dict[str, float]:
    jobs = [labeled.job for labeled in persona.jobs]
    relevance_by_id = {labeled.job.id: labeled.relevance for labeled in persona.jobs}

    hybrid = ranking.rank_jobs(persona.profile, jobs, use_llm=False)
    dense = ranking.rank_jobs_dense_only(persona.profile, jobs)

    hybrid_rels = [relevance_by_id[item.job.id] for item in hybrid]
    dense_rels = [relevance_by_id[item.job.id] for item in dense]

    return {
        "hybrid_ndcg10": ndcg_at_k(hybrid_rels, 10),
        "hybrid_mrr": mrr(hybrid_rels),
        "dense_ndcg10": ndcg_at_k(dense_rels, 10),
        "dense_mrr": mrr(dense_rels),
    }


def main() -> int:
    # Ensure M8 traces / embedding_cache tables exist (CLI has no FastAPI lifespan).
    ensure_db()

    from app.services.embeddings import embeddings_endpoint

    if not is_set(settings.EMBEDDINGS_API_KEY) or not embeddings_endpoint():
        print(
            "SKIP: embeddings not configured — set EMBEDDINGS_API_KEY and "
            "EMBEDDINGS_API (or LLM_API_BASE) to run eval"
        )
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

    failures: list[str] = []
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
    append_eval_history(metrics_out)

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())