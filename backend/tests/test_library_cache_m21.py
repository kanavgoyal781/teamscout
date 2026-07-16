"""M21: cache transparency — re-upload / re-sync performs zero parse LLM + zero new embeds."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.schemas.resume import ResumeProfile
from app.services.library import store as library_store
from fastapi.testclient import TestClient


def _profile(name: str = "Alex") -> ResumeProfile:
    return ResumeProfile(
        name=name,
        title="Engineer",
        years_of_experience=5,
        location="Remote",
        skills=["Python", "SQL"],
        work_experience=[],
        summary="Backend engineer with Python and SQL.",
    )


def test_reupload_identical_files_zero_parse_and_embed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-uploading the same bytes: ZERO parse_resume LLM calls and ZERO new embedding API calls."""
    profile = _profile()
    parse_calls: list[str] = []
    embed_calls: list[int] = []

    def fake_parse_text(text: str) -> ResumeProfile:
        parse_calls.append(text[:40])
        return profile

    def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        embed_calls.append(len(texts))
        return [[0.1] * 8 for _ in texts]

    monkeypatch.setattr("app.services.resume.parser.parse_resume_text", fake_parse_text)
    monkeypatch.setattr("app.services.inference.embeddings.embed_batch", fake_embed_batch)
    monkeypatch.setattr("app.core.env_utils.is_set", lambda _k: True)
    # Ensure unit indexing thinks embeddings are configured
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "EMBEDDINGS_API_KEY", "test-embed-key")

    payload = b"%PDF-1.4 identical-resume-body-m21-cache"
    with patch("app.services.library.store.parser.extract_text", return_value="Alex Engineer Python SQL"):
        r1 = client.post(
            "/library/upload",
            files={"files": ("a.pdf", payload, "application/pdf")},
        )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["files_parsed"] == 1
    assert body1["files_skipped"] == 0
    assert body1["file_results"][0]["status"] == "parsed"
    first_parse = len(parse_calls)
    first_embed = sum(embed_calls)
    assert first_parse == 1
    assert first_embed >= 1  # units indexed on first ingest

    # Clear counters for re-upload
    parse_calls.clear()
    embed_calls.clear()

    with patch("app.services.library.store.parser.extract_text", return_value="Alex Engineer Python SQL"):
        r2 = client.post(
            "/library/upload",
            files={"files": ("a-copy.pdf", payload, "application/pdf")},
        )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["files_parsed"] == 0
    assert body2["files_skipped"] == 1
    assert body2["file_results"][0]["status"] == "cached"
    assert len(parse_calls) == 0, f"parse LLM called on cache hit: {parse_calls}"
    assert sum(embed_calls) == 0, f"new embeds on cache hit: {embed_calls}"


def test_upload_one_new_among_many_parses_exactly_one(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """50 cached + 1 new → exactly 1 parse LLM call."""
    profiles = {i: _profile(f"P{i}") for i in range(51)}
    parse_calls: list[str] = []

    def fake_parse_text(text: str) -> ResumeProfile:
        # text unused for identity; track call
        parse_calls.append("x")
        # return a stable profile — content_hash is from bytes
        return _profile("New" if len(parse_calls) > 50 else "Old")

    monkeypatch.setattr("app.services.resume.parser.parse_resume_text", fake_parse_text)
    monkeypatch.setattr(
        "app.services.inference.embeddings.embed_batch",
        lambda texts: [[0.1] * 4 for _ in texts],
    )
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "EMBEDDINGS_API_KEY", "test-embed-key")

    # Seed 50 distinct files
    for i in range(50):
        data = f"%PDF-1.4 resume-body-{i:03d}-padding".encode()
        with patch("app.services.library.store.parser.extract_text", return_value=f"resume {i}"):
            resp = client.post(
                "/library/upload",
                files={"files": (f"r{i}.pdf", data, "application/pdf")},
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["files_parsed"] == 1

    parse_calls.clear()
    # Re-upload all 50 identical + 1 new
    files = []
    for i in range(50):
        data = f"%PDF-1.4 resume-body-{i:03d}-padding".encode()
        files.append(("files", (f"r{i}.pdf", data, "application/pdf")))
    files.append(("files", ("r-new.pdf", b"%PDF-1.4 resume-body-NEW-only-once", "application/pdf")))

    with patch("app.services.library.store.parser.extract_text", return_value="bulk"):
        resp = client.post("/library/upload", files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["files_parsed"] == 1
    assert body["files_skipped"] == 50
    assert len(parse_calls) == 1
    statuses = [fr["status"] for fr in body["file_results"]]
    assert statuses.count("parsed") == 1
    assert statuses.count("cached") == 50
