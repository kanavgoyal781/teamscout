from app.errors import ValidationError
from app.prompts import load_prompt
from app.schemas.job_metadata import JobMetadata
from app.schemas.jobs import Job
from app.schemas.team import TeamExtraction
from app.services import llm


def extract_team_from_job(
    job: Job,
    *,
    metadata_hints: JobMetadata | None = None,
) -> TeamExtraction:
    if not job.description.strip():
        raise ValidationError("Job description is required for team extraction")
    tmpl = load_prompt("team_extract")
    title = (metadata_hints.title if metadata_hints and metadata_hints.title else job.title) or ""
    company = (metadata_hints.company if metadata_hints and metadata_hints.company else job.company) or ""
    location = (metadata_hints.location if metadata_hints and metadata_hints.location else job.location) or ""
    dept = metadata_hints.department if metadata_hints else None
    senior = metadata_hints.seniority if metadata_hints else None
    hint_lines = []
    if dept:
        hint_lines.append(f"Detected department: {dept}")
    if senior:
        hint_lines.append(f"Detected seniority: {senior}")
    hints = ("\n".join(hint_lines) + "\n") if hint_lines else ""
    prompt = (
        f"{tmpl.body}\n\n"
        f"{hints}"
        f"Job title: {title}\n"
        f"Company: {company}\n"
        f"Location: {location}\n\n"
        f"Description:\n{job.description[:6000]}"
    )
    return llm.complete_json(
        prompt,
        TeamExtraction,
        system=tmpl.system,
        max_retries=1,
        operation="team_extract",
        prompt_meta=tmpl,
        max_tokens=int(tmpl.model_params.get("max_tokens") or 2048),
    )
