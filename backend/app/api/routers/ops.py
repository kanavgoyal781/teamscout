from __future__ import annotations
import hmac
from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import get_db
from app.errors import OpsAuthError
from app.services import feedback_store, observability
from app.services.ops.html_render import _render_html
router = APIRouter(tags=["ops"])
def _extract_token(request: Request, token: str | None) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        value = auth[7:].strip()
        if value: return value
    header = request.headers.get("x-ops-token")
    if header and header.strip(): return header.strip()
    env = (settings.ENV or "").strip().lower()
    if env not in {"prod", "production"} and token and token.strip(): return token.strip()
    return None
def require_ops_token(
    request: Request,
    token: str | None = Query(
        default=None,
        description="Local-dev only (disabled when ENV=prod). Prefer Authorization: Bearer or X-Ops-Token.",
    ),
) -> None:
    expected = settings.OPS_TOKEN
    if not is_set(expected): raise OpsAuthError("Ops access denied — OPS_TOKEN is not configured")
    provided = _extract_token(request, token)
    if not provided or not _tokens_match(provided, expected or ""): raise OpsAuthError("Ops access denied — missing or invalid token")
def _tokens_match(provided: str, expected: str) -> bool:
    try:
        return hmac.compare_digest(provided, expected)
    except (TypeError, ValueError):
        return False
def _ops_payload(db: Session) -> dict[str, Any]:
    stats = observability.ops_stats(db)
    learning = feedback_store.learning_file_stats()
    learning["feedback_counts"] = feedback_store.feedback_label_counts(db)
    stats["learning"] = learning
    lat = stats.get("latency_by_operation") or {}
    err = stats.get("error_rate_by_service") or {}
    source_rows = []
    for op, v in lat.items():
        if not str(op).startswith("source."): continue
        name = str(op).split(".", 1)[-1]
        svc = err.get("source") or err.get(name) or {}
        source_rows.append({
            "source": name, "calls": v.get("count"), "p50_ms": v.get("p50_ms"),
            "p95_ms": v.get("p95_ms"), "error_rate": svc.get("error_rate"),
        })
    stats["job_sources"] = source_rows
    stats["m24_panel"] = f"models={(settings.JUDGE_PANEL_MODELS or '(single)')} critique={settings.ADVERSARIAL_CRITIQUE} max_pairs={settings.PAIRWISE_PANEL_MAX_PAIRS} agree={stats.get('judge_agreement_mean_today')} n={stats.get('judge_agreement_samples_today')}"
    return stats
@router.get("/ops", response_class=HTMLResponse)
def ops_dashboard(
    _auth: None = Depends(require_ops_token),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return HTMLResponse(content=_render_html(_ops_payload(db)))
@router.get("/ops/json")
def ops_json(
    _auth: None = Depends(require_ops_token),
    db: Session = Depends(get_db),
) -> JSONResponse:
    return JSONResponse(content=_ops_payload(db))

