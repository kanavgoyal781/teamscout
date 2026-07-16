import io
import zipfile
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
import respx
from app.core.config import settings
from app.db.models import DriveSyncedFile, JobCache, Resume
from app.db.session import SessionLocal, init_db
from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
from app.schemas.library import LibraryResumeOut, RankedResumeRecommendation, RequirementCoverage
from app.schemas.resume import ResumeProfile
from app.services import drive
from fastapi.testclient import TestClient


def _profile(name: str, title: str, skills: list[str], summary: str) -> ResumeProfile:
    return ResumeProfile(
        name=name,
        title=title,
        years_of_experience=6,
        location="San Francisco, CA",
        skills=skills,
        work_experience=[],
        summary=summary,
    )


def _seed_library_resume(
    client: TestClient,
    *,
    file_hash: str,
    filename: str,
    profile: ResumeProfile,
) -> str:
    with patch("app.services.library.store.parser.parse_resume_file", return_value=(file_hash, profile)):
        response = client.post(
            "/library/upload",
            files={"files": (filename, b"%PDF resume", "application/pdf")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["files_parsed"] >= 1 or body["files_skipped"] >= 1
    return body["resumes"][0]["id"]


def test_drive_url_validation() -> None:
    with pytest.raises(Exception) as exc:
        drive.parse_folder_id("https://example.com/not-a-folder")
    assert exc.value.error_code == "validation_error"

    folder_id = drive.parse_folder_id("https://drive.google.com/drive/folders/abc123XYZ")
    assert folder_id == "abc123XYZ"


def test_drive_hard_fail_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_REFRESH_TOKEN", None)
    with pytest.raises(Exception) as exc:
        drive.list_folder_files("folder-1")
    assert exc.value.error_code == "service_not_configured"


@respx.mock
def test_library_upload_hash_dedup(client: TestClient) -> None:
    profile = _profile("Alex", "Backend Engineer", ["Python"], "Python APIs")
    first = _seed_library_resume(client, file_hash="lib-hash-1", filename="a.pdf", profile=profile)
    second = _seed_library_resume(client, file_hash="lib-hash-1", filename="b.pdf", profile=profile)
    assert first == second

    listing = client.get("/library/resumes")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_library_upload_zip(client: TestClient) -> None:
    profile = _profile("Sam", "Data Engineer", ["SQL"], "Pipelines")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.pdf", b"%PDF-1.4")
        archive.writestr("notes.txt", b"ignore")
    buffer.seek(0)

    with patch("app.services.library.store.parser.parse_resume_file", return_value=("zip-hash-1", profile)):
        response = client.post(
            "/library/upload",
            files={"files": ("resumes.zip", buffer.read(), "application/zip")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["files_parsed"] == 1
    assert body["files_ignored"] == 1


@respx.mock
def test_drive_list_folder_paginates(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", "drive-test-key")

    list_route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "nextPageToken": "page-2",
                    "files": [
                        {
                            "id": "file-1",
                            "name": "one.pdf",
                            "mimeType": "application/pdf",
                            "modifiedTime": "2026-01-01T00:00:00.000Z",
                        },
                        {
                            "id": "img-1",
                            "name": "photo.png",
                            "mimeType": "image/png",
                            "modifiedTime": "2026-01-01T00:00:00.000Z",
                        },
                    ],
                },
            ),
            httpx.Response(
                200,
                json={
                    "files": [
                        {
                            "id": "file-2",
                            "name": "two.docx",
                            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "modifiedTime": "2026-01-02T00:00:00.000Z",
                        }
                    ]
                },
            ),
        ]
    )

    result = drive.list_folder_files("folder-paginated")
    assert list_route.call_count == 2
    assert len(result.supported_files) == 2
    assert result.files_ignored == 1


@respx.mock
def test_drive_sync_ingests_files(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", "drive-test-key")
    profile = _profile("Jordan", "Platform Engineer", ["Go"], "Distributed systems")

    list_route = respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "resume.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                    {
                        "id": "img-1",
                        "name": "photo.png",
                        "mimeType": "image/png",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    },
                ]
            },
        )
    )
    download_route = respx.get("https://www.googleapis.com/drive/v3/files/file-1").mock(
        return_value=httpx.Response(200, content=b"%PDF drive")
    )

    with patch("app.services.library.store.ingest_resume_bytes") as ingest_mock:
        ingest_mock.return_value = (
            LibraryResumeOut(
                id="resume-drive-1",
                filename="resume.pdf",
                content_hash="drive-hash",
                source="drive",
                profile=profile,
                created_at=None,
            ),
            True,
        )
        response = client.post(
            "/library/drive/sync",
            json={"folder_url": "https://drive.google.com/drive/folders/folder-abc"},
        )

    assert response.status_code == 200
    assert list_route.called
    assert download_route.called
    body = response.json()
    assert body["folder_id"] == "folder-abc"
    assert body["files_seen"] == 1
    assert body["files_parsed"] == 1
    assert body["files_ignored"] == 1


