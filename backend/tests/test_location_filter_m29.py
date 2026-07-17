"""M29 location matrix: Require hard-drops only foreign-HQ + no matching region."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
import pytest
from app.schemas.jobs import Job, SearchParams
from app.services.jobs_svc.filters import apply_hard_filters, soft_boost_score
from app.services.jobs_svc.geo import job_geo_match, parse_country, region_countries

def _job(jid: str, *, loc: str, desc: str, remote: str = "remote") -> Job:
    return Job(
        id=jid, source="f", source_job_id=jid, title="Engineer", company="Co",
        location=loc, description=desc, apply_url=f"https://x/{jid}",
        posted_at=datetime.now(UTC) - timedelta(days=1), skills=["Python"],
        remote_mode=remote, employment_type="fulltime",
    )

def _require_us() -> SearchParams:
    return SearchParams(location_country="US", location_country_pref="hard", include_worldwide_remote=True, use_expand=False)

# --- extractors ---
@pytest.mark.parametrize(
    "text,expect",
    [
        ("Seattle, WA", "US"),
        ("United States", "US"),
        ("San Francisco, CA", "US"),
        ("Chicago, IL", "US"),
        ("Indianapolis, IN", "US"),
        ("Wilmington, DE", "US"),
        ("Austin, TX", "US"),
        ("Gurugram, India", "IN"),
        ("Remote US", "US"),
        ("Canada", "CA"),
        ("Germany", "DE"),
        ("Remote", None),
        ("", None),
    ],
)
def test_parse_country_matrix(text: str, expect: str | None) -> None:
    assert parse_country(text) == expect

def test_region_iso_multi_list() -> None:
    codes = region_countries("Open to candidates in US, UK, and Canada. Python.")
    assert "US" in codes and "GB" in codes and "CA" in codes
    assert "US" in region_countries("Hiring region: US/UK/CA remote.")

def test_region_allcaps_english_in_not_india() -> None:
    d = "WE ARE HIRING. EXPERIENCE IN PYTHON. IT IS A FULLY REMOTE ROLE."
    codes = region_countries(d)
    assert "IN" not in codes and "IT" not in codes

# --- job_geo_match decision matrix ---
@pytest.mark.parametrize(
    "loc,desc,remote,expect",
    [
        # keep: match / worldwide / unknown
        ("Austin, TX", "Onsite Python team.", "onsite", "match"),
        ("San Francisco, CA", "Onsite ML.", "onsite", "match"),
        ("Chicago, IL", "Hybrid data.", "hybrid", "match"),
        ("Remote", "Hiring across Northern America and LATAM.", "remote", "match"),
        ("Remote", "US timezones preferred. Python.", "remote", "match"),
        ("Remote", "Americas and Europe. Python.", "remote", "match"),
        ("Remote", "Worldwide remote. Work from anywhere.", "remote", "worldwide"),
        ("Gurugram, India", "Remote. Hiring in US, UK, and Canada.", "remote", "match"),
        ("Remote", "Fully remote. Competitive pay.", "remote", "unknown"),
        # skeptic: Europe/EMEA mention WITHOUT foreign HQ location → unknown (keep)
        ("Remote", "Collaborate with teams in Europe. Fully remote Python role.", "remote", "unknown"),
        ("Remote", "EMEA collaboration; distributed product team. Remote.", "remote", "unknown"),
        ("Remote", "WE ARE HIRING. EXPERIENCE IN PYTHON. IT IS REMOTE.", "remote", "unknown"),
        # hard-drop: foreign HQ, no matching region
        ("Gurugram, India", "Fully remote Python role. Competitive pay.", "remote", "hq_mismatch"),
        ("Gurugram", "Remote role. No region stated.", "remote", "hq_mismatch"),
        ("Berlin, Germany", "EMEA only. Remote within Europe.", "remote", "hq_mismatch"),
        ("Bangalore, India", "APAC remote engineering.", "remote", "hq_mismatch"),
    ],
)
def test_job_geo_match_matrix(loc: str, desc: str, remote: str, expect: str) -> None:
    assert job_geo_match(
        user_country="US", job_location=loc, job_description=desc, remote_mode=remote,
    ) == expect

def test_job_geo_match_skip_no_user() -> None:
    assert job_geo_match(user_country=None, job_location="x", job_description="y", remote_mode="remote") == "skip"

# --- apply_hard_filters Require path ---
def test_require_matrix_keeps_and_drops() -> None:
    jobs = [
        _job("sf", loc="San Francisco, CA", desc="Onsite ML.", remote="onsite"),
        _job("chi", loc="Chicago, IL", desc="Hybrid.", remote="hybrid"),
        _job("am", loc="Remote", desc="Northern America and LATAM. Python."),
        _job("ww", loc="Remote", desc="Worldwide. Work from anywhere."),
        _job("eu-collab", loc="Remote", desc="Collaborate with teams in Europe. Fully remote."),
        _job("caps", loc="Remote", desc="EXPERIENCE IN PYTHON. IT IS REMOTE."),
        _job("gurg-iso", loc="Gurugram, India", desc="Remote. Hiring in US, UK, and Canada."),
        _job("gurg", loc="Gurugram, India", desc="Fully remote. No region."),
        _job("berlin", loc="Berlin, Germany", desc="EMEA only. Remote within Europe."),
    ]
    kept, dropped = apply_hard_filters(jobs, _require_us())
    ids = {j.id for j in kept}
    assert {"sf", "chi", "am", "ww", "eu-collab", "caps", "gurg-iso"} <= ids
    assert "gurg" not in ids and "berlin" not in ids
    assert dropped.hard_location == 2

def test_prefer_demotes_hq_mismatch_not_drop() -> None:
    bad = _job("gurg", loc="Gurugram, Haryana, India", desc="Remote Python. No region stated.")
    good = _job("us", loc="Remote", desc="US timezones preferred. Python.")
    params = SearchParams(location_country="US", location_country_pref="soft", use_expand=False)
    kept, dropped = apply_hard_filters([bad, good], params)
    assert len(kept) == 2 and dropped.hard_location == 0
    assert soft_boost_score(good, params, 80.0) > soft_boost_score(bad, params, 80.0)
