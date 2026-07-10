"""Tests for requirement-level resume ranking (MaxSim + grounding)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.errors import ServiceFailingError
from app.schemas.jobs import Job
from app.schemas.library import ResumeCandidate
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services import resume_ranking
from app.services.resume_ranking import (
    _rationale_cites_units,
    _rationale_references_resume,
    _ResumeRerankItem,
    _ResumeRerankResponse,
    rank_resumes_for_job,
)


def _norm_bag(text: str, dim: int = 32) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().replace("/", " ").split():
        h = hash(token) % dim
        vec[h] += 1.0
    n = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / n for x in vec]


def _embed_batch(texts: list[str]) -> list[list[float]]:
    return [_norm_bag(t) for t in texts]


def _candidate(
    resume_id: str, title: str, skills: list[str], summary: str, bullets: list[str] | None = None
) -> ResumeCandidate:
    return ResumeCandidate(
        resume_id=resume_id,
        filename=f"{resume_id}.pdf",
        content_hash=f"hash-{resume_id}",
        profile=ResumeProfile(
            name=title,
            title=title,
            years_of_experience=6,
            location="Remote",
            skills=skills,
            work_experience=[
                WorkExperience(title=title, company="Acme", bullets=bullets or [summary]),
            ],
            summary=summary,
        ),
    )


def test_rank_resumes_for_job_orders_best_first() -> None:
    job = Job(
        id="rank-job-1",
        source="fixture",
        source_job_id="rank-fixture-1",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI PostgreSQL AWS required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI", "PostgreSQL", "AWS"],
    )
    candidates = [
        _candidate("weak", "Java Engineer", ["Java"], "Java microservices", ["Java Spring only"]),
        _candidate(
            "best",
            "Senior Python Engineer",
            ["Python", "FastAPI", "PostgreSQL", "AWS"],
            "Built Python APIs at Acme with FastAPI and PostgreSQL on AWS",
            ["Built Python APIs at Acme with FastAPI and PostgreSQL on AWS"],
        ),
        _candidate("mid", "Python Developer", ["Python", "Django"], "Django web apps", ["Django apps"]),
    ]

    with patch("app.services.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume_ranking.decompose_jd") as dec:
                from app.services.jd_decompose import JdRequirement

                dec.return_value = [
                    JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="FastAPI", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="PostgreSQL", kind="must", category="skill", weight=2.0),
                    JdRequirement(text="AWS", kind="must", category="skill", weight=1.0),
                ]
                ranked = rank_resumes_for_job(job, candidates, use_llm=False)

    assert ranked[0].resume_id == "best"
    assert ranked[0].coverage_score >= ranked[-1].coverage_score
    assert ranked[0].alignment
    assert ranked[0].cluster_id is not None


def test_rank_resumes_includes_alignment_matrix() -> None:
    job = Job(
        id="rank-job-align",
        source="fixture",
        source_job_id="rank-align",
        title="Python Engineer",
        company="Acme",
        location="Remote",
        description="Python required.",
        apply_url="https://example.com/apply",
        posted_at=None,
        skills=["Python"],
    )
    candidates = [_candidate("only", "Python Engineer", ["Python"], "Python services")]
    with patch("app.services.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.resume_ranking.decompose_jd") as dec:
            from app.services.jd_decompose import JdRequirement

            dec.return_value = [
                JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
            ]
            ranked = rank_resumes_for_job(job, candidates, use_llm=False)
    assert len(ranked) == 1
    assert ranked[0].alignment[0].requirement == "Python"
    assert 0.0 <= ranked[0].coverage_score <= 1.0


def test_rationale_references_resume_rejects_generic_praise() -> None:
    profile = ResumeProfile(
        name="Alex Rivera",
        title="Senior Python Engineer",
        years_of_experience=6,
        location="Remote",
        skills=["Python", "FastAPI"],
        work_experience=[],
        summary="Built Python APIs at Acme",
    )
    assert _rationale_references_resume("Great candidate with strong overall fit.", profile) is False
    assert (
        _rationale_references_resume(
            "Built Python APIs at Acme with FastAPI on AWS.",
            profile,
        )
        is True
    )


def test_rationale_cites_units_grounding() -> None:
    units = ["Shipped FastAPI microservices on AWS with PostgreSQL"]
    assert _rationale_cites_units("Excellent overall culture fit and communication.", units) is False
    assert _rationale_cites_units(
        "Strong match because they Shipped FastAPI microservices on AWS with PostgreSQL in production.",
        units,
    )


def test_llm_justify_retries_then_rejects_generic_rationale() -> None:
    job = Job(
        id="rank-job-2",
        source="fixture",
        source_job_id="rank-fixture-2",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python", "FastAPI"],
    )
    candidate = _candidate(
        "best",
        "Senior Python Engineer",
        ["Python", "FastAPI"],
        "Built Python APIs at Acme",
        ["Built Python APIs at Acme with FastAPI"],
    )
    alignment = {
        "best": [
            {
                "requirement": "Python",
                "evidence_unit": "Built Python APIs at Acme with FastAPI",
                "evidence_score": 0.9,
                "status": "hit",
            }
        ]
    }
    from app.services.jd_decompose import JdRequirement

    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]
    generic = _ResumeRerankItem(
        resume_id="best",
        fit_score=90,
        matched_skills=["Python"],
        missing_skills=[],
        rationale="Excellent overall fit for this role.",
        coverage=[],
    )
    concrete = _ResumeRerankItem(
        resume_id="best",
        fit_score=95,
        matched_skills=["Python", "FastAPI"],
        missing_skills=[],
        rationale="Built Python APIs at Acme with FastAPI.",
        coverage=[],
    )

    with patch(
        "app.services.resume_justify.llm.complete_json",
        side_effect=[
            _ResumeRerankResponse(results=[generic]),
            _ResumeRerankResponse(results=[concrete]),
        ],
    ) as llm_mock:
        result = resume_ranking._llm_justify(job, [candidate], alignment, reqs)

    assert llm_mock.call_count == 2
    assert result["best"].rationale.startswith("Built Python")


def test_llm_justify_raises_after_generic_retry_exhausted() -> None:
    job = Job(
        id="rank-job-3",
        source="fixture",
        source_job_id="rank-fixture-3",
        title="Senior Python Engineer",
        company="Acme",
        location="Remote",
        description="Python FastAPI required.",
        apply_url="https://example.com/apply",
        posted_at=datetime.now(UTC),
        skills=["Python"],
    )
    candidate = _candidate("best", "Senior Python Engineer", ["Python"], "Python at Acme")
    alignment = {
        "best": [
            {
                "requirement": "Python",
                "evidence_unit": "Python services at Acme cloud",
                "evidence_score": 0.8,
                "status": "hit",
            }
        ]
    }
    from app.services.jd_decompose import JdRequirement

    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]
    generic = _ResumeRerankItem(
        resume_id="best",
        fit_score=90,
        matched_skills=["Python"],
        missing_skills=[],
        rationale="Excellent overall fit for this role.",
        coverage=[],
    )

    with patch(
        "app.services.resume_justify.llm.complete_json",
        return_value=_ResumeRerankResponse(results=[generic]),
    ):
        with pytest.raises(ServiceFailingError) as exc:
            resume_ranking._llm_justify(job, [candidate], alignment, reqs)

    assert "evidence units" in exc.value.message or "concrete" in exc.value.message


def test_rationale_cites_units_rejects_skill_name_only() -> None:
    units = ["Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards"]
    assert (
        _rationale_cites_units(
            "Candidate has strong FastAPI and PostgreSQL experience overall.",
            units,
        )
        is False
    )
    assert (
        _rationale_cites_units(
            "Strong match: Shipped FastAPI microservices on AWS with PostgreSQL observability dashboards.",
            units,
        )
        is True
    )


def test_rationale_cites_units_rejects_skill_label_when_long_unit_present() -> None:
    units = ["Python", "Shipped Python FastAPI services on AWS with PostgreSQL at scale"]
    assert (
        _rationale_cites_units(
            "Excellent culture fit with solid Python background for the team.",
            units,
        )
        is False
    )
    assert (
        _rationale_cites_units(
            "Evidence: Shipped Python FastAPI services on AWS with PostgreSQL at scale.",
            units,
        )
        is True
    )


def test_rationale_cites_units_allows_short_when_only_short_units() -> None:
    assert (
        _rationale_cites_units(
            "Candidate has solid Python experience for this backend role.",
            ["Python"],
        )
        is True
    )


def test_rationale_cites_units_fail_closed_on_empty() -> None:
    assert _rationale_cites_units("Built Python APIs at Acme with FastAPI on AWS.", []) is False


def test_pairwise_cache_key_includes_prompt_version_and_is_ab_symmetric() -> None:
    from unittest.mock import patch

    from app.prompts import load_prompt
    from app.schemas.jobs import Job
    from app.services.pairwise_tournament import pairwise_cache_key, tournament_jd_key

    job = Job(
        id="j1",
        source="fixture",
        source_job_id="j1",
        title="Engineer",
        company="Co",
        location="Remote",
        description="Python FastAPI",
        apply_url="https://example.com",
        posted_at=None,
        skills=["Python"],
    )
    key = tournament_jd_key(job)
    k1 = pairwise_cache_key(key, "hash-a", "hash-b")
    k2 = pairwise_cache_key(key, "hash-b", "hash-a")
    assert k1 == k2
    # Prompt version is folded into tournament_jd_key
    tmpl = load_prompt("pairwise_judge")
    with patch("app.services.pairwise_tournament.load_prompt") as lp:

        class T:
            version = tmpl.version + "-mutated"
            content_hash = "deadbeef"
            name = "pairwise_judge"
            body = tmpl.body
            system = tmpl.system
            model_params = tmpl.model_params

        lp.return_value = T()
        key2 = tournament_jd_key(job)
    assert key2 != key


def test_rationale_rank_consistent_rejects_superlative_for_non_first() -> None:
    from app.services.resume_justify import rationale_rank_consistent

    assert rationale_rank_consistent("Best match for this role with FastAPI evidence.", final_rank=1) is True
    assert (
        rationale_rank_consistent("Best match for this role with FastAPI evidence.", final_rank=2) is False
    )
    assert (
        rationale_rank_consistent(
            "Solid FastAPI coverage with shipped microservices evidence.",
            final_rank=2,
        )
        is True
    )
    # Broader superlative coverage for rank > 1 (must require real complements)
    for phrase in (
        "best fit for the role with FastAPI evidence unit here",
        "best candidate overall with FastAPI evidence unit here",
        "top pick given FastAPI evidence unit here",
        "ideal match citing FastAPI microservices evidence",
        "preferred choice after reviewing FastAPI evidence unit",
        "strongest overall among peers with FastAPI evidence",
        "strongest match citing FastAPI microservices evidence",
        "strongest candidate with FastAPI evidence unit here",
        "strongest overall match for this FastAPI role with evidence",
        # #1 forms (word-boundary hole fixed — `#` is non-word)
        "#1 overall for this role with FastAPI evidence",
        "is #1 pick given FastAPI microservices evidence",
        "This is the #1 resume for FastAPI coverage",
        "# 1 among peers with FastAPI evidence unit",
        "top resume with FastAPI microservices evidence unit",
        "most suitable candidate citing FastAPI evidence",
    ):
        assert rationale_rank_consistent(phrase, final_rank=2) is False, phrase
    # Negative: ordinary English "strongest …" is NOT a rank claim
    for phrase in (
        "Strongest evidence of FastAPI services on AWS is present.",
        "Has the strongest depth in antibodies among the evidence units.",
        "Shows the strongest technical write-up of FastAPI microservices.",
    ):
        assert rationale_rank_consistent(phrase, final_rank=2) is True, phrase


def test_tournament_override_match_scores_non_increasing() -> None:
    """After tournament reorder, Overall match rings must not invert vs card order."""
    from unittest.mock import MagicMock, patch

    from app.services.jd_decompose import JdRequirement

    job = Job(
        id="ov-job",
        source="fixture",
        source_job_id="ov",
        title="ML Engineer",
        company="Co",
        location="Remote",
        description="Need antibody engineering and Python.",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["antibody engineering", "Python"],
    )
    high_cov = _candidate(
        "cov-leader",
        "General",
        ["Python"],
        "Python analysis of sequencing data",
        ["Python analysis of sequencing data"],
    )
    low_cov = _candidate(
        "tour-winner",
        "Antibody",
        ["antibody engineering", "Python"],
        "Led antibody engineering campaigns with phage display",
        ["Led antibody engineering campaigns with phage display"],
    )
    # Force coverage order via deterministic bag embeddings + fixed requirements.
    reqs = [
        JdRequirement(text="Python", kind="must", category="skill", weight=2.0),
        JdRequirement(text="antibody engineering", kind="must", category="skill", weight=2.0),
    ]

    def fake_complete(prompt, schema, **kwargs):
        fields = getattr(schema, "model_fields", {}) or {}
        if "results" in fields:
            # justify path — rank-safe, monotonic fit
            return schema(
                results=[
                    {
                        "resume_id": "tour-winner",
                        "fit_score": 90,
                        "matched_skills": ["antibody engineering"],
                        "missing_skills": [],
                        "rationale": "Led antibody engineering campaigns with phage display.",
                        "coverage": [],
                    },
                    {
                        "resume_id": "cov-leader",
                        "fit_score": 80,
                        "matched_skills": ["Python"],
                        "missing_skills": ["antibody engineering"],
                        "rationale": "Python analysis of sequencing data without antibody campaigns.",
                        "coverage": [],
                    },
                ]
            )
        # pairwise path — prefer tour-winner filename
        if "tour-winner" in prompt and "Resume A (tour-winner" in prompt:
            return schema(
                winner="A",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="tour-winner has antibody engineering campaigns",
            )
        if "tour-winner" in prompt:
            return schema(
                winner="B",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="tour-winner has antibody engineering campaigns",
            )
        return schema(
            winner="A",
            margin="slight",
            key_differences=["tie"],
            reason="slight edge on shared skills",
        )

    prompt_meta = MagicMock(
        body="Judge",
        system="json",
        version="2",
        content_hash="ph",
        name="pairwise_judge",
        model_params={},
    )
    with patch("app.services.embeddings.embed_batch", side_effect=_embed_batch):
        with patch("app.services.embeddings.embed", side_effect=lambda t: _norm_bag(t)):
            with patch("app.services.resume_ranking.decompose_jd", return_value=reqs):
                with patch("app.services.pairwise_tournament.llm.complete_json", side_effect=fake_complete):
                    with patch("app.services.resume_justify.llm.complete_json", side_effect=fake_complete):
                        with patch("app.services.pairwise_tournament.load_prompt", return_value=prompt_meta):
                            with patch("app.services.resume_justify.load_prompt", return_value=prompt_meta):
                                ranked = rank_resumes_for_job(
                                    job, [high_cov, low_cov], use_llm=True
                                )

    assert len(ranked) >= 2
    # If tournament overrode, enforce non-increasing match_score with final order.
    if ranked[0].tournament and ranked[0].tournament.overrode_coverage:
        assert ranked[0].match_score + 1e-9 >= ranked[1].match_score
        assert ranked[0].resume_id == "tour-winner"
    else:
        # Coverage path alone still non-increasing by construction
        assert ranked[0].match_score + 1e-9 >= ranked[1].match_score


def test_generate_biomedicines_tournament_leads_and_justification_rank_safe() -> None:
    """Synthetic Generate Biomedicines JD: tournament #1 leads; non-#1 cannot claim best match."""
    from unittest.mock import MagicMock, patch

    from app.services.jd_decompose import JdRequirement
    from app.services.pairwise_tournament import AlignmentEvidence, maybe_run_tournament
    from app.services.resume_justify import llm_justify, rationale_rank_consistent

    job = Job(
        id="gen-bio",
        source="fixture",
        source_job_id="gen-bio",
        title="Scientist, Antibody Engineering",
        company="Generate Biomedicines",
        location="Somerville, MA",
        description=(
            "Generate Biomedicines seeks a scientist with antibody engineering, "
            "protein design, display technologies, and ML-guided sequence optimization."
        ),
        apply_url="https://example.com/genbio",
        posted_at=datetime.now(UTC),
        skills=["antibody engineering", "protein design", "phage display", "Python"],
    )
    reqs = [
        JdRequirement(text="antibody engineering", kind="must", category="skill", weight=2.0),
        JdRequirement(text="protein design", kind="must", category="skill", weight=2.0),
        JdRequirement(text="phage display", kind="must", category="skill", weight=2.0),
        JdRequirement(text="Python", kind="must", category="skill", weight=1.0),
        JdRequirement(text="ML-guided sequence optimization", kind="nice", category="domain", weight=1.0),
    ]
    # Coverage puts mid slightly ahead; tournament must flip order to antibody-strong.
    ordered = [
        AlignmentEvidence(
            resume_id="bio-mid",
            content_hash="h-mid",
            coverage=0.72,
            filename="general_scientist.pdf",
            top_units=["Python analysis of sequencing data"],
            alignment_rows=[
                {
                    "requirement": "Python",
                    "kind": "must",
                    "category": "skill",
                    "evidence_unit": "Python analysis of sequencing data",
                    "evidence_score": 1.0,
                    "status": "hit",
                },
                {
                    "requirement": "antibody engineering",
                    "kind": "must",
                    "category": "skill",
                    "evidence_unit": "No clear evidence",
                    "evidence_score": 0.0,
                    "status": "miss",
                },
            ],
        ),
        AlignmentEvidence(
            resume_id="bio-strong",
            content_hash="h-strong",
            coverage=0.70,
            filename="antibody_expert.pdf",
            top_units=["Led antibody engineering campaigns with phage display"],
            alignment_rows=[
                {
                    "requirement": "antibody engineering",
                    "kind": "must",
                    "category": "skill",
                    "evidence_unit": "Led antibody engineering campaigns with phage display",
                    "evidence_score": 1.0,
                    "status": "hit",
                },
                {
                    "requirement": "protein design",
                    "kind": "must",
                    "category": "skill",
                    "evidence_unit": "Designed therapeutic proteins with Rosetta",
                    "evidence_score": 0.9,
                    "status": "hit",
                },
            ],
        ),
    ]

    def fake_judge(prompt, schema, **kwargs):
        # Prefer A when A is bio-strong's evidence (filename appears in prompt)
        if "antibody_expert.pdf" in prompt and "Resume A (antibody_expert.pdf)" in prompt:
            return schema(
                winner="A",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="Resume A shows antibody engineering with phage display",
            )
        if "antibody_expert.pdf" in prompt and "Resume B (antibody_expert.pdf)" in prompt:
            return schema(
                winner="B",
                margin="decisive",
                key_differences=["antibody engineering depth"],
                reason="Resume B shows antibody engineering with phage display",
            )
        return schema(winner="A", margin="slight", key_differences=["tie-break"], reason="slight edge")

    with patch("app.services.pairwise_tournament.llm.complete_json", side_effect=fake_judge):
        with patch("app.services.pairwise_tournament.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Judge holistically.",
                system="json",
                version="2",
                content_hash="ph2",
                name="pairwise_judge",
                model_params={},
            )
            result = maybe_run_tournament(job, reqs, ordered, use_llm=True, db=None)

    assert result.ran is True
    assert result.ordered_ids[0] == "bio-strong"
    assert result.overrode_coverage is True  # mid led coverage; tournament flipped
    assert result.wins.get("bio-strong", 0) >= 1

    # Justification after ordering: rank 2 must not claim best match
    candidates = [
        _candidate(
            "bio-strong",
            "Antibody Engineer",
            ["antibody engineering", "protein design", "phage display", "Python"],
            "Led antibody engineering campaigns with phage display",
            ["Led antibody engineering campaigns with phage display"],
        ),
        _candidate(
            "bio-mid",
            "Scientist",
            ["Python", "sequencing"],
            "Python analysis of sequencing data",
            ["Python analysis of sequencing data"],
        ),
    ]
    alignment = {
        "bio-mid": ordered[0].alignment_rows,
        "bio-strong": ordered[1].alignment_rows,
    }
    rank_by_id = {"bio-strong": 1, "bio-mid": 2}

    def fake_justify(prompt, schema, **kwargs):
        return schema(
            results=[
                {
                    "resume_id": "bio-strong",
                    "fit_score": 92,
                    "matched_skills": ["antibody engineering"],
                    "missing_skills": [],
                    "rationale": (
                        "Best match: Led antibody engineering campaigns with phage display "
                        "and protein design depth for Generate Biomedicines."
                    ),
                    "coverage": [],
                },
                {
                    "resume_id": "bio-mid",
                    "fit_score": 70,
                    "matched_skills": ["Python"],
                    "missing_skills": ["antibody engineering"],
                    "rationale": (
                        "Python analysis of sequencing data is relevant but lacks "
                        "antibody engineering campaigns evidence."
                    ),
                    "coverage": [],
                },
            ]
        )

    with patch("app.services.resume_justify.llm.complete_json", side_effect=fake_justify):
        with patch("app.services.resume_justify.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Justify with ranks.",
                system="json",
                version="2",
                content_hash="jh2",
                name="justify",
                model_params={},
            )
            out = llm_justify(
                job,
                candidates,
                alignment,
                reqs,
                rank_by_id=rank_by_id,
                tournament_wins=result.wins,
                contested_ids=set(result.contested_ids),
            )

    assert out["bio-strong"].fit_score >= out["bio-mid"].fit_score
    assert rationale_rank_consistent(out["bio-strong"].rationale, final_rank=1)
    assert rationale_rank_consistent(out["bio-mid"].rationale, final_rank=2)


