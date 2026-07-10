"""Platt scaling for match-score → likelihood. Fit only via scripts; never auto-mutates rankers."""
from __future__ import annotations
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from sqlalchemy.exc import SQLAlchemyError
from app.core.logging import get_logger
from app.db.models import ScoreCalibration
from app.db.session import SessionLocal, ensure_db
logger = get_logger(__name__)
MIN_LABELS_FIT = 30
MIN_LABELS_UI = 50
HOLDOUT_FRACTION = 0.2
@dataclass(frozen=True)
class PlattParams:
    a: float
    b: float
    n_labels: int
    holdout_auc: float | None
    fit_at: str
    metadata: dict[str, Any]
def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)
def platt_likelihood(score_0_100: float, a: float, b: float) -> float:
    s = max(0.0, min(1.0, float(score_0_100) / 100.0))
    return sigmoid(a * s + b)
def _binary_auc(scores: list[float], labels: list[int]) -> float:
    pairs = sorted(zip(scores, labels, strict=True), key=lambda t: t[0])
    n_pos, n_neg = sum(labels), len(labels) - sum(labels)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = sum(i for i, (_, y) in enumerate(pairs, start=1) if y == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
def _shuffle_idx(n: int, seed: int) -> list[int]:
    idx, state = list(range(n)), seed & 0xFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        j = state % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return idx
def fit_platt(
    scores: list[float], labels: list[int], *, max_iter: int = 200, lr: float = 0.05,
    holdout_fraction: float = HOLDOUT_FRACTION, seed: int = 42,
) -> PlattParams:
    n = len(scores)
    if n < MIN_LABELS_FIT:
        raise ValueError(f"need ≥{MIN_LABELS_FIT} labels to fit calibration, got {n}")
    if len(labels) != n or not all(y in (0, 1) for y in labels):
        raise ValueError("bad scores/labels")
    idx = _shuffle_idx(n, seed)
    n_hold = max(1, int(n * holdout_fraction)) if n >= 10 else 0
    hold = set(idx[:n_hold]) if n_hold else set()
    train_s = [scores[i] / 100.0 for i in range(n) if i not in hold]
    train_y = [labels[i] for i in range(n) if i not in hold]
    hold_s = [scores[i] / 100.0 for i in range(n) if i in hold]
    hold_y = [labels[i] for i in range(n) if i in hold]
    a, b = 1.0, 0.0
    for _ in range(max_iter):
        ga = gb = 0.0
        for s, y in zip(train_s, train_y, strict=True):
            p = sigmoid(a * s + b)
            ga += (p - y) * s
            gb += p - y
        m = max(len(train_s), 1)
        a -= lr * ga / m
        b -= lr * gb / m
    auc = None
    if hold_s and len(set(hold_y)) > 1:
        auc = round(_binary_auc([sigmoid(a * s + b) for s in hold_s], hold_y), 4)
    return PlattParams(
        a=round(a, 6), b=round(b, 6), n_labels=n, holdout_auc=auc,
        fit_at=datetime.now(UTC).isoformat(),
        metadata={"train_n": len(train_s), "holdout_n": len(hold_s), "seed": seed},
    )
def save_calibration(params: PlattParams, *, kind: str = "platt_jobs") -> None:
    ensure_db()
    session = SessionLocal()
    try:
        session.query(ScoreCalibration).filter(ScoreCalibration.kind == kind).delete()
        session.add(ScoreCalibration(
            kind=kind, a=params.a, b=params.b, n_labels=params.n_labels,
            holdout_auc=params.holdout_auc, fit_at=datetime.now(UTC).replace(tzinfo=None),
            metadata_json=json.dumps(params.metadata, sort_keys=True),
        ))
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("calibration.save_failed", error=str(exc))
        raise
    finally:
        session.close()
def load_active_calibration(*, kind: str = "platt_jobs") -> PlattParams | None:
    ensure_db()
    session = SessionLocal()
    try:
        row = (
            session.query(ScoreCalibration).filter(ScoreCalibration.kind == kind)
            .order_by(ScoreCalibration.fit_at.desc()).first()
        )
        if row is None:
            return None
        meta: dict[str, Any] = {}
        if row.metadata_json:
            try:
                loaded = json.loads(row.metadata_json)
                meta = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                meta = {}
        return PlattParams(
            a=float(row.a), b=float(row.b), n_labels=int(row.n_labels or 0),
            holdout_auc=float(row.holdout_auc) if row.holdout_auc is not None else None,
            fit_at=row.fit_at.isoformat() if row.fit_at else "", metadata=meta,
        )
    except SQLAlchemyError as exc:
        logger.warning("calibration.load_failed", error=str(exc))
        return None
    finally:
        session.close()
def ui_match_likelihood(
    score_0_100: float,
    params: PlattParams | None = None,
) -> float | None:
    """Return 0–1 likelihood only when RANKING_USE_CALIBRATION is on and n≥50.

    Fitting writes SQLite proposals; the UI path stays off until a human sets
    RANKING_USE_CALIBRATION=true after reviewing the fit (no silent auto-apply).
    """
    from app.core.config import settings

    if not settings.RANKING_USE_CALIBRATION:
        return None
    if params is None:
        params = load_active_calibration()
    if params is None or params.n_labels < MIN_LABELS_UI:
        return None
    return round(platt_likelihood(score_0_100, params.a, params.b), 4)
