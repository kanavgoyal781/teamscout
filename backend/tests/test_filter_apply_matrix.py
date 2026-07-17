"""Every SearchFilters control maps to real hard/soft/query behavior on the shipped path."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
import pytest
from app.schemas.jobs import Job, SearchParams
from app.schemas.resume import ResumeProfile
from app.services.jobs_svc.filters import apply_hard_filters, jsearch_params_from_search, soft_boost_score
from app.services.jobs_svc.fetch import resolve_search_queries

def _job(jid: str, **kw) -> Job:
    defaults = dict(
        id=jid, source="f", source_job_id=jid, title="Engineer", company="Co",
        location="Austin, TX", description="Python backend. Full-time.", apply_url=f"https://x/{jid}",
        posted_at=datetime.now(UTC) - timedelta(days=1), skills=["Python"],
        remote_mode="remote", employment_type="fulltime", seniority="senior",
        salary_min=120_000.0, salary_unknown=False,
    )
    defaults.update(kw)
    return Job(**defaults)

def test_date_window_hard_drops_stale() -> None:
    jobs = [
        _job("fresh", posted_at=datetime.now(UTC) - timedelta(days=1)),
        _job("stale", posted_at=datetime.now(UTC) - timedelta(days=40)),
    ]
    kept, dropped = apply_hard_filters(jobs, SearchParams(date_window="week", use_expand=False))
    assert [j.id for j in kept] == ["fresh"]
    assert dropped.recency == 1
    jp = jsearch_params_from_search(SearchParams(date_window="week"))
    assert jp["date_posted"] == "week"

def test_remote_require_and_prefer() -> None:
    jobs = [_job("r", remote_mode="remote"), _job("o", remote_mode="onsite", location="NYC")]
    hard = SearchParams(remote_mode="remote", remote_mode_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, hard)
    assert [j.id for j in kept] == ["r"]
    assert dropped.hard_remote == 1
    soft = SearchParams(remote_mode="remote", remote_mode_pref="soft", use_expand=False)
    k2, d2 = apply_hard_filters(jobs, soft)
    assert len(k2) == 2 and d2.hard_remote == 0
    assert soft_boost_score(jobs[0], soft, 80.0) > soft_boost_score(jobs[1], soft, 80.0)
    assert jsearch_params_from_search(hard).get("remote_jobs_only") == "true"
    assert "remote_jobs_only" not in jsearch_params_from_search(soft)

def test_employment_require_and_prefer() -> None:
    jobs = [
        _job("ft", employment_type="fulltime"),
        _job("ct", employment_type="contractor", description="Contract Python role."),
    ]
    hard = SearchParams(employment_type="fulltime", employment_type_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, hard)
    assert [j.id for j in kept] == ["ft"]
    assert dropped.hard_employment == 1
    soft = SearchParams(employment_type="fulltime", employment_type_pref="soft", use_expand=False)
    k2, d2 = apply_hard_filters(jobs, soft)
    assert len(k2) == 2 and d2.hard_employment == 0
    assert soft_boost_score(jobs[0], soft, 80.0) > soft_boost_score(jobs[1], soft, 80.0)
    jp = jsearch_params_from_search(hard)
    assert jp["employment_types"] == "FULLTIME"

def test_seniority_require_and_prefer() -> None:
    jobs = [
        _job("s", title="Senior Engineer", seniority="senior"),
        _job("j", title="Junior Engineer", seniority="junior"),
    ]
    hard = SearchParams(seniority="senior", seniority_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, hard)
    assert [j.id for j in kept] == ["s"]
    assert dropped.hard_seniority == 1
    soft = SearchParams(seniority="senior", seniority_pref="soft", use_expand=False)
    k2, d2 = apply_hard_filters(jobs, soft)
    assert len(k2) == 2 and d2.hard_seniority == 0
    assert soft_boost_score(jobs[0], soft, 80.0) > soft_boost_score(jobs[1], soft, 80.0)

def test_min_salary_require_and_prefer() -> None:
    jobs = [
        _job("low", salary_min=50_000.0, salary_unknown=False),
        _job("hi", salary_min=150_000.0, salary_unknown=False),
        _job("unk", salary_min=None, salary_unknown=True),
    ]
    hard = SearchParams(min_salary=100_000, min_salary_pref="hard", use_expand=False)
    kept, dropped = apply_hard_filters(jobs, hard)
    ids = {j.id for j in kept}
    assert ids == {"hi", "unk"}
    assert dropped.hard_salary == 1
    soft = SearchParams(min_salary=100_000, min_salary_pref="soft", use_expand=False)
    k2, d2 = apply_hard_filters(jobs, soft)
    assert len(k2) == 3 and d2.hard_salary == 0
    assert soft_boost_score(jobs[1], soft, 80.0) > soft_boost_score(jobs[0], soft, 80.0)

def test_location_require_prefer_and_worldwide() -> None:
    us = _job("us", location="Austin, TX", description="Onsite in Austin.")
    gurg = _job("g", location="Gurugram, India", description="Remote only. No region.")
    ww = _job("ww", location="Remote", description="Worldwide remote. Work from anywhere.")
    hard = SearchParams(
        location_country="US", location_country_pref="hard",
        include_worldwide_remote=True, use_expand=False,
    )
    kept, dropped = apply_hard_filters([us, gurg, ww], hard)
    ids = {j.id for j in kept}
    assert "us" in ids and "ww" in ids and "g" not in ids
    assert dropped.hard_location >= 1
    hard_no_ww = SearchParams(
        location_country="US", location_country_pref="hard",
        include_worldwide_remote=False, use_expand=False,
    )
    k2, d2 = apply_hard_filters([ww], hard_no_ww)
    assert "ww" not in {j.id for j in k2}
    assert d2.hard_location >= 1
    soft = SearchParams(location_country="US", location_country_pref="soft", use_expand=False)
    k3, d3 = apply_hard_filters([us, gurg], soft)
    assert len(k3) == 2 and d3.hard_location == 0
    assert soft_boost_score(us, soft, 80.0) > soft_boost_score(gurg, soft, 80.0)

def test_any_modes_are_noops_for_hard_drops() -> None:
    jobs = [
        _job("a", remote_mode="onsite", employment_type="contractor", seniority="junior", salary_min=40_000.0),
        _job("b", remote_mode="remote", employment_type="fulltime", seniority="senior", salary_min=200_000.0),
    ]
    params = SearchParams(
        remote_mode="any", employment_type="any", seniority="any",
        min_salary=None, location_country=None, use_expand=False,
    )
    kept, dropped = apply_hard_filters(jobs, params)
    assert len(kept) == 2
    assert dropped.hard_remote == 0 and dropped.hard_employment == 0
    assert dropped.hard_seniority == 0 and dropped.hard_salary == 0 and dropped.hard_location == 0

def test_use_expand_flag_selects_query_path() -> None:
    profile = ResumeProfile(title="Data Scientist", skills=["Python", "SQL"], location="United States")
    with_expand = SearchParams(use_expand=True)
    without = SearchParams(use_expand=False)
    db = None  # expand may need db — call resolve and mock expand
    from unittest.mock import MagicMock, patch
    mock_db = MagicMock()
    with patch("app.services.ranking.query_expand.expand_queries", return_value=["expanded q1", "expanded q2"]) as exp:
        q1 = resolve_search_queries(profile, mock_db, params=with_expand)
        exp.assert_called_once()
        assert q1 == ["expanded q1", "expanded q2"]
    q2 = resolve_search_queries(profile, mock_db, params=without)
    assert any("Data Scientist" in q or "data scientist" in q.lower() for q in q2)
    assert all("expanded" not in q for q in q2)
