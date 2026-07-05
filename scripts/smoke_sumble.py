#!/usr/bin/env python3
"""Smoke test Sumble REST client against the live API.

Exercises per Milestone 5:
org resolve (domain/name) → job match search → find-related-people (primary)
→ people/find fallback → gated email enrich.
Prints credits_used / credits_remaining (logged + returned) at each step.
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
from app.services import sumble


def main() -> int:
    if not is_set(settings.SUMBLE_API_KEY):
        print("SKIP: SUMBLE_API_KEY not set — smoke_sumble.py exiting 0")
        return 0

    company = os.environ.get("SMOKE_SUMBLE_COMPANY", "Stripe")
    jd_title = os.environ.get("SMOKE_SUMBLE_JD_TITLE", "Software Engineer")
    print(f"Sumble smoke: org lookup for {company!r} (apply_url heuristic if present)")

    # Use a plausible apply_url to exercise domain derivation
    apply_url = os.environ.get("SMOKE_SUMBLE_APPLY_URL", "https://jobs.lever.co/stripe/xxxx")
    org = sumble.lookup_organization(company, apply_url)
    print(f"  organization_id={org.organization_id} name={org.name!r}")

    # 1. Preferred: search org job posts then find-related-people
    print("  step: search org job posts for match (title sim + company)")
    matched = sumble.find_best_matching_job_post(org.organization_id, jd_title, company)
    path_used = "Matched Sumble job post"
    people: list[sumble.SumblePerson] = []
    credits = 0
    if matched is not None:
        print(f"  matched sumble job_id={matched}")
        people, credits = sumble.get_related_people_for_job(matched)
        print(f"  find-related-people people_found={len(people)} credits_used={credits}")
    else:
        path_used = "Filtered by function/level"
        print("  no strong job post match — will fallback")

    # 2. Fallback demo (always exercise the people/find path too for smoke)
    if not people:
        print("  step: fallback people/find with function/level")
        people, credits = sumble.search_people(
            organization_id=org.organization_id,
            team_name="Engineering",
            department="Engineering",
            likely_hiring_titles=["Engineering Manager", "Software Engineer"],
        )
        print(f"  people_found={len(people)} credits_used={credits} path={path_used}")
    else:
        print(f"  primary path used: {path_used} (credits={credits})")
        # also exercise fallback explicitly for completeness
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