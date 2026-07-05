from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.schemas.team import TeamExtraction
from app.services import sumble


@pytest.fixture
def sumble_base() -> str:
    return settings.SUMBLE_BASE_URL.rstrip("/")


@pytest.fixture
def sample_job() -> Job:
    return Job(
        id="job-cache-1",
        source="fixture",
        source_job_id="fixture-cache-1",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/apply",
        posted_at=None,
        skills=["Python"],
    )


@pytest.fixture
def sample_extraction() -> TeamExtraction:
    return TeamExtraction(
        team_name="Platform",
        department="Engineering",
        likely_hiring_titles=["Engineering Manager"],
    )


@pytest.fixture
def sample_person() -> sumble.SumblePerson:
    return sumble.SumblePerson(
        person_id=9001,
        name="Alex Manager",
        title="Engineering Manager",
        team="Platform",
        seniority="Manager",
        job_function="Engineering",
    )


def _seed_extraction(client: TestClient, job: Job, extraction: TeamExtraction) -> str:
    with patch("app.api.routers.jobs.resolve_job", return_value=job):
        with patch("app.api.routers.jobs.team_extract.extract_team_from_job", return_value=extraction):
            response = client.post(f"/jobs/{job.id}/extract-team")
    assert response.status_code == 200
    return response.json()["extraction_id"]


def _seed_contact(
    client: TestClient,
    job: Job,
    extraction_id: str,
    person: sumble.SumblePerson,
) -> str:
    org = sumble.SumbleOrganization(organization_id=42, name="Acme")
    with patch("app.api.routers.jobs.resolve_job", return_value=job):
        with patch("app.services.team_search.sumble.lookup_organization", return_value=org):
            with patch("app.services.team_search.sumble.search_people", return_value=([person], 5)):
                response = client.post(
                    f"/jobs/{job.id}/find-team",
                    json={"extraction_id": extraction_id},
                )
    assert response.status_code == 200
    return response.json()["contacts"][0]["id"]


def test_sumble_hard_fail_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", None)
    with pytest.raises(Exception) as exc:
        sumble.lookup_organization("Acme Corp")
    assert exc.value.error_code == "service_not_configured"


