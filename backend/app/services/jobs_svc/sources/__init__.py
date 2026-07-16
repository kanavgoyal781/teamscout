"""Multi-source job ingestion registry (official APIs only — no HTML scraping)."""

from app.services.jobs_svc.sources.base import FetchCriteria, JobSource, SourceFetchOutcome
from app.services.jobs_svc.sources.registry import (
    all_sources,
    enabled_sources,
    fetch_from_registry,
    source_health_status,
)

__all__ = [
    "FetchCriteria",
    "JobSource",
    "SourceFetchOutcome",
    "all_sources",
    "enabled_sources",
    "fetch_from_registry",
    "source_health_status",
]
