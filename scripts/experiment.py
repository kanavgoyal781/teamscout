#!/usr/bin/env python3
"""Ranking experiment harness — observe only; never mutates production defaults.

Usage:
  python scripts/experiment.py --variants configs/experiments/*.json

Variants declare ranking params. config_hash covers all RESULT_PARAM_KEYS.
Offline suite measures weights/rrf/recency/rerank via settings + use_mmr/mmr_lambda via
diversity/persona diversify. expansion/tournament_threshold are production LLM knobs
(hashed for provenance; not exercised offline without LLM).
Writes evals/experiments.jsonl keyed by config_hash + git_sha.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import ensure_db  # noqa: E402
from app.prompts import prompt_versions  # noqa: E402
from app.services.ranking_config import (  # noqa: E402
    DEFAULT_EXPANSION,
    DEFAULT_MMR_LAMBDA,
    DEFAULT_TOURNAMENT_THRESHOLD,
    DEFAULT_USE_MMR,
    RESULT_PARAM_KEYS,
    ranking_config_hash as _shared_config_hash,
)
from app.services import ranking  # noqa: E402
from scripts.eval_ranking import (  # noqa: E402
    append_eval_history,
    evaluate_diversity,
    evaluate_persona,
)
from scripts.fixtures.ranking_fixtures import PERSONAS  # noqa: E402

OUT = ROOT / "evals" / "experiments.jsonl"


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


def normalize_variant(raw: dict[str, Any]) -> dict[str, Any]:
    weights = raw.get("weights") or {}
    return {
        "name": str(raw.get("name") or "unnamed"),
        "weights": {
            "llm": float(weights.get("llm", settings.RANKING_WEIGHT_LLM)),
            "rrf": float(weights.get("rrf", settings.RANKING_WEIGHT_RRF)),
            "skills": float(weights.get("skills", settings.RANKING_WEIGHT_SKILLS)),
            "recency": float(weights.get("recency", settings.RANKING_WEIGHT_RECENCY)),
            "experience": float(weights.get("experience", settings.RANKING_WEIGHT_EXPERIENCE)),
            "requirements": float(weights.get("requirements", settings.RANKING_WEIGHT_REQUIREMENTS)),
        },
        "rrf_k": int(raw.get("rrf_k", settings.RRF_K)),
        "mmr_lambda": float(raw.get("mmr_lambda", DEFAULT_MMR_LAMBDA)),
        "use_mmr": bool(raw.get("use_mmr", DEFAULT_USE_MMR)),
        "expansion": bool(raw.get("expansion", DEFAULT_EXPANSION)),
        "tournament_threshold": float(raw.get("tournament_threshold", DEFAULT_TOURNAMENT_THRESHOLD)),
        "recency_half_life_days": int(
            raw.get("recency_half_life_days", settings.RECENCY_HALF_LIFE_DAYS)
        ),
        "rerank_top_n": int(raw.get("rerank_top_n", settings.RERANK_TOP_N)),
        "search_results_top_n": int(
            raw.get("search_results_top_n", settings.SEARCH_RESULTS_TOP_N)
        ),
    }


def config_hash(variant: dict[str, Any]) -> str:
    return _shared_config_hash(variant)


def apply_variant(variant: dict[str, Any]) -> dict[str, Any]:
    """Monkeypatch settings for this process only. Returns previous values."""
    w = variant["weights"]
    prev = {
        "RANKING_WEIGHT_LLM": settings.RANKING_WEIGHT_LLM,
        "RANKING_WEIGHT_RRF": settings.RANKING_WEIGHT_RRF,
        "RANKING_WEIGHT_SKILLS": settings.RANKING_WEIGHT_SKILLS,
        "RANKING_WEIGHT_RECENCY": settings.RANKING_WEIGHT_RECENCY,
        "RANKING_WEIGHT_EXPERIENCE": settings.RANKING_WEIGHT_EXPERIENCE,
        "RANKING_WEIGHT_REQUIREMENTS": settings.RANKING_WEIGHT_REQUIREMENTS,
        "RRF_K": settings.RRF_K,
        "RECENCY_HALF_LIFE_DAYS": settings.RECENCY_HALF_LIFE_DAYS,
        "RERANK_TOP_N": settings.RERANK_TOP_N,
        "SEARCH_RESULTS_TOP_N": settings.SEARCH_RESULTS_TOP_N,
    }
    settings.RANKING_WEIGHT_LLM = w["llm"]
    settings.RANKING_WEIGHT_RRF = w["rrf"]
    settings.RANKING_WEIGHT_SKILLS = w["skills"]
    settings.RANKING_WEIGHT_RECENCY = w["recency"]
    settings.RANKING_WEIGHT_EXPERIENCE = w["experience"]
    settings.RANKING_WEIGHT_REQUIREMENTS = w["requirements"]
    settings.RRF_K = variant["rrf_k"]
    settings.RECENCY_HALF_LIFE_DAYS = variant["recency_half_life_days"]
    settings.RERANK_TOP_N = variant["rerank_top_n"]
    settings.SEARCH_RESULTS_TOP_N = variant["search_results_top_n"]
    return prev


def restore_settings(prev: dict[str, Any]) -> None:
    for key, value in prev.items():
        setattr(settings, key, value)


def run_synthetic(variant: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    """Persona NDCG/MRR + diversity under variant (use_llm=False).

    Returns (metrics, variant_flags). Weights/rrf_k/recency/rerank already applied
    via apply_variant → settings. MMR params applied here to diversity + persona diversify.
    expansion/tournament_threshold are production knobs (LLM paths); recorded in flags only
    for this offline suite (no silent fake metric impact).
    """
    from app.core.env_utils import is_set
    from app.services.embeddings import embeddings_endpoint

    totals = {"hybrid_ndcg10": 0.0, "hybrid_mrr": 0.0, "dense_ndcg10": 0.0, "dense_mrr": 0.0}
    original_diversify = ranking._diversify_ranked

    def diversify_patched(ranked: list, *, lambda_: float = 0.75, top_n: int | None = None):
        return original_diversify(ranked, lambda_=variant["mmr_lambda"], top_n=top_n)

    ranking._diversify_ranked = diversify_patched  # type: ignore[assignment]
    try:
        out: dict[str, float] = {}
        use_div = bool(variant["use_mmr"])
        if is_set(settings.EMBEDDINGS_API_KEY) and embeddings_endpoint():
            for persona in PERSONAS:
                metrics = evaluate_persona(persona, diversify=use_div)
                for k, v in metrics.items():
                    totals[k] += v
            n = max(len(PERSONAS), 1)
            out = {k: v / n for k, v in totals.items()}
        else:
            print("NOTE: embeddings missing — synthetic persona metrics skipped for this variant")
            out = {k: 0.0 for k in totals}
            out["personas_skipped"] = 1.0

        div = evaluate_diversity(
            mmr_lambda=float(variant["mmr_lambda"]),
            use_mmr=bool(variant["use_mmr"]),
        )
        out["mmr_companies_top10"] = div["mmr_companies_top10"]
        out["mmr_ndcg_drop"] = div["mmr_ndcg_drop"]
        out["rel_only_companies_top10"] = div["rel_only_companies_top10"]

        flags = {
            "use_mmr": bool(variant["use_mmr"]),
            "mmr_lambda": float(variant["mmr_lambda"]),
            "expansion": bool(variant["expansion"]),
            "tournament_threshold": float(variant["tournament_threshold"]),
            "rrf_k": int(variant["rrf_k"]),
        }
        return out, flags
    finally:
        ranking._diversify_ranked = original_diversify  # type: ignore[assignment]


def run_feedback_suite() -> dict[str, float] | None:
    path = ROOT / "evals" / "feedback_set.jsonl"
    if not path.is_file():
        return None
    labels = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            labels.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(labels) < 30:
        return {"label_count": float(len(labels)), "insufficient": 1.0}
    # Aggregate: fraction of thumbs_up+apply among thumbs+apply+down
    pos = sum(1 for L in labels if L.get("kind") in {"thumbs_up", "apply_click"})
    neg = sum(1 for L in labels if L.get("kind") == "thumbs_down")
    scored = pos + neg
    precision_proxy = (pos / scored) if scored else 0.0
    return {
        "label_count": float(len(labels)),
        "positive_rate": precision_proxy,
        "pos": float(pos),
        "neg": float(neg),
    }


def append_experiment(record: dict[str, Any]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def load_variants(patterns: list[str]) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for pat in patterns:
        matched = [Path(p) for p in sorted(glob.glob(pat))]
        if not matched and Path(pat).is_file():
            matched = [Path(pat)]
        paths.extend(matched)
    if not paths:
        raise SystemExit(f"No variant files matched: {patterns}")
    variants = []
    for p in paths:
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise SystemExit(f"Variant must be JSON object: {p}")
        variants.append(normalize_variant(raw))
    return variants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["configs/experiments/*.json"],
        help="Glob(s) for experiment JSON variants",
    )
    args = parser.parse_args()

    ensure_db()
    variants = load_variants(args.variants)
    print(f"TeamScout experiment harness — {len(variants)} variant(s)")
    print("NOTE: observe-only; does not write production ranking weights/prompts.\n")

    table: list[tuple[str, str, dict[str, float]]] = []
    for variant in variants:
        ch = config_hash(variant)
        prev = apply_variant(variant)
        try:
            metrics, flags = run_synthetic(variant)
            fb = run_feedback_suite()
            if fb:
                metrics = {**metrics, **{f"feedback_{k}": v for k, v in fb.items()}}
        finally:
            restore_settings(prev)

        record = {
            "ts": datetime.now(UTC).isoformat(),
            "name": variant["name"],
            "config_hash": ch,
            "git_sha": _git_sha(),
            "variant": {k: variant[k] for k in RESULT_PARAM_KEYS},
            "variant_flags": flags,
            "metrics": metrics,
            "prompt_versions": prompt_versions(),
            "model": settings.LLM_MODEL,
            "embeddings_model": settings.EMBEDDINGS_MODEL,
        }
        append_experiment(record)
        # Also append a history line for ops suite trends (experiment suite)
        append_eval_history(metrics, suite=f"experiment:{variant['name']}")
        table.append((variant["name"], ch, metrics))
        print(
            f"  {variant['name']} hash={ch} hybrid_ndcg10={metrics.get('hybrid_ndcg10', 0):.4f} "
            f"mmr_companies={metrics.get('mmr_companies_top10', 0):.0f}"
        )

    print("\n=== metrics table ===")
    print(f"{'name':16} {'hash':16} {'ndcg10':>8} {'mrr':>8} {'mmr_drop':>8}")
    for name, ch, m in table:
        print(
            f"{name:16} {ch:16} {m.get('hybrid_ndcg10', 0):8.4f} "
            f"{m.get('hybrid_mrr', 0):8.4f} {m.get('mmr_ndcg_drop', 0):8.4f}"
        )
    # rank by hybrid_ndcg10
    ranked = sorted(table, key=lambda t: -t[2].get("hybrid_ndcg10", 0.0))
    print("\nrank by hybrid_ndcg10:")
    for i, (name, ch, m) in enumerate(ranked, 1):
        print(f"  #{i} {name} ({ch}) ndcg={m.get('hybrid_ndcg10', 0):.4f}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
