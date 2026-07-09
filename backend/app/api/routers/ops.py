"""Minimal ops dashboard: token-gated HTML of trace stats (no charting libs).

Primary auth: Authorization Bearer or X-Ops-Token. Query ?token= is local-dev only
(leaks via logs/history/Referer) and is accepted as a fallback.
"""

from __future__ import annotations

import hmac
import html
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import get_db
from app.errors import OpsAuthError
from app.services import observability

router = APIRouter(tags=["ops"])


def _extract_token(request: Request, token: str | None) -> str | None:
    # Prefer headers (do not land in access logs / Referer) over query token.
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        value = auth[7:].strip()
        if value:
            return value
    header = request.headers.get("x-ops-token")
    if header and header.strip():
        return header.strip()
    # Local-dev convenience only — prefer Bearer / X-Ops-Token in production.
    if token and token.strip():
        return token.strip()
    return None


def require_ops_token(
    request: Request,
    token: str | None = Query(
        default=None,
        description="Local-dev only. Prefer Authorization: Bearer or X-Ops-Token.",
    ),
) -> None:
    expected = settings.OPS_TOKEN
    if not is_set(expected):
        raise OpsAuthError("Ops access denied — OPS_TOKEN is not configured")
    provided = _extract_token(request, token)
    if not provided or not _tokens_match(provided, expected or ""):
        raise OpsAuthError("Ops access denied — missing or invalid token")


def _tokens_match(provided: str, expected: str) -> bool:
    try:
        return hmac.compare_digest(provided, expected)
    except (TypeError, ValueError):
        # Unequal lengths / types — treat as mismatch (compare_digest may raise).
        return False


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body_rows = []
    for row in rows:
        tds = "".join(f"<td>{html.escape(str(c) if c is not None else '')}</td>" for c in row)
        body_rows.append(f"<tr>{tds}</tr>")
    return f"<table border='1' cellpadding='4' cellspacing='0'><thead><tr>{th}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _render_html(stats: dict[str, Any]) -> str:
    lat_rows = [
        [op, v["count"], v["p50_ms"], v["p95_ms"]]
        for op, v in (stats.get("latency_by_operation") or {}).items()
    ]
    err_rows = [
        [svc, v["errors"], v["total"], v["error_rate"]]
        for svc, v in (stats.get("error_rate_by_service") or {}).items()
    ]
    trace_rows = [
        [
            t.get("created_at"),
            t.get("operation"),
            t.get("status"),
            t.get("latency_ms"),
            t.get("cost_usd"),
            t.get("credits_used"),
            t.get("prompt_name"),
            t.get("prompt_version"),
            t.get("cache_hit"),
            t.get("error_type"),
            t.get("request_id"),
        ]
        for t in (stats.get("recent_traces") or [])
    ]
    summary_rows = [
        ["total_cost_today_usd", stats.get("total_cost_today_usd")],
        ["llm_cost_today_usd", stats.get("llm_cost_today_usd")],
        ["llm_ceiling_usd", stats.get("llm_ceiling_usd")],
        ["sumble_credits_today", stats.get("sumble_credits_today")],
        ["sumble_ceiling", stats.get("sumble_ceiling")],
        ["cost_per_feature1_run_usd", stats.get("cost_per_feature1_run_usd")],
        ["feature1_runs_today", stats.get("feature1_runs_today")],
        ["cost_per_feature2_run_usd", stats.get("cost_per_feature2_run_usd")],
        ["feature2_runs_today", stats.get("feature2_runs_today")],
        ["embedding_cache_hit_rate", stats.get("embedding_cache_hit_rate")],
        ["embedding_cache_hits", stats.get("embedding_cache_hits")],
        ["embedding_cache_total", stats.get("embedding_cache_total")],
    ]
    return f"""<!DOCTYPE html>
<html><head><title>TeamScout Ops</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.5rem; }}
h1,h2 {{ margin-top: 1.5rem; }}
table {{ border-collapse: collapse; margin: 0.5rem 0 1.5rem; font-size: 13px; }}
th {{ background: #eee; text-align: left; }}
</style></head>
<body>
<h1>TeamScout Ops</h1>
<p>Numbers only. Token-gated. No charting libraries.</p>
<h2>Summary (today UTC)</h2>
{_table(["metric", "value"], summary_rows)}
<h2>Latency by operation (p50 / p95 ms)</h2>
{_table(["operation", "count", "p50_ms", "p95_ms"], lat_rows)}
<h2>Error rate by service</h2>
{_table(["service", "errors", "total", "error_rate"], err_rows)}
<h2>Last 100 traces</h2>
{_table(
    ["created_at", "operation", "status", "latency_ms", "cost_usd", "credits", "prompt", "ver", "cache_hit", "error", "request_id"],
    trace_rows,
)}
</body></html>"""


@router.get("/ops", response_class=HTMLResponse)
def ops_dashboard(
    _auth: None = Depends(require_ops_token),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    stats = observability.ops_stats(db)
    return HTMLResponse(content=_render_html(stats))


@router.get("/ops/json")
def ops_json(
    _auth: None = Depends(require_ops_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return JSONResponse(content=observability.ops_stats(db))
