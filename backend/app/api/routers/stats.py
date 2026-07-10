"""Public GET /stats — safe aggregates for About (no auth, no PII)."""
from __future__ import annotations

import statistics
import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, stats_limit
from app.db.models import JobTeamSearch, Resume, Trace
from app.db.session import get_db
from app.schemas.stats import PublicStats
from app.services.observability import LLM_OPERATIONS

router = APIRouter(tags=["stats"])
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_TTL, _MEDIAN_N = 60.0, 500

def compute_public_stats(db: Session) -> dict[str, Any]:
    try:
        jobs = int(db.execute(text(
            "SELECT COALESCE(SUM(json_array_length(results_json)), 0) FROM searches "
            "WHERE results_json IS NOT NULL AND substr(results_json, 1, 1) = '['"
        )).scalar() or 0)
    except SQLAlchemyError:
        jobs = 0
    rows = (
        db.query(Trace.latency_ms)
        .filter(Trace.operation == "rerank", Trace.latency_ms.isnot(None), Trace.status == "ok")
        .order_by(Trace.created_at.desc()).limit(_MEDIAN_N).all()
    )
    vals = [float(r[0]) for r in rows if r[0] is not None]
    cost = db.query(func.coalesce(func.sum(Trace.cost_usd), 0.0)).filter(
        Trace.operation.in_(LLM_OPERATIONS)
    ).scalar()
    return {
        "jobs_ranked_total": jobs,
        "resumes_parsed_total": int(db.query(func.count(Resume.id)).scalar() or 0),
        "teams_discovered_total": int(db.query(func.count(JobTeamSearch.id)).scalar() or 0),
        "median_rank_latency_ms": round(float(statistics.median(vals)), 1) if vals else None,
        "total_llm_cost_usd": round(float(cost or 0.0), 6),
    }

def get_public_stats(db: Session) -> PublicStats:
    now = time.monotonic()
    if _CACHE["payload"] is not None and (now - float(_CACHE["at"])) < _TTL:
        return PublicStats.model_validate(_CACHE["payload"])
    payload = compute_public_stats(db)
    _CACHE["at"], _CACHE["payload"] = now, payload
    return PublicStats.model_validate(payload)

def clear_public_stats_cache() -> None:
    _CACHE["at"], _CACHE["payload"] = 0.0, None

@router.get("/stats", response_model=PublicStats)
@limiter.limit(stats_limit)
def public_stats(request: Request, db: Session = Depends(get_db)) -> PublicStats:
    return get_public_stats(db)
