from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from app.api.routers import contacts, feedback, jobs, library, ops, resumes, searches, stats, workspace
from app.core.config import settings
from app.core.exception_handlers import teamscout_error_handler, unhandled_exception_handler
from app.core.logging import configure_logging, get_logger, log_configured_services
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.request_id import RequestIdMiddleware
from app.core.workspace import WorkspaceMiddleware, maybe_sweep_expired
from app.core.upload_limit import UploadSizeLimitMiddleware
from app.db.session import init_db
from app.errors import TeamScoutError
from app.services.health import run_health_checks
from app.services.ranking_math import validate_ranking_weights
logger = get_logger(__name__)
def _cors_origins() -> list[str]:
    if settings.is_prod:
        raw = settings.ALLOWED_ORIGINS
        if not raw or not str(raw).strip():
            raise RuntimeError(
                "CORS: ALLOWED_ORIGINS must be set explicitly in prod "
                "(comma-separated public frontend origins; no localhost fallback; no '*')"
            )
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise RuntimeError(
                "CORS: ALLOWED_ORIGINS must be an explicit origin list in prod (wildcard '*' is not allowed)"
            )
        return origins
    return settings.allowed_origins_list
@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.LOG_LEVEL, env=settings.ENV)
    validate_ranking_weights()
    init_db()
    maybe_sweep_expired(force=True)
    log_configured_services()
    logger.info("app.startup", env=settings.ENV, version=settings.app_version)
    yield
    logger.info("app.shutdown")
app = FastAPI(title="TeamScout", version=settings.app_version, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(WorkspaceMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_exception_handler(TeamScoutError, teamscout_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(resumes.router)
app.include_router(searches.router)
app.include_router(jobs.router)
app.include_router(contacts.router)
app.include_router(library.router)
app.include_router(feedback.router)
app.include_router(ops.router)
app.include_router(stats.router)
app.include_router(workspace.router)
@app.get("/livez")
async def livez() -> dict[str, str]:
    """Process liveness only (always 200 when the app responds)."""
    return {"status": "alive"}
@app.get("/health")
async def health() -> JSONResponse:
    payload = run_health_checks()
    status_code = 200 if payload["ok"] else 503
    return JSONResponse(content=payload, status_code=status_code)