@respx.mock
def test_lookup_organization(sumble_base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    route = respx.post(f"{sumble_base}/v6/organizations").mock(
        return_value=httpx.Response(
            200,
            json={
                "credits_used": 1,
                "credits_remaining": 99,
                "organizations": [{"attributes": {"id": 42, "name": "Acme Corp"}}],
                "total": 1,
            },
        )
    )

    org = sumble.lookup_organization("Acme Corp")
    assert org.organization_id == 42
    assert org.name == "Acme Corp"
    assert route.called


@respx.mock
def test_search_people(sumble_base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    respx.post(f"{sumble_base}/v6/people").mock(
        return_value=httpx.Response(
            200,
            json={
                "credits_used": 12,
                "credits_remaining": 88,
                "people": [
                    {
                        "person_id": 9001,
                        "attributes": {
                            "name": "Alex Manager",
                            "job_title": "Engineering Manager",
                            "job_function": "Engineering",
                            "job_level": "Manager",
                        },
                    }
                ],
                "total": 1,
            },
        )
    )

    people, credits = sumble.search_people(
        organization_id=42,
        team_name="Platform",
        department="Engineering",
        likely_hiring_titles=["Engineering Manager"],
    )
    assert len(people) == 1
    assert people[0].person_id == 9001
    assert people[0].seniority == "Manager"
    assert credits == 12


@respx.mock
def test_reveal_email(sumble_base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    respx.post(f"{sumble_base}/v6/people").mock(
        return_value=httpx.Response(
            200,
            json={
                "credits_used": 10,
                "credits_remaining": 78,
                "people": [{"person_id": 9001, "attributes": {"email": "alex@acme.com"}}],
                "total": 1,
            },
        )
    )

    email, credits = sumble.reveal_email(9001)
    assert email == "alex@acme.com"
    assert credits == 10


def test_email_reveal_cache_prevents_double_charge(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job = Job(
        id="job-reveal-cache",
        source="fixture",
        source_job_id="fixture-reveal-cache",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/reveal-cache",
        posted_at=None,
        skills=["Python"],
    )
    extraction_id = _seed_extraction(client, job, sample_extraction)
    contact_id = _seed_contact(client, job, extraction_id, sample_person)

    reveal_calls: list[int] = []

    def _fake_reveal(person_id: int) -> tuple[str | None, int]:
        reveal_calls.append(person_id)
        return "alex@acme.com", 10

    with patch("app.services.email_reveal.sumble.reveal_email", side_effect=_fake_reveal):
        preview = client.post(f"/contacts/{contact_id}/reveal-email")
        assert preview.status_code == 200
        assert preview.json()["cost_credits"] == 10
        assert preview.json()["cached"] is False

        confirmed = client.post(f"/contacts/{contact_id}/reveal-email?confirm=true")
        assert confirmed.status_code == 200
        assert confirmed.json()["email"] == "alex@acme.com"

        cached = client.post(f"/contacts/{contact_id}/reveal-email?confirm=true")
        assert cached.status_code == 200
        assert cached.json()["cached"] is True
        assert cached.json()["email"] == "alex@acme.com"

    assert reveal_calls == [9001]


def test_not_found_reveal_is_terminal_and_stores_credits(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job = Job(
        id="job-not-found",
        source="fixture",
        source_job_id="fixture-not-found",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/not-found",
        posted_at=None,
        skills=["Python"],
    )
    extraction_id = _seed_extraction(client, job, sample_extraction)
    contact_id = _seed_contact(client, job, extraction_id, sample_person)

    reveal_calls: list[int] = []

    def _fake_reveal(person_id: int) -> tuple[str | None, int]:
        reveal_calls.append(person_id)
        return None, 10

    with patch("app.services.email_reveal.sumble.reveal_email", side_effect=_fake_reveal):
        first = client.post(f"/contacts/{contact_id}/reveal-email?confirm=true")
        assert first.status_code == 400
        assert "no email found" in first.json()["message"].lower() or "did not return" in first.json()["message"].lower()

        retry = client.post(f"/contacts/{contact_id}/reveal-email?confirm=true")
        assert retry.status_code == 400
        assert "cached" in retry.json()["message"].lower()

        preview = client.post(f"/contacts/{contact_id}/reveal-email")
        assert preview.status_code == 200
        assert preview.json()["cached"] is True
        assert preview.json()["status"] == "not_found"
        assert preview.json()["cost_credits"] == 10

    assert reveal_calls == [9001]


def test_same_person_across_two_jobs(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job_a = Job(
        id="job-a",
        source="fixture",
        source_job_id="fixture-a",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Platform team role",
        apply_url="https://example.com/a",
        posted_at=None,
        skills=["Python"],
    )
    job_b = Job(
        id="job-b",
        source="fixture",
        source_job_id="fixture-b",
        title="Staff Engineer",
        company="Acme",
        location="Remote",
        description="Platform team staff role",
        apply_url="https://example.com/b",
        posted_at=None,
        skills=["Python"],
    )

    extraction_a = _seed_extraction(client, job_a, sample_extraction)
    extraction_b = _seed_extraction(client, job_b, sample_extraction)

    org = sumble.SumbleOrganization(organization_id=42, name="Acme")
    with patch("app.api.routers.jobs.resolve_job", side_effect=lambda job_id, db: job_a if job_id == "job-a" else job_b):
        with patch("app.services.team_search.sumble.lookup_organization", return_value=org):
            with patch("app.services.team_search.sumble.search_people", return_value=([sample_person], 5)):
                found_a = client.post(f"/jobs/{job_a.id}/find-team", json={"extraction_id": extraction_a})
                found_b = client.post(f"/jobs/{job_b.id}/find-team", json={"extraction_id": extraction_b})

    assert found_a.status_code == 200
    assert found_b.status_code == 200
    contact_a = found_a.json()["contacts"][0]["id"]
    contact_b = found_b.json()["contacts"][0]["id"]
    assert contact_a != contact_b


def test_zero_result_find_team_persists_team_searched(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job = Job(
        id="job-zero-results",
        source="fixture",
        source_job_id="fixture-zero-results",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/zero",
        posted_at=None,
        skills=["Python"],
    )
    extraction_id = _seed_extraction(client, job, sample_extraction)
    org = sumble.SumbleOrganization(organization_id=42, name="Acme")

    with patch("app.api.routers.jobs.resolve_job", return_value=job):
        with patch("app.services.team_search.sumble.lookup_organization", return_value=org):
            with patch("app.services.team_search.sumble.search_people", return_value=([], 3)):
                found = client.post(
                    f"/jobs/{job.id}/find-team",
                    json={"extraction_id": extraction_id},
                )

    assert found.status_code == 200
    assert found.json()["contacts"] == []
    assert found.json()["team_searched"] is True

    with patch("app.api.routers.jobs.resolve_job", return_value=job):
        team = client.get(f"/jobs/{job.id}/team")

    assert team.status_code == 200
    assert team.json()["contacts"] == []
    assert team.json()["team_searched"] is True


def test_find_team_rejects_unknown_extraction_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_job: Job,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    with patch("app.api.routers.jobs.resolve_job", return_value=sample_job):
        response = client.post(
            f"/jobs/{sample_job.id}/find-team",
            json={"extraction_id": "missing-extraction"},
        )
    assert response.status_code == 400
    assert "extract-team" in response.json()["message"].lower()


def test_find_team_ignores_client_supplied_extraction_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_job: Job,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    extraction_id = _seed_extraction(client, sample_job, sample_extraction)

    stored_extraction = TeamExtraction(
        team_name="Platform",
        department="Engineering",
        likely_hiring_titles=["Engineering Manager"],
    )
    spoofed_extraction = TeamExtraction(
        team_name="Totally Different",
        department="Sales",
        likely_hiring_titles=["VP Sales"],
    )

    org = sumble.SumbleOrganization(organization_id=42, name="Acme")
    captured: dict[str, str] = {}

    def _capture_search(**kwargs):
        captured["team_name"] = kwargs["team_name"]
        captured["department"] = kwargs["department"]
        return [sample_person], 5

    with patch("app.api.routers.jobs.resolve_job", return_value=sample_job):
        with patch("app.api.routers.jobs._load_confirmed_extraction", return_value=stored_extraction):
            with patch("app.services.team_search.sumble.lookup_organization", return_value=org):
                with patch("app.services.team_search.sumble.search_people", side_effect=_capture_search):
                    response = client.post(
                        f"/jobs/{sample_job.id}/find-team",
                        json={
                            "extraction_id": extraction_id,
                            "team_name": spoofed_extraction.team_name,
                            "department": spoofed_extraction.department,
                            "likely_hiring_titles": spoofed_extraction.likely_hiring_titles,
                        },
                    )

    assert response.status_code == 200
    assert captured["team_name"] == stored_extraction.team_name
    assert captured["department"] == stored_extraction.department


def test_pending_reveal_blocks_second_confirm_without_sumble(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    from app.db.models import EmailReveal
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job = Job(
        id="job-pending",
        source="fixture",
        source_job_id="fixture-pending",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/pending",
        posted_at=None,
        skills=["Python"],
    )
    extraction_id = _seed_extraction(client, job, sample_extraction)
    contact_id = _seed_contact(client, job, extraction_id, sample_person)

    db = SessionLocal()
    db.add(
        EmailReveal(
            contact_id=contact_id,
            sumble_person_id="9001",
            status="pending",
        )
    )
    db.commit()
    db.close()

    reveal_calls: list[int] = []

    def _fake_reveal(person_id: int) -> tuple[str | None, int]:
        reveal_calls.append(person_id)
        return "alex@acme.com", 10

    with patch("app.services.email_reveal.sumble.reveal_email", side_effect=_fake_reveal):
        response = client.post(f"/contacts/{contact_id}/reveal-email?confirm=true")

    assert response.status_code == 400
    assert "in progress" in response.json()["message"].lower()
    assert reveal_calls == []


def test_integrity_error_race_returns_cached_reveal(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    sample_extraction: TeamExtraction,
    sample_person: sumble.SumblePerson,
) -> None:
    from app.db.models import Contact, EmailReveal
    from app.db.session import SessionLocal
    from app.services import email_reveal
    from sqlalchemy.exc import IntegrityError

    monkeypatch.setattr(settings, "SUMBLE_API_KEY", "test-key")
    job = Job(
        id="job-race",
        source="fixture",
        source_job_id="fixture-race",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Join the Platform team in Engineering.",
        apply_url="https://example.com/race",
        posted_at=None,
        skills=["Python"],
    )
    extraction_id = _seed_extraction(client, job, sample_extraction)
    contact_id = _seed_contact(client, job, extraction_id, sample_person)

    seed_db = SessionLocal()
    seed_db.add(
        EmailReveal(
            contact_id=contact_id,
            sumble_person_id="9001",
            email="alex@acme.com",
            cost_credits=10,
            status="revealed",
        )
    )
    seed_db.commit()
    seed_db.close()

    reveal_calls: list[int] = []

    def _fake_reveal(person_id: int) -> tuple[str | None, int]:
        reveal_calls.append(person_id)
        return "alex@acme.com", 10

    db = SessionLocal()
    contact = db.query(Contact).filter(Contact.id == contact_id).one()
    original_flush = db.flush

    def _flush_conflict_on_pending_insert(*args, **kwargs):
        if any(isinstance(obj, EmailReveal) and obj.status == "pending" for obj in db.new):
            raise IntegrityError("insert conflict", {}, Exception("conflict"))
        return original_flush(*args, **kwargs)

    with patch("app.services.email_reveal.sumble.reveal_email", side_effect=_fake_reveal):
        with patch.object(db, "flush", side_effect=_flush_conflict_on_pending_insert):
            result = email_reveal.confirm_reveal(db, contact)

    assert reveal_calls == []
    assert result.cached is True
    assert result.email == "alex@acme.com"
    db.close()