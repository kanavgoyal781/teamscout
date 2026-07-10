import hashlib
import re
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import JobCache
from app.errors import NotFoundError, ValidationError
from app.schemas.jobs import Job
_SKILL_STOP = frozenset({
    "tracking", "written", "verbal", "strong", "ability", "working", "using", "including", "related", "tools", "stack", "role", "team", "work", "build", "built", "develop", "developing", "knowledge", "familiarity", "proficient", "proficiency",
    "communication", "teamwork", "ownership", "skills", "deliverables",
    "experience", "years", "year", "plus", "strong", "excellent", "ability",
    "requirements", "qualifications", "responsibilities", "preferred",
    "and", "or", "the", "with", "from", "for", "to", "of",
    "in", "on", "at", "a", "an", "experience", "years", "year",
    "plus", "must", "have", "has", "strong", "preferred", "required", "requirement",
    "requirements", "qualifications", "qualification", "ability", "able", "work", "working", "using",
    "use", "including", "include", "knowledge", "understanding", "familiar", "proficient", "proficiency",
    "solid", "excellent", "good", "team", "teams", "environment", "role", "position",
    "job", "minimum", "maximum", "etc", "etc.", "other", "related", "relevant",
    "such", "as", "well", "also", "will", "can", "should", "need",
    "needs",
})
_TECH_ALLOW = frozenset({
    "python", "java", "javascript", "typescript", "golang", "go", "rust", "ruby", "scala", "kotlin",
    "c++", "c#", "swift", "php", "r", "sql", "nosql", "postgresql", "mysql", "mongodb", "redis",
    "aws", "gcp", "azure", "docker", "ansible", "linux",
    "react", "vue", "angular", "node", "nodejs", "fastapi", "django", "flask", "spring",
    "pytorch", "tensorflow", "sklearn", "scikit-learn", "pandas", "numpy", "spark",
    "ml", "machine learning", "deep learning", "nlp", "llm", "rag", "mlflow", "airflow",
    "ci/cd", "graphql", "rest", "grpc", "hadoop", "hive", "snowflake", "databricks",
    "prometheus", "grafana", "elasticsearch", "opensearch", "helm",
})
def extract_skills_from_jd_text(description: str, title: str = "") -> list[str]:
    """High-precision skill list for pasted JDs (allowlist + JD-derived tech tokens)."""
    from app.services.ranking_math import extract_requirement_terms
    blob = f"{title}\n{description}" if title else (description or "")
    lowered = blob.lower()
    out: list[str] = []
    seen: set[str] = set()
    for tech in sorted(_TECH_ALLOW, key=len, reverse=True):
        pattern = r"(?<![a-z0-9])" + re.escape(tech) + r"(?![a-z0-9])"
        if re.search(pattern, lowered) and tech not in seen:
            seen.add(tech)
            out.append(tech)
        if len(out) >= 16:
            return out
    for term in extract_requirement_terms([], blob):
        key = re.sub(r"\s+", " ", (term or "").strip()).strip(".,;:()").lower()
        if not key or key in seen or key in _SKILL_STOP:
            continue
        if re.fullmatch(r"\d+\+?", key) or re.search(r"\d+\s*\+?\s*years?", key):
            continue
        if len(key) <= 2 and key not in {"go", "r", "c"}:
            continue
        if key in {"also", "with", "and", "the", "for", "stack", "years", "experience", "preferred"}:
            continue
        if re.fullmatch(r"[a-z][a-z0-9+#./-]{1,32}", key):
            seen.add(key)
            out.append(key)
        if len(out) >= 16:
            break
    return out
def resolve_job(job_id: str, db: Session) -> Job:
    row = db.query(JobCache).filter(JobCache.job_id == job_id).one_or_none()
    if row is None or not row.payload_json:
        raise NotFoundError("job", job_id)
    return Job.model_validate_json(row.payload_json)
def cache_pasted_job(
    *,
    description: str,
    title: str = "",
    company: str = "",
    location: str = "",
    apply_url: str = "",
    db: Session,
) -> Job:
    """Persist a user-pasted JD as a JobCache row and return the Job."""
    desc = (description or "").strip()
    if len(desc) < 40:
        raise ValidationError(
            "Job description is too short — paste the full posting (at least ~40 characters)"
        )
    title_clean = (title or "").strip() or "Pasted job"
    company_clean = (company or "").strip() or "Unknown company"
    location_clean = (location or "").strip() or ""
    apply_clean = (apply_url or "").strip() or "https://www.linkedin.com/jobs/view/pasted"
    content_hash = hashlib.sha256(desc.encode("utf-8")).hexdigest()[:32]
    source_job_id = f"paste-{content_hash}"
    skills = extract_skills_from_jd_text(desc, title_clean)
    existing = (
        db.query(JobCache)
        .filter(JobCache.source == "paste", JobCache.source_job_id == source_job_id)
        .first()
    )
    if existing is not None and existing.payload_json:
        job = Job.model_validate_json(existing.payload_json)
        updated = job.model_copy(
            update={
                "title": title_clean,
                "company": company_clean,
                "location": location_clean,
                "description": desc,
                "apply_url": apply_clean if apply_url.strip() else job.apply_url,
                "skills": skills or job.skills,
            }
        )
        existing.title = updated.title
        existing.payload_json = updated.model_dump_json()
        if not existing.job_id:
            existing.job_id = updated.id
        db.add(existing)
        db.commit()
        return updated
    job = Job(
        id=str(uuid.uuid4()),
        source="paste",
        source_job_id=source_job_id,
        title=title_clean,
        company=company_clean,
        location=location_clean,
        description=desc,
        apply_url=apply_clean,
        posted_at=None,
        skills=skills,
    )
    try:
        with db.begin_nested():
            db.add(
                JobCache(
                    job_id=job.id,
                    source=job.source,
                    source_job_id=job.source_job_id,
                    title=job.title,
                    payload_json=job.model_dump_json(),
                )
            )
            db.flush()
        db.commit()
        return job
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(JobCache)
            .filter(JobCache.source == "paste", JobCache.source_job_id == source_job_id)
            .first()
        )
        if existing is None or not existing.payload_json:
            raise
        stable = Job.model_validate_json(existing.payload_json)
        updated = stable.model_copy(
            update={
                "title": title_clean,
                "company": company_clean,
                "location": location_clean,
                "description": desc,
                "apply_url": apply_clean if apply_url.strip() else stable.apply_url,
                "skills": skills or stable.skills,
            }
        )
        existing.job_id = updated.id
        existing.title = updated.title
        existing.payload_json = updated.model_dump_json()
        db.add(existing)
        db.commit()
        return updated