def test_llm_justify_rejects_rank2_best_match_claim() -> None:
    from unittest.mock import MagicMock, patch

    from app.services.jd_decompose import JdRequirement

    job = Job(
        id="j-rank",
        source="fixture",
        source_job_id="j-rank",
        title="Engineer",
        company="Co",
        location="Remote",
        description="Python FastAPI",
        apply_url="https://example.com",
        posted_at=datetime.now(UTC),
        skills=["Python"],
    )
    c1 = _candidate("r1", "Eng", ["Python"], "Built Python FastAPI services on AWS", ["Built Python FastAPI services on AWS"])
    c2 = _candidate("r2", "Eng", ["Python"], "Built Python FastAPI services on AWS", ["Built Python FastAPI services on AWS"])
    alignment = {
        "r1": [{"requirement": "Python", "evidence_unit": "Built Python FastAPI services on AWS", "evidence_score": 1.0, "status": "hit"}],
        "r2": [{"requirement": "Python", "evidence_unit": "Built Python FastAPI services on AWS", "evidence_score": 0.9, "status": "hit"}],
    }
    reqs = [JdRequirement(text="Python", kind="must", category="skill", weight=2.0)]
    calls = {"n": 0}

    def bad_then_good(prompt, schema, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return schema(
                results=[
                    {
                        "resume_id": "r1",
                        "fit_score": 90,
                        "matched_skills": ["Python"],
                        "missing_skills": [],
                        "rationale": "Built Python FastAPI services on AWS — solid coverage.",
                        "coverage": [],
                    },
                    {
                        "resume_id": "r2",
                        "fit_score": 88,
                        "matched_skills": ["Python"],
                        "missing_skills": [],
                        "rationale": "Best match overall with Built Python FastAPI services on AWS.",
                        "coverage": [],
                    },
                ]
            )
        return schema(
            results=[
                {
                    "resume_id": "r1",
                    "fit_score": 90,
                    "matched_skills": ["Python"],
                    "missing_skills": [],
                    "rationale": "Built Python FastAPI services on AWS — solid coverage.",
                    "coverage": [],
                },
                {
                    "resume_id": "r2",
                    "fit_score": 88,
                    "matched_skills": ["Python"],
                    "missing_skills": [],
                    "rationale": "Built Python FastAPI services on AWS with slightly lower coverage.",
                    "coverage": [],
                },
            ]
        )

    with patch("app.services.resume_justify.llm.complete_json", side_effect=bad_then_good):
        with patch("app.services.resume_justify.load_prompt") as lp:
            lp.return_value = MagicMock(
                body="Justify",
                system="json",
                version="2",
                content_hash="j",
                name="justify",
                model_params={},
            )
            out = resume_ranking._llm_justify(
                job,
                [c1, c2],
                alignment,
                reqs,
                rank_by_id={"r1": 1, "r2": 2},
            )
    assert calls["n"] == 2
    assert "best match" not in out["r2"].rationale.lower()
