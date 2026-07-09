#!/usr/bin/env python3
"""Demo readiness check against a *deployed* TeamScout API.

Hits public HTTP only. API keys must already be configured on the server;
this script never reads or prints secrets.

Env (first wins):
  DEMO_API_BASE
  BACKEND_URL

Usage:
  DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check
  python3 scripts/demo_check.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "sample_resume.pdf"

try:
    import httpx
except ImportError:  # pragma: no cover - operator env
    print("FAIL: httpx is required (pip install httpx, or use backend venv)", file=sys.stderr)
    sys.exit(2)


def _base() -> str:
    raw = (os.environ.get("DEMO_API_BASE") or os.environ.get("BACKEND_URL") or "").strip()
    if not raw:
        print(
            "FAIL: set DEMO_API_BASE or BACKEND_URL to the deployed API origin "
            "(e.g. https://teamscout-api.fly.dev)",
            file=sys.stderr,
        )
        sys.exit(2)
    return raw.rstrip("/")


def _step(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return passed


def main() -> int:
    base = _base()
    print(f"demo-check: target={base}")
    results: list[bool] = []
    # Search can take a while (jobs fetch + embeddings + LLM rerank).
    timeout = httpx.Timeout(connect=15.0, read=300.0, write=60.0, pool=15.0)

    with httpx.Client(base_url=base, timeout=timeout, follow_redirects=True) as client:
        # 1) Health
        try:
            health = client.get("/health")
            body = health.json() if health.headers.get("content-type", "").startswith("application/json") else {}
            # Accept 200 (all green) or 503 (process up, integrations degraded) for connectivity.
            # For a *demo* we require ok=true so ranking E2E can succeed.
            health_ok = health.status_code in {200, 503} and isinstance(body, dict) and "checks" in body
            demo_ready = health.status_code == 200 and body.get("ok") is True
            results.append(
                _step(
                    "GET /health",
                    health_ok,
                    f"status={health.status_code} ok={body.get('ok')}",
                )
            )
            if health_ok and not demo_ready:
                results.append(
                    _step(
                        "health integrations configured",
                        False,
                        "ok!=true — set LLM/embeddings/jobs/sumble secrets on the server "
                        "before full demo E2E",
                    )
                )
            else:
                results.append(_step("health integrations configured", demo_ready, f"ok={body.get('ok')}"))
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            results.append(_step("GET /health", False, type(exc).__name__ + ": " + str(exc)))
            results.append(_step("health integrations configured", False, "skipped"))
            return 1 if not all(results) else 0

        if not SAMPLE.is_file():
            results.append(_step("sample resume present", False, str(SAMPLE)))
            return 1
        results.append(_step("sample resume present", True, SAMPLE.name))

        # 2) Upload
        resume_id = ""
        try:
            with SAMPLE.open("rb") as fh:
                upload = client.post(
                    "/resumes/upload",
                    files={"file": (SAMPLE.name, fh, "application/pdf")},
                )
            upload_ok = upload.status_code == 200
            upload_body = upload.json() if upload_ok else {}
            resume_id = str(upload_body.get("id") or "")
            profile = upload_body.get("profile") or {}
            results.append(
                _step(
                    "POST /resumes/upload",
                    upload_ok and bool(resume_id),
                    f"status={upload.status_code} id={resume_id[:12] + '…' if len(resume_id) > 12 else resume_id}",
                )
            )
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            results.append(_step("POST /resumes/upload", False, str(exc)))
            return 1

        if not resume_id:
            return 1

        # 3) Confirm
        title = (profile.get("title") or "Software Engineer").strip() or "Software Engineer"
        location = (profile.get("location") or "Remote").strip() or "Remote"
        skills = profile.get("skills") or ["Python"]
        if not isinstance(skills, list) or not skills:
            skills = ["Python"]
        try:
            confirm = client.put(
                f"/resumes/{resume_id}/confirm",
                json={"title": title, "location": location, "skills": skills},
            )
            confirm_body = confirm.json() if confirm.status_code == 200 else {}
            results.append(
                _step(
                    "PUT /resumes/{id}/confirm",
                    confirm.status_code == 200 and bool(confirm_body.get("confirmed")),
                    f"status={confirm.status_code}",
                )
            )
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            results.append(_step("PUT /resumes/{id}/confirm", False, str(exc)))
            return 1

        # 4) Search top-10 with score_breakdown
        try:
            t0 = time.monotonic()
            search = client.post("/searches", json={"resume_id": resume_id})
            elapsed = time.monotonic() - t0
            search_ok = search.status_code == 200
            search_body = search.json() if search_ok else {}
            results_list = search_body.get("results") if search_ok else None
            if not isinstance(results_list, list):
                results_list = []
            n = len(results_list)
            # Require at least 1 result; prefer up to top-10. Fail if empty when health was green.
            has_results = n >= 1
            breakdown_ok = True
            missing = 0
            for item in results_list[:10]:
                bd = (item or {}).get("score_breakdown") if isinstance(item, dict) else None
                if not isinstance(bd, dict) or "final_score" not in bd:
                    breakdown_ok = False
                    missing += 1
            results.append(
                _step(
                    "POST /searches",
                    search_ok and has_results,
                    f"status={search.status_code} n={n} elapsed_s={elapsed:.1f}",
                )
            )
            results.append(
                _step(
                    "score_breakdown on results",
                    search_ok and has_results and breakdown_ok,
                    f"checked={min(n, 10)} missing_breakdown={missing}",
                )
            )
            if search_ok and n > 0:
                top = results_list[0]
                job = (top or {}).get("job") or {}
                bd = (top or {}).get("score_breakdown") or {}
                print(
                    f"  top[0]: {job.get('title', '?')} @ {job.get('company', '?')} "
                    f"final_score={bd.get('final_score')}"
                )
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            results.append(_step("POST /searches", False, str(exc)))
            results.append(_step("score_breakdown on results", False, "skipped"))

    failed = sum(1 for r in results if not r)
    print(f"demo-check: {len(results) - failed}/{len(results)} steps passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
