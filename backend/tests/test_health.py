import pytest
from fastapi.testclient import TestClient


def test_health_reports_missing_when_unconfigured(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["db"] is True
    for service in ("llm", "embeddings", "jobs_api", "sumble"):
        assert payload["checks"][service] == "missing"
    assert payload["checks"]["google_drive"] == "missing"
    assert "google_drive" in payload["optional_checks"]


def test_health_ok_with_required_only_drive_optional(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-llm")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "test-embed")
    monkeypatch.setattr(settings, "EMBEDDINGS_API", "https://api.example.com/v1/embeddings")
    monkeypatch.setattr(settings, "JOBS_API_KEY", "test-jobs")
    monkeypatch.setattr(settings, "JOBS_API_BASE", "https://jobs.example.com")
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-sumble")
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_REFRESH_TOKEN", None)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["checks"]["google_drive"] == "missing"
    for service in ("llm", "embeddings", "jobs_api", "sumble"):
        assert payload["checks"][service] == "configured"


def test_health_ok_when_fully_configured(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "test-llm")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "EMBEDDINGS_API_KEY", "test-embed")
    monkeypatch.setattr(settings, "EMBEDDINGS_API", "https://api.example.com/v1/embeddings")
    monkeypatch.setattr(settings, "JOBS_API_KEY", "test-jobs")
    monkeypatch.setattr(settings, "JOBS_API_BASE", "https://jobs.example.com")
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-sumble")
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", "drive-key")

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert all(status == "configured" for status in payload["checks"].values())


def test_health_reports_db_failure(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr("app.services.health.ping_db", lambda: False)

    response = client.get("/health")
    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["db"] is False


def test_health_treats_whitespace_keys_as_missing(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "   ")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://api.example.com/v1")

    response = client.get("/health")
    assert response.json()["checks"]["llm"] == "missing"