"""M8: traces, cost ceilings, embedding cache, ops auth, prompt registry."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import EmbeddingCache, Trace
from app.db.session import SessionLocal
from app.errors import CostCeilingExceededError
from app.prompts import load_prompt
from app.services import embeddings, llm, observability, sumble, sumble_client


def _clear_traces() -> None:
    db = SessionLocal()
    try:
        db.query(Trace).delete()
        db.query(EmbeddingCache).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean_traces() -> None:
    _clear_traces()
    yield
    _clear_traces()


def test_load_prompt_returns_metadata_and_hash() -> None:
    tmpl = load_prompt("resume_schema")
    assert tmpl.name == "resume_schema"
    assert tmpl.version == "1"
    assert tmpl.body
    assert len(tmpl.content_hash) == 16
    assert "Extract a structured resume profile" in tmpl.body
    expected_hash = hashlib.sha256(tmpl.body.encode("utf-8")).hexdigest()[:16]
    assert tmpl.content_hash == expected_hash
    assert load_prompt("resume_schema").content_hash == tmpl.content_hash


def test_load_prompt_rerank_justify_team() -> None:
    for name in ("rerank", "justify", "team_extract"):
        tmpl = load_prompt(name)
        assert tmpl.name == name
        assert tmpl.version
        assert tmpl.content_hash


def test_load_prompt_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist_prompt_xyz")


def test_load_prompt_rejects_bad_frontmatter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.prompts as prompts_mod

    monkeypatch.setattr(prompts_mod, "_PROMPTS_DIR", tmp_path)
    prompts_mod.load_prompt.cache_clear()

    (tmp_path / "no_fm.md").write_text("no frontmatter here\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        load_prompt("no_fm")

    (tmp_path / "no_version.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError, match="name and version"):
        load_prompt("no_version")

    prompts_mod.load_prompt.cache_clear()


def test_llm_trace_written_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "LLM_DAILY_COST_CEILING_USD", 100.0)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )

    with patch("app.services.llm.httpx.Client", return_value=mock_client):
        out = llm.complete("hi", operation="parse_resume")

    assert out == "hello"
    db = SessionLocal()
    try:
        rows = db.query(Trace).filter(Trace.operation == "parse_resume").all()
        assert len(rows) == 1
        assert rows[0].status == "ok"
        assert rows[0].input_tokens == 10
        assert rows[0].output_tokens == 5
        assert rows[0].cost_usd is not None and rows[0].cost_usd > 0
        assert rows[0].model
    finally:
        db.close()


def test_llm_daily_ceiling_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "LLM_DAILY_COST_CEILING_USD", 0.000001)

    db = SessionLocal()
    try:
        db.add(
            Trace(
                operation="parse_resume",
                cost_usd=1.0,
                status="ok",
            )
        )
        db.commit()
    finally:
        db.close()

    with pytest.raises(CostCeilingExceededError) as exc:
        llm.complete("hi", operation="parse_resume")
    assert exc.value.status_code == 429
    assert exc.value.error_code == "cost_ceiling_exceeded"


def test_llm_ceiling_uses_full_max_tokens_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Worst-case preflight (output_tokens=max_tokens) must block near-ceiling spend.

    Old max_tokens//4 estimate would under-count and allow a call that can still
    bill the full max_tokens budget and overshoot the daily ceiling.
    """
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "LLM_PRICE_INPUT_PER_1M", 0.0)
    monkeypatch.setattr(settings, "LLM_PRICE_OUTPUT_PER_1M", 1.0)  # $1 per 1M out tokens

    max_tokens = 4000
    # Worst-case cost for empty-ish prompt: ~0 + max_tokens/1e6 * $1
    worst = observability.estimate_llm_cost_usd(
        model=settings.LLM_MODEL, input_tokens=1, output_tokens=max_tokens
    )
    optimistic = observability.estimate_llm_cost_usd(
        model=settings.LLM_MODEL, input_tokens=1, output_tokens=max_tokens // 4
    )
    assert worst > optimistic

    # Remaining budget is between optimistic and worst-case → must deny under fail-closed policy.
    ceiling = worst - 1e-12
    spent = 0.0
    monkeypatch.setattr(settings, "LLM_DAILY_COST_CEILING_USD", ceiling)
    # no prior spend rows
    with pytest.raises(CostCeilingExceededError) as exc:
        llm.complete("x", operation="rerank", max_tokens=max_tokens)
    assert exc.value.status_code == 429
    _ = spent


def test_sumble_daily_credit_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "SUMBLE_DAILY_CREDIT_CEILING", 5)

    db = SessionLocal()
    try:
        db.add(Trace(operation="sumble.people", credits_used=5, status="ok"))
        db.commit()
    finally:
        db.close()

    with pytest.raises(CostCeilingExceededError) as exc:
        sumble_client.post("/v6/people", {"mode": "filter"})
    assert exc.value.status_code == 429


