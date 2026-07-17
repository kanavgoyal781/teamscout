"""M26: ops Summary table formats values from metric names; real _render_html path."""

from __future__ import annotations

import re

from app.services.ops.html_render import _fmt_cell, _is_num_key, _render_html, _table


def _realistic_stats() -> dict:
    return {
        "latency_by_operation": {
            "rerank": {"count": 3, "p50_ms": 320.7, "p95_ms": 410.2},
            "pairwise_judge": {"count": 2, "p50_ms": 180.1, "p95_ms": 220.0},
        },
        "error_rate_by_service": {"llm": {"errors": 1, "total": 10, "error_rate": 0.1}},
        "recent_traces": [
            {
                "created_at": "2026-07-16T12:00:00",
                "operation": "rerank",
                "status": "ok",
                "latency_ms": 120.4,
                "cost_usd": 0.0123,
                "credits_used": None,
                "prompt_name": "rerank",
                "prompt_version": "1",
                "cache_hit": False,
                "error_type": None,
                "request_id": "r1",
            }
        ],
        "total_cost_today_usd": 1.234,
        "llm_cost_today_usd": 1.234,
        "llm_ceiling_usd": 5.0,
        "sumble_credits_today": 12,
        "sumble_ceiling": 1000,
        "cost_per_feature1_run_usd": 0.4567,
        "feature1_runs_today": 3,
        "cost_per_feature2_run_usd": 0.1,
        "feature2_runs_today": 4,
        "embedding_cache_hit_rate": 0.55,
        "embedding_cache_hits": 11,
        "embedding_cache_total": 20,
        "workspace_llm_ceiling_usd": 1.0,
        "workspace_sumble_ceiling": 100,
        "workspace_usage_today": [{"workspace_id": "w1", "llm_cost_usd": 0.5, "sumble_credits": 2}],
        "learning": {"evals_root": "/evals", "feedback_counts": {"thumbs_up": 2}, "suites": [], "experiments": []},
        "job_sources": [{"source": "jsearch", "calls": 5, "p50_ms": 90.2, "p95_ms": 120.0, "error_rate": 0.0}],
        "judge_agreement_mean_today": 0.6667,
        "judge_agreement_samples_today": 3,
        "m24_panel": "models=(single)",
    }


def test_fmt_cell_uses_metric_name_keys() -> None:
    assert _fmt_cell("llm_cost_today_usd", 1.234) == "1.23"
    assert _fmt_cell("p50_ms", 320.7) == "321"
    assert _fmt_cell("feature2_runs_today", 4.0) == "4"
    assert _is_num_key("llm_cost_today_usd")
    assert not _is_num_key("metric")


def test_summary_kv_table_value_cells_num_and_2dp() -> None:
    rows = [
        ["llm_cost_today_usd", 1.234],
        ["feature2_runs_today", 4],
        ["p50_ms", 320.7],  # not a real summary key but proves ms formatting via col0
    ]
    html = _table(["metric", "value"], rows)
    assert 'class="num">1.23</td>' in html
    assert 'class="num">4</td>' in html
    assert 'class="num">321</td>' in html
    # metric names are not num class
    assert re.search(r"<td>llm_cost_today_usd</td>", html)


def test_render_html_summary_craft_from_real_path() -> None:
    html = _render_html(_realistic_stats())
    assert "ops-table" in html and "setOpsTheme" in html
    assert "F7F4ED" in html and "0A182E" in html
    # Summary section includes formatted cost from metric name
    assert "llm_cost_today_usd" in html
    assert re.search(r"llm_cost_today_usd</td><td class=\"num\">1\.23</td>", html)
    assert re.search(r"feature2_runs_today</td><td class=\"num\">4</td>", html)
    # Latency table still formats via column headers
    assert re.search(r"<td class=\"num\">321</td>", html)  # p50 rounded
    assert "theme-bar" in html
