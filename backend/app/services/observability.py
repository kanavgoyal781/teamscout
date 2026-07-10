"""LLM/embed/hiring-team/JSearch tracing, ceilings, optional OTLP."""

from __future__ import annotations

import statistics
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.db.models import Trace
from app.db.session import SessionLocal
from app.errors import CostCeilingExceededError

logger = get_logger(__name__)

LLM_OPERATIONS = frozenset({"parse_resume", "rerank", "team_extract", "justify", "embed"})
FEATURE1_OPS = frozenset(
    {
        "parse_resume",
        "rerank",
        "team_extract",
        "jsearch.search",
        "sumble.organizations",
        "sumble.people",
        "sumble.jobs",
        "sumble.title_lookup",
        "sumble.email_reveal",
        "sumble.unknown",
    }
)
FEATURE2_OPS = frozenset({"justify"})

def current_request_id() -> str | None:
    try:
        ctx = structlog.contextvars.get_contextvars()
    except (AttributeError, TypeError, RuntimeError):
        return None
    rid = ctx.get("request_id")
    return str(rid) if rid else None

def estimate_llm_cost_usd(
    *, model: str | None, input_tokens: int | None, output_tokens: int | None
) -> float:
    _ = model
    inp = max(int(input_tokens or 0), 0)
    out = max(int(output_tokens or 0), 0)
    return (inp / 1_000_000.0) * settings.LLM_PRICE_INPUT_PER_1M + (
        out / 1_000_000.0
    ) * settings.LLM_PRICE_OUTPUT_PER_1M

def estimate_embedding_cost_usd(*, input_tokens: int | None) -> float:
    return (max(int(input_tokens or 0), 0) / 1_000_000.0) * settings.EMBEDDINGS_PRICE_PER_1M

def approx_token_count(text: str) -> int:
    return 0 if not text else max(1, len(text) // 4)

def _today_start_naive() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

def llm_cost_today_usd(db: Session | None = None) -> float:
    own = db is None
    session = db or SessionLocal()
    try:
        total = (
            session.query(func.coalesce(func.sum(Trace.cost_usd), 0.0))
            .filter(Trace.created_at >= _today_start_naive(), Trace.operation.in_(tuple(LLM_OPERATIONS)))
            .scalar()
        )
        return float(total or 0.0)
    except SQLAlchemyError as exc:
        raise CostCeilingExceededError(
            "LLM cost ceiling check failed — denying request (fail closed)",
            details={"reason": str(exc)},
        ) from exc
    finally:
        if own:
            session.close()

def sumble_credits_today(db: Session | None = None) -> int:
    own = db is None
    session = db or SessionLocal()
    try:
        total = (
            session.query(func.coalesce(func.sum(Trace.credits_used), 0))
            .filter(Trace.created_at >= _today_start_naive(), Trace.operation.like("sumble.%"))
            .scalar()
        )
        return int(total or 0)
    except SQLAlchemyError as exc:
        raise CostCeilingExceededError(
            "Sumble credit ceiling check failed — denying request (fail closed)",
            details={"reason": str(exc)},
        ) from exc
    finally:
        if own:
            session.close()

def assert_llm_budget_allows(*, estimated_cost_usd: float = 0.0) -> None:
    spent = llm_cost_today_usd()
    ceiling = float(settings.LLM_DAILY_COST_CEILING_USD)
    if spent + max(estimated_cost_usd, 0.0) > ceiling:
        raise CostCeilingExceededError(
            f"Daily LLM cost ceiling exceeded (${spent:.4f} spent, ceiling ${ceiling:.2f})",
            details={"spent_usd": spent, "ceiling_usd": ceiling},
        )

def assert_sumble_budget_allows(*, estimated_credits: int = 0) -> None:
    spent = sumble_credits_today()
    ceiling = int(settings.SUMBLE_DAILY_CREDIT_CEILING)
    if spent + max(estimated_credits, 0) > ceiling:
        raise CostCeilingExceededError(
            f"Daily Sumble credit ceiling exceeded ({spent} used, ceiling {ceiling})",
            details={"spent_credits": spent, "ceiling_credits": ceiling},
        )

def record_trace(
    *,
    operation: str,
    model: str | None = None,
    prompt_name: str | None = None,
    prompt_version: str | None = None,
    prompt_hash: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: float | None = None,
    cost_usd: float | None = None,
    credits_used: int | None = None,
    status: str = "ok",
    error_type: str | None = None,
    cache_hit: bool = False,
    request_id: str | None = None,
) -> None:
    rid = request_id if request_id is not None else current_request_id()
    row = Trace(
        request_id=rid,
        operation=operation,
        model=model,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        credits_used=credits_used,
        status=status,
        error_type=error_type,
        cache_hit=cache_hit,
    )
    session = SessionLocal()
    try:
        session.add(row)
        session.commit()
        session.refresh(row)
        op_name = row.operation
        op_status = row.status or "ok"
        op_rid = row.request_id or ""
    except SQLAlchemyError as exc:
        session.rollback()
        logger.error("trace.record_failed", operation=operation, error=str(exc))
        return
    finally:
        session.close()
    _maybe_export_otlp(operation=op_name, status=op_status, request_id=op_rid)

def _maybe_export_otlp(*, operation: str, status: str, request_id: str) -> None:
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if not is_set(endpoint):
        return
    url = (endpoint or "").rstrip("/")
    if not url.endswith("/v1/traces"):
        url = f"{url}/v1/traces"
    body = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": operation,
                                "attributes": [
                                    {"key": "teamscout.operation", "value": {"stringValue": operation}},
                                    {"key": "teamscout.status", "value": {"stringValue": status}},
                                    {
                                        "key": "teamscout.request_id",
                                        "value": {"stringValue": request_id},
                                    },
                                ],
                            }
                        ]
                    }
                ]
            }
        ]
    }
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            client.post(url, json=body, headers={"Content-Type": "application/json"})
    except httpx.HTTPError as exc:
        logger.warning("otlp.export_failed", error=str(exc), host=urlparse(url).netloc)

