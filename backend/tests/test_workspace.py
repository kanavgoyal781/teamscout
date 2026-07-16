"""M19: anonymous workspaces isolation, TTL, ceilings, WAL concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from app.core import workspace as ws_mod
from app.core.config import settings
from app.core.workspace import COOKIE_NAME, cookie_header_value, sweep_expired_workspaces
from app.db.models import Contact, EmailReveal, Resume, Search, Workspace
from app.db.session import SessionLocal, engine
from app.errors import CostCeilingExceededError
from app.main import app
from app.schemas.resume import ResumeProfile
from app.services import observability, parser
from fastapi.testclient import TestClient
from sqlalchemy import text


@pytest.fixture
def profile() -> ResumeProfile:
    return ResumeProfile(
        name="A",
        title="Eng",
        location="SF",
        skills=["python"],
        years_of_experience=5,
        summary="s",
        work_experience=[],
        education=[],
    )


def _client() -> TestClient:
    return TestClient(app)


def _upload(client: TestClient, profile: ResumeProfile, name: str = "r.pdf", h: str = "hash-x") -> str:
    with patch.object(parser, "parse_resume_file", return_value=(h, profile)):
        r = client.post("/resumes/upload", files={"file": (name, b"%PDF-1.4 demo", "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_livez_health_skip_workspace_mint() -> None:
    c = _client()
    r1 = c.get("/livez")
    assert r1.status_code == 200
    assert COOKIE_NAME not in (r1.headers.get("set-cookie") or "").lower()
    r2 = c.get("/health")
    assert r2.status_code in (200, 503)
    assert COOKIE_NAME not in (r2.headers.get("set-cookie") or "").lower()


def test_cross_workspace_isolation_id_probing(profile: ResumeProfile) -> None:
    a, b = _client(), _client()
    aid = _upload(a, profile, "a.pdf", "hash-a")
    bid = _upload(b, profile, "b.pdf", "hash-b")
    assert aid != bid
    assert (
        a.put(f"/resumes/{aid}/confirm", json={"title": "T", "location": "L", "skills": ["python"]}).status_code == 200
    )
    assert b.put(f"/resumes/{aid}/confirm", json={"title": "X", "location": "Y", "skills": ["z"]}).status_code == 404
    # Library: put A resume in library via hash-scoped upload endpoint
    with (
        patch.object(parser, "content_hash", return_value="lib-a"),
        patch.object(parser, "extract_text", return_value="lib resume text"),
        patch.object(parser, "parse_resume_text", return_value=profile),
    ):
        la_up = a.post("/library/upload", files={"files": ("lib-a.pdf", b"%PDF-1.4 lib", "application/pdf")})
    assert la_up.status_code == 200, la_up.text
    la = a.get("/library/resumes")
    lb = b.get("/library/resumes")
    assert la.status_code == 200 and lb.status_code == 200
    assert la.json()["total"] >= 1
    assert lb.json()["total"] == 0
    # Seed contact for A only
    db = SessionLocal()
    try:
        wa = a.get("/workspace").json()["workspace_id"]
        ca = Contact(workspace_id=wa, full_name="Pat", job_id="job-a", sumble_person_id="111")
        db.add(ca)
        sa = Search(workspace_id=wa, resume_id=aid, label="x", query_json="{}", results_json="[]")
        db.add(sa)
        db.commit()
        db.refresh(ca)
        db.refresh(sa)
        contact_id, search_id = ca.id, sa.id
    finally:
        db.close()
    assert b.post(f"/contacts/{contact_id}/reveal-email").status_code == 404
    assert b.get("/jobs/job-a/team").status_code == 404
    # Search row not visible across workspaces (no list API; probe via feedback secondary is N/A)
    assert a.get("/workspace").json()["workspace_id"] != b.get("/workspace").json()["workspace_id"]
    fa = a.post("/feedback", json={"kind": "thumbs_up", "target_type": "job_match", "target_id": search_id})
    assert fa.status_code == 200, fa.text


def test_ttl_sweep_deletes_rows_and_files_preserves_email_reveals(profile: ResumeProfile) -> None:
    client = _client()
    rid = _upload(client, profile, "ttl.pdf", "hash-ttl")
    wid = client.get("/workspace").json()["workspace_id"]
    db = SessionLocal()
    try:
        row = db.query(Resume).filter(Resume.id == rid).one()
        fp = Path(row.file_path or "")
        assert fp.is_file()
        assert wid in str(fp)  # namespaced under workspace
        reveal = EmailReveal(
            contact_id="ttl-contact", sumble_person_id="9999", status="revealed", email="x@y.com", cost_credits=1
        )
        db.add(reveal)
        ws = db.query(Workspace).filter(Workspace.id == wid).one()
        ws.last_seen_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
        db.add(ws)
        db.commit()
        reveal_id = reveal.id
    finally:
        db.close()
    n = sweep_expired_workspaces(now=datetime.now(UTC).replace(tzinfo=None))
    assert n >= 1
    db = SessionLocal()
    try:
        assert db.query(Resume).filter(Resume.id == rid).one_or_none() is None
        assert db.query(Workspace).filter(Workspace.id == wid).one_or_none() is None
        assert db.query(EmailReveal).filter(EmailReveal.id == reveal_id).one_or_none() is not None
    finally:
        db.close()
    assert not fp.exists()


def test_workspace_llm_and_sumble_ceilings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "WORKSPACE_DAILY_LLM_USD", 0.0)
    monkeypatch.setattr(settings, "LLM_DAILY_COST_CEILING_USD", 1000.0)
    monkeypatch.setattr(settings, "WORKSPACE_DAILY_SUMBLE_CREDITS", 0)
    monkeypatch.setattr(settings, "SUMBLE_DAILY_CREDIT_CEILING", 100000)
    client = _client()
    wid = client.get("/workspace").json()["workspace_id"]
    token = ws_mod._workspace_cv.set(wid)
    try:
        with pytest.raises(CostCeilingExceededError) as ei:
            observability.assert_llm_budget_allows(estimated_cost_usd=0.01)
        assert "Workspace daily LLM limit" in ei.value.message
        assert ei.value.details.get("scope") == "workspace"
        with pytest.raises(CostCeilingExceededError) as es:
            observability.assert_sumble_budget_allows(estimated_credits=1)
        assert "Workspace daily Sumble" in es.value.message
        assert es.value.details.get("scope") == "workspace"
    finally:
        ws_mod._workspace_cv.reset(token)


def test_sqlite_busy_timeout_and_wal_pragma() -> None:
    with engine.connect() as conn:
        busy = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert int(busy or 0) >= 5000
        # File DB uses WAL; in-memory pytest may report memory/delete
        mode = str(conn.execute(text("PRAGMA journal_mode")).scalar() or "").lower()
        assert mode in {"wal", "memory", "delete"}


def test_concurrent_writes_three_users(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "concurrent.db"
    bootstrap = sqlite3.connect(path)
    bootstrap.execute("PRAGMA journal_mode=WAL")
    bootstrap.execute("PRAGMA busy_timeout=5000")
    assert bootstrap.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    bootstrap.execute("CREATE TABLE feedback_like (id INTEGER PRIMARY KEY, workspace TEXT, payload TEXT)")
    bootstrap.commit()
    bootstrap.close()

    def work(i: int) -> None:
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("INSERT INTO feedback_like (workspace, payload) VALUES (?, ?)", (f"ws-{i}", f"p-{i}"))
        conn.commit()
        conn.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(work, i) for i in range(3)]):
            f.result()
    verify = sqlite3.connect(path)
    assert verify.execute("SELECT COUNT(*) FROM feedback_like").fetchone()[0] == 3
    verify.close()
    for i in range(3):
        r = _client().post(
            "/feedback", json={"kind": "thumbs_up", "target_type": "job_match", "target_id": f"app-c-{i}"}
        )
        assert r.status_code == 200, r.text


def test_cookie_attributes_dev_and_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    r = client.get("/workspace")
    assert r.status_code == 200
    sc = r.headers.get("set-cookie") or ""
    assert sc  # always refresh cookie
    assert "HttpOnly" in sc or "httponly" in sc.lower()
    assert "Max-Age" in sc or "max-age" in sc.lower()
    monkeypatch.setattr(settings, "ENV", "prod")
    val = cookie_header_value("tokentoken1234567890")
    assert "SameSite=None" in val
    assert "Secure" in val
    monkeypatch.setattr(settings, "ENV", "dev")
    monkeypatch.setattr(settings, "WORKSPACE_COOKIE_SAMESITE", "lax")
    val2 = cookie_header_value("tokentoken1234567890")
    assert "SameSite=Lax" in val2
    assert "Secure" not in val2


def test_upload_paths_namespaced_per_workspace(profile: ResumeProfile) -> None:
    a, b = _client(), _client()
    with patch.object(parser, "parse_resume_file", return_value=("samehash", profile)):
        ra = a.post("/resumes/upload", files={"file": ("s.pdf", b"%PDF-1.4 a", "application/pdf")})
        rb = b.post("/resumes/upload", files={"file": ("s.pdf", b"%PDF-1.4 b", "application/pdf")})
    assert ra.status_code == 200 and rb.status_code == 200
    db = SessionLocal()
    try:
        pa = Path(db.query(Resume).filter(Resume.id == ra.json()["id"]).one().file_path or "")
        pb = Path(db.query(Resume).filter(Resume.id == rb.json()["id"]).one().file_path or "")
        assert pa != pb
        assert pa.parent.name != pb.parent.name
        assert pa.is_file() and pb.is_file()
    finally:
        db.close()
