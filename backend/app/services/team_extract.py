from app.errors import ValidationError
from app.schemas.jobs import Job
from app.schemas.team import TeamExtraction
from app.services import llm

_SYSTEM = (
    "You extract hiring-team signals from job descriptions for recruiter outreach. "
    "Return JSON with team_name (specific team or squad if inferable), "
    "department (e.g. Engineering, Product, Sales), and likely_hiring_titles "
    "(2-5 realistic manager/lead titles who would hire for this role)."
)


def extract_team_from_job(job: Job) -> TeamExtraction:
    if not job.description.strip():
        raise ValidationError("Job description is required for team extraction")

    prompt = (
        f"Job title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n\n"
        f"Description:\n{job.description[:6000]}\n\n"
        "Extract team_name, department, and likely_hiring_titles as JSON."
    )
    return llm.complete_json(prompt, TeamExtraction, system=_SYSTEM, max_retries=1)