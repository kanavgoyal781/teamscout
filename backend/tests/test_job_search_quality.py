"""Hard/soft filters, salary unknown, dedup, facets, query-expand cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.schemas.jobs import Job, SearchParams
from app.schemas.resume import ResumeProfile
from app.services import job_dedup, job_facets, job_filters, query_expand


def _job(
    jid: str,
    *,
    title: str = "Engineer",
    company: str = "Acme",
    description: str = "Python backend role",
    location: str = "Remote",
    posted_days: int | None = 2,
    seniority: str | None = None,
    remote_mode: str | None = "remote",
    employment_type: str | None = "fulltime",
    salary_min: float | None = None,
    salary_unknown: bool = True,
    apply_url: str = "https://example.com/a",
) -> Job:
    posted = None if posted_days is None else datetime.now(UTC) - timedelta(days=posted_days)
    return Job(
        id=jid,
        source="fixture",
        source_job_id=jid,
        title=title,
        company=company,
        location=location,
        description=description,
        apply_url=apply_url,
        posted_at=posted,
        skills=["Python"],
        seniority=seniority,
        remote_mode=remote_mode,
        employment_type=employment_type,
        salary_min=salary_min,
        salary_unknown=salary_unknown,
    )


def test_hard_seniority_excludes() -> None:
    jobs = [
        _job("1", title="Senior Engineer", seniority="senior"),
        _job("2", title="Junior Engineer", seniority="junior"),
    ]
    params = SearchParams(seniority="senior", seniority_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    assert [j.id for j in kept] == ["1"]
    assert dropped.hard_seniority == 1


def test_soft_seniority_does_not_exclude() -> None:
    jobs = [
        _job("1", title="Senior Engineer", seniority="senior"),
        _job("2", title="Junior Engineer", seniority="junior"),
    ]
    params = SearchParams(seniority="senior", seniority_pref="soft", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    assert len(kept) == 2
    assert dropped.hard_seniority == 0
    boost_hi = job_filters.soft_boost_score(jobs[0], params, 80.0)
    boost_lo = job_filters.soft_boost_score(jobs[1], params, 80.0)
    assert boost_hi > boost_lo


def test_hard_remote_keeps_unknown() -> None:
    jobs = [
        _job("1", remote_mode="onsite", location="NYC"),
        _job("2", remote_mode="unknown", location=""),
        _job("3", remote_mode="remote", location="Remote"),
    ]
    params = SearchParams(remote_mode="remote", remote_mode_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "1" not in ids
    assert "2" in ids  # unknown kept
    assert "3" in ids
    assert dropped.hard_remote == 1


def test_hard_salary_keeps_unknown() -> None:
    jobs = [
        _job("1", salary_min=50_000, salary_unknown=False, description="Pay $50000"),
        _job("2", salary_min=None, salary_unknown=True, description="Competitive pay"),
        _job("3", salary_min=150_000, salary_unknown=False, description="Pay $150000"),
    ]
    params = SearchParams(min_salary=100_000, min_salary_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert ids == {"2", "3"}
    assert dropped.hard_salary == 1
    assert all(j.salary_unknown or (j.salary_min and j.salary_min >= 100_000) for j in kept if j.id != "2")


def test_soft_salary_boosts_known_match() -> None:
    low = _job("1", salary_min=50_000, salary_unknown=False)
    high = _job("2", salary_min=150_000, salary_unknown=False)
    unknown = _job("3", salary_unknown=True)
    params = SearchParams(min_salary=100_000, min_salary_pref="soft", use_expand=False)
    assert job_filters.soft_boost_score(high, params, 70.0) > job_filters.soft_boost_score(low, params, 70.0)
    # unknown not boosted
    assert job_filters.soft_boost_score(unknown, params, 70.0) == 70.0


def test_parse_salary_from_description() -> None:
    mn, unknown = job_filters.parse_salary_min(description="Salary $120k-$150k plus equity")
    assert not unknown
    assert mn is not None
    assert 100_000 <= mn <= 150_000


def test_annotate_remote_and_seniority() -> None:
    job = _job(
        "1", title="Senior Backend Engineer", location="San Francisco, CA", description="On-site team", remote_mode=None
    )
    ann = job_filters.annotate_job(job, is_remote_flag=False)
    assert ann.seniority == "senior"
    assert ann.remote_mode in {"onsite", "unknown"}


def test_exact_dedup_keeps_earliest_and_counts() -> None:
    older = _job("1", title="Backend Engineer", company="Acme Inc", posted_days=5)
    newer = _job("2", title="Backend  Engineer", company="Acme", posted_days=1)
    kept, dropped = job_dedup.dedupe_exact([newer, older])
    assert len(kept) == 1
    assert kept[0].id == "1"
    assert kept[0].duplicates_count == 2
    assert dropped.exact_duplicate == 1


def test_embedding_dedup_near_duplicates() -> None:
    a = _job(
        "a",
        title="ML Engineer",
        company="X",
        description="Build models with pytorch and deploy to production platforms daily.",
    )
    b = _job(
        "b",
        title="ML Engineer",
        company="Y",
        description="Build models with pytorch and deploy to production platforms daily!!",
    )
    c = _job("c", title="Barista", company="Cafe", description="Pour lattes and manage the espresso bar schedule.")

    def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        # near-identical for first two
        out = []
        for t in texts:
            if "latte" in t.lower() or "barista" in t.lower() or "espresso" in t.lower():
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([1.0, 0.0, 0.0])
        return out

    with patch.object(job_dedup.embeddings, "embed_batch", side_effect=fake_embed_batch):
        kept, dropped = job_dedup.dedupe_embeddings([a, b, c], threshold=0.97)
    assert len(kept) == 2
    assert dropped.embedding_duplicate == 1
    ids = {j.id for j in kept}
    assert "c" in ids


def test_facets_buckets() -> None:
    jobs = [
        _job(
            "1",
            company="Acme",
            seniority="senior",
            remote_mode="remote",
            salary_min=130_000,
            salary_unknown=False,
            posted_days=1,
        ),
        _job("2", company="Acme", seniority="junior", remote_mode="onsite", salary_unknown=True, posted_days=10),
        _job(
            "3",
            company="Beta",
            seniority="senior",
            remote_mode="remote",
            salary_min=90_000,
            salary_unknown=False,
            posted_days=2,
        ),
    ]
    facets = job_facets.compute_facets(jobs)
    assert any(b.value == "Acme" and b.count == 2 for b in facets.company)
    assert any(b.value == "senior" for b in facets.seniority)
    assert any(b.value == "unknown" for b in facets.salary_bucket)


def test_query_expand_cache_hit() -> None:
    profile = ResumeProfile(title="Data Scientist", skills=["Python", "SQL"], location="NYC", summary="ML")
    params = SearchParams(use_expand=True)
    db = MagicMock()
    # First call: no cache
    db.query.return_value.filter.return_value.one_or_none.return_value = None

    class FakeResp:
        variants = [
            query_expand._ExpandVariant(title="Data Scientist", skills=["Python"], query="Data Scientist Python"),
            query_expand._ExpandVariant(title="ML Engineer", skills=["PyTorch"], query="ML Engineer PyTorch"),
            query_expand._ExpandVariant(title="Applied Scientist", skills=["SQL"], query="Applied Scientist SQL"),
        ]

    with patch.object(query_expand.llm, "complete_json", return_value=FakeResp()) as mock_llm:
        q1 = query_expand.expand_queries(profile, db, params=params)
        assert len(q1) >= 3
        assert mock_llm.called
        # Simulate cache hit on second call
        cached_row = MagicMock()
        cached_row.expansions_json = __import__("json").dumps(q1)
        db.query.return_value.filter.return_value.one_or_none.return_value = cached_row
        mock_llm.reset_mock()
        q2 = query_expand.expand_queries(profile, db, params=params)
        assert q2 == q1
        mock_llm.assert_not_called()


def test_jsearch_params_mapping() -> None:
    params = SearchParams(
        date_window="week",
        employment_type="contractor",
        employment_type_pref="hard",
        remote_mode="remote",
        remote_mode_pref="hard",
        use_expand=False,
    )
    j = job_filters.jsearch_params_from_search(params)
    assert j["date_posted"] == "week"
    assert j["employment_types"] == "CONTRACTOR"
    assert j["remote_jobs_only"] == "true"


def test_dropped_counts_merge() -> None:
    from app.schemas.jobs import DroppedCounts

    a = DroppedCounts(recency=2, hard_salary=1)
    b = DroppedCounts(recency=1, missing_apply_url=3)
    m = a.merge(b)
    assert m.recency == 3
    assert m.hard_salary == 1
    assert m.missing_apply_url == 3
    assert m.as_dict()["recency"] == 3


def test_jsearch_soft_employment_does_not_narrow() -> None:
    soft = SearchParams(employment_type="fulltime", employment_type_pref="soft", use_expand=False)
    hard = SearchParams(employment_type="fulltime", employment_type_pref="hard", use_expand=False)
    soft_p = job_filters.jsearch_params_from_search(soft)
    hard_p = job_filters.jsearch_params_from_search(hard)
    assert soft_p["employment_types"] == "FULLTIME,CONTRACTOR,PARTTIME"
    assert hard_p["employment_types"] == "FULLTIME"


def test_jsearch_soft_contractor_does_not_narrow() -> None:
    soft = SearchParams(employment_type="contractor", employment_type_pref="soft", use_expand=False)
    hard = SearchParams(employment_type="contractor", employment_type_pref="hard", use_expand=False)
    assert "CONTRACTOR" in job_filters.jsearch_params_from_search(soft)["employment_types"]
    assert "," in job_filters.jsearch_params_from_search(soft)["employment_types"]
    assert job_filters.jsearch_params_from_search(hard)["employment_types"] == "CONTRACTOR"


def test_annotate_employment_unknown_without_signal() -> None:
    job = _job(
        "1",
        description="Build cool products with Python and teamwork.",
        employment_type=None,
    )
    ann = job_filters.annotate_job(job)
    assert ann.employment_type == "unknown"


def test_hard_contractor_keeps_unknown_employment() -> None:
    jobs = [
        _job("1", employment_type="unknown", description="Python"),
        _job("2", employment_type="fulltime", description="Full time Python"),
        _job("3", employment_type="contractor", description="Contract Python"),
    ]
    params = SearchParams(employment_type="contractor", employment_type_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "1" in ids  # unknown kept
    assert "3" in ids
    assert "2" not in ids
    assert dropped.hard_employment == 1


def test_soft_fulltime_does_not_boost_unknown_employment() -> None:
    unknown = _job("1", employment_type="unknown")
    full = _job("2", employment_type="fulltime")
    params = SearchParams(employment_type="fulltime", employment_type_pref="soft", use_expand=False)
    assert job_filters.soft_boost_score(unknown, params, 70.0) == 70.0
    assert job_filters.soft_boost_score(full, params, 70.0) == 70.0 + job_filters.SOFT_BOOST_POINTS


def test_hard_seniority_keeps_unknown() -> None:
    jobs = [
        _job("1", title="Engineer", seniority=None, description="Build things"),
        _job("2", title="Junior Engineer", seniority="junior", description="Entry level"),
        _job("3", title="Senior Engineer", seniority="senior", description="Lead projects"),
    ]
    params = SearchParams(seniority="senior", seniority_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "1" in ids  # unknown kept
    assert "3" in ids
    assert "2" not in ids
    assert dropped.hard_seniority == 1


def test_soft_boost_clamps_at_100() -> None:
    job = _job(
        "1",
        seniority="senior",
        remote_mode="remote",
        employment_type="fulltime",
        salary_min=200_000,
        salary_unknown=False,
    )
    params = SearchParams(
        remote_mode="remote",
        remote_mode_pref="soft",
        employment_type="fulltime",
        employment_type_pref="soft",
        seniority="senior",
        seniority_pref="soft",
        min_salary=100_000,
        min_salary_pref="soft",
        use_expand=False,
    )
    # 4 soft boosts * 5 = 20 → 95+20 would exceed 100
    assert job_filters.soft_boost_score(job, params, 95.0) == 100.0


def test_embedding_dedup_stricter_cross_company() -> None:
    """Same vector at 0.98 must not merge different companies (need >0.99)."""
    a = _job("a", title="Software Engineer", company="Acme", description="Build software.")
    b = _job("b", title="Software Engineer", company="Beta", description="Build software.")

    def fake_embed_batch(texts: list[str]) -> list[list[float]]:
        # Identical vectors → cosine 1.0 still merges cross-company at >0.99
        return [[1.0, 0.0, 0.0] for _ in texts]

    with patch.object(job_dedup.embeddings, "embed_batch", side_effect=fake_embed_batch):
        kept, dropped = job_dedup.dedupe_embeddings([a, b], threshold=0.97)
    # cosine 1.0 > 0.99 → still merges as true cross-post rehost
    assert len(kept) == 1
    assert dropped.embedding_duplicate == 1

    # At 0.98 sim (mock via slightly different vectors) different companies must NOT merge
    def fake_98(texts: list[str]) -> list[list[float]]:
        # cosine between [1,0] and normalized [0.98, sqrt(1-0.98^2)] ≈ 0.98
        import math

        x = 0.98
        y = math.sqrt(max(0.0, 1.0 - x * x))
        return [[1.0, 0.0], [x, y]]

    with patch.object(job_dedup.embeddings, "embed_batch", side_effect=fake_98):
        kept2, dropped2 = job_dedup.dedupe_embeddings([a, b], threshold=0.97)
    assert len(kept2) == 2
    assert dropped2.embedding_duplicate == 0


def test_dedup_embedding_text_includes_company() -> None:
    job = _job("1", company="UniqueCo", title="Engineer", description="x" * 20)
    assert "UniqueCo" in job.dedup_embedding_text()


def test_soft_remote_boost_only() -> None:
    jobs = [
        _job("1", remote_mode="remote"),
        _job("2", remote_mode="onsite", location="NYC"),
        _job("3", remote_mode="unknown", location=""),
    ]
    params = SearchParams(remote_mode="remote", remote_mode_pref="soft", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    assert len(kept) == 3
    assert dropped.hard_remote == 0
    assert job_filters.soft_boost_score(jobs[0], params, 70.0) > job_filters.soft_boost_score(jobs[1], params, 70.0)


def test_hard_recency_via_apply_hard_filters() -> None:
    jobs = [
        _job("1", posted_days=2),
        _job("2", posted_days=20),
        _job("3", posted_days=None),
    ]
    params = SearchParams(date_window="week", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "1" in ids
    assert "2" not in ids
    assert "3" in ids  # undated kept
    assert dropped.recency == 1


def test_hard_lead_keeps_staff_drops_senior() -> None:
    jobs = [
        _job("1", title="Staff Engineer", seniority="staff"),
        _job("2", title="Senior Engineer", seniority="senior"),
        _job("3", title="Lead Engineer", seniority="lead"),
    ]
    params = SearchParams(seniority="lead", seniority_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert ids == {"1", "3"}
    assert dropped.hard_seniority == 1


def test_hard_remote_drops_hybrid_keeps_unknown() -> None:
    jobs = [
        _job("1", remote_mode="hybrid", location="SF"),
        _job("2", remote_mode="unknown", location=""),
        _job("3", remote_mode="remote", location="Remote"),
    ]
    params = SearchParams(remote_mode="remote", remote_mode_pref="hard", use_expand=False)
    kept, dropped = job_filters.apply_hard_filters(jobs, params)
    ids = {j.id for j in kept}
    assert "1" not in ids
    assert "2" in ids
    assert "3" in ids
    assert dropped.hard_remote == 1
