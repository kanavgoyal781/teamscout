"""M21-D: secret redaction + Drive per-file resilience."""

from __future__ import annotations

import logging
from unittest.mock import patch

import httpx
import pytest
import respx
from app.core.config import settings
from app.core.redact import drive_user_reason, format_httpx_error, redact_error
from app.errors import ServiceFailingError
from app.services.library import drive as drive_mod
from fastapi.testclient import TestClient


SECRET_KEY = "AIzaSyDummyTestKey_NOT_REAL_1234567890"
KEY_URL = (
    f"https://www.googleapis.com/drive/v3/files/file-secret"
    f"?alt=media&key={SECRET_KEY}"
)


def test_redact_error_strips_query_keys_and_aiza_and_bearer() -> None:
    raw = (
        f'Client error \'403 Forbidden\' for url \'{KEY_URL}\' '
        f"Authorization: Bearer ya29.secret-token-value"
    )
    safe = redact_error(raw)
    assert "key=" not in safe.lower() or "key=[REDACTED]" in safe.lower()
    assert SECRET_KEY not in safe
    assert "AIza" not in safe
    assert "ya29.secret-token-value" not in safe
    assert "Bearer [REDACTED]" in safe or "Bearer" not in safe
    assert "www.googleapis.com" in safe
    assert "alt=media" not in safe  # query stripped from URL


def test_format_httpx_error_host_status_only() -> None:
    request = httpx.Request("GET", KEY_URL)
    response = httpx.Response(403, request=request, text="Forbidden")
    exc = httpx.HTTPStatusError("403", request=request, response=response)
    msg = format_httpx_error(exc)
    assert "403" in msg
    assert "www.googleapis.com" in msg
    assert "key=" not in msg
    assert SECRET_KEY not in msg
    assert "AIza" not in msg


def test_service_failing_error_auto_redacts_reason() -> None:
    err = ServiceFailingError("Google Drive", f"Client error for url '{KEY_URL}'")
    assert SECRET_KEY not in err.message
    assert "AIza" not in err.message
    assert "key=" not in err.message or "key=[REDACTED]" in err.message
    assert SECRET_KEY not in str(err.details)


def test_drive_user_reason_403_plain_language() -> None:
    request = httpx.Request("GET", KEY_URL)
    response = httpx.Response(403, request=request)
    exc = httpx.HTTPStatusError("403", request=request, response=response)
    reason = drive_user_reason(exc, status_code=403)
    assert "Anyone with the link" in reason
    assert SECRET_KEY not in reason


@respx.mock
def test_drive_download_403_raises_redacted_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", SECRET_KEY)
    route = respx.get("https://www.googleapis.com/drive/v3/files/file-1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    with pytest.raises(ServiceFailingError) as ei:
        drive_mod.download_file("file-1")
    assert route.called
    msg = ei.value.message
    assert "403" in msg or "Forbidden" in msg or "Google Drive" in msg
    assert SECRET_KEY not in msg
    assert "AIza" not in msg
    assert "key=" not in msg


@respx.mock
def test_drive_sync_403_api_response_and_logs_have_no_secrets(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Live regression: per-file 403 must not toast a raw googleapis URL with key."""
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", SECRET_KEY)
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "ok-file",
                        "name": "good.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                    {
                        "id": "blocked-file",
                        "name": "private.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                    {
                        "id": "gdoc-1",
                        "name": "Notes",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                ]
            },
        )
    )
    respx.get("https://www.googleapis.com/drive/v3/files/ok-file").mock(
        return_value=httpx.Response(200, content=b"%PDF good")
    )
    respx.get("https://www.googleapis.com/drive/v3/files/blocked-file").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )

    profile = __import__("app.schemas.resume", fromlist=["ResumeProfile"]).ResumeProfile(
        name="J",
        title="Eng",
        years_of_experience=3,
        location="R",
        skills=["Go"],
        work_experience=[],
        summary="s",
    )

    with caplog.at_level(logging.WARNING):
        with patch(
            "app.services.library.store.ingest_resume_bytes",
            return_value=(
                __import__("app.schemas.library", fromlist=["LibraryResumeOut"]).LibraryResumeOut(
                    id="r1",
                    filename="good.pdf",
                    content_hash="h-good",
                    source="drive",
                    profile=profile,
                    created_at=None,
                ),
                True,
            ),
        ):
            response = client.post(
                "/library/drive/sync",
                json={"folder_url": "https://drive.google.com/drive/folders/folder-secret"},
            )

    assert response.status_code == 200, response.text
    body = response.json()
    blob = response.text
    assert SECRET_KEY not in blob
    assert "AIza" not in blob
    assert "key=" not in blob.lower() or "key=[redacted]" in blob.lower()
    assert "Bearer" not in blob or "Bearer [REDACTED]" in blob

    # Sync continued: one parsed, failures recorded (403 + native Google Doc)
    assert body["files_parsed"] == 1
    assert body["files_failed"] >= 2
    failed = [fr for fr in body["file_results"] if fr["status"] == "failed"]
    reasons = " ".join(fr.get("reason") or "" for fr in failed)
    assert "Anyone with the link" in reasons
    assert "Google Docs format" in reasons or "PDF" in reasons
    for fr in failed:
        assert SECRET_KEY not in (fr.get("reason") or "")
        assert "AIza" not in (fr.get("reason") or "")
        assert "googleapis.com/drive" not in (fr.get("reason") or "")

    log_blob = " ".join(r.message for r in caplog.records) + " " + " ".join(
        str(getattr(r, "error", "")) for r in caplog.records
    )
    # Caplog may not expand structlog kwargs — also check getMessage
    full_log = "\n".join(r.getMessage() for r in caplog.records)
    combined = log_blob + "\n" + full_log + "\n" + str(caplog.text)
    assert SECRET_KEY not in combined
    assert "AIzaSyDummyTestKey" not in combined


@respx.mock
def test_drive_list_skips_native_google_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", "drive-test-key")
    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "pdf-1",
                        "name": "r.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                    {
                        "id": "doc-1",
                        "name": "Resume Draft",
                        "mimeType": "application/vnd.google-apps.document",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                ]
            },
        )
    )
    result = drive_mod.list_folder_files("folder-1")
    assert len(result.supported_files) == 1
    assert result.supported_files[0].name == "r.pdf"
    assert len(result.skipped_native) == 1
    assert "PDF" in result.skipped_native[0].reason
