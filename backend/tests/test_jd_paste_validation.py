"""Pasted JD pre-flight: user-input 422, zero LLM for chrome; real short JD passes."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.core import workspace as ws_mod
from app.db.session import SessionLocal, init_db
from app.errors import ValidationError
from app.schemas.jobs import Job
from app.services.jobs_svc import jd_metadata as jd_meta_mod
from app.services.jobs_svc.store import cache_pasted_job
from app.services.resume.jd_decompose import (
    JD_NOT_POSTING_MSG,
    assert_pasted_jd_looks_valid,
    decompose_jd,
    looks_like_job_description,
)
from fastapi.testclient import TestClient

# Literal fixture from product brief — match-widget chrome, not a posting.
JUNK_PASTE = "64% / Resume Match / 7 of 11 keywords / Simplify / V1 / V2"

REAL_STARTUP_JD = (
    "We are hiring a Founding Engineer at Northwind Labs. "
    "You will own our API layer and ship product with the founding team. "
    "Requirements: Python, Postgres, and three years building production systems."
)


def test_junk_chrome_rejected_by_looks_like() -> None:
    assert looks_like_job_description(JUNK_PASTE) is False
    with pytest.raises(ValidationError) as ei:
        assert_pasted_jd_looks_valid(JUNK_PASTE)
    assert ei.value.status_code == 422
    assert ei.value.message == JD_NOT_POSTING_MSG
    assert ei.value.details and ei.value.details.get("reason") == "not_a_job_description"


def test_real_three_sentence_startup_jd_passes() -> None:
    assert looks_like_job_description(REAL_STARTUP_JD) is True
    assert_pasted_jd_looks_valid(REAL_STARTUP_JD)  # no raise


def test_cache_pasted_junk_zero_llm(client: TestClient) -> None:
    """POST /jobs/from-text with chrome → 422, no LLM / no complete_json."""
    with patch("app.services.inference.llm.complete_json") as mock_llm:
        r = client.post("/jobs/from-text", json={"description": JUNK_PASTE})
    assert r.status_code == 422, r.text
    body = r.json()
    assert body.get("error") == "validation_error"
    assert JD_NOT_POSTING_MSG in (body.get("message") or "")
    assert mock_llm.call_count == 0


def test_extract_metadata_junk_zero_llm() -> None:
    with patch.object(jd_meta_mod.llm, "complete_json") as mock_llm:
        with pytest.raises(ValidationError) as ei:
            jd_meta_mod.extract_job_metadata(JUNK_PASTE, db=None)
    assert ei.value.status_code == 422
    assert mock_llm.call_count == 0


def test_recommend_from_jd_junk_zero_llm(client: TestClient) -> None:
    """With a non-empty library, junk paste still 422s before any LLM spend."""
    from app.db.models import Resume
    from app.db.session import SessionLocal, init_db
    from app.schemas.resume import ResumeProfile

    init_db()
    db = SessionLocal()
    wid = client.get("/workspace").json()["workspace_id"]
    try:
        profile = ResumeProfile(
            name="Ada",
            title="Backend Engineer",
            skills=["Python"],
            summary="Backend engineer with Python.",
        )
        db.add(
            Resume(
                workspace_id=wid,
                filename="ada.pdf",
                content_hash="hash-ada-jd-preflight",
                parsed_json=profile.model_dump_json(),
                confirmed=True,
                in_library=True,
            )
        )
        db.commit()
    finally:
        db.close()

    with patch("app.services.inference.llm.complete_json") as mock_llm:
        r = client.post(
            "/library/recommend-from-jd",
            json={"job_description": JUNK_PASTE},
        )
    assert r.status_code == 422, r.text
    assert JD_NOT_POSTING_MSG in (r.json().get("message") or "")
    assert mock_llm.call_count == 0


def test_cache_pasted_real_jd_ok() -> None:
    init_db()
    db = SessionLocal()
    token = ws_mod._workspace_cv.set("ws-jd-preflight")
    try:
        job = cache_pasted_job(description=REAL_STARTUP_JD, title="Founding Engineer", company="Northwind", db=db)
        assert job.source == "paste"
        assert "Python" in job.description or "python" in job.description.lower()
    finally:
        ws_mod._workspace_cv.reset(token)
        db.close()


def test_empty_decomposition_is_validation_not_service_failing() -> None:
    from app.schemas.job_metadata import JobMetadata
    from app.services.resume import jd_decompose as mod

    job = Job(
        id="p1",
        source="paste",
        source_job_id="p1",
        title="Engineer",
        company="Acme",
        location="",
        description=REAL_STARTUP_JD,
        apply_url="https://example.com",
        posted_at=None,
        skills=["Python"],
    )

    class Empty:
        requirements = []

    with patch.object(mod.llm, "complete_json", return_value=Empty()):
        with pytest.raises(ValidationError) as ei:
            decompose_jd(job, use_llm=True, db=None, metadata_hints=JobMetadata())
    assert ei.value.status_code == 422
    assert ei.value.details and ei.value.details.get("reason") == "empty_decomposition"
    assert ei.value.message == JD_NOT_POSTING_MSG
