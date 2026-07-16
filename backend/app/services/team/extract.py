from app.errors import ValidationError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.schemas.team import TeamExtraction
from app.services import llm
def extract_team_from_job(job: Job) -> TeamExtraction:
    if not job.description.strip():
        raise ValidationError("Job description is required for team extraction")
    tmpl = load_prompt("team_extract")
    prompt = (
        f"{tmpl.body}\n\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n\n"
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
