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
from app.services import feedback_store, observability
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
def _is_num_key(key: str) -> bool:
    hs = (key or "").lower()
    return any(k in hs for k in ("ms", "cost", "usd", "count", "calls", "credits", "errors", "total", "rate", "runs", "ceiling", "hits"))
def _fmt_cell(key: str, c: Any) -> str:
    if c is None or c == "": return ""
    hs = (key or "").lower()
    try:
        if "cost" in hs or "usd" in hs: return f"{float(c):.2f}"
        if "rate" in hs and "error_rate" not in hs: return f"{float(c):.4f}".rstrip("0").rstrip(".") or "0"
        if "ms" in hs or any(k in hs for k in ("count", "calls", "credits", "errors", "total", "runs", "hits", "ceiling")):
            return str(int(round(float(c))))
        if "error_rate" in hs: return f"{float(c):.4f}".rstrip("0").rstrip(".") or "0"
    except (TypeError, ValueError): pass
    return str(c)
def _table(headers: list[str], rows: list[list[Any]]) -> str:
    """KV tables (metric,value): format/class value cells from metric name in col0."""
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    kv = len(headers) == 2 and str(headers[1]).lower() in {"value", "val"}
    body = []
    for row in rows:
        tds = []
        for i, c in enumerate(row):
            if i == 0:
                tds.append(f"<td>{html.escape(str(c) if c is not None else '')}</td>"); continue
            fmt_key = str(row[0] or "") if kv else str(headers[i] if i < len(headers) else "")
            cls = "num" if _is_num_key(fmt_key) else ""
            tds.append(f'<td class="{cls}">{html.escape(_fmt_cell(fmt_key, c))}</td>')
        body.append(f"<tr>{''.join(tds)}</tr>")
    return f"<table class='ops-table'><thead><tr>{th}</tr></thead><tbody>{''.join(body)}</tbody></table>"
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
    return stats
