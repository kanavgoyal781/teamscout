"""M29 location Require/Prefer: foreign-HQ remote excluded; region/worldwide/onsite pass."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
from app.schemas.jobs import Job, SearchParams
from app.services.jobs_svc.filters import apply_hard_filters, soft_boost_score
from app.services.jobs_svc.geo import job_geo_match, parse_country

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

def test_require_excludes_gurugram_hq_remote_no_region() -> None:
    jobs = [
        _job("gurg", loc="Gurugram, India", desc="Fully remote Python role. Competitive pay."),
        _job("us-on", loc="Austin, TX", desc="Onsite Python team.", remote="onsite"),
    ]
    params = SearchParams(location_country="US", location_country_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, params)
    assert [j.id for j in kept] == ["us-on"]
    assert dropped.hard_location == 1

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
