"""Outreach draft endpoint + prompt metadata (compose deep-links only)."""

from __future__ import annotations

from unittest.mock import patch

from app.db.models import Contact, EmailReveal, JobCache
from app.db.session import SessionLocal
from app.prompts import load_prompt
from app.services.outreach_draft import OutreachDraftResult
from fastapi.testclient import TestClient


def _workspace_id(client: TestClient) -> str:
    return client.get("/workspace").json()["workspace_id"]


def _seed_revealed_contact(client: TestClient, suffix: str = "1") -> tuple[str, str]:
    wid = _workspace_id(client)
    db = SessionLocal()
    try:
        job_id = f"job-draft-{suffix}"
        contact_id = f"contact-draft-{suffix}"
        person_id = f"sumble-ada-{suffix}"
        job = JobCache(
            workspace_id=wid,
            job_id=job_id,
            source="test",
            source_job_id=f"src-draft-{suffix}",
            title="ML Engineer",
            payload_json=(
                f'{{"id":"{job_id}","source":"test","source_job_id":"src-draft-{suffix}",'
                f'"title":"ML Engineer","company":"Acme","location":"Remote",'
                f'"description":"Build models.","apply_url":"https://example.com","skills":["python"]}}'
            ),
        )
        db.add(job)
        contact = Contact(
            id=contact_id,
            workspace_id=wid,
            full_name="Ada Lovelace",
            title="Engineering Manager",
            company="Acme",
            team="Platform",
            seniority="senior",
            job_id=job_id,
            sumble_person_id=person_id,
        )
        db.add(contact)
        reveal = EmailReveal(
            contact_id=contact_id,
            sumble_person_id=person_id,
            email="ada@acme.example",
            cost_credits=5,
            status="revealed",
        )
        db.add(reveal)
        db.commit()
        return contact.id, reveal.email or ""
    finally:
        db.close()


def test_outreach_draft_prompt_has_frontmatter_and_loads() -> None:
    tmpl = load_prompt("outreach_draft")
    assert tmpl.name == "outreach_draft"
    assert tmpl.version == "1"
    assert tmpl.content_hash
    assert tmpl.system
    assert "subject" in tmpl.body.lower() or "JSON" in (tmpl.system or "")
    assert "{{recipient_name}}" in tmpl.body
    assert "{{strengths_block}}" in tmpl.body


def test_outreach_draft_requires_revealed_email(client: TestClient) -> None:
    wid = _workspace_id(client)
    db = SessionLocal()
    try:
        c = Contact(
            id="contact-no-email",
            workspace_id=wid,
            full_name="No Email",
            title="EM",
            company="X",
            job_id=None,
            sumble_person_id="s-none",
        )
        db.add(c)
        db.commit()
    finally:
        db.close()

    resp = client.post("/contacts/contact-no-email/outreach-draft")
    assert resp.status_code == 400
    assert "reveal" in resp.json()["message"].lower()


def test_outreach_draft_not_found(client: TestClient) -> None:
    _workspace_id(client)
    resp = client.post("/contacts/missing-contact/outreach-draft")
    assert resp.status_code == 404


def test_outreach_draft_success_traced(client: TestClient) -> None:
    contact_id, email = _seed_revealed_contact(client, "ok")

    fake = OutreachDraftResult(
        subject="ML Engineer at Acme",
        body=(
            "Ada — saw the ML Engineer opening on Platform at Acme. "
            "I have shipped ranking systems and Python ML pipelines that match the stack. "
            "Open to a 15-minute chat if useful."
        ),
    )

    with patch(
        "app.api.routers.contacts.outreach_draft.generate_outreach_draft",
        return_value=(fake, email),
    ) as mocked:
        resp = client.post(f"/contacts/{contact_id}/outreach-draft")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contact_id"] == contact_id
        assert body["email"] == email
        assert body["subject"] == fake.subject
        assert body["body"] == fake.body
        mocked.assert_called_once()


def test_outreach_draft_calls_llm_with_prompt_meta(client: TestClient) -> None:
    contact_id, email = _seed_revealed_contact(client, "llm")

    captured: dict = {}

    def fake_complete_json(prompt, model, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return OutreachDraftResult(
            subject="Quick note on the ML Engineer role",
            body="Ada — " + ("word " * 100).strip(),
        )

    with patch("app.services.outreach_draft.llm.complete_json", side_effect=fake_complete_json):
        resp = client.post(f"/contacts/{contact_id}/outreach-draft")
    assert resp.status_code == 200, resp.text
    assert "Ada Lovelace" in captured["prompt"] or "Ada" in captured["prompt"]
    meta = captured["kwargs"].get("prompt_meta")
    assert meta is not None
    assert meta.name == "outreach_draft"
    assert meta.version == "1"
    assert meta.content_hash
    assert captured["kwargs"].get("operation") == "outreach_draft"
    assert resp.json()["email"] == email


def test_compose_opened_feedback_accepted(client: TestClient) -> None:
    _workspace_id(client)
    resp = client.post(
        "/feedback",
        json={
            "kind": "compose_opened",
            "target_type": "contact",
            "target_id": "contact-draft-1",
            "secondary_id": "gmail",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["kind"] == "compose_opened"
