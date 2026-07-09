import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.main import teamscout_error_handler
from app.services import embeddings, llm
from pydantic import BaseModel
from starlette.requests import Request


class _SampleModel(BaseModel):
    name: str
    score: int


def test_llm_missing_key_returns_503_style_error() -> None:
    with pytest.raises(ServiceNotConfiguredError) as exc:
        llm.complete("hello")

    assert exc.value.status_code == 503
    assert "LLM API not configured" in exc.value.message
    assert exc.value.error_code == "service_not_configured"


def test_embeddings_missing_key_returns_503_style_error() -> None:
    with pytest.raises(ServiceNotConfiguredError) as exc:
        embeddings.embed("hello")

    assert exc.value.status_code == 503
    assert "Embeddings API not configured" in exc.value.message
    assert exc.value.error_code == "service_not_configured"


def test_service_not_configured_error_serializes_cleanly() -> None:
    exc = ServiceNotConfiguredError("Embeddings", "EMBEDDINGS_API_KEY")

    assert exc.status_code == 503
    assert exc.error_code == "service_not_configured"
    assert exc.message == "Embeddings API not configured — set EMBEDDINGS_API_KEY"
    assert exc.details["env_var"] == "EMBEDDINGS_API_KEY"


def test_llm_whitespace_key_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "   ")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")

    with pytest.raises(ServiceNotConfiguredError):
        llm.complete("hello")


def test_llm_http_error_raises_service_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("app.services.llm.httpx.Client", return_value=mock_client):
        with pytest.raises(ServiceFailingError) as exc:
            llm.complete("hello")

    assert exc.value.status_code == 503
    assert exc.value.error_code == "service_failing"
    assert "connection refused" in exc.value.message


def test_embeddings_http_error_raises_service_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDINGS_API", "https://api.example.com/v1/embeddings")

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.side_effect = httpx.ConnectError("connection refused")

    with patch("app.services.embeddings.httpx.Client", return_value=mock_client):
        with pytest.raises(ServiceFailingError) as exc:
            embeddings.embed("hello")

    assert exc.value.status_code == 503
    assert exc.value.error_code == "service_failing"


def test_complete_json_retries_once_on_schema_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")

    responses = iter(["not json", '{"name": "alice", "score": 7}'])
    with patch("app.services.llm.complete", side_effect=lambda *_args, **_kwargs: next(responses)) as mocked:
        result = llm.complete_json('{"name":"alice","score":7}', _SampleModel)

    assert mocked.call_count == 2
    assert result.name == "alice"
    assert result.score == 7


def test_complete_json_raises_after_retry_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")

    with patch("app.services.llm.complete", return_value="still not json"):
        with pytest.raises(ServiceFailingError) as exc:
            llm.complete_json('{"name":"alice","score":7}', _SampleModel)

    assert "invalid JSON schema" in exc.value.message


@pytest.mark.asyncio
async def test_teamscout_error_handler_returns_clean_json() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    exc = ServiceNotConfiguredError("LLM", "LLM_API_KEY")

    response = await teamscout_error_handler(request, exc)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["error"] == "service_not_configured"
    assert payload["message"] == "LLM API not configured — set LLM_API_KEY"
    assert payload["details"]["env_var"] == "LLM_API_KEY"


def test_loads_llm_json_repairs_trailing_comma() -> None:
    raw = '{"results": [{"job_id": "a", "fit_score": 80, "matched_skills": [], "missing_skills": [], "rationale": "ok"},]}'
    payload = llm._loads_llm_json(raw)
    assert payload["results"][0]["job_id"] == "a"


def test_loads_llm_json_salvages_truncated_results() -> None:
    # Truncated mid-second object (classic max_tokens cut)
    raw = (
        '{"results": ['
        '{"job_id": "j1", "fit_score": 90, "matched_skills": ["Python"], '
        '"missing_skills": [], "rationale": "good fit"}, '
        '{"job_id": "j2", "fit_score": 40, "matched_skills": ["Go"], '
        '"missing_skills": ["Rust"], "rationale": "partial'
    )
    payload = llm._loads_llm_json(raw)
    assert len(payload["results"]) == 1
    assert payload["results"][0]["job_id"] == "j1"


def test_loads_llm_json_reads_fenced_block() -> None:
    raw = 'Here you go:\n```json\n{"name": "x", "score": 1}\n```\n'
    payload = llm._loads_llm_json(raw)
    assert payload == {"name": "x", "score": 1}
