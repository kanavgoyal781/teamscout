"""M29 location Require/Prefer: foreign-HQ remote excluded; region/worldwide/onsite pass."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
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

def test_parse_country_profile_us_and_india() -> None:
    assert parse_country("Seattle, WA") == "US"
    assert parse_country("United States") == "US"
    assert parse_country("Gurugram, India") == "IN"
    assert parse_country("Remote US") == "US"

def test_parse_country_us_city_state_not_foreign() -> None:
    """Skeptic: ', CA'/', IL'/', IN'/', DE' must not map to Canada/Israel/India/Germany."""
    assert parse_country("San Francisco, CA") == "US"
    assert parse_country("Chicago, IL") == "US"
    assert parse_country("Indianapolis, IN") == "US"
    assert parse_country("Wilmington, DE") == "US"
    assert parse_country("Austin, TX") == "US"
    # Full country names still work
    assert parse_country("Canada") == "CA"
    assert parse_country("Israel") == "IL"
    assert parse_country("Germany") == "DE"

def test_region_countries_iso_multi_list() -> None:
    codes = region_countries("Open to candidates in US, UK, and Canada. Python.")
    assert "US" in codes and "GB" in codes and "CA" in codes
    codes2 = region_countries("Hiring region: US/UK/CA remote.")
    assert "US" in codes2 and "GB" in codes2

def test_require_excludes_gurugram_hq_remote_no_region() -> None:
    jobs = [
        _job("gurg", loc="Gurugram, India", desc="Fully remote Python role. Competitive pay."),
        _job("us-on", loc="Austin, TX", desc="Onsite Python team.", remote="onsite"),
    ]
    params = SearchParams(location_country="US", location_country_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, params)
    assert [j.id for j in kept] == ["us-on"]
    assert dropped.hard_location == 1

def test_require_keeps_us_city_state_onsite() -> None:
    jobs = [
        _job("sf", loc="San Francisco, CA", desc="Onsite ML platform.", remote="onsite"),
        _job("chi", loc="Chicago, IL", desc="Hybrid data team.", remote="hybrid"),
        _job("gurg", loc="Gurugram, India", desc="Remote only. No region.", remote="remote"),
    ]
    params = SearchParams(location_country="US", location_country_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "sf" in ids and "chi" in ids
    assert "gurg" not in ids
    assert dropped.hard_location == 1

def test_require_keeps_gurugram_with_iso_multi_country_region() -> None:
    jobs = [
        _job("gurg-iso", loc="Gurugram, India", desc="Remote. Hiring in US, UK, and Canada. Python backend."),
    ]
    params = SearchParams(location_country="US", location_country_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, params)
    assert [j.id for j in kept] == ["gurg-iso"]
    assert dropped.hard_location == 0

def test_require_keeps_americas_region_and_worldwide() -> None:
    jobs = [
        _job("am", loc="Remote", desc="Hiring across Northern America and LATAM. Python backend."),
        _job("ww", loc="Remote", desc="Worldwide remote. Work from anywhere. Python."),
        _job("eu", loc="Berlin, Germany", desc="EMEA only. Remote within Europe."),
    ]
    params = SearchParams(location_country="US", location_country_pref="hard", include_worldwide_remote=True, use_expand=False)
    kept, dropped = apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "am" in ids and "ww" in ids
    assert "eu" not in ids
    assert dropped.hard_location >= 1

def test_prefer_demotes_hq_mismatch_not_drop() -> None:
    bad = _job("gurg", loc="Gurugram, Haryana, India", desc="Remote Python. No region stated.")
    good = _job("us", loc="Remote", desc="US timezones preferred. Python.")
    params = SearchParams(location_country="US", location_country_pref="soft", use_expand=False)
    kept, dropped = apply_hard_filters([bad, good], params)
    assert len(kept) == 2 and dropped.hard_location == 0
    assert soft_boost_score(good, params, 80.0) > soft_boost_score(bad, params, 80.0)

def test_job_geo_match_edges() -> None:
    assert job_geo_match(user_country="US", job_location="Remote", job_description="Americas and Europe", remote_mode="remote") == "match"
    assert job_geo_match(user_country="US", job_location="Gurugram", job_description="Remote role", remote_mode="remote") == "hq_mismatch"
    assert job_geo_match(user_country="US", job_location="Remote", job_description="Worldwide", remote_mode="remote") == "worldwide"
    assert job_geo_match(user_country=None, job_location="x", job_description="y", remote_mode="remote") == "skip"
    assert job_geo_match(user_country="US", job_location="San Francisco, CA", job_description="Onsite", remote_mode="onsite") == "match"
    assert job_geo_match(user_country="US", job_location="Gurugram, India", job_description="US, UK, Canada remote", remote_mode="remote") == "match"