@dataclass
class TraceContext:
    operation: str
    model: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    credits_used: int | None = None
    cache_hit: bool = False
    status: str = "ok"
    error_type: str | None = None

@contextmanager
def traced_call(
    operation: str,
    *,
    model: str | None = None,
    prompt_name: str | None = None,
    prompt_version: str | None = None,
    prompt_hash: str | None = None,
    check_llm_ceiling: bool = False,
    check_sumble_ceiling: bool = False,
    estimated_cost_usd: float = 0.0,
    estimated_credits: int = 0,
) -> Generator[TraceContext, None, None]:
    if check_llm_ceiling:
        assert_llm_budget_allows(estimated_cost_usd=estimated_cost_usd)
    if check_sumble_ceiling:
        assert_sumble_budget_allows(estimated_credits=estimated_credits)
    ctx = TraceContext(
        operation=operation,
        model=model,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
    )
    started = time.perf_counter()
    try:
        yield ctx
    except BaseException as exc:
        ctx.status = "error"
        ctx.error_type = type(exc).__name__
        record_trace(
            operation=ctx.operation,
            model=ctx.model,
            prompt_name=ctx.prompt_name,
            prompt_version=ctx.prompt_version,
            prompt_hash=ctx.prompt_hash,
            input_tokens=ctx.input_tokens,
            output_tokens=ctx.output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            cost_usd=ctx.cost_usd,
            credits_used=ctx.credits_used,
            status=ctx.status,
            error_type=ctx.error_type,
            cache_hit=ctx.cache_hit,
        )
        raise
    else:
        record_trace(
            operation=ctx.operation,
            model=ctx.model,
            prompt_name=ctx.prompt_name,
            prompt_version=ctx.prompt_version,
            prompt_hash=ctx.prompt_hash,
            input_tokens=ctx.input_tokens,
            output_tokens=ctx.output_tokens,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            cost_usd=ctx.cost_usd,
            credits_used=ctx.credits_used,
            status=ctx.status,
            error_type=ctx.error_type,
            cache_hit=ctx.cache_hit,
        )

