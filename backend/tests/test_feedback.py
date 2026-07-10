"""Feedback capture + learning loop observe-only guarantees."""

from __future__ import annotations

import json

from app.core.config import settings
from app.db.models import Feedback
from app.db.session import SessionLocal
from app.services import feedback_store
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_post_feedback_writes_row_with_provenance(client: TestClient) -> None:
    resp = client.post(
        "/feedback",
        json={
            "kind": "thumbs_up",
            "target_type": "job_match",
            "target_id": "job-abc",
            "profile_hash": "aaaaaaaaaaaaaaaa",
            "jd_hash": "bbbbbbbbbbbbbbbb",
            "score_shown": 87.5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "thumbs_up"
    assert body["target_id"] == "job-abc"
    assert body["id"]

    db: Session = SessionLocal()
    try:
        row = db.query(Feedback).filter(Feedback.id == body["id"]).one()
        assert row.score_shown == 87.5
        assert row.profile_hash == "aaaaaaaaaaaaaaaa"
        assert row.model == settings.LLM_MODEL
        assert row.embeddings_model == settings.EMBEDDINGS_MODEL
        assert row.prompt_versions_json
        versions = json.loads(row.prompt_versions_json)
        assert isinstance(versions, dict)
    finally:
        db.close()


def test_implicit_kinds_accepted(client: TestClient) -> None:
    for kind in ("apply_click", "find_team_click", "thumbs_down"):
        resp = client.post(
            "/feedback",
            json={
                "kind": kind,
                "target_type": "job_match",
                "target_id": f"job-{kind}",
                "score_shown": 50.0,
            },
        )
        assert resp.status_code == 200, resp.text


def test_feedback_label_counts(client: TestClient) -> None:
    client.post(
        "/feedback",
        json={"kind": "thumbs_up", "target_type": "resume_pick", "target_id": "r1"},
    )
    client.post(
        "/feedback",
        json={"kind": "apply_click", "target_type": "job_match", "target_id": "j1"},
    )
    db = SessionLocal()
    try:
        counts = feedback_store.feedback_label_counts(db)
    finally:
        db.close()
    assert counts["total"] >= 2
    assert counts["thumbs_up"] >= 1
    assert counts["apply_click"] >= 1


def test_ops_includes_learning_section(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "OPS_TOKEN", "secret-ops")
    # ensure at least one feedback row
    client.post(
        "/feedback",
        json={"kind": "thumbs_up", "target_type": "job_match", "target_id": "ops-j"},
    )
    resp = client.get("/ops", headers={"X-Ops-Token": "secret-ops"})
    assert resp.status_code == 200
    assert "Evals" in resp.text
    assert "Last experiments" in resp.text

    resp_json = client.get("/ops/json", headers={"Authorization": "Bearer secret-ops"})
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert "learning" in data
    assert "feedback_counts" in data["learning"]


def test_invalid_kind_rejected(client: TestClient) -> None:
    resp = client.post(
        "/feedback",
        json={"kind": "not_a_kind", "target_type": "job_match", "target_id": "x"},
    )
    assert resp.status_code == 422


def test_score_shown_bounds(client: TestClient) -> None:
    bad = client.post(
        "/feedback",
        json={"kind": "thumbs_up", "target_type": "job_match", "target_id": "j1", "score_shown": 101},
    )
    assert bad.status_code == 422
    bad2 = client.post(
        "/feedback",
        json={"kind": "thumbs_up", "target_type": "job_match", "target_id": "j1", "score_shown": -1},
    )
    assert bad2.status_code == 422


def test_hash_must_be_hex(client: TestClient) -> None:
    bad = client.post(
        "/feedback",
        json={
            "kind": "thumbs_up",
            "target_type": "job_match",
            "target_id": "j1",
            "profile_hash": "not-hex!!",
        },
    )
    assert bad.status_code == 422
    ok = client.post(
        "/feedback",
        json={
            "kind": "thumbs_up",
            "target_type": "job_match",
            "target_id": "j1",
            "profile_hash": "deadbeefcafebabe",
            "jd_hash": "0123456789abcdef",
            "score_shown": 88.5,
            "secondary_id": "sec-1",
        },
    )
    assert ok.status_code == 200, ok.text
    from app.db.models import Feedback
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Feedback).filter(Feedback.id == ok.json()["id"]).one()
        assert row.profile_hash == "deadbeefcafebabe"
        assert row.secondary_id == "sec-1"
        assert row.ranking_config_hash
    finally:
        db.close()


def test_invalid_target_type_and_empty_id(client: TestClient) -> None:
    assert (
        client.post(
            "/feedback",
            json={"kind": "thumbs_up", "target_type": "nope", "target_id": "x"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/feedback",
            json={"kind": "thumbs_up", "target_type": "job_match", "target_id": ""},
        ).status_code
        == 422
    )


def test_feedback_label_counts_delta(client: TestClient) -> None:
    from app.db.session import SessionLocal
    from app.services import feedback_store

    db = SessionLocal()
    try:
        before = feedback_store.feedback_label_counts(db)
    finally:
        db.close()
    client.post(
        "/feedback",
        json={"kind": "thumbs_down", "target_type": "job_match", "target_id": "delta-1"},
    )
    db = SessionLocal()
    try:
        after = feedback_store.feedback_label_counts(db)
    finally:
        db.close()
    assert after["thumbs_down"] == before["thumbs_down"] + 1
    assert after["total"] == before["total"] + 1


def test_score_shown_null_ok(client: TestClient) -> None:
    resp = client.post(
        "/feedback",
        json={"kind": "thumbs_up", "target_type": "job_match", "target_id": "null-score"},
    )
    assert resp.status_code == 200, resp.text
    from app.db.models import Feedback
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Feedback).filter(Feedback.id == resp.json()["id"]).one()
        assert row.score_shown is None
    finally:
        db.close()
