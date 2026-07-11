"""Job ranking uses experience + requirements without needing embeddings when use_llm=False
and hybrid path is stubbed — here we unit-test score assembly via pure math ranking path.
"""

from app.schemas.jobs import Job
from app.schemas.resume import ResumeProfile
from app.services.ranking_math import (
    experience_fit_score,
    fuse_final_score,
    requirements_met_score,
    skill_jaccard,
)


def _job(job_id: str, title: str, skills: list[str], description: str) -> Job:
    return Job(
        id=job_id,
        source="test",
        source_job_id=job_id,
        title=title,
        company="Co",
        location="Remote",
        description=description,
        apply_url=f"https://example.com/{job_id}",
        skills=skills,
    )


def test_mid_level_prefers_level_matched_over_staff_by_final_signal() -> None:
    profile = ResumeProfile(
        title="Software Engineer",
        years_of_experience=3,
        skills=["Python", "Django", "PostgreSQL", "Docker"],
        summary="3 years Python backend",
    )
    good = _job(
        "good",
        "Software Engineer",
        ["Python", "Django", "PostgreSQL"],
        "Requirements: 2-4 years of experience. Python and Django on PostgreSQL.",
    )
    staff = _job(
        "staff",
        "Staff Software Engineer",
        ["Python", "leadership"],
        "Minimum 10+ years of experience. Lead multi-team architecture.",
    )
    text = profile.search_text()

    def score(job: Job) -> float:
        return fuse_final_score(
            llm_fit=0,
            rrf_normalized=0.5,  # equal retrieval
            skill_overlap=skill_jaccard(profile.skills, job.skills),
            recency=0.5,
            experience_fit=experience_fit_score(
                profile.years_of_experience, title=job.title, description=job.description
            ),
            requirements_met=requirements_met_score(
                profile_skills=profile.skills,
                profile_text=text,
                job_skills=job.skills,
                job_description=job.description,
            ),
        )

    assert score(good) > score(staff)


def test_requirements_beat_keyword_title_only() -> None:
    profile = ResumeProfile(
        title="Software Engineer",
        years_of_experience=3,
        skills=["Python", "Django", "PostgreSQL"],
        summary="Django REST",
    )
    real = _job(
        "real",
        "Software Engineer",
        ["Python", "Django", "PostgreSQL"],
        "Requirements: Python, Django, PostgreSQL. 3 years.",
    )
    trap = _job(
        "trap",
        "Software Engineer",
        ["Kubernetes", "Go"],
        "Software Engineer title. Need Kubernetes and Go, 8+ years distributed systems.",
    )
    text = profile.search_text()

    def req(job: Job) -> float:
        return requirements_met_score(
            profile_skills=profile.skills,
            profile_text=text,
            job_skills=job.skills,
            job_description=job.description,
        )

    assert req(real) > req(trap)


def test_llm_rerank_batches_calls(monkeypatch) -> None:
    from app.schemas.jobs import Job
    from app.schemas.resume import ResumeProfile
    from app.services import ranking

    jobs = [
        Job(
            id=f"job-{i}",
            source="t",
            source_job_id=f"s{i}",
            title=f"Engineer {i}",
            company="Co",
            location="Remote",
            description="Python backend role with 3 years experience.",
            apply_url=f"https://example.com/{i}",
            skills=["Python"],
        )
        for i in range(10)
    ]
    profile = ResumeProfile(title="Engineer", years_of_experience=3, skills=["Python"])
    calls: list[int] = []

    def fake_batch(p, batch):
        calls.append(len(batch))
        from app.services.ranking import _RerankItem

        return {
            j.id: _RerankItem(job_id=j.id, fit_score=50.0, rationale="ok")
            for j in batch
        }

    monkeypatch.setattr(ranking, "_llm_rerank_batch", fake_batch)
    out = ranking._llm_rerank(profile, jobs)
    assert len(out) == 10
    assert calls == [8, 2]


def test_map_alias_results_maps_short_ids() -> None:
    from app.services.ranking import _RerankItem, _RerankResponse, _map_alias_results

    resp = _RerankResponse(
        results=[
            _RerankItem(job_id="j0", fit_score=80, rationale="ok"),
            _RerankItem(job_id="j1", fit_score=40, rationale="weak"),
        ]
    )
    alias_to_real = {"j0": "uuid-a", "j1": "uuid-b"}
    mapped = _map_alias_results(resp, alias_to_real)
    assert set(mapped) == {"uuid-a", "uuid-b"}
    assert mapped["uuid-a"].fit_score == 80
    assert mapped["uuid-a"].job_id == "uuid-a"


def test_heuristic_rerank_item_uses_profile_skills() -> None:
    from app.schemas.jobs import Job
    from app.schemas.resume import ResumeProfile
    from app.services.ranking import _heuristic_rerank_item

    profile = ResumeProfile(
        title="Data Scientist",
        years_of_experience=3,
        skills=["Python", "SQL", "Pandas"],
    )
    job = Job(
        id="j",
        source="t",
        source_job_id="s",
        title="Data Scientist",
        company="Co",
        location="Remote",
        description="Requirements: 2-4 years. Python and SQL.",
        apply_url="https://example.com/j",
        skills=["Python", "SQL", "Spark"],
    )
    item = _heuristic_rerank_item(profile, job)
    assert item.job_id == "j"
    assert 0 <= item.fit_score <= 100
    assert "Python" in item.matched_skills
    assert "heuristic" in item.rationale.lower()


def test_llm_rerank_batch_fills_missing_without_raising(monkeypatch) -> None:
    from app.schemas.jobs import Job
    from app.schemas.resume import ResumeProfile
    from app.services import ranking
    from app.services.ranking import _RerankItem, _RerankResponse

    jobs = [
        Job(
            id=f"uuid-{i}",
            source="t",
            source_job_id=f"s{i}",
            title="Engineer",
            company="Co",
            location="Remote",
            description="Python 3 years.",
            apply_url=f"https://example.com/{i}",
            skills=["Python"],
        )
        for i in range(3)
    ]
    profile = ResumeProfile(title="Engineer", years_of_experience=3, skills=["Python"])

    calls = {"n": 0}

    def fake_call(p, alias_jobs, max_retries=2):
        calls["n"] += 1
        # First call: only j0; second (retry): still incomplete → heuristic fills rest
        if calls["n"] == 1:
            return _RerankResponse(
                results=[_RerankItem(job_id="j0", fit_score=90, rationale="good")]
            )
        return _RerankResponse(results=[])

    monkeypatch.setattr(ranking, "_call_rerank_llm", fake_call)
    out = ranking._llm_rerank_batch(profile, jobs)
    assert set(out) == {"uuid-0", "uuid-1", "uuid-2"}
    assert out["uuid-0"].fit_score == 90
    assert "heuristic" in out["uuid-1"].rationale.lower()
