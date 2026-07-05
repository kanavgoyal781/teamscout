from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import init_db
from app.errors import TeamScoutError
from app.api.routers import contacts, jobs, library, resumes, searches
from app.services.health import run_health_checks
from app.services.ranking_math import validate_ranking_weights

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.LOG_LEVEL)
    validate_ranking_weights()
    init_db()
    logger.info("app.startup", env=settings.ENV)
    yield
    logger.info("app.shutdown")


app = FastAPI(title="TeamScout", version="0.4.0-m4", lifespan=lifespan)

app.include_router(resumes.router)
app.include_router(searches.router)
app.include_router(jobs.router)
app.include_router(contacts.router)
app.include_router(library.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TeamScoutError)
async def teamscout_error_handler(_request: Request, exc: TeamScoutError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


@app.get("/health")
async def health() -> JSONResponse:
    payload = run_health_checks()
    status_code = 200 if payload["ok"] else 503
    return JSONResponse(content=payload, status_code=status_code)