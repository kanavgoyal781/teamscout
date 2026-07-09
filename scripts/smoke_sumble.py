#!/usr/bin/env python3
"""Smoke test Sumble REST client against the live API.

Exercises M5/M6 paths:
  org resolve (domain/name) → job-post match → related_people (primary)
  → people filter fallback → optional gated email enrich.

All credit-costing helpers return (result, credits_used) tuples (M6).
Prints credits at each step. Exit 0 with SKIP when SUMBLE_API_KEY is missing.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ensure_db
from app.services import sumble


def main() -> int:
    if not is_set(settings.SUMBLE_API_KEY):
        print("SKIP: SUMBLE_API_KEY not set — smoke_sumble.py exiting 0")
        return 0

    # Ensure M8 traces/embedding_cache tables exist (scripts skip FastAPI lifespan).
    ensure_db()

    company = os.environ.get("SMOKE_SUMBLE_COMPANY", "Stripe")
    jd_title = os.environ.get("SMOKE_SUMBLE_JD_TITLE", "Software Engineer")
    apply_url = os.environ.get("SMOKE_SUMBLE_APPLY_URL", "https://jobs.lever.co/stripe/xxxx")
    print(f"Sumble smoke: org lookup for {company!r} (apply_url heuristic if present)")

    org, org_credits = sumble.lookup_organization(company, apply_url)
    print(
        f"  organization_id={org.organization_id} name={org.name!r} "
        f"credits_used={org_credits}"
    )

    # 1. Preferred: search org job posts then find-related-people
    print("  step: search org job posts for match (title sim + company)")
    matched_id, job_credits = sumble.find_best_matching_job_post(
        org.organization_id, jd_title, company
    )
    path_used = "Matched posted role"
    people: list[sumble.SumblePerson] = []
    path_credits = job_credits
    if matched_id is not None:
        print(f"  matched sumble job_id={matched_id} job_search_credits={job_credits}")
        people, related_credits = sumble.get_related_people_for_job(matched_id)
        path_credits = job_credits + related_credits
        print(
            f"  find-related-people people_found={len(people)} "
            f"related_credits={related_credits} path_credits={path_credits}"
        )
        if not people:
            path_used = "Matched by role filters"
            print("  matched job but empty related_people — will fallback")
    else:
        path_used = "Matched by role filters"
        print(f"  no strong job post match (job_search_credits={job_credits}) — will fallback")

    # 2. Fallback people/find (always exercise when primary yielded no people)
    if not people:
        print("  step: fallback people/find with function/level")
        people, search_credits = sumble.search_people(
            organization_id=org.organization_id,
            team_name="Engineering",
            department="Engineering",
            likely_hiring_titles=["Engineering Manager", "Software Engineer"],
        )
        path_credits = job_credits + search_credits
        print(
            f"  people_found={len(people)} search_credits={search_credits} "
            f"path_credits={path_credits} path={path_used}"
        )
    else:
        print(f"  primary path used: {path_used} (path_credits={path_credits})")
        fb_people, fb_c = sumble.search_people(
            organization_id=org.organization_id,
            team_name="",
            department="Engineering",
            likely_hiring_titles=["Software Engineer"],
        )
        print(f"  (also exercised fallback people/find: {len(fb_people)} people, credits={fb_c})")

    for person in people[:3]:
        print(
            f"    - {person.name} | {person.title} | "
            f"{person.seniority} | func={person.job_function}"
        )

    total = org_credits + path_credits
    print(f"  aggregate (org + path) credits_used≈{total}")

    # 3. Gated enrich
    if os.environ.get("SMOKE_SUMBLE_REVEAL", "").lower() in {"1", "true", "yes"}:
        if people:
            email, reveal_credits = sumble.reveal_email(people[0].person_id)
            print(f"  email_reveal credits_used={reveal_credits} email={email!r}")
        else:
            print("  email_reveal skipped (no people returned)")
    else:
        print("  email_reveal skipped (set SMOKE_SUMBLE_REVEAL=true to charge credits)")

    print("Sumble smoke: OK (all steps, credits logged via sumble.credit_result)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
