#!/usr/bin/env python3
"""Propose ranking weights via pure-Python logistic regression (no numpy) on feedback.

NEVER mutates live config / settings / defaults.json.
Writes only:
  - configs/experiments/learned_weights.json  (normalized weights; experiment harness only)
  - a fit report printed to stdout (n_labels, holdout AUC)

Also fits Platt calibration into SQLite when ≥30 labels (UI needs ≥50 + RANKING_USE_CALIBRATION).

Feature prep: continuous component features are **z-scored using train-split stats only**
(no holdout leakage). Softplus on raw coefs → non-negative fusion weights summing to 1 —
intentional product constraint (fusion weights cannot be negative).

Usage:
  python scripts/fit_weights.py
  python scripts/fit_weights.py --feedback-set evals/feedback_set.jsonl

Requires ≥30 labeled feedback events with score_components + shown_rank (or score_shown for calibration).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.db.models import Feedback  # noqa: E402
from app.db.session import SessionLocal, ensure_db  # noqa: E402
from app.services import calibration as cal  # noqa: E402

MIN_LABELS = 30
COMPONENT_KEYS = (
    "llm", "rrf", "skills", "recency", "experience", "requirements", "cross_encoder",
)
OUT_WEIGHTS = ROOT / "configs" / "experiments" / "learned_weights.json"
# Rank feature is a covariate (position bias control), not a fusion weight.
RANK_FEATURE = "shown_rank"


def _kind_label(kind: str) -> int | None:
    if kind in {"thumbs_up", "apply_click", "find_team_click"}:
        return 1
    if kind == "thumbs_down":
        return 0
    return None


def _load_from_db() -> list[dict[str, Any]]:
    ensure_db()
    db = SessionLocal()
    try:
        rows = db.query(Feedback).order_by(Feedback.created_at.asc()).all()
    finally:
        db.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        y = _kind_label(str(row.kind))
        if y is None:
            continue
        comps: dict[str, float] = {}
        if row.score_components_json:
            try:
                raw = json.loads(row.score_components_json)
                if isinstance(raw, dict):
                    comps = {str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float))}
            except (json.JSONDecodeError, TypeError, ValueError):
                comps = {}
        out.append(
            {
                "y": y,
                "score_shown": float(row.score_shown) if row.score_shown is not None else None,
                "shown_rank": int(row.shown_rank) if row.shown_rank is not None else None,
                "components": comps,
            }
        )
    return out


def _load_from_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        y = _kind_label(str(row.get("kind") or ""))
        if y is None:
            # relevance-style labels from feedback_set
            rel = row.get("relevance")
            if rel is None:
                continue
            y = 1 if float(rel) >= 2.0 else 0
        comps = row.get("score_components") or row.get("components") or {}
        if not isinstance(comps, dict):
            comps = {}
        out.append(
            {
                "y": y,
                "score_shown": float(row["score_shown"]) if row.get("score_shown") is not None else None,
                "shown_rank": int(row["shown_rank"]) if row.get("shown_rank") is not None else None,
                "components": {str(k): float(v) for k, v in comps.items() if isinstance(v, (int, float))},
            }
        )
    return out


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _auc(probs: list[float], labels: list[int]) -> float:
    pairs = sorted(zip(probs, labels, strict=True), key=lambda t: t[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = 0.0
    for i, (_, y) in enumerate(pairs, start=1):
        if y == 1:
            rank_sum += i
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def _shuffle_idx(n: int, seed: int = 42) -> list[int]:
    idx = list(range(n))
    state = seed & 0xFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        j = state % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return idx


def _zscore_train_only(
    X: list[list[float]], train_i: list[int]
) -> tuple[list[list[float]], list[float], list[float]]:
    """Z-score columns using train indices only; apply to full X. Returns (Xz, means, stds)."""
    if not X or not train_i:
        return X, [], []
    d = len(X[0])
    means = [0.0] * d
    for j in range(d):
        means[j] = sum(X[i][j] for i in train_i) / len(train_i)
    stds = [0.0] * d
    for j in range(d):
        var = sum((X[i][j] - means[j]) ** 2 for i in train_i) / max(len(train_i), 1)
        stds[j] = math.sqrt(var) if var > 1e-12 else 1.0
    xz = [[(row[j] - means[j]) / stds[j] for j in range(d)] for row in X]
    return xz, means, stds


def fit_logistic(
    X: list[list[float]],
    y: list[int],
    *,
    max_iter: int = 400,
    lr: float = 0.15,
    l2: float = 0.01,
    holdout_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[list[float], float, float, dict[str, Any]]:
    """Return (weights_with_bias, holdout_auc, train_auc, meta). Bias is last weight.

    Continuous features are z-scored with train-split mean/std only (no holdout leakage).
    """
    n = len(X)
    if n != len(y):
        raise ValueError("X/y length mismatch")
    d = len(X[0]) if X else 0
    idx = _shuffle_idx(n, seed=seed)
    n_hold = max(1, int(n * holdout_fraction)) if n >= 10 else 0
    hold = set(idx[:n_hold]) if n_hold else set()
    train_i = [i for i in range(n) if i not in hold]
    hold_i = [i for i in range(n) if i in hold]

    Xz, means, stds = _zscore_train_only(X, train_i)

    # w[0:d] features, w[d] bias
    w = [0.0] * (d + 1)
    for _ in range(max_iter):
        grad = [0.0] * (d + 1)
        for i in train_i:
            z = w[d]
            for j in range(d):
                z += w[j] * Xz[i][j]
            p = _sigmoid(z)
            err = p - y[i]
            for j in range(d):
                grad[j] += err * Xz[i][j] + l2 * w[j]
            grad[d] += err
        m = max(len(train_i), 1)
        for j in range(d + 1):
            w[j] -= lr * grad[j] / m

    def _probs(indices: list[int]) -> list[float]:
        out = []
        for i in indices:
            z = w[d]
            for j in range(d):
                z += w[j] * Xz[i][j]
            out.append(_sigmoid(z))
        return out

    train_auc = _auc(_probs(train_i), [y[i] for i in train_i]) if train_i else 0.5
    hold_auc = _auc(_probs(hold_i), [y[i] for i in hold_i]) if hold_i and len(set(y[i] for i in hold_i)) > 1 else 0.5
    meta = {
        "train_n": len(train_i), "holdout_n": len(hold_i), "seed": seed, "l2": l2,
        "zscore_means": [round(m, 6) for m in means],
        "zscore_stds": [round(s, 6) for s in stds],
        "feature_standardization": "train_only_zscore",
    }
    return w, hold_auc, train_auc, meta


def _normalize_positive_weights(raw: dict[str, float]) -> dict[str, float]:
    """Map coef → non-negative fusion weights summing to 1 via softplus (intentional).

    Fusion weights must be non-negative and sum to 1.0; softplus enforces that product constraint.
    """
    pos = {k: math.log1p(math.exp(min(v, 20.0))) for k, v in raw.items()}  # softplus, overflow-safe
    total = sum(pos.values()) or 1.0
    return {k: round(v / total, 6) for k, v in pos.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feedback-set", type=Path, default=None, help="Optional JSONL; else SQLite feedback")
    parser.add_argument("--out", type=Path, default=OUT_WEIGHTS)
    args = parser.parse_args()

    rows = _load_from_jsonl(args.feedback_set) if args.feedback_set else _load_from_db()
    if len(rows) < MIN_LABELS:
        print(f"REFUSE: need ≥{MIN_LABELS} labels, got {len(rows)}. No files written. Live config untouched.")
        return 2

    # Weight fit requires component vectors
    usable = [r for r in rows if r["components"]]
    if len(usable) < MIN_LABELS:
        print(
            f"REFUSE weights: need ≥{MIN_LABELS} rows with score_components, got {len(usable)}. "
            "Live config untouched."
        )
        weight_ok = False
    else:
        weight_ok = True

    if weight_ok:
        # Never impute shown_rank as 0 (best rank). Drop missing-rank rows for weight fit.
        ranked_rows = [r for r in usable if r.get("shown_rank") is not None]
        dropped_rank = len(usable) - len(ranked_rows)
        if len(ranked_rows) < MIN_LABELS:
            print(
                f"REFUSE weights: need ≥{MIN_LABELS} rows with score_components AND shown_rank, "
                f"got {len(ranked_rows)} (dropped {dropped_rank} missing shown_rank). "
                "Live config untouched."
            )
            weight_ok = False
        else:
            usable = ranked_rows

    if weight_ok:
        X: list[list[float]] = []
        y: list[int] = []
        for r in usable:
            comps = r["components"]
            feat = []
            for k in COMPONENT_KEYS:
                v = float(comps.get(k, 0.0))
                # llm often 0–100; others 0–1 — normalize llm
                if k == "llm" and v > 1.0:
                    v = v / 100.0
                feat.append(v)
            # position bias covariate (required; not exported as fusion weight)
            feat.append(float(r["shown_rank"]))
            X.append(feat)
            y.append(int(r["y"]))

        w, hold_auc, train_auc, meta = fit_logistic(X, y)
        coef = {COMPONENT_KEYS[i]: w[i] for i in range(len(COMPONENT_KEYS))}
        # drop rank coef from fusion proposal
        weights = _normalize_positive_weights(coef)
        # Ensure sum 1 after rounding
        s = sum(weights.values())
        if s > 0 and not math.isclose(s, 1.0, abs_tol=1e-4):
            weights = {k: round(v / s, 6) for k, v in weights.items()}

        payload = {
            "name": "learned_weights",
            "weights": weights,
            "note": (
                "PROPOSAL ONLY — never auto-applied. Promote via experiment harness + human review. "
                f"fit n={len(usable)} holdout_auc={hold_auc:.4f} train_auc={train_auc:.4f}. "
                f"shown_rank used as bias covariate (coef={w[len(COMPONENT_KEYS)]:.4f}), not a fusion weight. "
                "Calibration in SQLite is also proposal-only until RANKING_USE_CALIBRATION=true."
            ),
            "fit": {
                "n_labels": len(usable),
                "holdout_auc": round(hold_auc, 4),
                "train_auc": round(train_auc, 4),
                "rank_coef": round(w[len(COMPONENT_KEYS)], 6),
                **meta,
            },
            # Keep experiment harness happy with full variant shape
            "rrf_k": 60,
            "mmr_lambda": 0.75,
            "use_mmr": True,
            "expansion": True,
            "tournament_threshold": 0.05,
            "recency_half_life_days": 7,
            "rerank_top_n": 30,
            "search_results_top_n": 10,
            "use_cross_encoder": False,
            "llm_listwise": False,
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote proposal → {args.out}")
        print(f"  n_labels={len(usable)} holdout_auc={hold_auc:.4f} train_auc={train_auc:.4f}")
        print(f"  weights={weights}")
        print("  LIVE CONFIG NOT MODIFIED (observe-only proposal).")
    else:
        print("Skipping weight proposal (insufficient component vectors).")

    # Calibration on score_shown
    cal_rows = [r for r in rows if r.get("score_shown") is not None]
    if len(cal_rows) < MIN_LABELS:
        print(f"REFUSE calibration: need ≥{MIN_LABELS} score_shown labels, got {len(cal_rows)}")
        return 0 if weight_ok else 2
    scores = [float(r["score_shown"]) for r in cal_rows]
    labels = [int(r["y"]) for r in cal_rows]
    params = cal.fit_platt(scores, labels)
    cal.save_calibration(params)
    print(
        f"saved Platt calibration a={params.a} b={params.b} n={params.n_labels} "
        f"holdout_auc={params.holdout_auc} (UI shows likelihood only when n≥{cal.MIN_LABELS_UI})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
