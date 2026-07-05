import os
from collections.abc import Generator
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

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
):
    os.environ.pop(key, None)

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


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app.db.session import init_db

    init_db()
    with TestClient(app) as test_client:
        yield test_client