"""Public GET /stats — safe aggregates only."""

from __future__ import annotations

import json

from app.api.routers.stats import clear_public_stats_cache
from app.db.models import JobTeamSearch, Resume, Search, Trace
from app.db.session import SessionLocal
from fastapi.testclient import TestClient


def test_stats_shape(client: TestClient) -> None:
    clear_public_stats_cache()
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "jobs_ranked_total",
        "resumes_parsed_total",
        "teams_discovered_total",
        "median_rank_latency_ms",
        "total_llm_cost_usd",
    }
    assert isinstance(body["jobs_ranked_total"], int)
    assert isinstance(body["resumes_parsed_total"], int)
    assert isinstance(body["teams_discovered_total"], int)
    assert body["total_llm_cost_usd"] >= 0


def test_stats_jobs_ranked_sums_result_lengths(client: TestClient) -> None:
    """jobs_ranked_total = sum of ranked results, not search row count."""
    clear_public_stats_cache()
    before = client.get("/stats").json()["jobs_ranked_total"]

    db = SessionLocal()
    try:
        db.add(
            Search(
                resume_id="r-stats",
                label="q",
                query_json="{}",
                results_json=json.dumps([{"job": {"id": "a"}}, {"job": {"id": "b"}}, {"job": {"id": "c"}}]),
            )
        )
        db.add(
            Search(
                resume_id="r-stats-2",
                label="q2",
                query_json="{}",
                results_json=json.dumps([{"job": {"id": "d"}}]),
            )
        )
        # empty array contributes 0
        db.add(Search(resume_id="r-empty", label="e", query_json="{}", results_json="[]"))
        db.commit()
    finally:
        db.close()

    clear_public_stats_cache()
    after = client.get("/stats").json()["jobs_ranked_total"]
    assert after == before + 4


def test_stats_median_rerank_only(client: TestClient) -> None:
    """jsearch latencies must not move median_rank_latency_ms."""
    clear_public_stats_cache()
    db = SessionLocal()
    try:
        db.add(Trace(operation="rerank", latency_ms=100.0, cost_usd=0.01, status="ok"))
        db.add(Trace(operation="rerank", latency_ms=200.0, cost_usd=0.01, status="ok"))
        db.add(Trace(operation="rerank", latency_ms=300.0, cost_usd=0.01, status="ok"))
        # huge jsearch should be ignored
        db.add(Trace(operation="jsearch.search", latency_ms=99999.0, cost_usd=0.0, status="ok"))
        db.commit()
    finally:
        db.close()
    clear_public_stats_cache()
    med = client.get("/stats").json()["median_rank_latency_ms"]
    assert med == 200.0


def test_stats_aggregates_and_cache(client: TestClient) -> None:
    clear_public_stats_cache()
    before = client.get("/stats").json()

    db = SessionLocal()
    try:
        db.add(Resume(filename="a.pdf", content_hash="stats-h-a2", confirmed=True, source="upload"))
        db.add(Resume(filename="b.pdf", content_hash="stats-h-b2", confirmed=False, source="upload"))
        db.add(
            JobTeamSearch(
                job_id="stats-j2",
                extraction_id="e2",
                search_id=None,
                credits_used=0,
                search_path="Matched posted role",
            )
        )
        db.add(Trace(operation="rerank", latency_ms=50.0, cost_usd=0.02, status="ok"))
        db.commit()
    finally:
        db.close()

    r_cached = client.get("/stats")
    assert r_cached.json()["resumes_parsed_total"] == before["resumes_parsed_total"]

    clear_public_stats_cache()
    after = client.get("/stats").json()
    assert after["resumes_parsed_total"] == before["resumes_parsed_total"] + 2
    assert after["teams_discovered_total"] == before["teams_discovered_total"] + 1
    assert after["total_llm_cost_usd"] >= before["total_llm_cost_usd"] + 0.02 - 1e-9


def test_stats_has_no_sensitive_keys(client: TestClient) -> None:
    clear_public_stats_cache()
    body = client.get("/stats").json()
    forbidden = {
        "recent_traces",
        "request_id",
        "ops",
        "token",
        "api_key",
        "email",
        "full_name",
        "sumble",
        "prompt_hash",
    }
    assert forbidden.isdisjoint(body.keys())


def test_stats_response_model_forbids_extra(client: TestClient) -> None:
    clear_public_stats_cache()
    body = client.get("/stats").json()
    # FastAPI response_model strips extras; only whitelist remains
    assert len(body) == 5