def _render_html(stats: dict[str, Any]) -> str:
    lat_rows = [
        [op, v["count"], v["p50_ms"], v["p95_ms"]] for op, v in (stats.get("latency_by_operation") or {}).items()
    ]
    err_rows = [
        [svc, v["errors"], v["total"], v["error_rate"]] for svc, v in (stats.get("error_rate_by_service") or {}).items()
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
        ["m24_panel", f"models={(__import__('app.core.config', fromlist=['settings']).settings.JUDGE_PANEL_MODELS or '(single)')} critique={__import__('app.core.config', fromlist=['settings']).settings.ADVERSARIAL_CRITIQUE} max_pairs={__import__('app.core.config', fromlist=['settings']).settings.PAIRWISE_PANEL_MAX_PAIRS} agree={stats.get('judge_agreement_mean_today')} n={stats.get('judge_agreement_samples_today')}"],
    ]
    learning = stats.get("learning") or {}
    fb = learning.get("feedback_counts") or {}
    fb_rows = [[k, v] for k, v in fb.items()]
    suite_rows: list[list[Any]] = []
    for s in learning.get("suites") or []:
        metrics = s.get("metrics") or {}
        metric_s = " ".join(f"{k}={v}" for k, v in metrics.items())
        trend = s.get("trend") or {}
        trend_s = " ".join(f"{k}:{t.get('delta')}" for k, t in trend.items() if t.get("delta") is not None)
        suite_rows.append([s.get("suite"), s.get("ts"), s.get("git_sha"), metric_s, trend_s])
    exp_rows: list[list[Any]] = []
    for e in learning.get("experiments") or []:
        m = e.get("metrics") or {}
        exp_rows.append([e.get("name") or e.get("variant"), e.get("config_hash"), e.get("git_sha"), e.get("ts"), " ".join(f"{k}={v}" for k, v in m.items())])
    css = (
        ":root{--bg:#F7F4ED;--bg-raised:#FDFBF7;--ink:#0C1F3F;--ink-strong:#081426;--muted:#5C6B82;--line:rgba(12,31,63,.12);--accent:#0C1F3F}"
        "html.dark,:root[data-theme=dark]{--bg:#0A182E;--bg-raised:#102340;--ink:#F2EDE2;--ink-strong:#FDFBF7;--muted:#9AA3B5;--line:rgba(242,237,226,.14);--accent:#F2EDE2}"
        "body{font-family:system-ui,sans-serif;margin:1.5rem;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.45}"
        "h1,h2,h3{color:var(--ink-strong);margin-top:1.5rem}h1{font-size:1.5rem}h2{font-size:1.15rem}p,.lede{color:var(--muted)}"
        ".ops-table{border-collapse:collapse;margin:.5rem 0 1.5rem;font-size:13px;width:100%;background:var(--bg-raised);border:1px solid var(--line);border-radius:10px}"
        ".ops-table th,.ops-table td{border-bottom:1px solid var(--line);padding:8px 10px;text-align:left}"
        ".ops-table th{background:color-mix(in srgb,var(--ink) 4%,var(--bg-raised));color:var(--muted);font-size:11px;letter-spacing:.08em;text-transform:uppercase;position:sticky;top:0}"
        ".ops-table tbody tr:nth-child(even){background:color-mix(in srgb,var(--ink) 3%,transparent)}"
        ".ops-table td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;text-align:right}"
        "a{color:var(--accent)}a:focus-visible,button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}"
        ".theme-bar{display:flex;gap:.5rem;margin-bottom:1rem}.theme-bar button{background:var(--bg-raised);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:6px 12px;cursor:pointer;font:inherit}"
        ".theme-bar button:hover{border-color:var(--ink)}"
    )
    js = "(function(){try{var t=localStorage.getItem('ops-theme')||'light';document.documentElement.classList.toggle('dark',t==='dark');document.documentElement.dataset.theme=t}catch(e){}})();function setOpsTheme(t){document.documentElement.classList.toggle('dark',t==='dark');document.documentElement.dataset.theme=t;try{localStorage.setItem('ops-theme',t)}catch(e){}}"
    src = [[s.get("source"), s.get("calls"), s.get("p50_ms"), s.get("p95_ms"), s.get("error_rate")] for s in (stats.get("job_sources") or [])] or [["—", "", "", "", "no source traces"]]
    ws = [[w.get("workspace_id"), w.get("llm_cost_usd"), w.get("sumble_credits")] for w in (stats.get("workspace_usage_today") or [])] or [["—", "", ""]]
    tr_h = ["created_at","operation","status","latency_ms","cost_usd","credits","prompt","ver","cache_hit","error","request_id"]
    return (
        f"<!DOCTYPE html><html data-theme='light'><head><title>TeamScout Ops</title><meta name='color-scheme' content='light dark'/>"
        f"<style>{css}</style><script>{js}</script></head><body>"
        f"<div class='theme-bar' role='group' aria-label='Theme'>"
        f"<button type='button' onclick=\"setOpsTheme('light')\">Light</button>"
        f"<button type='button' onclick=\"setOpsTheme('dark')\">Dark</button></div>"
        f"<h1>TeamScout Ops</h1><p class='lede'>Numbers only. Token-gated. Observe-only learning loop (never auto-mutates production).</p>"
        f"<h2>Summary (today UTC)</h2>{_table(['metric','value'], summary_rows)}"
        f"<h2>Evals</h2><p>Observe-only · evals_root={html.escape(str((stats.get('learning') or {}).get('evals_root') or ''))}</p>"
        f"<h3>Feedback labels</h3>{_table(['kind','count'], fb_rows or [['total',0]])}"
        f"<h3>Suite metrics</h3>{_table(['suite','ts','git_sha','metrics','trend_delta'], suite_rows or [['—','','','no history','']])}"
        f"<h2>Last experiments</h2>{_table(['name','config_hash','git_sha','ts','metrics'], exp_rows or [['—','','','','no experiments']])}"
        f"<h2>Job sources</h2>{_table(['source','calls','p50_ms','p95_ms','error_rate'], src)}"
        f"<h2>Per-workspace usage</h2>{_table(['workspace_id','llm_cost_usd','sumble_credits'], ws)}"
        f"<p>Workspace ceilings: LLM ${html.escape(str(stats.get('workspace_llm_ceiling_usd')))} / Sumble {html.escape(str(stats.get('workspace_sumble_ceiling')))} credits.</p>"
        f"<h2>Latency by operation</h2>{_table(['operation','count','p50_ms','p95_ms'], lat_rows)}"
        f"<h2>Error rate by service</h2>{_table(['service','errors','total','error_rate'], err_rows)}"
        f"<h2>Last 100 traces</h2>{_table(tr_h, trace_rows)}</body></html>"
    )
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