@respx.mock
def test_drive_resync_skips_known_hashes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_API_KEY", "drive-test-key")
    profile = _profile("Jordan", "Platform Engineer", ["Go"], "Distributed systems")
    init_db()
    wid = client.get("/workspace").json()["workspace_id"]
    db = SessionLocal()
    try:
        db.add(
            Resume(
                workspace_id=wid,
                filename="resume.pdf",
                content_hash="drive-hash-resync",
                parsed_json=profile.model_dump_json(),
                in_library=True,
                source="drive",
            )
        )
        db.add(
            DriveSyncedFile(
                workspace_id=wid,
                folder_id="folder-resync",
                file_id="file-1",
                filename="resume.pdf",
                modified_time="2026-01-01T00:00:00.000Z",
                content_hash="drive-hash-resync",
            )
        )
        db.commit()
    finally:
        db.close()

    respx.get("https://www.googleapis.com/drive/v3/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "resume.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-01-01T00:00:00.000Z",
                    }
                ]
            },
        )
    )
    download_route = respx.get("https://www.googleapis.com/drive/v3/files/file-1")

    with patch("app.services.library.store.ingest_resume_bytes") as ingest_mock:
        response = client.post(
            "/library/drive/sync",
            json={"folder_url": "https://drive.google.com/drive/folders/folder-resync"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["files_seen"] == 1
    assert body["files_parsed"] == 0
    assert body["files_skipped"] == 1
    ingest_mock.assert_not_called()
    assert not download_route.called


def test_intent_search_stores_results(client: TestClient) -> None:
    job = Job(
        id="intent-job-1",
        source="fixture",
        source_job_id="intent-fixture-1",
        title="Backend Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python"],
    )
    ranked = RankedJob(
        job=job,
        match_score=90.0,
        score_breakdown=ScoreBreakdown(
            llm_fit=90,
            rrf_normalized=0.8,
            skill_jaccard=0.5,
            recency=0.7,
            final_score=90.0,
            matched_skills=["Python"],
            missing_skills=[],
            rationale="Strong fit",
        ),
    )

    with patch("app.api.routers.library.jobs.fetch_jobs_for_intent", return_value=[job]):
        with patch("app.api.routers.library.ranking.rank_jobs", return_value=[ranked]):
            response = client.post(
                "/library/intent/search",
                json={
                    "role": "Backend Engineer",
                    "years_of_experience": 5,
                    "location": "Remote",
                    "remote_preference": "remote",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["search_id"]
    assert len(body["results"]) == 1


def test_recommend_resumes_ranking(client: TestClient) -> None:
    init_db()
    wid = client.get("/workspace").json()["workspace_id"]
    db = SessionLocal()
    try:
        job = Job(
            id="pick-job-1",
            source="fixture",
            source_job_id="pick-fixture-1",
            title="Senior Python Engineer",
            company="Acme",
            location="Remote",
            description="Need Python, FastAPI, PostgreSQL, and AWS experience.",
            apply_url="https://example.com/apply",
            posted_at=datetime.now(UTC),
            skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
        )
        db.add(
            JobCache(
                workspace_id=wid,
                job_id=job.id,
                source=job.source,
                source_job_id=job.source_job_id,
                title=job.title,
                payload_json=job.model_dump_json(),
            )
        )
        for index, skills in enumerate(
            (
                ["Python", "FastAPI", "PostgreSQL", "AWS"],
                ["Java", "Spring"],
                ["Python", "Django"],
            ),
            start=1,
        ):
            db.add(
                Resume(
                    workspace_id=wid,
                    filename=f"resume-{index}.pdf",
                    content_hash=f"pick-hash-{index}",
                    parsed_json=_profile(
                        f"Person {index}",
                        f"Engineer {index}",
                        skills,
                        f"Summary {index}",
                    ).model_dump_json(),
                    in_library=True,
                    source="upload",
                )
            )
        db.commit()
    finally:
        db.close()

    recommendations = [
        RankedResumeRecommendation(
            resume_id="will-be-replaced",
            filename="resume-1.pdf",
            match_score=95.0,
            score_breakdown=ScoreBreakdown(
                llm_fit=95,
                rrf_normalized=0.9,
                skill_jaccard=0.8,
                recency=0.7,
                final_score=95.0,
                matched_skills=["Python", "FastAPI"],
                missing_skills=[],
                rationale="Strong Python and FastAPI delivery at Acme.",
            ),
            coverage=[
                RequirementCoverage(
                    requirement="Python",
                    status="hit",
                    evidence="8 years Python at Acme",
                )
            ],
        )
    ]

    with patch("app.api.routers.library.resume_ranking.rank_resumes_for_job") as rank_mock:
        rank_mock.return_value = recommendations
        response = client.post("/library/jobs/pick-job-1/recommend-resumes")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "pick-job-1"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["coverage"][0]["status"] == "hit"


def test_recommend_from_jd_happy_path(client: TestClient) -> None:
    """Primary Feature 2 path: paste JD → cache job → rank library (mocked rank)."""
    profile = _profile(
        "Alex",
        "Backend Engineer",
        ["Python", "FastAPI", "PostgreSQL"],
        "Python APIs and services",
    )
    _seed_library_resume(
        client,
        file_hash="from-jd-hash-1",
        filename="alex.pdf",
        profile=profile,
    )

    recommendations = [
        RankedResumeRecommendation(
            resume_id="seeded",
            filename="alex.pdf",
            match_score=88.0,
            score_breakdown=ScoreBreakdown(
                llm_fit=88,
                rrf_normalized=0.85,
                skill_jaccard=0.75,
                recency=0.6,
                final_score=88.0,
                matched_skills=["Python", "FastAPI"],
                missing_skills=[],
                rationale="Strong backend match for the pasted JD.",
            ),
            coverage=[
                RequirementCoverage(
                    requirement="Python",
                    status="hit",
                    evidence="Python APIs and services",
                )
            ],
        )
    ]

    jd = (
        "Senior Backend Engineer role requiring Python, FastAPI, and PostgreSQL. "
        "Build reliable APIs and data services for a product team."
    )
    with patch("app.api.routers.library.resume_ranking.rank_resumes_for_job") as rank_mock:
        rank_mock.return_value = recommendations
        response = client.post(
            "/library/recommend-from-jd",
            json={
                "job_description": jd,
                "title": "Senior Backend Engineer",
                "company": "PastedCo",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"]
    assert body["job_title"] == "Senior Backend Engineer"
    assert body["job_company"] == "PastedCo"
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["filename"] == "alex.pdf"
    assert body["recommendations"][0]["coverage"][0]["status"] == "hit"
    assert body["tournament_ran"] is False
    assert body["tournament_comparisons"] == 0
    rank_mock.assert_called_once()
    # Synthetic job was cached and passed into ranking
    call_job = rank_mock.call_args.args[0]
    assert call_job.source == "paste"
    assert "Python" in call_job.description


def test_recommend_from_jd_empty_library_400(client: TestClient) -> None:
    response = client.post(
        "/library/recommend-from-jd",
        json={
            "job_description": (
                "A sufficiently long job description for a role that needs "
                "at least forty characters of pasted text."
            ),
            "title": "Engineer",
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("error") == "validation_error"
    assert "empty" in (body.get("message") or "").lower()
