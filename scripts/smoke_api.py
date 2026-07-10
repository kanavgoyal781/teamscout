#!/usr/bin/env python3
"""Smoke-test core API flows via FastAPI TestClient."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

# Force in-memory SQLite so polluted process env / repo .env cannot open the live
# teamscout.db (same isolation rule as backend/tests/conftest.py).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
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

from fastapi.testclient import TestClient

from app.db.models import JobCache
from app.db.session import SessionLocal, init_db
from app.main import app
from app.schemas.jobs import Job, RankedJob, ScoreBreakdown
from app.schemas.resume import ResumeProfile

SAMPLE_PDF = BACKEND / "tests" / "fixtures" / "sample_resume.pdf"


def _step(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return passed


def main() -> int:
    init_db()
    results: list[bool] = []

    with TestClient(app) as client:
        health = client.get("/health")
        health_body = health.json() if health.status_code in {200, 503} else {}
        health_ok = "checks" in health_body and "db" in health_body
        results.append(
            _step(
                "GET /health",
                health_ok,
                f"status={health.status_code} ok={health_body.get('ok')}",
            )
        )

        profile = ResumeProfile(
            name="Jane Doe",
            title="Senior Backend Engineer",
            years_of_experience=8,
            location="San Francisco, CA",
            skills=["Python", "FastAPI", "PostgreSQL"],
            work_experience=[],
            summary="Backend engineer",
        )
        pdf_bytes = SAMPLE_PDF.read_bytes() if SAMPLE_PDF.exists() else b"%PDF-1.4 smoke"
        with patch("app.api.routers.resumes.parser.parse_resume_file", return_value=("smoke-hash-1", profile)):
            upload = client.post(
                "/resumes/upload",
                files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
            )
        results.append(_step("POST /resumes/upload", upload.status_code == 200))
        resume_id = upload.json().get("id", "") if upload.status_code == 200 else ""

        confirm = client.put(
            f"/resumes/{resume_id}/confirm",
            json={"title": "Senior Backend Engineer", "location": "Remote", "skills": ["Python", "FastAPI"]},
        )
        results.append(_step("PUT /resumes/{id}/confirm", confirm.status_code == 200 and confirm.json().get("confirmed")))

        job = Job(
            id="smoke-job-1",
            source="fixture",
            source_job_id="smoke-fixture-1",
            title="Backend Engineer",
            company="Acme",
            location="Remote",
            description="Python FastAPI PostgreSQL",
            apply_url="https://example.com/apply",
            posted_at=None,
            skills=["Python", "FastAPI"],
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
        from app.services.jobs import JobFetchResult
        with patch("app.api.routers.searches.jobs.fetch_jobs_detailed", return_value=JobFetchResult(jobs=[job])):
            with patch("app.api.routers.searches.ranking.rank_jobs", return_value=[ranked]):
                search = client.post("/searches", json={"resume_id": resume_id})
        results.append(_step("POST /searches", search.status_code == 200 and len(search.json().get("results", [])) >= 1))

        with patch("app.services.library_store.parser.parse_resume_file", return_value=("lib-smoke-hash", profile)):
            library_upload = client.post(
                "/library/upload",
                files={"files": ("library.pdf", pdf_bytes, "application/pdf")},
            )
        results.append(_step("POST /library/upload", library_upload.status_code == 200))

        library_list = client.get("/library/resumes")
        results.append(
            _step(
                "GET /library/resumes",
                library_list.status_code == 200 and library_list.json().get("total", 0) >= 1,
            )
        )

        db = SessionLocal()
        try:
            db.add(
                JobCache(
                    job_id=job.id,
                    source=job.source,
                    source_job_id=job.source_job_id,
                    title=job.title,
                    payload_json=job.model_dump_json(),
                )
            )
            db.commit()
        finally:
            db.close()

        with patch("app.api.routers.library.jobs.fetch_jobs_for_intent", return_value=[job]):
            with patch("app.api.routers.library.ranking.rank_jobs", return_value=[ranked]):
                intent = client.post(
                    "/library/intent/search",
                    json={
                        "role": "Backend Engineer",
                        "years_of_experience": 5,
                        "location": "Remote",
                        "remote_preference": "remote",
                    },
                )
        results.append(_step("POST /library/intent/search", intent.status_code == 200))

        from app.schemas.library import RankedResumeRecommendation

        recommendation = RankedResumeRecommendation(
            resume_id="lib-resume-1",
            filename="library.pdf",
            match_score=88.0,
            score_breakdown=ScoreBreakdown(
                llm_fit=88,
                rrf_normalized=0.7,
                skill_jaccard=0.6,
                recency=0.0,
                experience_fit=0.8,
                final_score=88.0,
                matched_skills=["Python"],
                missing_skills=[],
                rationale="Python APIs at Acme",
            ),
            coverage=[],
        )
        with patch("app.api.routers.library.resume_ranking.rank_resumes_for_job", return_value=[recommendation]):
            recommend = client.post(f"/library/jobs/{job.id}/recommend-resumes")
        results.append(
            _step(
                "POST /library/jobs/{job_id}/recommend-resumes",
                recommend.status_code == 200 and len(recommend.json().get("recommendations", [])) >= 1,
            )
        )

    passed = all(results)
    print(f"\nRESULT: {sum(results)}/{len(results)} steps passed")
    if not passed:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())