def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

def sumble_operation_from_path(path: str) -> str:
    p = path.strip().rstrip("/")
    if "title-lookup" in p:
        return "sumble.title_lookup"
    if p.endswith("/organizations") or "/organizations" in p:
        return "sumble.organizations"
    if p.endswith("/people"):
        return "sumble.people"
    if "/jobs" in p:
        return "sumble.jobs"
    return "sumble.unknown"

def ops_stats(db: Session) -> dict[str, Any]:
    start = _today_start_naive()
    recent = db.query(Trace).order_by(Trace.created_at.desc()).limit(100).all()
    today = db.query(Trace).filter(Trace.created_at >= start).all()

    latency_by_op: dict[str, list[float]] = {}
    errors_by_svc: dict[str, list[int]] = {}
    for row in today:
        svc = row.operation.split(".", 1)[0]
        bucket = errors_by_svc.setdefault(svc, [0, 0])
        bucket[1] += 1
        if row.status != "ok":
            bucket[0] += 1
        if row.latency_ms is not None:
            latency_by_op.setdefault(row.operation, []).append(float(row.latency_ms))

    latency_summary = {
        op: {
            "count": len(v),
            "p50_ms": round(_percentile(sorted(v), 0.50), 1),
            "p95_ms": round(_percentile(sorted(v), 0.95), 1),
        }
        for op, v in sorted(latency_by_op.items())
    }

    f1_rids = {r.request_id for r in today if r.request_id and r.operation in FEATURE1_OPS}
    f2_rids = {r.request_id for r in today if r.request_id and r.operation in FEATURE2_OPS}
    f1_costs = [sum(float(x.cost_usd or 0) for x in today if x.request_id == rid) for rid in f1_rids]
    f2_costs = [sum(float(x.cost_usd or 0) for x in today if x.request_id == rid) for rid in f2_rids]
    embeds = [r for r in today if r.operation == "embed"]
    hits = sum(1 for r in embeds if r.cache_hit)

    return {
        "recent_traces": [
            {
                "id": r.id,
                "request_id": r.request_id,
                "operation": r.operation,
                "model": r.model,
                "prompt_name": r.prompt_name,
                "prompt_version": r.prompt_version,
                "prompt_hash": r.prompt_hash,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "latency_ms": r.latency_ms,
                "cost_usd": r.cost_usd,
                "credits_used": r.credits_used,
                "status": r.status,
                "error_type": r.error_type,
                "cache_hit": r.cache_hit,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
        "latency_by_operation": latency_summary,
        "total_cost_today_usd": round(sum(float(r.cost_usd or 0) for r in today), 6),
        "llm_cost_today_usd": round(
            sum(float(r.cost_usd or 0) for r in today if r.operation in LLM_OPERATIONS), 6
        ),
        "llm_ceiling_usd": float(settings.LLM_DAILY_COST_CEILING_USD),
        "sumble_credits_today": sum(
            int(r.credits_used or 0) for r in today if (r.operation or "").startswith("sumble.")
        ),
        "sumble_ceiling": int(settings.SUMBLE_DAILY_CREDIT_CEILING),
        "cost_per_feature1_run_usd": round(statistics.mean(f1_costs) if f1_costs else 0.0, 6),
        "feature1_runs_today": len(f1_costs),
        "cost_per_feature2_run_usd": round(statistics.mean(f2_costs) if f2_costs else 0.0, 6),
        "feature2_runs_today": len(f2_costs),
        "error_rate_by_service": {
            svc: {
                "errors": c[0],
                "total": c[1],
                "error_rate": round(c[0] / c[1], 4) if c[1] else 0.0,
            }
            for svc, c in sorted(errors_by_svc.items())
        },
        "embedding_cache_hit_rate": round((hits / len(embeds)) if embeds else 0.0, 4),
        "embedding_cache_hits": hits,
        "embedding_cache_total": len(embeds),
    }
