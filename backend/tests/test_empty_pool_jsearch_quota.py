"""Empty-pool is a results state; JSearch quota soft-fails; all-sources-errored stays hard."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from app.errors import ServiceFailingError
from app.schemas.jobs import Job, SearchParams, SourceCounts
from app.schemas.resume import ResumeProfile
from app.services.jobs_svc.fetch import (
    JobFetchResult,
    _merge_fetch,
    all_enabled_sources_errored,
    build_pool_notices,
    format_all_sources_failed_message,
)
from app.services.jobs_svc.jsearch import (
    JSEARCH_QUOTA_NOTICE,
    JSearchQuotaError,
    dedupe_jsearch_queries,
    jsearch_get,
)


def _profile() -> ResumeProfile:
    return ResumeProfile(name="A", title="Engineer", skills=["Python"], location="Remote")


def _job(source: str = "remotive", sid: str = "1") -> Job:
    return Job(
        id=f"id-{source}-{sid}",
        source=source,
        source_job_id=sid,
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Build APIs with Python and Postgres in production every day for years.",
        apply_url=f"https://example.com/{source}/{sid}",
        posted_at=datetime.now(UTC),
        skills=["Python"],
        remote_mode="remote",
    )


# --- message template ---


def test_service_failing_no_api_api_duplication() -> None:
    err = ServiceFailingError("Jobs API", "upstream boom")
    assert "API API" not in err.message
    assert err.message.startswith("Jobs API is failing")
    soft = ServiceFailingError("LLM", "timeout")
    assert soft.message.startswith("LLM API is failing")


def test_all_sources_failed_message_names_each() -> None:
    msg = format_all_sources_failed_message(["jsearch:boom", "remotive:timeout", "jsearch:again"])
    assert "jsearch" in msg and "remotive" in msg
    assert "All job sources failed" in msg


# --- (a) zero kept + one errored → success path helpers ---


def test_empty_pool_partial_not_all_failed() -> None:
    per = {
        "jsearch": SourceCounts(fetched=0, errors=1),
        "remotive": SourceCounts(fetched=0, kept_after_filters=0, errors=0),
    }
    errs = [f"jsearch:{JSEARCH_QUOTA_NOTICE}"]
    assert all_enabled_sources_errored(per, errs) is False
    notices, reason = build_pool_notices(
        params=SearchParams(date_window="day"),
        per_source=per,
        source_errors=errs,
        empty=True,
    )
    assert reason == "partial_sources"
    assert any("widening Posted within" in n for n in notices)
    assert any("jsearch:" in n or "fetched=" in n for n in notices)


def test_merge_fetch_empty_partial_returns_result_not_raise() -> None:
    """Fixture (a): all sources zero kept + one errored → JobFetchResult empty, no ServiceFailingError."""
    per = {
        "jsearch": SourceCounts(fetched=0, errors=1),
        "remotive": SourceCounts(fetched=0, errors=0),
    }
    errs = ["jsearch:ServiceFailingError: upstream request failed"]
    db = MagicMock()
    with patch(
        "app.services.jobs_svc.sources.fetch_from_registry",
        return_value=([], per, errs),
    ):
        with patch("app.services.inference.embeddings.embeddings_endpoint", return_value=None):
            result = _merge_fetch(
                _profile(),
                db,
                queries=["engineer"],
                params=SearchParams(date_window="day"),
            )
    assert isinstance(result, JobFetchResult)
    assert result.jobs == []
    assert result.pool_empty_reason == "partial_sources"
    assert result.pool_notices
    assert any("widening" in n.lower() or "window" in n.lower() for n in result.pool_notices)


# --- (b) jsearch 429 + boards return jobs ---


def test_merge_fetch_jsearch_quota_with_board_jobs() -> None:
    board = _job("remotive", "r1")
    per = {
        "jsearch": SourceCounts(fetched=0, errors=1),
        "remotive": SourceCounts(fetched=1, kept_after_filters=1, errors=0),
    }
    errs = [f"jsearch:{JSEARCH_QUOTA_NOTICE}"]
    db = MagicMock()
    with patch(
        "app.services.jobs_svc.sources.fetch_from_registry",
        return_value=([board], per, errs),
    ):
        with patch("app.services.inference.embeddings.embeddings_endpoint", return_value=None):
            with patch("app.services.jobs_svc.fetch._cache_jobs", side_effect=lambda _db, jobs: jobs):
                with patch("app.services.jobs_svc.fetch._assign_stable_ids", side_effect=lambda _db, jobs: jobs):
                    result = _merge_fetch(
                        _profile(),
                        db,
                        queries=["engineer"],
                        params=SearchParams(date_window="week"),
                    )
    assert len(result.jobs) >= 1
    assert result.pool_empty_reason is None
    assert any("quota" in n.lower() for n in result.pool_notices)


def test_jsearch_get_raises_quota_on_429() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "quota exceeded"
    mock_resp.raise_for_status.side_effect = Exception("should not be called after 429 check")
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp
    with patch("app.services.jobs_svc.jsearch.httpx.Client", return_value=mock_client):
        with pytest.raises(JSearchQuotaError) as ei:
            jsearch_get({"query": "engineer", "date_posted": "day"})
    assert JSEARCH_QUOTA_NOTICE in str(ei.value)


# --- (c) all sources errored ---


def test_all_sources_errored_raises_clear_error() -> None:
    per = {
        "jsearch": SourceCounts(fetched=0, errors=1),
        "remotive": SourceCounts(fetched=0, errors=1),
    }
    errs = ["jsearch:boom", "remotive:timeout"]
    assert all_enabled_sources_errored(per, errs) is True
    db = MagicMock()
    with patch(
        "app.services.jobs_svc.sources.fetch_from_registry",
        return_value=([], per, errs),
    ):
        with patch("app.services.inference.embeddings.embeddings_endpoint", return_value=None):
            with pytest.raises(ServiceFailingError) as ei:
                _merge_fetch(
                    _profile(),
                    db,
                    queries=["engineer"],
                    params=SearchParams(date_window="day"),
                )
    assert "All job sources failed" in ei.value.message
    assert "jsearch" in ei.value.message and "remotive" in ei.value.message
    assert "API API" not in ei.value.message


# --- expansion cap / dedupe ---


def test_dedupe_jsearch_queries_caps_and_collapses_near_dups() -> None:
    qs = [
        "Senior Engineer in SF",
        "senior engineer in sf",
        "Senior Engineer in San Francisco",  # may near-dup depending on overlap
        "Python Engineer remote",
        "Python engineer Remote!",
        "Data Scientist NYC",
        "ML Engineer Austin",
        "Backend Go Engineer",
    ]
    out = dedupe_jsearch_queries(qs, max_n=4)
    assert len(out) <= 4
    norms = [q.lower() for q in out]
    assert len(norms) == len(set(norms))


def test_grep_kill_api_api_in_error_module() -> None:
    from pathlib import Path

    text = Path("app/errors.py").read_text()
    # Template must not concatenate bare 'API' after service that may already end with API
    assert 'f"{service} API is failing' not in text
    assert "_service_label" in text


def test_fetch_jsearch_raw_concurrent_cache_with_real_session() -> None:
    """Honest concurrency: ≥2 queries + real SessionLocal cache must not raise InvalidRequestError.

    Reproduces the shared-session bug: workers must each open SessionLocal, not share ``db``.
    """
    from app.core import workspace as ws_mod
    from app.db.session import SessionLocal, init_db
    from app.services.jobs_svc.jsearch import fetch_jsearch_raw

    init_db()
    db = SessionLocal()
    token = ws_mod._workspace_cv.set("ws-jsearch-concurrent-cache")
    sessions_opened: list[int] = []

    def make_resp(query: str):
        r = MagicMock()
        r.status_code = 200
        r.text = "{}"
        r.raise_for_status = MagicMock()
        r.json.return_value = {
            "data": {
                "jobs": [
                    {
                        "job_id": f"jid-{query}",
                        "job_title": f"Engineer {query}",
                        "job_description": "Build production APIs with Python and Postgres every day.",
                        "job_apply_link": f"https://example.com/j/{hash(query) & 0xFFFF}",
                        "employer_name": "Acme",
                    }
                ]
            }
        }
        return r

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = lambda url, headers=None, params=None: make_resp((params or {}).get("query", "x"))

    real_session_local = SessionLocal

    def counting_session_local(*a, **k):
        s = real_session_local(*a, **k)
        sessions_opened.append(id(s))
        return s

    try:
        with patch("app.services.jobs_svc.jsearch.httpx.Client", return_value=mock_client):
            with patch("app.db.session.SessionLocal", side_effect=counting_session_local):
                with patch("app.services.ops.observability.record_trace"):
                    # Pass shared db (old bug path); workers must ignore it for cache.
                    items, failed, n_req = fetch_jsearch_raw(
                        [
                            "Python Engineer remote",
                            "Data Scientist New York",
                            "Backend Go Engineer Austin",
                        ],
                        base_params={"date_posted": "week"},
                        db=db,
                    )
        assert failed == 0, "HTTP mocks succeeded — failures would mean cache/session crash"
        assert n_req >= 2
        assert len(items) >= 2
        # Per-worker sessions: get+set for each query ⇒ multiple SessionLocal opens
        assert len(sessions_opened) >= 2
        # Second search hits cache path under concurrency without InvalidRequestError
        with patch("app.services.jobs_svc.jsearch.httpx.Client", return_value=mock_client):
            with patch("app.services.ops.observability.record_trace"):
                items2, failed2, _ = fetch_jsearch_raw(
                    ["Python Engineer remote", "Data Scientist New York"],
                    base_params={"date_posted": "week"},
                    db=db,
                )
        assert failed2 == 0
        assert len(items2) >= 1
    finally:
        ws_mod._workspace_cv.reset(token)
        db.close()
