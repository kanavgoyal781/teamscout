import os
from collections.abc import Generator
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

# Force in-memory SQLite for unit tests. Must override (not setdefault): pipeline_check
# and developer shells load repo-root .env with DATABASE_URL=sqlite:///./teamscout.db,
# which would otherwise make pytest mutate the live dev DB and flake on unique constraints.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Disable rate limits for unit tests (re-enabled in test_rate_limit.py).
os.environ["RATE_LIMIT_ENABLED"] = "false"

# Force unconfigured integrations for honesty-layer tests.
# Empty env vars override repo-root .env (pydantic-settings precedence) so local
# developer keys do not mark services as "configured" during pytest.
for key in (
    "LLM_API_KEY",
    "LLM_API_BASE",
    "EMBEDDINGS_API_KEY",
    "EMBEDDINGS_API",
    "JOBS_API_KEY",
    "JOBS_API_BASE",
    "SUMBLE_API_KEY",
    "GOOGLE_DRIVE_API_KEY",
    "GOOGLE_DRIVE_CLIENT_ID",
    "GOOGLE_DRIVE_CLIENT_SECRET",
    "GOOGLE_DRIVE_REFRESH_TOKEN",
    "OPS_TOKEN",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
):
    os.environ[key] = ""

# High ceilings by default so instrumented call tests are not blocked.
os.environ.setdefault("LLM_DAILY_COST_CEILING_USD", "1000")
os.environ.setdefault("SUMBLE_DAILY_CREDIT_CEILING", "100000")

from app.main import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES / "sample_resume.pdf"
SAMPLE_RESUME_TEXT = """Jane Doe
Senior Backend Engineer
San Francisco, CA

Summary
Backend engineer with 8 years building distributed APIs and data pipelines.

Skills
Python, FastAPI, PostgreSQL, Redis, AWS, Docker, Kubernetes
"""


@pytest.fixture(scope="session", autouse=True)
def _ensure_sample_pdf() -> None:
    if SAMPLE_PDF.exists():
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), SAMPLE_RESUME_TEXT)
    doc.save(SAMPLE_PDF)
    doc.close()


@pytest.fixture(scope="session", autouse=True)
def _init_db() -> None:
    from app.db.session import init_db

    init_db()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app.db.session import init_db

    init_db()
    with TestClient(app) as test_client:
        yield test_client
