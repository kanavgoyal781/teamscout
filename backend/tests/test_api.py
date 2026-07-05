import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
from app.schemas.resume import ResumeProfile


def test_upload_and_confirm_resume(client: TestClient) -> None:
    from tests.conftest import SAMPLE_PDF

    profile = ResumeProfile(
        name="Jane Doe",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI", "PostgreSQL"],
        work_experience=[],
        summary="Backend engineer",
    )

    with patch("app.api.routers.resumes.parser.parse_resume_file", return_value=("hash-1", profile)):
        upload = client.post(
            "/resumes/upload",
            files={"file": ("resume.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
        )

    assert upload.status_code == 200
    payload = upload.json()
    resume_id = payload["id"]
    assert payload["profile"]["title"] == "Senior Backend Engineer"

    confirm = client.put(
        f"/resumes/{resume_id}/confirm",
        json={"title": "Staff Backend Engineer", "location": "Remote", "skills": ["Python", "Go"]},
    )
    assert confirm.status_code == 200
    confirmed = confirm.json()
    assert confirmed["confirmed"] is True
    assert confirmed["profile"]["title"] == "Staff Backend Engineer"
    assert confirmed["profile"]["skills"] == ["Python", "Go"]


def test_create_search_requires_confirmed_resume(client: TestClient) -> None:
    from tests.conftest import SAMPLE_PDF

    profile = ResumeProfile(
        name="Jane Doe",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI", "PostgreSQL"],
        work_experience=[],
        summary="Backend engineer",
    )

    with patch("app.api.routers.resumes.parser.parse_resume_file", return_value=("hash-3", profile)):
        upload = client.post(
            "/resumes/upload",
            files={"file": ("resume.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
        )
    resume_id = upload.json()["id"]

    response = client.post("/searches", json={"resume_id": resume_id})
    assert response.status_code == 400
    assert "confirmed" in response.json()["message"].lower()


def test_create_search_uses_confirmed_snapshot_not_request_override(client: TestClient) -> None:
    from tests.conftest import SAMPLE_PDF

    profile = ResumeProfile(
        name="Jane Doe",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI", "PostgreSQL"],
        work_experience=[],
        summary="Backend engineer",
    )
    job = Job(
        id="job-1",
        source="fixture",
        source_job_id="fixture-1",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Python FastAPI PostgreSQL",
        apply_url="https://example.com/apply",
        posted_at=None,
        skills=["Python", "FastAPI"],
    )
    ranked = RankedJob(
        job=job,
        match_score=88.5,
        score_breakdown=ScoreBreakdown(
            llm_fit=90,
            rrf_normalized=0.8,
            skill_jaccard=0.5,
            recency=0.7,
            final_score=88.5,
            matched_skills=["Python"],
            missing_skills=["Redis"],
            rationale="Strong Python overlap",
        ),
    )

    with patch("app.api.routers.resumes.parser.parse_resume_file", return_value=("hash-4", profile)):
        upload = client.post(
            "/resumes/upload",
            files={"file": ("resume.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
        )
    resume_id = upload.json()["id"]

    client.put(
        f"/resumes/{resume_id}/confirm",
        json={"title": "Confirmed Title", "location": "Confirmed City", "skills": ["Python"]},
    )

    with patch("app.api.routers.searches.jobs.fetch_jobs") as fetch_mock:
        with patch("app.api.routers.searches.ranking.rank_jobs", return_value=[ranked]):
            response = client.post("/searches", json={"resume_id": resume_id})

    assert response.status_code == 200
    called_profile = fetch_mock.call_args.args[0]
    assert called_profile.title == "Confirmed Title"
    assert called_profile.location == "Confirmed City"
    assert called_profile.skills == ["Python"]


def test_create_search_returns_ranked_jobs(client: TestClient) -> None:
    from tests.conftest import SAMPLE_PDF

    profile = ResumeProfile(
        name="Jane Doe",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI", "PostgreSQL"],
        work_experience=[],
        summary="Backend engineer",
    )
    job = Job(
        id="job-1",
        source="fixture",
        source_job_id="fixture-1",
        title="Backend Engineer",
        company="Acme",
        location="San Francisco, CA",
        description="Python FastAPI PostgreSQL",
        apply_url="https://example.com/apply",
        posted_at=None,
        skills=["Python", "FastAPI"],
    )
    ranked = RankedJob(
        job=job,
        match_score=88.5,
        score_breakdown=ScoreBreakdown(
            llm_fit=90,
            rrf_normalized=0.8,
            skill_jaccard=0.5,
            recency=0.7,
            final_score=88.5,
            matched_skills=["Python"],
            missing_skills=["Redis"],
            rationale="Strong Python overlap",
        ),
    )

    with patch("app.api.routers.resumes.parser.parse_resume_file", return_value=("hash-2", profile)):
        upload = client.post(
            "/resumes/upload",
            files={"file": ("resume.pdf", SAMPLE_PDF.read_bytes(), "application/pdf")},
        )
    resume_id = upload.json()["id"]

    confirm = client.put(
        f"/resumes/{resume_id}/confirm",
        json={"title": profile.title, "location": profile.location, "skills": profile.skills},
    )
    assert confirm.status_code == 200

    with patch("app.api.routers.searches.jobs.fetch_jobs", return_value=[job]):
        with patch("app.api.routers.searches.ranking.rank_jobs", return_value=[ranked]):
            response = client.post("/searches", json={"resume_id": resume_id})

    assert response.status_code == 200
    body = response.json()
    assert body["resume_id"] == resume_id
    assert len(body["results"]) == 1
    assert body["results"][0]["match_score"] == 88.5
    assert body["results"][0]["score_breakdown"]["matched_skills"] == ["Python"]