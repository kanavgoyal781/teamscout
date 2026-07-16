"""M18: multi-source registry adapters, isolation, filters, cache, slug config."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.schemas.jobs import Job, SearchParams
from app.schemas.resume import ResumeProfile
from app.services import job_dedup, jobs
from app.services.jobs_svc.sources import FetchCriteria, fetch_from_registry
from app.services.jobs_svc.sources.sources import (
    AdzunaSource,
    AshbySource,
    GreenhouseSource,
    LeverSource,
    RemoteOKSource,
    RemotiveSource,
    _ashby_remote,
)
from app.services.jobs_svc.sources.util import (
    job_matches_criteria,
    load_ats_slugs,
    strip_html,
)

FIXTURES = Path(__file__).parent / "fixtures" / "job_sources"


def _profile(**kw) -> ResumeProfile:
    base = dict(title="Software Engineer", skills=["Python", "React"], location="United States")
    base.update(kw)
    return ResumeProfile(**base)


def _criteria(**kw) -> FetchCriteria:
    params = kw.pop("params", SearchParams(use_expand=False, date_window="month", remote_mode="any"))
    profile = kw.pop("profile", _profile())
    queries = kw.pop("queries", ["Software Engineer Python"])
    return FetchCriteria(profile=profile, params=params, queries=queries)


def _load(name: str):
    return json.loads((FIXTURES / name).read_text())


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload, *a, **k):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def get(self, *a, **k):
        return _FakeResp(self._payload)


def _patch_ats(monkeypatch, payload, slugs_key, slug):
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient(payload))
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.load_ats_slugs", lambda: {slugs_key: [slug]})
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.board_cache_get", lambda *a, **k: None)
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.board_cache_set", lambda *a, **k: None)
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.board_cache_delete", lambda *a, **k: None)

    class _Sess:
        def close(self):
            return None

    monkeypatch.setattr("app.db.session.SessionLocal", lambda: _Sess())


def test_greenhouse_adapter_and_html_unescape(monkeypatch):
    payload = _load("greenhouse_stripe.json")
    _patch_ats(monkeypatch, payload, "greenhouse", "stripe")
    # Bypass criteria filter for raw parse; assert unescape
    with patch("app.services.jobs_svc.sources.registry.filter_jobs", side_effect=lambda jobs, c: jobs):
        result = GreenhouseSource().fetch(_criteria(), db=None)
    assert result
    assert all(j.source == "greenhouse" and j.source_quality == "direct_ats" for j in result)
    assert all("&lt;" not in j.description for j in result)
    assert any(
        "Stripe" in j.description or "Who we are" in j.description or "financial" in j.description.lower()
        for j in result
    )


def test_lever_adapter_from_fixture(monkeypatch):
    _patch_ats(monkeypatch, _load("lever_spotify.json"), "lever", "spotify")
    result = LeverSource().fetch(_criteria(), db=None)
    assert result and all(j.source == "lever" for j in result)


def test_ashby_hybrid_prefers_workplace_type(monkeypatch):
    _patch_ats(monkeypatch, _load("ashby_notion.json"), "ashby", "notion")
    result = AshbySource().fetch(_criteria(), db=None)
    assert result
    hybrid = next(j for j in result if "Hybrid" in (_load("ashby_notion.json")["jobs"][0]["workplaceType"]))
    # first fixture row is hybrid with isRemote true
    assert hybrid.remote_mode == "hybrid"
    assert _ashby_remote({"workplaceType": "Hybrid", "isRemote": True}) == (None, "hybrid")


def test_remotive_adapter_from_fixture(monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient(_load("remotive.json"))
    )
    result = RemotiveSource().fetch(_criteria(), db=None)
    assert result and all(j.source == "remotive" for j in result)


def test_remoteok_adapter_from_fixture(monkeypatch):
    monkeypatch.setattr(
        "app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient(_load("remoteok.json"))
    )
    result = RemoteOKSource().fetch(_criteria(), db=None)
    assert result and all(j.source == "remoteok" for j in result)


def test_adzuna_adapter_from_fixture(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "app")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(
        "app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient(_load("adzuna.json"))
    )
    result = AdzunaSource().fetch(_criteria(), db=None)
    assert len(result) == 1 and result[0].source == "adzuna"


def test_registry_isolation_one_source_raises(monkeypatch):
    from app.services.jobs_svc.sources import registry as reg

    class Ok:
        name, cost_free, source_quality = "ok_src", True, "feed"

        def is_configured(self):
            return True

        def is_enabled_for(self, c):
            return True

        def fetch(self, c, db=None):
            return [
                Job(
                    id="1",
                    source="ok_src",
                    source_job_id="1",
                    source_quality="feed",
                    title="Python Engineer",
                    company="Co",
                    location="Remote",
                    description="Python work",
                    apply_url="https://example.com/1",
                    posted_at=datetime.now(UTC),
                )
            ]

    class Boom:
        name, cost_free, source_quality = "boom", True, "feed"

        def is_configured(self):
            return True

        def is_enabled_for(self, c):
            return True

        def fetch(self, c, db=None):
            raise KeyError("explode")  # broader than RuntimeError

    monkeypatch.setattr(reg, "enabled_sources", lambda c: [Boom(), Ok()])

    class Trace:
        input_tokens = output_tokens = 0
        status = "ok"
        error_type = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    monkeypatch.setattr("app.services.ops.observability.traced_call", lambda *a, **k: Trace())
    jobs_out, counts, errors = fetch_from_registry(_criteria(), db=None)
    assert len(jobs_out) == 1
    assert counts["boom"].errors == 1
    assert counts["ok_src"].fetched == 1
    assert counts["ok_src"].kept_after_filters == 1
    assert errors


def test_dedup_prefers_direct_ats_over_aggregator():
    posted = datetime.now(UTC) - timedelta(days=1)
    ats = Job(
        id="ats",
        source="greenhouse",
        source_job_id="g1",
        source_quality="direct_ats",
        title="Backend Engineer",
        company="Acme",
        location="SF",
        description="Python",
        apply_url="https://boards.greenhouse.io/x",
        posted_at=posted,
    )
    agg = Job(
        id="agg",
        source="jsearch",
        source_job_id="j1",
        source_quality="aggregator",
        title="Backend Engineer",
        company="Acme",
        location="SF",
        description="Python",
        apply_url="https://example.com/j",
        posted_at=posted - timedelta(days=2),
    )
    kept, dropped = job_dedup.dedupe_exact([agg, ats])
    assert len(kept) == 1 and kept[0].id == "ats" and dropped.exact_duplicate == 1


def test_title_filter_keeps_swe_family_roles():
    crit = _criteria()
    now = datetime.now(UTC)

    def mk(title, desc="Build platforms for customers.", loc="Remote"):
        return Job(
            id=title[:40],
            source="greenhouse",
            source_job_id=title[:40],
            source_quality="direct_ats",
            title=title,
            company="X",
            location=loc,
            description=desc,
            apply_url="https://example.com",
            posted_at=now,
        )

    # Title-primary positives for SWE+Python
    for title in (
        "Backend Engineer",
        "Full Stack Developer",
        "Machine Learning Engineer",
        "Software Engineer",
        "ML Engineer",
    ):
        assert job_matches_criteria(mk(title), crit), title
    # Negatives: generic engineer/developer/development without tech title signal
    for title, desc in (
        ("Business Development Representative", "Sell enterprise deals."),
        ("Curriculum Developer", "Design training curriculum."),
        ("Sales Engineer", "Support sales demos for enterprise buyers."),
        ("Account Executive", "Partner with engineering teams to close deals."),
        ("Hardware Engineer", "PCB and silicon validation."),
        ("Barista", "Coffee and latte art"),
    ):
        assert not job_matches_criteria(mk(title, desc=desc), crit), title
    # Skills may still match description when title is generic tech staff
    assert job_matches_criteria(
        mk("Member of Technical Staff", desc="Must know Python and distributed systems."),
        crit,
    )


def test_post_fetch_hard_remote_and_recency():
    now = datetime.now(UTC)
    crit = _criteria(
        params=SearchParams(remote_mode="remote", remote_mode_pref="hard", date_window="week", use_expand=False)
    )
    remote = Job(
        id="1",
        source="gh",
        source_job_id="1",
        source_quality="direct_ats",
        title="Backend Engineer",
        company="X",
        location="Remote",
        description="Systems",
        apply_url="https://x.com",
        posted_at=now,
        remote_mode="remote",
    )
    onsite = remote.model_copy(update={"id": "2", "remote_mode": "onsite", "location": "New York, NY"})
    stale = remote.model_copy(update={"id": "3", "posted_at": now - timedelta(days=40)})
    undated = remote.model_copy(update={"id": "4", "posted_at": None})
    assert job_matches_criteria(remote, crit)
    assert not job_matches_criteria(onsite, crit)
    assert not job_matches_criteria(stale, crit)
    assert job_matches_criteria(undated, crit)  # null posted_at kept


def test_location_filter_us_profile_drops_japan():
    crit = _criteria(profile=_profile(location="United States"))
    now = datetime.now(UTC)
    jp = Job(
        id="1",
        source="gh",
        source_job_id="1",
        source_quality="direct_ats",
        title="Backend Engineer",
        company="X",
        location="Tokyo, Japan",
        description="Systems",
        apply_url="https://x.com",
        posted_at=now,
    )
    sf = jp.model_copy(update={"id": "2", "location": "San Francisco, CA"})
    assert not job_matches_criteria(jp, crit)
    assert job_matches_criteria(sf, crit)


def test_strip_html_unescapes_entities():
    assert "&lt;" not in strip_html("&lt;h2&gt;Hello&lt;/h2&gt;")
    assert "Hello" in strip_html("&lt;h2&gt;Hello&lt;/h2&gt;")


def test_board_cache_only_after_successful_parse(monkeypatch):
    """Invalid payload must not be cached; valid parse then cache."""
    set_calls: list = []
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.board_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.jobs_svc.sources.sources.board_cache_set", lambda *a, **k: set_calls.append(k if k else a)
    )
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.board_cache_delete", lambda *a, **k: None)

    class _Sess:
        def close(self):
            return None

    monkeypatch.setattr("app.db.session.SessionLocal", lambda: _Sess())
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.load_ats_slugs", lambda: {"greenhouse": ["x"]})
    # bad payload: no cache
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient({"nope": 1}))
    with pytest.raises(Exception):
        GreenhouseSource().fetch(_criteria(), db=None)
    assert set_calls == []
    # good payload: cache once
    set_calls.clear()
    good = _load("greenhouse_stripe.json")
    monkeypatch.setattr("app.services.jobs_svc.sources.sources.httpx.Client", lambda *a, **k: _FakeClient(good))
    GreenhouseSource().fetch(_criteria(), db=None)
    assert len(set_calls) == 1


def test_greenhouse_skips_bad_item_not_whole_board(monkeypatch):
    payload = {
        "jobs": [
            "not-a-dict",
            {
                "id": 1,
                "title": "Backend Engineer",
                "absolute_url": "https://example.com/1",
                "location": {"name": "Remote"},
                "content": "Python systems",
                "first_published": datetime.now(UTC).isoformat(),
            },
            {"id": 2, "title": "", "absolute_url": ""},  # missing required
        ]
    }
    _patch_ats(monkeypatch, payload, "greenhouse", "x")
    result = GreenhouseSource().fetch(_criteria(), db=None)
    assert len(result) == 1
    assert result[0].title == "Backend Engineer"


def test_ats_slug_config_has_100_plus():
    slugs = load_ats_slugs()
    assert sum(len(v) for v in slugs.values()) >= 100


def test_validate_ats_slugs_script_importable():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "validate_ats_slugs.py"
    spec = importlib.util.spec_from_file_location("validate_ats_slugs", path)
    assert spec and spec.loader
    mod = __import__("importlib").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.URLS) == {"greenhouse", "lever", "ashby"}


def test_merge_fetch_uses_registry(monkeypatch):
    profile = _profile()
    posted = datetime.now(UTC) - timedelta(days=1)
    board_job = Job(
        id="b1",
        source="greenhouse",
        source_job_id="g1",
        source_quality="direct_ats",
        title="Software Engineer",
        company="Stripe",
        location="Remote",
        description="Python backend engineer role",
        apply_url="https://example.com/g",
        posted_at=posted,
        skills=["Python"],
    )
    jsearch_job = Job(
        id="j1",
        source="jsearch",
        source_job_id="js1",
        source_quality="aggregator",
        title="Software Engineer",
        company="Acme",
        location="Remote",
        description="Python services",
        apply_url="https://example.com/j",
        posted_at=posted,
        skills=["Python"],
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.one_or_none.return_value = None
    monkeypatch.setattr(jobs.settings, "JOBS_API_KEY", "test-key")
    monkeypatch.setattr(jobs.settings, "JOBS_API_BASE", "https://jsearch.example")
    monkeypatch.setattr(jobs.settings, "JOBS_FETCH_TARGET", 50)

    def fake_reg(criteria, db=None):
        from app.schemas.jobs import SourceCounts

        return (
            [jsearch_job, board_job],
            {
                "jsearch": SourceCounts(fetched=1, kept_after_filters=1),
                "greenhouse": SourceCounts(fetched=1, kept_after_filters=1),
            },
            [],
        )

    monkeypatch.setattr("app.services.jobs_svc.sources.fetch_from_registry", fake_reg)
    result = jobs.fetch_jobs(profile, db, params=SearchParams(use_expand=False))
    assert {j.source for j in result} >= {"jsearch", "greenhouse"}


def test_token_boundary_no_ml_in_html():
    crit = _criteria(profile=_profile(title="ML Engineer", skills=["ML"], location="Remote"), queries=["ML Engineer"])
    now = datetime.now(UTC)
    # "html" should not match skill token "ml" via substring
    job = Job(
        id="1",
        source="gh",
        source_job_id="1",
        source_quality="direct_ats",
        title="HTML Email Designer",
        company="X",
        location="Remote",
        description="Design newsletters",
        apply_url="https://x.com",
        posted_at=now,
    )
    # role tokens include engineer from expand of ML Engineer - title has neither ml nor engineer as whole tokens
    # "html" contains "ml" as substring but token match should fail; "designer" not in role family enough
    # Actually role_tokens from "ML Engineer" expand includes engineer, ml, machine, learning...
    # title tokens: html, email, designer - no match; skills phrase_in_text("ML", ...) should not match html
    assert job_matches_criteria(job, crit) is False