def test_sumble_email_reveal_operation_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "SUMBLE_DAILY_CREDIT_CEILING", 100000)
    monkeypatch.setattr(settings, "SUMBLE_BASE_URL", "https://api.sumble.test")

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = httpx.Response(
        200,
        json={
            "people": [{"attributes": {"email": "a@example.com"}}],
            "credits_used": 10,
        },
        request=httpx.Request("POST", "https://api.sumble.test/v6/people"),
    )

    with patch("app.services.sumble_client.httpx.Client", return_value=mock_client):
        email, credits = sumble.reveal_email(42)

    assert email == "a@example.com"
    assert credits == 10
    db = SessionLocal()
    try:
        rows = db.query(Trace).filter(Trace.operation == "sumble.email_reveal").all()
        assert len(rows) == 1
        assert rows[0].credits_used == 10
        assert rows[0].status == "ok"
        # people search must not be mis-labeled as email_reveal by default path map
        assert observability.sumble_operation_from_path("/v6/people") == "sumble.people"
    finally:
        db.close()


def test_embedding_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDINGS_API", "https://api.example.com/v1/embeddings")
    monkeypatch.setattr(settings, "LLM_DAILY_COST_CEILING_USD", 100.0)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = httpx.Response(
        200,
        json={"data": [{"embedding": [0.0, 1.0, 0.0], "index": 0}]},
        request=httpx.Request("POST", "https://api.example.com/v1/embeddings"),
    )

    with patch("app.services.embeddings.httpx.Client", return_value=mock_client):
        v1 = embeddings.embed("cache me please")
        v2 = embeddings.embed("cache me please")

    assert v1 == v2
    assert mock_client.post.call_count == 1
    db = SessionLocal()
    try:
        rows = db.query(Trace).filter(Trace.operation == "embed").order_by(Trace.created_at).all()
        assert len(rows) >= 2
        assert any(r.cache_hit for r in rows)
        assert any(not r.cache_hit for r in rows)
    finally:
        db.close()


def test_ops_denied_without_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPS_TOKEN", None)
    resp = client.get("/ops")
    assert resp.status_code == 401
    monkeypatch.setattr(settings, "OPS_TOKEN", "")
    resp2 = client.get("/ops", params={"token": "anything"})
    assert resp2.status_code == 401


def test_ops_denied_wrong_token(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPS_TOKEN", "secret-ops")
    resp = client.get("/ops", params={"token": "wrong"})
    assert resp.status_code == 401
    resp2 = client.get("/ops")
    assert resp2.status_code == 401


def test_ops_shows_numbers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OPS_TOKEN", "secret-ops")
    db = SessionLocal()
    try:
        db.add(
            Trace(
                operation="rerank",
                request_id="r1",
                latency_ms=120.0,
                cost_usd=0.01,
                status="ok",
                prompt_name="rerank",
                prompt_version="1",
                prompt_hash="abc",
            )
        )
        db.add(
            Trace(
                operation="embed",
                request_id="r1",
                latency_ms=10.0,
                cost_usd=0.0,
                status="ok",
                cache_hit=True,
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/ops", params={"token": "secret-ops"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "rerank" in resp.text
    assert "embedding_cache_hit_rate" in resp.text

    resp_json = client.get("/ops/json", headers={"Authorization": "Bearer secret-ops"})
    assert resp_json.status_code == 200
    payload = resp_json.json()
    assert payload["llm_ceiling_usd"] is not None
    assert len(payload["recent_traces"]) >= 2

    resp_hdr = client.get("/ops/json", headers={"X-Ops-Token": "secret-ops"})
    assert resp_hdr.status_code == 200


def test_ops_stats_latency_percentiles() -> None:
    db = SessionLocal()
    try:
        for ms in (10.0, 20.0, 30.0, 40.0, 100.0):
            db.add(Trace(operation="jsearch.search", latency_ms=ms, status="ok"))
        db.commit()
        stats = observability.ops_stats(db)
        lat = stats["latency_by_operation"]["jsearch.search"]
        assert lat["count"] == 5
        assert lat["p50_ms"] == 30.0
        assert lat["p95_ms"] >= 40.0
    finally:
        db.close()


def test_record_trace_no_secrets_in_otlp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "https://otel.example.com")
    seen: list[dict] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    def _post(url, json=None, headers=None, **kwargs):  # noqa: ANN001
        seen.append({"url": url, "json": json, "headers": headers})
        return _Resp()

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = _post

    with patch("app.services.observability_otlp.httpx.Client", return_value=mock_client):
        observability.record_trace(operation="rerank", status="ok", cost_usd=0.01)

    assert seen
    blob = str(seen[0]["json"])
    assert "api_key" not in blob.lower()
    assert "Bearer" not in blob
