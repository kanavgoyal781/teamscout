"""Rate-limit and request-id hardening tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.request_id import sanitize_request_id
from app.schemas.resume import ResumeProfile
from fastapi.testclient import TestClient


@pytest.fixture
def limited_client(client: TestClient) -> TestClient:
    """Enable limiter with very low upload quota for this test module."""
    previous_enabled = limiter.enabled
    previous_limit = settings.RATE_LIMIT_UPLOAD
    limiter.enabled = True
    settings.RATE_LIMIT_UPLOAD = "2/minute"
    limiter.reset()
    try:
        yield client
    finally:
        limiter.enabled = previous_enabled
        settings.RATE_LIMIT_UPLOAD = previous_limit
        limiter.reset()


def test_request_id_header_echoed(client: TestClient) -> None:
    response = client.get("/health")
    assert "x-request-id" in response.headers
    rid = response.headers["x-request-id"]
    assert len(rid) >= 8
    # Single header value (not "a, a" from duplicates)
    assert "," not in rid


def test_request_id_client_supplied(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-rid-123"})
    assert response.headers["x-request-id"] == "test-rid-123"


def test_request_id_rejects_crlf_injection(client: TestClient) -> None:
    evil = "abc\r\nX-Evil: 1"
    response = client.get("/health", headers={"X-Request-ID": evil})
    rid = response.headers["x-request-id"]
    assert "\r" not in rid
    assert "\n" not in rid
    assert "X-Evil" not in rid
    assert rid != evil
    # Sanitizer replaced with a UUID
    assert len(rid) >= 32


def test_sanitize_request_id_unit() -> None:
    assert sanitize_request_id("ok-id_1.2") == "ok-id_1.2"
    assert "\r" not in sanitize_request_id("a\r\nb")
    assert sanitize_request_id("") != ""
    assert sanitize_request_id("x" * 200) != "x" * 200
    assert sanitize_request_id("has space") != "has space"


def test_health_includes_version(client: TestClient) -> None:
    response = client.get("/health")
    payload = response.json()
    assert "version" in payload
    assert isinstance(payload["version"], str)
    assert payload["version"]


def test_upload_rate_limit_returns_429(limited_client: TestClient) -> None:
    from tests.conftest import SAMPLE_PDF

    profile = ResumeProfile(
        name="Jane Doe",
        title="Engineer",
        years_of_experience=5,
        location="Remote",
        skills=["Python"],
        work_experience=[],
        summary="x",
    )
    pdf = SAMPLE_PDF.read_bytes()

    statuses: list[int] = []
    with patch(
        "app.api.routers.resumes.parser.parse_resume_file",
        side_effect=lambda name, data: (f"hash-{len(statuses)}", profile),
    ):
        for i in range(4):
            resp = limited_client.post(
                "/resumes/upload",
                files={"file": (f"resume-{i}.pdf", pdf, "application/pdf")},
            )
            statuses.append(resp.status_code)

    assert 429 in statuses, f"expected a 429 among {statuses}"
    # Single X-Request-ID on 429 (middleware sole owner)
    body = limited_client.post(
        "/resumes/upload",
        files={"file": ("resume-x.pdf", pdf, "application/pdf")},
    )
    if body.status_code == 429:
        payload = body.json()
        assert payload["error"] == "rate_limit_exceeded"
        assert "Traceback" not in str(payload)
        rid = body.headers.get("x-request-id", "")
        assert rid
        assert "," not in rid


def test_llm_route_rate_limit_extract_team(client: TestClient) -> None:
    """extract-team is rate-limited (expensive LLM path)."""
    previous_enabled = limiter.enabled
    previous_limit = settings.RATE_LIMIT_LLM
    limiter.enabled = True
    settings.RATE_LIMIT_LLM = "2/minute"
    limiter.reset()
    try:
        statuses: list[int] = []
        with patch(
            "app.api.routers.jobs.resolve_job",
            side_effect=Exception("should not reach if limited first — or may hit 503/404"),
        ):
            # Call without mock first — will fail job resolve, but still counts toward limit
            pass
        with patch("app.api.routers.jobs.resolve_job") as resolve:
            from app.schemas.jobs import Job

            job = Job(
                id="j1",
                source="t",
                source_job_id="s1",
                title="Eng",
                company="C",
                location="Remote",
                description="d",
                apply_url="https://example.com",
                posted_at=None,
                skills=[],
            )
            resolve.return_value = job
            from app.schemas.team import TeamExtraction

            with patch(
                "app.api.routers.jobs.team_extract.extract_team_from_job",
                return_value=TeamExtraction(
                    team_name="Engineering",
                    department="Product",
                    likely_hiring_titles=["Engineer"],
                ),
            ):
                for _ in range(4):
                    resp = client.post("/jobs/j1/extract-team")
                    statuses.append(resp.status_code)
        assert 429 in statuses, f"expected 429 among {statuses}"
    finally:
        limiter.enabled = previous_enabled
        settings.RATE_LIMIT_LLM = previous_limit
        limiter.reset()


def test_content_length_over_limit_returns_413(client: TestClient) -> None:
    from app.core.config import settings as cfg

    previous = cfg.MAX_UPLOAD_BYTES
    cfg.MAX_UPLOAD_BYTES = 100
    try:
        resp = client.post(
            "/resumes/upload",
            files={"file": ("big.pdf", b"x" * 200, "application/pdf")},
            headers={"Content-Length": "200"},
        )
        assert resp.status_code == 413
        payload = resp.json()
        assert payload["error"] == "payload_too_large"
    finally:
        cfg.MAX_UPLOAD_BYTES = previous


def test_upload_body_over_limit_returns_400(client: TestClient) -> None:
    from app.core.config import settings as cfg

    previous = cfg.MAX_UPLOAD_BYTES
    cfg.MAX_UPLOAD_BYTES = 50
    try:
        from app.core.upload_limit import enforce_upload_size
        from app.errors import ValidationError

        with pytest.raises(ValidationError):
            enforce_upload_size(b"x" * 100)
    finally:
        cfg.MAX_UPLOAD_BYTES = previous


def test_unhandled_exception_no_stack_leak() -> None:
    """Generic 500 JSON for unhandled errors (no secrets/stack in body).

    Starlette ServerErrorMiddleware re-raises after the Exception handler so
    servers can log; use raise_server_exceptions=False to inspect the body.
    """
    from app.db.session import init_db
    from app.main import app

    @app.get("/__test_boom")
    async def _boom() -> None:
        raise RuntimeError("secret-key-material-xyz")

    init_db()
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/__test_boom")
        assert resp.status_code == 500
        payload = resp.json()
        assert payload["error"] == "internal_error"
        assert "secret-key-material-xyz" not in str(payload)
        assert "Traceback" not in str(payload)
        rid = resp.headers.get("x-request-id", "")
        assert rid
        assert "," not in rid
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom"]
