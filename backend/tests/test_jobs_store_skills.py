"""Paste-JD skill extraction quality."""

from app.services.jobs_store import extract_skills_from_jd_text
from app.services.ranking_math import skill_jaccard


def test_extract_skills_rejects_filler_tokens() -> None:
    jd = """
    Requirements:
    - Must have strong Python and Django experience
    - Preferred: PostgreSQL, Redis
    - Ability to work in a team environment
    """
    skills = extract_skills_from_jd_text(jd, title="Backend Engineer")
    lowered = {s.lower() for s in skills}
    for bad in (
        "must",
        "have",
        "strong",
        "for",
        "ability",
        "work",
        "team",
        "environment",
        "skills",
        "communication",
        "tracking",
    ):
        assert bad not in lowered, skills
    assert "python" in lowered
    assert "django" in lowered or any("postgres" in s for s in lowered)


def test_extract_skills_jaccard_near_one_with_noise() -> None:
    """Perfect tech match must not be diluted by soft/NL noise in the JD."""
    jd = (
        "Requirements: Python, AWS, communication skills, experience with teamwork, "
        "strong ownership and tracking deliverables. Must have excellent written communication."
    )
    job_skills = extract_skills_from_jd_text(jd, title="Cloud Engineer")
    profile_skills = ["Python", "AWS"]
    for bad in ("communication", "skills", "teamwork", "experience", "tracking", "ownership"):
        assert bad not in {s.lower() for s in job_skills}, job_skills
    assert "python" in {s.lower() for s in job_skills}
    assert "aws" in {s.lower() for s in job_skills}
    j = skill_jaccard(profile_skills, job_skills)
    assert j >= 0.9, (j, job_skills)


def test_extract_skills_rejects_yoe_keeps_ml_and_orch() -> None:
    """'5+ years ML with Kubernetes' → ml + orchestration, never '5+'."""
    jd = (
        "Requirements: 5+ years ML with Kubernetes and Docker. Also 10+ years experience preferred. Stack: k8s, Python."
    )
    skills = extract_skills_from_jd_text(jd, title="ML Platform Engineer")
    lowered = {s.lower() for s in skills}
    assert "5+" not in lowered and "5" not in lowered
    assert "10+" not in lowered and "10" not in lowered
    assert "ml" in lowered or "machine learning" in lowered
    assert "docker" in lowered
    assert "python" in lowered
    # orchestration allowlist (may be spelled out or short form)
    assert "k8s" in lowered or "kubernetes" in lowered, skills
