import logging
import sys

import structlog
from structlog.stdlib import LoggerFactory

from app.core.env_utils import is_set


def configure_logging(level: str = "INFO", *, env: str = "dev") -> None:
    """Configure structlog: JSON in prod / non-dev, pretty console in dev."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(logger_name).setLevel(log_level)

    is_prod = env.strip().lower() in {"prod", "production"}
    use_json = is_prod or not sys.stdout.isatty()

    processors: list[object] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    if use_json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__):
    return structlog.get_logger(name)


def log_configured_services() -> None:
    """Startup log of which integrations are configured (names only, never keys)."""
    # Local import avoids circular import at module load (settings ↔ logging).
    from app.core.config import settings

    services = {
        "llm": is_set(settings.LLM_API_KEY) and is_set(settings.LLM_API_BASE),
        "embeddings": is_set(settings.EMBEDDINGS_API_KEY) and is_set(settings.EMBEDDINGS_API),
        "jobs_api": is_set(settings.JOBS_API_KEY) and is_set(settings.JOBS_API_BASE),
        "sumble": is_set(settings.SUMBLE_API_KEY),
        "drive": (
            is_set(settings.GOOGLE_DRIVE_API_KEY)
            or (
                is_set(settings.GOOGLE_DRIVE_CLIENT_ID)
                and is_set(settings.GOOGLE_DRIVE_CLIENT_SECRET)
                and is_set(settings.GOOGLE_DRIVE_REFRESH_TOKEN)
            )
        ),
    }
    configured = sorted(name for name, ok in services.items() if ok)
    missing = sorted(name for name, ok in services.items() if not ok)
    get_logger(__name__).info(
        "app.services_config",
        configured=configured,
        missing=missing,
    )
