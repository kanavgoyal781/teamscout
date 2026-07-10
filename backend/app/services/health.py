from typing import Literal
from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ping_db
CheckStatus = Literal["configured", "missing", "failing", "disabled"]
REQUIRED_CHECKS = ("llm", "embeddings", "jobs_api", "sumble")
OPTIONAL_CHECKS = ("google_drive", "adzuna")
def check_llm() -> CheckStatus:
    if not is_set(settings.LLM_API_KEY) or not is_set(settings.LLM_API_BASE):
        return "missing"
    return "configured"
def check_embeddings() -> CheckStatus:
    from app.services.embeddings import embeddings_endpoint
    if not is_set(settings.EMBEDDINGS_API_KEY) or not embeddings_endpoint():
        return "missing"
    return "configured"
def check_jobs_api() -> CheckStatus:
    if not is_set(settings.JOBS_API_KEY) or not is_set(settings.JOBS_API_BASE):
        return "missing"
    return "configured"
def check_sumble() -> CheckStatus:
    if not is_set(settings.SUMBLE_API_KEY):
        return "missing"
    return "configured"
def check_google_drive() -> CheckStatus:
    if is_set(settings.GOOGLE_DRIVE_API_KEY):
        return "configured"
    oauth = (
        settings.GOOGLE_DRIVE_CLIENT_ID,
        settings.GOOGLE_DRIVE_CLIENT_SECRET,
        settings.GOOGLE_DRIVE_REFRESH_TOKEN,
    )
    if all(is_set(v) for v in oauth):
        return "configured"
    return "missing"
def run_health_checks() -> dict[str, object]:
    from app.services.job_sources import source_health_status
    checks: dict[str, CheckStatus] = {
        "llm": check_llm(),
        "embeddings": check_embeddings(),
        "jobs_api": check_jobs_api(),
        "sumble": check_sumble(),
        "google_drive": check_google_drive(),
    }
    job_sources = source_health_status()
    checks["adzuna"] = job_sources.get("adzuna", "disabled")  # type: ignore[assignment]
    db_ok = ping_db()
    ok = db_ok and all(checks[name] == "configured" for name in REQUIRED_CHECKS)
    return {
        "ok": ok,
        "version": settings.app_version,
        "checks": checks,
        "job_sources": job_sources,
        "required_checks": list(REQUIRED_CHECKS),
        "optional_checks": list(OPTIONAL_CHECKS),
        "db": db_ok,
    }
