#!/usr/bin/env python3
"""Smoke test Sumble REST client against the live API."""

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
    print(f"Sumble smoke: org lookup for {company!r}")

    org = sumble.lookup_organization(company)
    print(f"  organization_id={org.organization_id} name={org.name!r}")

    people, credits = sumble.search_people(
        organization_id=org.organization_id,
        team_name="Engineering",
        department="Engineering",
        likely_hiring_titles=["Engineering Manager", "Director of Engineering"],
    )
    print(f"  people_found={len(people)} credits_used={credits}")
    for person in people[:3]:
        print(
            f"    - {person.name} | {person.title} | "
            f"{person.seniority} | team={person.team}"
        )

    if os.environ.get("SMOKE_SUMBLE_REVEAL", "").lower() in {"1", "true", "yes"}:
        if people:
            email, reveal_credits = sumble.reveal_email(people[0].person_id)
            print(f"  email_reveal credits_used={reveal_credits} email={email!r}")
        else:
            print("  email_reveal skipped (no people returned)")
    else:
        print("  email_reveal skipped (set SMOKE_SUMBLE_REVEAL=true to charge credits)")

    print("Sumble smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())